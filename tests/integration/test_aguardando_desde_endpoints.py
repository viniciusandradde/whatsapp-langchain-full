"""Smoke + E2E do `aguardando_desde` e da busca por telefone (inbox agrupado).

Smoke (sem DB): a listagem com `q` existe e exige service token.

E2E (stack rodando): duas conversas na mesma empresa — uma respondida pela
IA, outra em que o cliente falou por último. A listagem devolve
`aguardando_desde` SÓ na segunda, com o `created_at` da mensagem do cliente;
nota interna e marker interno do worker não apagam o chip. De carona, `q`
com dígitos acha a conversa pelo telefone em qualquer grafia.

    uv run pytest tests/integration/test_aguardando_desde_endpoints.py::TestSmoke -v

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    uv run pytest tests/integration/test_aguardando_desde_endpoints.py::TestE2E -v
"""

from __future__ import annotations

import uuid
from datetime import datetime

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]
_D = f"{int(_RUN, 16) % 1_000_000:06d}"
# Dois telefones com os mesmos 6 dígitos finais distintos entre si: o
# "respondido" termina em _D, o "pendente" em _D invertido — pra busca por
# dígitos ter um alvo único em cada caso.
_TEL_RESPONDIDO = f"+5567998{_D}"
_TEL_PENDENTE = f"+5567997{_D[::-1]}"


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_listagem_com_q_sem_auth_401(self) -> None:
        r = _client().get("/api/atendimentos?q=99979")
        assert r.status_code == 401


