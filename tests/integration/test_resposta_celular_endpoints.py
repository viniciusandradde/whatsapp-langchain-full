"""E2E da ADR-008 (mig 205): resposta do dono pelo celular (Evolution
`fromMe`) vira bolha "WhatsApp (celular)" e pausa a IA na conversa;
"Devolver à IA" retoma. PR B: com prazo na conexão, a IA volta sozinha e
responde à última mensagem do cliente.

Usa a conexão Evolution padrão da empresa 1 do dev (worker em
`EVOLUTION_OUTBOUND_MODE=mock`, nada sai para o WhatsApp).

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_resposta_celular_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg_pool import AsyncConnectionPool

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]
_TEL = f"+5567998{int(_RUN[:5], 16) % 1000000:06d}"
# PR B usa outra conversa: a do PR A termina devolvida à IA.
_TEL2 = f"+5567997{int(_RUN[3:8], 16) % 1000000:06d}"


# ============================================================================
# Smoke (TestClient — sem DB real, roda em CI)
# ============================================================================


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_get_resposta_celular_sem_auth_401(self) -> None:
        assert _client().get("/api/conexoes/1/resposta-celular").status_code == 401

    def test_put_resposta_celular_sem_auth_401(self) -> None:
        r = _client().put(
            "/api/conexoes/1/resposta-celular", json={"retorno_ia_minutos": 30}
        )
        assert r.status_code == 401


@pytest.fixture(scope="module")
def ambiente():
    try:
        if httpx.get(f"{API_BASE_URL}/health", timeout=3).status_code != 200:
            pytest.skip("API do dev fora do ar")
    except Exception:
        pytest.skip("API do dev fora do ar")
    url = get_db_url()
    instancia = os.environ.get("EVOLUTION_INSTANCE_NAME", "empresa1_nexus_dev")
    apikey = os.environ.get("EVOLUTION_API_KEY", "")
    if not apikey:
        pytest.skip("EVOLUTION_API_KEY não definido")
    yield {"db": url, "instancia": instancia, "apikey": apikey}
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'true', false)")
        for tel in (_TEL, _TEL2):
            cur.execute(
                "DELETE FROM message_queue WHERE empresa_id = 1 AND phone_number = %s",
                (tel,),
            )
            cur.execute(
                "DELETE FROM atendimento WHERE empresa_id = 1 AND cliente_id IN "
                "(SELECT id FROM cliente WHERE empresa_id = 1 AND telefone = %s)",
                (tel,),
            )
            cur.execute(
                "DELETE FROM cliente WHERE empresa_id = 1 AND telefone = %s", (tel,)
            )


def _upsert(
    amb, *, from_me: bool, texto: str, mid: str, tel: str = _TEL
) -> httpx.Response:
    corpo = {
        "event": "messages.upsert",
        "instance": amb["instancia"],
        "data": {
            "key": {
                "remoteJid": f"{tel.lstrip('+')}@s.whatsapp.net",
                "fromMe": from_me,
                "id": mid,
            },
            "message": {"conversation": texto},
            "pushName": "E2E Celular",
            "messageTimestamp": int(time.time()),
            "source": "android",
        },
    }
    return httpx.post(
        f"{API_BASE_URL}/webhook/evolution",
        json=corpo,
        headers={"apikey": amb["apikey"]},
        timeout=15,
    )


def _consulta(amb, sql: str, params: tuple):
    with psycopg.connect(amb["db"]) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _executa(amb, sql: str, params: tuple) -> None:
    with psycopg.connect(amb["db"], autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'true', false)")
        cur.execute(sql, params)


def _headers() -> dict:
    h = get_admin_api_headers()
    h["X-User-Id"] = "dev-admin-0001"
    h["X-Empresa-Id"] = "1"
    return h


def _esperar_processada(amb, mid: str) -> tuple[str, str | None]:
    for _ in range(60):
        rows = _consulta(
            amb,
            "SELECT status, response FROM message_queue WHERE message_id = %s "
            "ORDER BY id DESC LIMIT 1",
            (mid,),
        )
        if rows and rows[0][0] in ("done", "failed"):
            return rows[0]
        time.sleep(1)
    raise AssertionError(f"worker não processou {mid}")


async def _rodar_job(amb) -> int:
    from whatsapp_langchain.shared.resposta_celular import retornar_ia_por_tempo

    async with AsyncConnectionPool(amb["db"], min_size=1, max_size=2) as pool:
        return await retornar_ia_por_tempo(pool, agora=datetime.now(UTC))


@pytest.mark.docker_demo
class TestE2ERespostaCelular:
    def test_01_resposta_do_celular_vira_bolha_e_pausa_a_ia(self, ambiente):
        mid = f"CEL-{_RUN}-1"
        assert (
            _upsert(
                ambiente, from_me=True, texto="Oi, aqui é pelo celular", mid=mid
            ).status_code
            == 200
        )
        linhas = _consulta(
            ambiente,
            "SELECT origem_resposta, normalized_input, response, atendimento_id FROM message_queue "
            "WHERE message_id = %s",
            (mid,),
        )
        assert len(linhas) == 1, linhas
        origem, ni, resp, atd = linhas[0]
        assert (
            origem == "celular"
            and ni == "manual:app:whatsapp"
            and resp == "Oi, aqui é pelo celular"
        )
        dono = _consulta(
            ambiente,
            "SELECT status, assigned_to_user_id FROM atendimento WHERE id = %s",
            (atd,),
        )
        assert dono == [("em_andamento", "whatsapp_celular")]

    def test_02_reentrega_nao_duplica(self, ambiente):
        mid = f"CEL-{_RUN}-1"
        assert (
            _upsert(
                ambiente, from_me=True, texto="Oi, aqui é pelo celular", mid=mid
            ).status_code
            == 200
        )
        n = _consulta(
            ambiente,
            "SELECT count(*) FROM message_queue WHERE message_id = %s",
            (mid,),
        )
        assert n == [(1,)]

    def test_03_grupo_fica_de_fora(self, ambiente):
        corpo_mid = f"CEL-{_RUN}-G"
        r = httpx.post(
            f"{API_BASE_URL}/webhook/evolution",
            json={
                "event": "messages.upsert",
                "instance": ambiente["instancia"],
                "data": {
                    "key": {
                        "remoteJid": "120363000000000@g.us",
                        "fromMe": True,
                        "id": corpo_mid,
                    },
                    "message": {"conversation": "no grupo"},
                },
            },
            headers={"apikey": ambiente["apikey"]},
            timeout=15,
        )
        assert r.status_code == 200
        assert _consulta(
            ambiente,
            "SELECT count(*) FROM message_queue WHERE message_id = %s",
            (corpo_mid,),
        ) == [(0,)]

    def test_04_cliente_escreve_e_a_ia_fica_calada(self, ambiente):
        mid = f"CLI-{_RUN}-1"
        assert (
            _upsert(
                ambiente, from_me=False, texto="Tudo certo então?", mid=mid
            ).status_code
            == 200
        )
        resp = None
        for _ in range(40):
            rows = _consulta(
                ambiente,
                "SELECT status, response FROM message_queue WHERE message_id = %s ORDER BY id DESC LIMIT 1",
                (mid,),
            )
            if rows and rows[0][0] in ("done", "failed"):
                resp = rows[0][1]
                break
            time.sleep(1)
        assert resp is not None, "worker não processou"
        assert resp.startswith("[handoff humano"), resp

    def test_05_devolver_a_ia_retoma(self, ambiente):
        atd = _consulta(
            ambiente,
            "SELECT atendimento_id FROM message_queue WHERE message_id = %s",
            (f"CEL-{_RUN}-1",),
        )[0][0]
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atd}/devolver-ia",
            headers=_headers(),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        dono = _consulta(
            ambiente,
            "SELECT assigned_to_user_id FROM atendimento WHERE id = %s",
            (atd,),
        )
        assert dono == [(None,)]


@pytest.mark.docker_demo
class TestE2ERetornoPorTempo:
    """PR B: `conexao.celular_retorno_ia_minutos` faz a IA voltar sozinha."""

    estado: dict = {}

    def test_10_conversa_pausada_pelo_celular(self, ambiente):
        mid = f"CEL-{_RUN}-B1"
        assert (
            _upsert(
                ambiente, from_me=True, texto="Te respondo já", mid=mid, tel=_TEL2
            ).status_code
            == 200
        )
        conexao_id, atd = _consulta(
            ambiente,
            "SELECT conexao_id, atendimento_id FROM message_queue WHERE message_id = %s",
            (mid,),
        )[0]
        self.estado.update(conexao_id=conexao_id, atd=atd, mid_cel=mid)
        cid = f"CLI-{_RUN}-B1"
        assert (
            _upsert(
                ambiente,
                from_me=False,
                texto="Qual o horário hoje?",
                mid=cid,
                tel=_TEL2,
            ).status_code
            == 200
        )
        _status, resp = _esperar_processada(ambiente, cid)
        assert (resp or "").startswith("[handoff humano"), resp
        self.estado["mid_cli"] = cid

    def test_11_config_da_conexao_padrao_e_validacao(self, ambiente):
        cid = self.estado["conexao_id"]
        url = f"{API_BASE_URL}/api/conexoes/{cid}/resposta-celular"
        r = httpx.get(url, headers=_headers(), timeout=15)
        assert r.status_code == 200, r.text
        self.estado["original"] = r.json()["retorno_ia_minutos"]
        for invalido in (0, 4, 10081):
            r = httpx.put(
                url,
                json={"retorno_ia_minutos": invalido},
                headers=_headers(),
                timeout=15,
            )
            assert r.status_code == 422, (invalido, r.text)
        r = httpx.put(
            url, json={"retorno_ia_minutos": 30}, headers=_headers(), timeout=15
        )
        assert r.status_code == 200, r.text
        assert (
            httpx.get(url, headers=_headers(), timeout=15).json()["retorno_ia_minutos"]
            == 30
        )

    def test_12_conexao_de_outra_empresa_404(self, ambiente):
        outra = _consulta(
            ambiente, "SELECT id FROM conexao WHERE empresa_id <> 1 LIMIT 1", ()
        )
        if not outra:
            pytest.skip("dev sem conexão de outra empresa")
        r = httpx.get(
            f"{API_BASE_URL}/api/conexoes/{outra[0][0]}/resposta-celular",
            headers=_headers(),
            timeout=15,
        )
        assert r.status_code == 404, r.text

    async def test_13_dentro_do_prazo_a_conversa_fica_com_o_dono(self, ambiente):
        await _rodar_job(ambiente)
        dono = _consulta(
            ambiente,
            "SELECT assigned_to_user_id FROM atendimento WHERE id = %s",
            (self.estado["atd"],),
        )
        assert dono == [("whatsapp_celular",)]

    async def test_14_operador_que_assumiu_nao_perde_a_conversa(self, ambiente):
        atd = self.estado["atd"]
        # Operador primeiro, prazo vencido depois: o laço do worker do dev
        # não pode achar a conversa vencida ainda com o dono sentinela.
        _executa(
            ambiente,
            "UPDATE atendimento SET assigned_to_user_id = 'dev-admin-0001' WHERE id = %s",
            (atd,),
        )
        _executa(
            ambiente,
            "UPDATE message_queue SET created_at = NOW() - interval '45 minutes' "
            "WHERE message_id = %s",
            (self.estado["mid_cel"],),
        )
        _executa(
            ambiente,
            "UPDATE message_queue SET created_at = NOW() - interval '40 minutes' "
            "WHERE message_id = %s",
            (self.estado["mid_cli"],),
        )
        await _rodar_job(ambiente)
        assert _consulta(
            ambiente,
            "SELECT status, assigned_to_user_id FROM atendimento WHERE id = %s",
            (atd,),
        ) == [("em_andamento", "dev-admin-0001")]

    async def test_15_prazo_vencido_a_ia_volta_e_responde(self, ambiente):
        atd = self.estado["atd"]
        _executa(
            ambiente,
            "UPDATE atendimento SET assigned_to_user_id = 'whatsapp_celular' WHERE id = %s",
            (atd,),
        )
        # O laço do worker do dev pode chegar antes: vale o estado final.
        await _rodar_job(ambiente)
        assert _consulta(
            ambiente,
            "SELECT assigned_to_user_id FROM atendimento WHERE id = %s",
            (atd,),
        ) == [(None,)]
        _status, resp = _esperar_processada(ambiente, self.estado["mid_cli"])
        assert resp and not resp.startswith("[handoff humano"), resp

    def test_16_restaura_a_config(self, ambiente):
        r = httpx.put(
            f"{API_BASE_URL}/api/conexoes/{self.estado['conexao_id']}/resposta-celular",
            json={"retorno_ia_minutos": self.estado.get("original")},
            headers=_headers(),
            timeout=15,
        )
        assert r.status_code == 200, r.text
