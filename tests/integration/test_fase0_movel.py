"""Smoke + E2E da Fase 0 do app Android.

Três mudanças de backend habilitam o cliente móvel:
- auth por token de sessão (coberto em unit por `test_auth_sessao_movel.py`);
- `GET /api/atendimentos/events` — stream da empresa, pra lista viva com UMA
  conexão em vez de uma por conversa;
- cursor `before_id` em `/mensagens` — Paging 3 do histórico.

O cursor corrigiu um bug ao vivo: a query era `created_at ASC LIMIT n`, que
devolvia as n mensagens MAIS ANTIGAS. Em produção há duas conversas acima de 200
mensagens (a maior com 301), e nelas o operador não via as últimas.

Smoke (sem DB): rotas existem e exigem auth. Roda em CI.
E2E (`docker_demo`): paginação real, sem pular nem repetir mensagem.

    uv run pytest tests/integration/test_fase0_movel.py::TestSmoke -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

# ============================================================================
# Smoke (TestClient — sem DB real, roda em CI)
# ============================================================================


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    """Rotas registradas e protegidas."""

    def test_sse_empresa_sem_auth_401(self) -> None:
        assert _client().get("/api/atendimentos/events").status_code == 401

    def test_sse_atendimento_sem_auth_401(self) -> None:
        assert _client().get("/api/atendimentos/1/events").status_code == 401

    def test_mensagens_com_cursor_sem_auth_401(self) -> None:
        resp = _client().get("/api/atendimentos/1/mensagens?before_id=99")
        assert resp.status_code == 401

    def test_rota_events_nao_e_engolida_por_atendimento_id(self) -> None:
        """`/events` é registrada ANTES de `/{atendimento_id}`.

        Se a ordem inverter, o FastAPI tenta converter "events" em int e devolve
        422 em vez de bater na rota certa. O 401 aqui prova que a rota existe e
        que o dispatch chegou na dependency de auth, não no parser de path.
        """
        assert _client().get("/api/atendimentos/events").status_code != 422

    # `before_id=0` é rejeitado pelo `ge=1` do Query, mas testar isso no smoke
    # exigiria passar da auth — e sem DB o TestClient trava no pool. A validação
    # é comportamento do Pydantic (visível na assinatura da rota) e o caminho
    # feliz da paginação está coberto no TestE2E abaixo.


# ============================================================================
# E2E (stack real — precisa make up)
# ============================================================================

pytestmark_e2e = pytest.mark.docker_demo

_RUN = uuid.uuid4().hex[:8]
_TOTAL_MSGS = 25  # > que o limit usado nos testes, pra forçar 3 páginas


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        r = httpx.get(f"{API_BASE_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("API não saudável. Rode: make up")
    except Exception:
        pytest.skip("API não acessível. Rode: make up")
    url = get_db_url()
    try:
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Verifique DATABASE_URL")
    return url


@pytest.fixture(scope="module")
def cenario(db_url: str):
    """Empresa + cliente + atendimento com `_TOTAL_MSGS` mensagens numeradas.

    O conteúdo é o índice ("msg-000", "msg-001"...) justamente pra que o teste
    de paginação possa afirmar ORDEM e AUSÊNCIA DE BURACO, não só contagem.
    """
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO empresa (nome, slug, plano, status)
            VALUES (%s, %s, 'free', 'active') RETURNING id
            """,
            (f"test-fase0-{_RUN}", f"test-fase0-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        empresa_id = int(row[0])

        cur.execute(
            """
            INSERT INTO cliente (empresa_id, telefone, nome)
            VALUES (%s, %s, 'Cliente Fase0') RETURNING id
            """,
            (empresa_id, f"+5567{_RUN[:4]}90000"),
        )
        row = cur.fetchone()
        assert row is not None
        cliente_id = int(row[0])

        cur.execute(
            """
            INSERT INTO atendimento (empresa_id, cliente_id, agente_atual, status)
            VALUES (%s, %s, 'vsa_tech', 'aguardando') RETURNING id
            """,
            (empresa_id, cliente_id),
        )
        row = cur.fetchone()
        assert row is not None
        atendimento_id = int(row[0])

        for i in range(_TOTAL_MSGS):
            cur.execute(
                """
                INSERT INTO message_queue
                    (empresa_id, atendimento_id, phone_number, agent_id,
                     thread_id, incoming_message, status)
                VALUES (%s, %s, %s, 'vsa_tech', %s, %s, 'done')
                """,
                (
                    empresa_id,
                    atendimento_id,
                    f"+5567{_RUN[:4]}90000",
                    f"+5567{_RUN[:4]}90000:vsa_tech",
                    f"msg-{i:03d}",
                ),
            )
    yield {"empresa_id": empresa_id, "atendimento_id": atendimento_id}
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))


