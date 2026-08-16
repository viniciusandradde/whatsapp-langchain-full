"""Smoke + E2E da conversa ativa 1:1 (mig 170).

Smoke (sem DB): rota existe e exige service token.
E2E (stack rodando): validações e o caminho de anexar — nada aqui toca
provedor de WhatsApp (o happy path com envio real é validado pela tela,
com EVOLUTION_OUTBOUND_MODE do ambiente).

Para rodar E2E (precisa make up + migrações):
    uv run pytest tests/integration/test_conversa_ativa_endpoints.py::TestE2E -v -s
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]
#: Sufixo NUMÉRICO. Telefone com letra do hex é flaky: `normalize_phone`
#: descarta não-dígitos, e o número semeado deixa de casar com o do request.
_D = f"{int(_RUN, 16) % 1_000_000:06d}"


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_iniciar_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/atendimentos/iniciar",
            json={"telefone": "+5567999990000", "conexao_id": 1, "mensagem": "oi"},
        )
        assert resp.status_code == 401


@pytest.mark.docker_demo
class TestE2E:
    @pytest.fixture(scope="class")
    def dados(self):
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO empresa (nome, slug, plano, status) "
            "VALUES (%s, %s, 'free', 'active') RETURNING id",
            (f"E2E Conversa Ativa {_RUN}", f"e2e-conv-{_RUN}"),
        )
        empresa_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO conexao (empresa_id, provider, from_number, payload_json)
            VALUES (%s, 'evolution', %s, '{"instance_name": "e2e-conv"}')
            RETURNING id
            """,
            (empresa_id, f"+5567900{_D}"),
        )
        conexao_id = cur.fetchone()[0]
        user_id = f"test-conv-{_RUN}"
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status,
                                      is_superadmin)
            VALUES (%s, 'Test Conversa', %s, TRUE, NOW(), NOW(), 'active', TRUE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )
        # Número em opt-out pro teste do 409.
        tel_optout = f"+5567988{_D}"
        cur.execute(
            """
            INSERT INTO disparador_opt_out (empresa_id, wa_jid, telefone)
            VALUES (%s, %s, %s)
            """,
            (empresa_id, f"{tel_optout.lstrip('+')}@s.whatsapp.net", tel_optout),
        )
        yield {
            "empresa_id": empresa_id,
            "conexao_id": conexao_id,
            "user_id": user_id,
            "tel_optout": tel_optout,
        }
        cur.execute("DELETE FROM message_queue WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM atendimento WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM cliente WHERE empresa_id = %s", (empresa_id,))
        cur.execute(
            "DELETE FROM disparador_opt_out WHERE empresa_id = %s", (empresa_id,)
        )
        cur.execute("DELETE FROM conexao WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))
        conn.close()

    def _headers(self, dados: dict) -> dict:
        h = get_admin_api_headers()
        h["X-User-Id"] = dados["user_id"]
        h["X-Empresa-Id"] = str(dados["empresa_id"])
        return h

    def _post(self, dados: dict, body: dict) -> httpx.Response:
        return httpx.post(
            f"{API_BASE_URL}/api/atendimentos/iniciar",
            headers=self._headers(dados),
            json=body,
            timeout=30,
        )

    def test_1_telefone_invalido_400(self, dados) -> None:
        r = self._post(
            dados,
            {
                "telefone": "12345678",
                "conexao_id": dados["conexao_id"],
                "mensagem": "oi",
            },
        )
        # 8 dígitos passa no Field mas normalize_phone recusa < 8 reais? Não:
        # 12345678 tem 8 dígitos e passa. Usamos um com menos após limpeza.
        r = self._post(
            dados,
            {
                "telefone": "+55 abc",
                "conexao_id": dados["conexao_id"],
                "mensagem": "oi",
            },
        )
        assert r.status_code in (400, 422), r.text

    def test_2_mensagem_e_template_juntos_422(self, dados) -> None:
        r = self._post(
            dados,
            {
                "telefone": "+5567999990001",
                "conexao_id": dados["conexao_id"],
                "mensagem": "oi",
                "template_id": 1,
            },
        )
        assert r.status_code == 422, r.text

    def test_3_optout_409(self, dados) -> None:
        r = self._post(
            dados,
            {
                "telefone": dados["tel_optout"],
                "conexao_id": dados["conexao_id"],
                "mensagem": "oi",
            },
        )
        assert r.status_code == 409, r.text
        assert "não receber" in r.json()["detail"]

    def test_4_anexa_em_aberto_sem_roubar_dono(self, dados) -> None:
        # Semeia cliente + atendimento aberto COM OUTRO dono; iniciar de novo
        # deve anexar (mesmo id) e preservar o dono. O envio vai falhar no
        # provedor fake — mas anexado (was_created=False) NÃO é desfeito, e a
        # falha volta como 502 sem apagar nada.
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        tel = f"+5567977{_D}"
        cur.execute(
            "INSERT INTO cliente (empresa_id, telefone, nome) VALUES (%s, %s, 'X') "
            "RETURNING id",
            (dados["empresa_id"], tel),
        )
        cliente_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO atendimento (empresa_id, cliente_id, conexao_id,
                                     agente_atual, status, assigned_to_user_id)
            VALUES (%s, %s, %s, 'agente', 'em_andamento', %s) RETURNING id
            """,
            (dados["empresa_id"], cliente_id, dados["conexao_id"], dados["user_id"]),
        )
        atd_id = cur.fetchone()[0]
        conn.close()

        r = self._post(
            dados,
            {"telefone": tel, "conexao_id": dados["conexao_id"], "mensagem": "olá"},
        )
        # Envio contra instância Evolution inexistente → 502; o atendimento
        # PRÉ-EXISTENTE precisa sobreviver com o dono intacto.
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT status, assigned_to_user_id, iniciado_cliente "
            "FROM atendimento WHERE id = %s",
            (atd_id,),
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None, "atendimento pré-existente foi apagado!"
        assert row[1] == dados["user_id"], "dono do atendimento foi trocado"
        assert r.status_code in (201, 502), r.text
        if r.status_code == 201:
            assert r.json()["was_created"] is False
            assert r.json()["atendimento"]["id"] == atd_id

    def test_5_falha_envio_desfaz_atendimento_novo(self, dados) -> None:
        tel = f"+5567966{_D}"
        r = self._post(
            dados,
            {"telefone": tel, "conexao_id": dados["conexao_id"], "mensagem": "oi"},
        )
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM atendimento a
              JOIN cliente c ON c.id = a.cliente_id
             WHERE a.empresa_id = %s AND c.telefone = %s
            """,
            (dados["empresa_id"], tel),
        )
        n = cur.fetchone()[0]
        conn.close()
        if r.status_code == 502:
            # Instância fake: envio falhou → atendimento órfão desfeito.
            assert n == 0, "atendimento órfão sobrou após falha de envio"
        else:
            # Ambiente com outbound mock: criou e enviou de verdade.
            assert r.status_code == 201, r.text
            assert n == 1
