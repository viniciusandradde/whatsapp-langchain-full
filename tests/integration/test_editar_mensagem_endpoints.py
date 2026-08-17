"""Smoke + E2E de editar e apagar mensagem já entregue (mig 172).

Smoke (sem DB): as duas rotas existem e exigem service token.

E2E (stack rodando): cobre as RECUSAS e os sinais que a UI usa. O caminho
feliz não entra aqui de propósito — editar de verdade chama a Evolution e
mexe no WhatsApp de alguém; isso é teste manual no aparelho pareado, descrito
no plano. O que dá pra automatizar sem tocar o provedor é justamente onde
moram os erros: quem NÃO pode alterar.

    uv run pytest tests/integration/test_editar_mensagem_endpoints.py::TestSmoke -v

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    uv run pytest tests/integration/test_editar_mensagem_endpoints.py::TestE2E -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]
#: Telefone só com dígitos derivado do run: `uuid.hex` pode sair com letras, e
#: um telefone com letra é descartado na normalização — a suite passaria a
#: testar outra coisa. Lição da suite da mig 170.
_D = f"{int(_RUN, 16) % 1_000_000:06d}"
_TEL = f"+5567999{_D}"


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_editar_sem_auth_401(self) -> None:
        r = _client().patch(
            "/api/atendimentos/1/mensagens/1/texto", json={"texto": "novo"}
        )
        assert r.status_code == 401

    def test_apagar_sem_auth_401(self) -> None:
        assert (
            _client().delete("/api/atendimentos/1/mensagens/1/texto").status_code == 401
        )


@pytest.mark.docker_demo
class TestE2E:
    @pytest.fixture(scope="class")
    def dados(self):
        """Uma conversa com quatro mensagens, cada uma num estado da regra."""
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO empresa (nome, slug, plano, status) "
            "VALUES (%s, %s, 'free', 'active') RETURNING id",
            (f"E2E Editar {_RUN}", f"e2e-editar-{_RUN}"),
        )
        empresa_id = cur.fetchone()[0]

        # Duas conexões: a Evolution é a que permite; a WABA existe pra provar
        # que o canal oficial da Meta é recusado.
        cur.execute(
            "INSERT INTO conexao (empresa_id, provider, from_number, status) "
            "VALUES (%s, 'evolution', %s, 'active') RETURNING id",
            (empresa_id, _TEL),
        )
        conexao_evo = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO conexao (empresa_id, provider, from_number, status) "
            "VALUES (%s, 'waba', %s, 'active') RETURNING id",
            (empresa_id, f"+5567988{_D}"),
        )
        conexao_waba = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO cliente (empresa_id, telefone, nome) "
            "VALUES (%s, %s, %s) RETURNING id",
            (empresa_id, _TEL, f"Cliente E2E {_RUN}"),
        )
        cliente_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO atendimento
                (empresa_id, cliente_id, conexao_id, agente_atual, status)
            VALUES (%s, %s, %s, 'agente', 'em_andamento') RETURNING id
            """,
            (empresa_id, cliente_id, conexao_evo),
        )
        atd_id = cur.fetchone()[0]

        def msg(normalized, message_id, conexao_id, idade_min, media=None):
            cur.execute(
                """
                INSERT INTO message_queue
                    (phone_number, agent_id, thread_id, incoming_message,
                     response, normalized_input, message_id, status,
                     empresa_id, atendimento_id, conexao_id,
                     response_media_url,
                     created_at, processed_at)
                VALUES (%s, 'agente', %s, '', 'texto original', %s, %s, 'done',
                        %s, %s, %s, %s,
                        NOW() - make_interval(mins => %s),
                        NOW() - make_interval(mins => %s))
                RETURNING id
                """,
                (
                    _TEL,
                    f"{_TEL}:agente",
                    normalized,
                    message_id,
                    empresa_id,
                    atd_id,
                    conexao_id,
                    media,
                    idade_min,
                    idade_min,
                ),
            )
            return cur.fetchone()[0]

        ids = {
            "ok": msg("manual:op", "3EB0RECENTE", conexao_evo, 1),
            "antiga": msg("manual:op", "3EB0ANTIGA", conexao_evo, 60),
            "agente": msg("agente", None, conexao_evo, 1),
            "waba": msg("manual:op", "wamid.XXX", conexao_waba, 1),
        }

        user_id = f"test-editar-{_RUN}"
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status,
                                      is_superadmin)
            VALUES (%s, 'Test Editar', %s, TRUE, NOW(), NOW(), 'active', TRUE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )
        yield {
            "empresa_id": empresa_id,
            "atd_id": atd_id,
            "user_id": user_id,
            **ids,
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

    def _patch(self, dados, mid, texto="corrigido"):
        return httpx.patch(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}/mensagens/{mid}/texto",
            headers=self._h(dados),
            json={"texto": texto},
            timeout=30,
        )

    def _delete(self, dados, mid):
        return httpx.request(
            "DELETE",
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}/mensagens/{mid}/texto",
            headers=self._h(dados),
            timeout=30,
        )

    def test_1_lista_marca_o_que_pode(self, dados) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}/mensagens",
            headers=self._h(dados),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        por_id = {m["id"]: m for m in r.json()["mensagens"]}

        # Recém-enviada pelo operador na Evolution: as duas ações.
        assert por_id[dados["ok"]]["pode_editar_resposta"] is True
        assert por_id[dados["ok"]]["pode_apagar_resposta"] is True
        # Uma hora depois: a edição fecha, apagar continua. É a razão de
        # "apagar" ter entrado no escopo.
        assert por_id[dados["antiga"]]["pode_editar_resposta"] is False
        assert por_id[dados["antiga"]]["pode_apagar_resposta"] is True
        # Resposta da IA: sem chave do provedor, nada é possível.
        assert por_id[dados["agente"]]["pode_editar_resposta"] is False
        assert por_id[dados["agente"]]["pode_apagar_resposta"] is False
        # Canal oficial da Meta não edita nem apaga.
        assert por_id[dados["waba"]]["pode_editar_resposta"] is False
        assert por_id[dados["waba"]]["pode_apagar_resposta"] is False

    def test_2_editar_fora_da_janela_recusa(self, dados) -> None:
        r = self._patch(dados, dados["antiga"])
        assert r.status_code == 400, r.text
        assert "15 minutos" in r.json()["detail"]

    def test_3_editar_mensagem_da_ia_recusa(self, dados) -> None:
        assert self._patch(dados, dados["agente"]).status_code == 400

    def test_4_editar_em_conexao_waba_recusa(self, dados) -> None:
        assert self._patch(dados, dados["waba"]).status_code == 400

    def test_5_apagar_mensagem_da_ia_recusa(self, dados) -> None:
        assert self._delete(dados, dados["agente"]).status_code == 400

    def test_6_mensagem_de_outro_atendimento_recusa(self, dados) -> None:
        # Id existente, atendimento errado: o filtro do WHERE tem que pegar.
        r = httpx.patch(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}"
            f"/mensagens/999999999/texto",
            headers=self._h(dados),
            json={"texto": "x"},
            timeout=30,
        )
        assert r.status_code == 400, r.text

    def test_7_texto_vazio_recusa(self, dados) -> None:
        # Validação do Pydantic (min_length=1) antes de qualquer chamada.
        assert self._patch(dados, dados["ok"], texto="").status_code == 422

    def test_8_nada_foi_alterado_no_banco(self, dados) -> None:
        # Nenhum teste acima chegou a alterar — todos recusaram. Se algum
        # tivesse passado, o texto teria mudado e isso apareceria aqui.
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT response, response_apagada_at FROM message_queue "
            "WHERE atendimento_id = %s ORDER BY id",
            (dados["atd_id"],),
        )
        linhas = cur.fetchall()
        conn.close()
        assert all(r[0] == "texto original" for r in linhas)
        assert all(r[1] is None for r in linhas)