def _headers(empresa_id: int) -> dict[str, str]:
    return {**get_admin_api_headers(), "X-Empresa-Id": str(empresa_id)}


@pytest.mark.docker_demo
class TestE2E:
    def test_1_sem_cursor_devolve_as_mais_RECENTES(self, cenario) -> None:
        """O bug corrigido: antes vinham as mais antigas."""
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/{cenario['atendimento_id']}/mensagens",
            params={"limit": 10},
            headers=_headers(cenario["empresa_id"]),
            timeout=10,
        )
        assert r.status_code == 200, r.text
        msgs = r.json()["mensagens"]
        assert len(msgs) == 10
        # ASC dentro da página, e a última é a mensagem mais nova de todas
        assert msgs[0]["incoming_message"] == "msg-015"
        assert msgs[-1]["incoming_message"] == f"msg-{_TOTAL_MSGS - 1:03d}"

    def test_2_pagina_cheia_traz_cursor(self, cenario) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/{cenario['atendimento_id']}/mensagens",
            params={"limit": 10},
            headers=_headers(cenario["empresa_id"]),
            timeout=10,
        )
        assert r.json()["next_cursor"] is not None

    def test_3_paginacao_completa_sem_pular_nem_repetir(self, cenario) -> None:
        """Percorre o histórico inteiro e reconstrói a conversa.

        É o teste que importa: qualquer erro de off-by-one no cursor aparece
        como mensagem duplicada ou faltando.
        """
        url = f"{API_BASE_URL}/api/atendimentos/{cenario['atendimento_id']}/mensagens"
        h = _headers(cenario["empresa_id"])
        coletadas: list[str] = []
        cursor = None
        for _ in range(10):  # trava anti-loop
            params: dict[str, object] = {"limit": 10}
            if cursor is not None:
                params["before_id"] = cursor
            r = httpx.get(url, params=params, headers=h, timeout=10)
            assert r.status_code == 200, r.text
            body = r.json()
            coletadas = [m["incoming_message"] for m in body["mensagens"]] + coletadas
            cursor = body["next_cursor"]
            if cursor is None:
                break
        assert cursor is None, "paginação não terminou — cursor nunca ficou null"
        esperado = [f"msg-{i:03d}" for i in range(_TOTAL_MSGS)]
        assert coletadas == esperado, (
            f"esperava {len(esperado)} mensagens em ordem, veio {len(coletadas)}"
        )

    def test_4_ultima_pagina_nao_traz_cursor(self, cenario) -> None:
        """Página incompleta = fim do histórico."""
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/{cenario['atendimento_id']}/mensagens",
            params={"limit": 500},
            headers=_headers(cenario["empresa_id"]),
            timeout=10,
        )
        body = r.json()
        assert len(body["mensagens"]) == _TOTAL_MSGS
        assert body["next_cursor"] is None

    def test_5_sse_empresa_conecta_e_anuncia_escopo(self, cenario) -> None:
        """O primeiro evento declara o escopo — prova o filtro de tenant."""
        import json

        url = f"{API_BASE_URL}/api/atendimentos/events"
        with httpx.stream(
            "GET", url, headers=_headers(cenario["empresa_id"]), timeout=15
        ) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            for linha in r.iter_lines():
                if linha.startswith("data:"):
                    payload = json.loads(linha[5:].strip())
                    assert payload["empresa_id"] == cenario["empresa_id"]
                    # stream de empresa não fixa atendimento
                    assert "atendimento_id" not in payload
                    break

    def test_6_cross_tenant_bloqueado(self, cenario) -> None:
        """Empresa sem membership segue 403, com ou sem app no meio."""
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/{cenario['atendimento_id']}/mensagens",
            headers={**get_admin_api_headers(), "X-Empresa-Id": "999999"},
            timeout=10,
        )
        assert r.status_code in (403, 404), r.text
