"""Resumo diário: falha de envio deixa de custar o dia inteiro.

O desenho anterior marcava o dia como enviado ANTES de mandar (claim atômico,
pra não duplicar com dois workers) e assumia o trade-off no comentário:
"falha de envio adia pro dia seguinte". Na prática isso significava que
qualquer erro — Evolution fora do ar por um minuto, conexão recém-trocada —
consumia a única chance do dia, sem retentativa e sem deixar rastro: o único
sinal era uma linha de log, que morre a cada deploy.

Agora a falha DEVOLVE o dia, e o próximo tick (60s) tenta de novo, até
`MAX_TENTATIVAS`. O teto existe pra que uma falha permanente (telefone
inválido, instância desconectada) não vire 1440 chamadas por dia contra o
provedor.

Só smoke:
    uv run pytest tests/integration/test_resumo_diario_retry.py::TestSmoke -v

E2E (precisa do banco):
    uv run pytest tests/integration/test_resumo_diario_retry.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared import resumo_diario as rd

from .helpers import get_db_url

_MIGRACAO = (
    Path(__file__).parents[2] / "db" / "migrations" / "162_resumo_diario_resultado.sql"
)
_TZ = "America/Campo_Grande"


# ============================================================================
# Smoke (sem DB — roda em CI)
# ============================================================================


class TestSmoke:
    def test_migracao_registra_o_resultado(self) -> None:
        """Sem resultado persistido, a única prova de que o envio aconteceu
        é uma linha de log — que some no deploy seguinte."""
        assert _MIGRACAO.exists(), f"migração ausente: {_MIGRACAO.name}"
        sql = _MIGRACAO.read_text()
        for col in (
            "resumo_diario_last_status",
            "resumo_diario_last_error",
            "resumo_diario_last_attempt_at",
            "resumo_diario_tentativas",
        ):
            assert col in sql, f"coluna {col} não criada"

    def test_existe_teto_de_tentativas(self) -> None:
        """Devolver o dia sem teto faria uma falha permanente virar uma
        chamada por minuto até a virada do dia."""
        assert isinstance(rd.MAX_TENTATIVAS, int)
        assert 1 < rd.MAX_TENTATIVAS <= 10

    def test_envio_manual_existe(self) -> None:
        """Sem gatilho manual, validar a funcionalidade exige esperar o dia
        seguinte — e mais um dia a cada tentativa frustrada."""
        assert hasattr(rd, "enviar_resumo_agora")

    def test_endpoint_de_teste_registrado(self) -> None:
        from whatsapp_langchain.server.main import app

        rotas = {
            (m, r.path)  # type: ignore[attr-defined]
            for r in app.routes
            for m in getattr(r, "methods", set()) or set()
        }
        assert (
            "POST",
            "/api/empresas/{empresa_id}/resumo-diario/testar",
        ) in rotas

    def test_endpoint_na_allowlist_do_invariante_rbac(self) -> None:
        """O router `empresa_admin` valida `is_admin_of` da empresa do PATH.
        `require_permission` checaria a empresa ATIVA do header, que pode ser
        outra — mesmo racional já documentado pro PUT.
        """
        from tests.unit.test_endpoint_permission_invariant import ALLOWLIST

        assert (
            "POST",
            "/api/empresas/{empresa_id}/resumo-diario",
        ) in ALLOWLIST


# ============================================================================
# E2E (banco real)
# ============================================================================

_RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def db_url() -> str:
    url = get_db_url()
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Rode: make db")
    return url


@pytest.fixture
def empresa_id(db_url: str):
    slug = f"test-resumo-{_RUN}-{uuid.uuid4().hex[:6]}"
    ontem = datetime.now(UTC).astimezone(ZoneInfo(_TZ)).date() - timedelta(days=1)
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status,
                                     resumo_diario_ativo, resumo_diario_telefone,
                                     resumo_diario_horario, resumo_diario_dias,
                                     resumo_diario_tz, resumo_diario_last_sent)
                VALUES (%s, %s, 'free', 'active',
                        TRUE, '+5567999068963', '00:00'::time,
                        '{1,2,3,4,5,6,7}', %s, %s)
                RETURNING id
                """,
                (slug, slug, _TZ, ontem),
            )
            row = cur.fetchone()
            assert row is not None
            eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


def _cfg(empresa_id: int, last_sent) -> rd.ResumoConfig:
    return rd.ResumoConfig(
        empresa_id=empresa_id,
        telefone="+5567999068963",
        horario=time(0, 0),
        dias=[1, 2, 3, 4, 5, 6, 7],
        tz=_TZ,
        last_sent=last_sent,
    )