@pytest.mark.docker_demo
class TestE2E:
    @pytest.fixture(scope="class")
    def dados(self):
        """Empresa isolada com 2 conversas: uma respondida, uma pendente."""
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO empresa (nome, slug, plano, status) "
            "VALUES (%s, %s, 'free', 'active') RETURNING id",
            (f"E2E Aguardando {_RUN}", f"e2e-aguardando-{_RUN}"),
        )
        empresa_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO conexao (empresa_id, provider, from_number, status) "
            "VALUES (%s, 'evolution', %s, 'active') RETURNING id",
            (empresa_id, _TEL_RESPONDIDO),
        )
        conexao_id = cur.fetchone()[0]

        user_id = f"test-aguardando-{_RUN}"
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status,
                                      is_superadmin)
            VALUES (%s, 'Test Aguardando', %s, TRUE, NOW(), NOW(), 'active', TRUE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )

        def _conversa(telefone: str, nome: str) -> int:
            cur.execute(
                "INSERT INTO cliente (empresa_id, telefone, nome) "
                "VALUES (%s, %s, %s) RETURNING id",
                (empresa_id, telefone, nome),
            )
            cliente_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO atendimento
                    (empresa_id, cliente_id, conexao_id, agente_atual, status)
                VALUES (%s, %s, %s, 'agente', 'aguardando') RETURNING id
                """,
                (empresa_id, cliente_id, conexao_id),
            )
            return cur.fetchone()[0]

        atd_respondido = _conversa(_TEL_RESPONDIDO, f"Respondido {_RUN}")
        atd_pendente = _conversa(_TEL_PENDENTE, f"Pendente {_RUN}")

        # Respondida: cliente falou e a IA respondeu na mesma row.
        cur.execute(
            """
            INSERT INTO message_queue
                (phone_number, agent_id, thread_id, incoming_message, response,
                 status, empresa_id, atendimento_id, conexao_id,
                 created_at, processed_at)
            VALUES (%s, 'agente', %s, 'oi, qual o horário?', 'Das 8h às 18h.',
                    'done', %s, %s, %s, NOW() - interval '3 hours', NOW())
            """,
            (
                _TEL_RESPONDIDO,
                f"{_TEL_RESPONDIDO}:agente",
                empresa_id,
                atd_respondido,
                conexao_id,
            ),
        )
        # Pendente: cliente falou há 2h e ninguém respondeu (row `queued`
        # esperando o worker — que está parado pra este teste não depender
        # dele; a semântica é a mesma de uma conversa em modo manual).
        cur.execute(
            """
            INSERT INTO message_queue
                (phone_number, agent_id, thread_id, incoming_message,
                 status, empresa_id, atendimento_id, conexao_id,
                 created_at, process_after)
            VALUES (%s, 'agente', %s, 'alguém me responde?', 'queued',
                    %s, %s, %s, NOW() - interval '2 hours', NOW() + interval '1 day')
            RETURNING created_at
            """,
            (
                _TEL_PENDENTE,
                f"{_TEL_PENDENTE}:agente",
                empresa_id,
                atd_pendente,
                conexao_id,
            ),
        )
        criada_em = cur.fetchone()[0]

        yield {
            "empresa_id": empresa_id,
            "conexao_id": conexao_id,
            "user_id": user_id,
            "atd_respondido": atd_respondido,
            "atd_pendente": atd_pendente,
            "criada_em": criada_em,
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

    def _listar(self, dados: dict, **params) -> dict[int, dict]:
        r = httpx.get(
            f"{API_BASE_URL}/api/atendimentos",
            params={"tipo": "todas", **params},
            headers=self._h(dados),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        return {a["id"]: a for a in r.json()["atendimentos"]}

    def test_1_respondida_nao_esta_aguardando(self, dados) -> None:
        por_id = self._listar(dados)
        assert dados["atd_respondido"] in por_id, "conversa sumiu da listagem"
        assert por_id[dados["atd_respondido"]]["aguardando_desde"] is None

    def test_2_pendente_aguarda_desde_a_mensagem_do_cliente(self, dados) -> None:
        por_id = self._listar(dados)
        desde = por_id[dados["atd_pendente"]]["aguardando_desde"]
        assert desde is not None
        assert datetime.fromisoformat(desde) == dados["criada_em"]

    def test_3_nota_interna_nao_apaga_o_chip(self, dados) -> None:
        """Nota interna é a última row, mas é filtrada no SQL do lote."""
        conn = psycopg.connect(get_db_url(), autocommit=True)
        conn.execute(
            """
            INSERT INTO message_queue
                (phone_number, agent_id, thread_id, incoming_message, response,
                 interna, status, empresa_id, atendimento_id,
                 created_at, processed_at)
            VALUES (%s, 'agente', %s, '', 'anotação privada', TRUE, 'done',
                    %s, %s, NOW(), NOW())
            """,
            (
                _TEL_PENDENTE,
                f"{_TEL_PENDENTE}:agente",
                dados["empresa_id"],
                dados["atd_pendente"],
            ),
        )
        conn.close()
        por_id = self._listar(dados)
        desde = por_id[dados["atd_pendente"]]["aguardando_desde"]
        assert desde is not None
        assert datetime.fromisoformat(desde) == dados["criada_em"]

    def test_4_marker_interno_do_worker_nao_e_resposta(self, dados) -> None:
        """Modo manual grava `[modo manual …]` em response: nada chegou ao
        cliente, ele continua esperando desde ESSA mensagem (mais nova)."""
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.execute(
            """
            INSERT INTO message_queue
                (phone_number, agent_id, thread_id, incoming_message, response,
                 status, empresa_id, atendimento_id, conexao_id,
                 created_at, processed_at)
            VALUES (%s, 'agente', %s, 'oi de novo',
                    '[modo manual — IA desligada nesta conexão]', 'done',
                    %s, %s, %s, NOW() - interval '30 minutes', NOW())
            RETURNING created_at
            """,
            (
                _TEL_PENDENTE,
                f"{_TEL_PENDENTE}:agente",
                dados["empresa_id"],
                dados["atd_pendente"],
                dados["conexao_id"],
            ),
        )
        criada_em = cur.fetchone()[0]
        conn.close()
        por_id = self._listar(dados)
        desde = por_id[dados["atd_pendente"]]["aguardando_desde"]
        assert desde is not None
        assert datetime.fromisoformat(desde) == criada_em

    def test_5_resposta_do_operador_apaga_o_chip(self, dados) -> None:
        """Row de saída do composer (`incoming_message=""` + response)."""
        conn = psycopg.connect(get_db_url(), autocommit=True)
        conn.execute(
            """
            INSERT INTO message_queue
                (phone_number, agent_id, thread_id, incoming_message, response,
                 normalized_input, status, empresa_id, atendimento_id,
                 conexao_id, created_at, processed_at)
            VALUES (%s, 'agente', %s, '', 'Oi! Já estou olhando.',
                    %s, 'done', %s, %s, %s, NOW(), NOW())
            """,
            (
                _TEL_PENDENTE,
                f"{_TEL_PENDENTE}:agente",
                f"manual:{dados['user_id']}",
                dados["empresa_id"],
                dados["atd_pendente"],
                dados["conexao_id"],
            ),
        )
        conn.close()
        por_id = self._listar(dados)
        assert por_id[dados["atd_pendente"]]["aguardando_desde"] is None

    def test_6_busca_por_telefone_com_mascara(self, dados) -> None:
        """Dígitos do fim do número, digitados com máscara, acham a conversa."""
        fim = _TEL_PENDENTE[-6:]
        q = f"{fim[:2]} {fim[2:]}"  # "12 3456"
        por_id = self._listar(dados, q=q)
        assert dados["atd_pendente"] in por_id
        # Só afirma a exclusão quando o bloco não ocorre por acaso no outro
        # número (os dois vêm do mesmo hash do run).
        if fim not in _TEL_RESPONDIDO:
            assert dados["atd_respondido"] not in por_id

    def test_7_busca_por_nome_continua_funcionando(self, dados) -> None:
        por_id = self._listar(dados, q=f"Respondido {_RUN}")
        assert dados["atd_respondido"] in por_id
        assert dados["atd_pendente"] not in por_id

    def test_8_poucos_digitos_nao_casam_telefone(self, dados) -> None:
        """'+55 6' (3 dígitos) não pode varrer os telefones da empresa — cai
        na busca de sempre por nome/protocolo, que não casa nada aqui."""
        por_id = self._listar(dados, q="+55 6")
        assert dados["atd_respondido"] not in por_id
        assert dados["atd_pendente"] not in por_id
