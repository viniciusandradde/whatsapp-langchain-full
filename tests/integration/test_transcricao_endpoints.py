"""Smoke + E2E da transcrição de áudio pro operador (mig 169).

Smoke (sem DB): rota existe e exige service token.
E2E (com stack rodando): idempotência (mensagem já transcrita devolve o texto
salvo SEM chamada de LLM) e recusa de mensagem sem áudio — os dois caminhos
que não dependem do OpenRouter.

Para rodar só smoke:
    uv run pytest tests/integration/test_transcricao_endpoints.py::TestSmoke -v

Para rodar E2E (precisa make up + migrações aplicadas):
    uv run pytest tests/integration/test_transcricao_endpoints.py::TestE2E -v -s
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]

# ============================================================================
# Smoke (TestClient — sem DB real, roda em CI)
# ============================================================================


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    """Verifica que a rota está registrada e exige auth."""

    def test_transcrever_sem_auth_401(self) -> None:
        resp = _client().post("/api/atendimentos/1/mensagens/1/transcrever")
        assert resp.status_code == 401

    def test_patch_conexao_sem_auth_401(self) -> None:
        resp = _client().patch(
            "/api/conexoes/1", json={"transcrever_audio_sempre": True}
        )
        assert resp.status_code == 401


# ============================================================================
# E2E (stack real — @docker_demo)
# ============================================================================


@pytest.mark.docker_demo
class TestE2E:
    @pytest.fixture(scope="class")
    def dados(self):
        """Empresa + atendimento + 2 mensagens: uma de áudio JÁ transcrita
        (caminho idempotente, sem LLM) e uma de texto puro (caminho 400)."""
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO empresa (nome, slug, plano, status) "
            # Pro: a transcrição para o operador é feature de plano (ADR-005
            # leva B) — o 402 do Free tem teste em test_plano_leva_b_endpoints.
            "VALUES (%s, %s, 'pro', 'active') RETURNING id",
            (f"E2E Transcrição {_RUN}", f"e2e-transc-{_RUN}"),
        )
        empresa_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO cliente (empresa_id, telefone, nome)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (empresa_id, f"+5567{_RUN[:8]}", f"Cliente E2E {_RUN}"),
        )
        cliente_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO atendimento (empresa_id, cliente_id, agente_atual, status)
            VALUES (%s, %s, 'agente', 'aguardando') RETURNING id
            """,
            (empresa_id, cliente_id),
        )
        atd_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO message_queue
                (phone_number, agent_id, thread_id, incoming_message, status,
                 empresa_id, atendimento_id, media_url, media_type, transcricao)
            VALUES (%s, 'agente', %s, '', 'done', %s, %s,
                    'data:audio/ogg;base64,T2dnUw==', 'audio/ogg',
                    'texto já transcrito')
            RETURNING id
            """,
            (f"+5567{_RUN[:8]}", f"+5567{_RUN[:8]}:agente", empresa_id, atd_id),
        )
        msg_audio_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO message_queue
                (phone_number, agent_id, thread_id, incoming_message, status,
                 empresa_id, atendimento_id)
            VALUES (%s, 'agente', %s, 'oi', 'done', %s, %s)
            RETURNING id
            """,
            (f"+5567{_RUN[:8]}", f"+5567{_RUN[:8]}:agente", empresa_id, atd_id),
        )
        msg_texto_id = cur.fetchone()[0]
        # User superadmin de teste — get_empresa_context exige membership ou
        # superadmin; superadmin evita montar perfil/permissões aqui.
        user_id = f"test-transc-{_RUN}"
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status,
                                      is_superadmin)
            VALUES (%s, 'Test Transcrição', %s, TRUE, NOW(), NOW(),
                    'active', TRUE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )
        yield {
            "empresa_id": empresa_id,
            "atd_id": atd_id,
            "msg_audio_id": msg_audio_id,
            "msg_texto_id": msg_texto_id,
            "user_id": user_id,
        }
        cur.execute("DELETE FROM message_queue WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM atendimento WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM cliente WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))
        conn.close()

    def _headers(self, dados: dict) -> dict:
        h = get_admin_api_headers()
        h["X-User-Id"] = dados["user_id"]
        h["X-Empresa-Id"] = str(dados["empresa_id"])
        return h

    def test_1_idempotente_devolve_texto_salvo(self, dados) -> None:
        # Mensagem com `transcricao` preenchida: o endpoint devolve o texto
        # salvo sem chamar o provedor — é o contrato de idempotência.
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}"
            f"/mensagens/{dados['msg_audio_id']}/transcrever",
            headers=self._headers(dados),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["transcricao"] == "texto já transcrito"

    def test_2_mensagem_sem_audio_400(self, dados) -> None:
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}"
            f"/mensagens/{dados['msg_texto_id']}/transcrever",
            headers=self._headers(dados),
            timeout=30,
        )
        assert r.status_code == 400, r.text

    def test_3_transcricao_aparece_na_lista(self, dados) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}/mensagens",
            headers=self._headers(dados),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        por_id = {m["id"]: m for m in r.json()["mensagens"]}
        assert por_id[dados["msg_audio_id"]]["transcricao"] == "texto já transcrito"
        assert por_id[dados["msg_texto_id"]]["transcricao"] is None

    def test_4_patch_conexao_flag(self, dados) -> None:
        # Cria conexão da empresa e liga/desliga a flag pelo PATCH.
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO conexao (empresa_id, provider, from_number, payload_json)
            VALUES (%s, 'evolution', %s, '{"instance_name": "e2e-transc"}')
            RETURNING id
            """,
            (dados["empresa_id"], f"+5599{_RUN[:8]}"),
        )
        conexao_id = cur.fetchone()[0]
        try:
            r = httpx.patch(
                f"{API_BASE_URL}/api/conexoes/{conexao_id}",
                headers=self._headers(dados),
                json={"transcrever_audio_sempre": True},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            assert r.json()["transcrever_audio_sempre"] is True
        finally:
            cur.execute("DELETE FROM conexao WHERE id = %s", (conexao_id,))
            conn.close()
