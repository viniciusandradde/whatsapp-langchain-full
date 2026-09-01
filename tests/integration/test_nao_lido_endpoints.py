"""Smoke + E2E do marcar-não-lida e do filtro por responsável (leva fila).

Smoke (sem DB): rota nova existe e exige service token.

E2E (stack rodando): o ciclo completo do read receipt — conversa nova conta
como não lida, marcar-lido zera, marcar-nao-lido devolve o marcador (DELETE
do receipt: volta ao estado "nunca aberta", que os contadores já tratam).
De carona, o filtro `?assigned_to=` da mesma leva.

    uv run pytest tests/integration/test_nao_lido_endpoints.py::TestSmoke -v

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    uv run pytest tests/integration/test_nao_lido_endpoints.py::TestE2E -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]
_D = f"{int(_RUN, 16) % 1_000_000:06d}"
_TEL = f"+5567997{_D}"


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_marcar_nao_lido_sem_auth_401(self) -> None:
        r = _client().post("/api/atendimentos/1/marcar-nao-lido")
        assert r.status_code == 401

    def test_listagem_com_assigned_to_sem_auth_401(self) -> None:
        r = _client().get("/api/atendimentos?assigned_to=alguem")
        assert r.status_code == 401


@pytest.mark.docker_demo
class TestE2E:
    @pytest.fixture(scope="class")
    def dados(self):
        """Empresa isolada com 1 conversa (1 msg inbound) e 1 user."""
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO empresa (nome, slug, plano, status) "
            "VALUES (%s, %s, 'free', 'active') RETURNING id",
            (f"E2E NaoLido {_RUN}", f"e2e-naolido-{_RUN}"),
        )
        empresa_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO conexao (empresa_id, provider, from_number, status) "
            "VALUES (%s, 'evolution', %s, 'active') RETURNING id",
            (empresa_id, _TEL),
        )
        conexao_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO cliente (empresa_id, telefone, nome) "
            "VALUES (%s, %s, %s) RETURNING id",
            (empresa_id, _TEL, f"Cliente NaoLido {_RUN}"),
        )
        cliente_id = cur.fetchone()[0]

        user_id = f"test-naolido-{_RUN}"
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status,
                                      is_superadmin)
            VALUES (%s, 'Test NaoLido', %s, TRUE, NOW(), NOW(), 'active', TRUE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )

        # Atendimento ATRIBUÍDO ao user — serve pro filtro assigned_to e pro
        # ciclo lido/não-lido ao mesmo tempo.
        cur.execute(
            """
            INSERT INTO atendimento
                (empresa_id, cliente_id, conexao_id, agente_atual, status,
                 assigned_to_user_id)
            VALUES (%s, %s, %s, 'agente', 'em_andamento', %s) RETURNING id
            """,
            (empresa_id, cliente_id, conexao_id, user_id),
        )
        atd_id = cur.fetchone()[0]

        # 1 mensagem do cliente, entregue — é o que o contador de não lidas
        # conta (status done + incoming não vazio + não interna).
        cur.execute(
            """
            INSERT INTO message_queue
                (phone_number, agent_id, thread_id, incoming_message,
                 status, empresa_id, atendimento_id, conexao_id,
                 created_at, processed_at)
            VALUES (%s, 'agente', %s, 'oi, preciso de ajuda', 'done',
                    %s, %s, %s, NOW(), NOW())
            """,
            (_TEL, f"{_TEL}:agente", empresa_id, atd_id, conexao_id),
        )

        yield {
            "empresa_id": empresa_id,
            "atd_id": atd_id,
            "user_id": user_id,
        }
        cur.execute("DELETE FROM message_queue WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM atendimento WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM cliente WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM conexao WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))
        conn.close()

    def _h(self, dados: dict) -> dict:
        h = get_admin_api_headers()
        h["X-User-Id"] = dados["user_id"]
        h["X-Empresa-Id"] = str(dados["empresa_id"])
        return h

    def _nao_lidas(self, dados: dict) -> int:
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos?tipo=todas",
            headers=self._h(dados),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        por_id = {a["id"]: a for a in r.json()["atendimentos"]}
        assert dados["atd_id"] in por_id, "atendimento sumiu da listagem"
        return por_id[dados["atd_id"]]["nao_lidas"]

    def test_1_conversa_nova_conta_nao_lida(self, dados) -> None:
        assert self._nao_lidas(dados) == 1

    def test_2_marcar_lido_zera(self, dados) -> None:
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}/marcar-lido",
            headers=self._h(dados),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert self._nao_lidas(dados) == 0

    def test_3_marcar_nao_lido_devolve(self, dados) -> None:
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}/marcar-nao-lido",
            headers=self._h(dados),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert self._nao_lidas(dados) == 1

    def test_4_marcar_nao_lido_idempotente(self, dados) -> None:
        """Repetir não erra nem muda nada — o DELETE de linha ausente é no-op."""
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}/marcar-nao-lido",
            headers=self._h(dados),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert self._nao_lidas(dados) == 1

    def test_5_filtro_assigned_to(self, dados) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos",
            params={"assigned_to": dados["user_id"]},
            headers=self._h(dados),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        ids = [a["id"] for a in r.json()["atendimentos"]]
        assert dados["atd_id"] in ids

    def test_6_filtro_assigned_to_outro_user_vazio(self, dados) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos",
            params={"assigned_to": f"ninguem-{_RUN}"},
            headers=self._h(dados),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert dados["atd_id"] not in [a["id"] for a in r.json()["atendimentos"]]