def _estado(db_url: str, empresa_id: int) -> dict:
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT resumo_diario_last_sent, resumo_diario_last_status,
                       resumo_diario_last_error, resumo_diario_tentativas,
                       resumo_diario_last_attempt_at
                  FROM empresa WHERE id = %s
                """,
                (empresa_id,),
            )
            r = cur.fetchone()
    assert r is not None
    return {
        "last_sent": r[0],
        "status": r[1],
        "error": r[2],
        "tentativas": r[3],
        "attempt_at": r[4],
    }


class _ClientFake:
    def __init__(self, erro: str | None = None) -> None:
        self.erro = erro
        self.enviados: list[tuple[str, str]] = []

    async def send_message(self, to: str, body: str) -> str:
        if self.erro:
            raise RuntimeError(self.erro)
        self.enviados.append((to, body))
        return "fake-id"


@pytest.fixture
def outbound(monkeypatch):
    """Troca conexão + cliente por dublês.

    `_processar_empresa` importa os dois DENTRO da função, então o patch no
    módulo de origem pega. Sem isso o teste precisaria de uma `conexao` real
    com credenciais — e não é isso que está sob teste.
    """
    from whatsapp_langchain.shared import conexao as mod_conexao
    from whatsapp_langchain.shared import outbound as mod_outbound

    estado: dict = {"client": _ClientFake(), "conexoes": [object()]}

    async def _list(_pool, _eid):
        return estado["conexoes"]

    async def _build(_pool, _conexao):
        return estado["client"], "mock"

    monkeypatch.setattr(mod_conexao, "list_conexoes", _list)
    monkeypatch.setattr(mod_outbound, "build_outbound_client", _build)
    monkeypatch.setattr(
        mod_conexao, "Conexao", getattr(mod_conexao, "Conexao", object), raising=False
    )
    return estado


class _ConexaoFake:
    id = 999
    status = "active"


@pytest.mark.docker_demo
class TestE2E:
    async def test_sucesso_grava_ok_e_consome_o_dia(
        self, db_url: str, empresa_id: int, outbound
    ) -> None:
        outbound["conexoes"] = [_ConexaoFake()]
        hoje = datetime.now(UTC).astimezone(ZoneInfo(_TZ)).date()
        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            enviado = await rd._processar_empresa(
                pool, _cfg(empresa_id, hoje - timedelta(days=1))
            )

        assert enviado is True
        st = _estado(db_url, empresa_id)
        assert st["last_sent"] == hoje, "sucesso tem que consumir o dia"
        assert st["status"] == "ok"
        assert st["error"] is None
        assert st["tentativas"] == 0
        assert st["attempt_at"] is not None
        assert len(outbound["client"].enviados) == 1

    async def test_falha_devolve_o_dia_pra_proxima_tentativa(
        self, db_url: str, empresa_id: int, outbound
    ) -> None:
        """O ponto do PR: erro não pode custar o dia inteiro."""
        outbound["conexoes"] = [_ConexaoFake()]
        outbound["client"] = _ClientFake(erro="evolution 502")
        hoje = datetime.now(UTC).astimezone(ZoneInfo(_TZ)).date()
        ontem = hoje - timedelta(days=1)

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            enviado = await rd._processar_empresa(pool, _cfg(empresa_id, ontem))

        assert enviado is False
        st = _estado(db_url, empresa_id)
        assert st["last_sent"] == ontem, "o dia não foi devolvido — não haverá retry"
        assert st["status"] == "erro"
        assert "502" in (st["error"] or "")
        assert st["tentativas"] == 1

    async def test_sem_conexao_ativa_tambem_devolve_o_dia(
        self, db_url: str, empresa_id: int, outbound
    ) -> None:
        """Antes esse caminho dava `continue` DEPOIS do claim: a empresa
        perdia o dia por não ter conexão naquele instante."""
        outbound["conexoes"] = []
        hoje = datetime.now(UTC).astimezone(ZoneInfo(_TZ)).date()
        ontem = hoje - timedelta(days=1)

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            enviado = await rd._processar_empresa(pool, _cfg(empresa_id, ontem))

        assert enviado is False
        st = _estado(db_url, empresa_id)
        assert st["last_sent"] == ontem
        assert st["status"] == "erro"
        assert "conex" in (st["error"] or "").lower()

    async def test_esgota_o_teto_e_desiste_do_dia(
        self, db_url: str, empresa_id: int, outbound
    ) -> None:
        """Sem teto, telefone inválido viraria uma chamada por minuto até a
        virada do dia."""
        outbound["conexoes"] = [_ConexaoFake()]
        outbound["client"] = _ClientFake(erro="numero invalido")
        hoje = datetime.now(UTC).astimezone(ZoneInfo(_TZ)).date()
        ontem = hoje - timedelta(days=1)

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            for _ in range(rd.MAX_TENTATIVAS):
                st = _estado(db_url, empresa_id)
                await rd._processar_empresa(
                    pool, _cfg(empresa_id, st["last_sent"] or ontem)
                )

        st = _estado(db_url, empresa_id)
        assert st["tentativas"] == rd.MAX_TENTATIVAS
        assert st["last_sent"] == hoje, "esgotado o teto, o dia tem que ser consumido"
        assert st["status"] == "erro"

    async def test_enviar_agora_nao_consome_o_dia(
        self, db_url: str, empresa_id: int, outbound
    ) -> None:
        """O botão de teste existe pra validar a configuração sem gastar a
        chance do agendamento."""
        outbound["conexoes"] = [_ConexaoFake()]
        ontem = datetime.now(UTC).astimezone(ZoneInfo(_TZ)).date() - timedelta(days=1)

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            ok, erro = await rd.enviar_resumo_agora(pool, empresa_id)

        assert ok is True, erro
        st = _estado(db_url, empresa_id)
        assert st["last_sent"] == ontem, "o envio manual não pode consumir o dia"
        assert st["status"] == "ok"
        assert len(outbound["client"].enviados) == 1

    async def test_enviar_agora_devolve_o_erro_em_vez_de_engolir(
        self, db_url: str, empresa_id: int, outbound
    ) -> None:
        outbound["conexoes"] = [_ConexaoFake()]
        outbound["client"] = _ClientFake(erro="instancia desconectada")

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            ok, erro = await rd.enviar_resumo_agora(pool, empresa_id)

        assert ok is False
        assert "desconectada" in (erro or "")
        st = _estado(db_url, empresa_id)
        assert st["status"] == "erro"
        assert "desconectada" in (st["error"] or "")
