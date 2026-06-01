"""E2E do módulo Histórico de Atendimentos (`/api/historico`).

TestSmoke (sem DB) vive em tests/unit/test_historico_endpoints_smoke.py.
Aqui: TestE2E (docker_demo, httpx + psycopg real) cobre lista + filtros +
detalhe + export CSV/XLSX, e TestE2EIsolamento (empresa não vê dados de outra).

Rodar com a stack de pé:
  DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
  INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
  uv run pytest tests/integration/test_historico_endpoints.py
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

pytestmark = pytest.mark.docker_demo

_RUN = uuid.uuid4().hex[:8]


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
        pytest.skip("DB não acessível")
    return url


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


def _criar_empresa(cur, slug: str) -> int:
    cur.execute(
        "INSERT INTO empresa (nome, slug, plano, status) "
        "VALUES (%s, %s, 'free', 'active') RETURNING id",
        (slug, slug),
    )
    return int(cur.fetchone()[0])


def _criar_admin(cur, empresa_id: int, user_id: str) -> None:
    cur.execute(
        'INSERT INTO auth."user" (id, name, email, "emailVerified", '
        '"createdAt", "updatedAt", status, is_superadmin) '
        "VALUES (%s, 'Hist E2E', %s, TRUE, NOW(), NOW(), 'active', FALSE)",
        (user_id, f"{user_id}@e2e.test"),
    )
    cur.execute(
        "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
        "VALUES (%s, %s, 'admin', TRUE)",
        (empresa_id, user_id),
    )
    cur.execute(
        "INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system) "
        "VALUES (%s, 'Admin', 'Acesso total', TRUE) "
        "ON CONFLICT (empresa_id, nome) DO NOTHING RETURNING id",
        (empresa_id,),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "SELECT id FROM perfil_acesso WHERE empresa_id=%s AND nome='Admin'",
            (empresa_id,),
        )
        row = cur.fetchone()
    perfil_id = int(row[0])
    cur.execute(
        "INSERT INTO perfil_permissao (perfil_id, permissao_codigo) "
        "SELECT %s, codigo FROM permissao ON CONFLICT DO NOTHING",
        (perfil_id,),
    )
    cur.execute(
        "INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id, "
        "assigned_by_user_id) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (user_id, perfil_id, empresa_id, user_id),
    )


@pytest.fixture(scope="module")
def setup(db_url: str):
    """Cria empresa A (com 3 atendimentos variados) + empresa B (vazia)."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, f"test-hist-{_RUN}")
        uid = f"test-hist-user-{_RUN}"
        _criar_admin(cur, eid, uid)

        eid_b = _criar_empresa(cur, f"test-hist-b-{_RUN}")
        uid_b = f"test-hist-userb-{_RUN}"
        _criar_admin(cur, eid_b, uid_b)

        cur.execute(
            "INSERT INTO conexao (empresa_id, provider, from_number, "
            "display_name, status) VALUES (%s, 'twilio_sandbox', %s, %s, 'active') "
            "RETURNING id",
            (eid, f"+15550{_RUN[:5]}", f"Canal {_RUN}"),
        )
        conexao_id = int(cur.fetchone()[0])

        cur.execute(
            "INSERT INTO cliente (empresa_id, telefone, nome, status) "
            "VALUES (%s, %s, 'Maria Historico', 'active') RETURNING id",
            (eid, f"+5511{_RUN[:7]}"),
        )
        cliente_id = int(cur.fetchone()[0])

        # 3 atendimentos: resolvido (com nota), abandonado, aguardando.
        ids: dict[str, int] = {}
        for status, dias, fechar in [
            ("resolvido", 5, True),
            ("abandonado", 3, True),
            ("aguardando", 1, False),
        ]:
            cur.execute(
                """
                INSERT INTO atendimento
                    (empresa_id, cliente_id, conexao_id, agente_atual, status,
                     created_at, last_message_at, closed_at, iniciado_cliente)
                VALUES (%s, %s, %s, 'vsa_tech', %s,
                        NOW() - (%s || ' days')::interval,
                        NOW() - (%s || ' days')::interval,
                        CASE WHEN %s THEN NOW() - (%s || ' days')::interval END,
                        TRUE)
                RETURNING id
                """,
                (eid, cliente_id, conexao_id, status, dias, dias, fechar, dias),
            )
            ids[status] = int(cur.fetchone()[0])

        # Avaliação no resolvido + uma mensagem na timeline.
        cur.execute(
            "INSERT INTO atendimento_avaliacao (atendimento_id, empresa_id, "
            "cliente_id, nota, categoria) VALUES (%s, %s, %s, 10, 'promotor')",
            (ids["resolvido"], eid, cliente_id),
        )
        cur.execute(
            "INSERT INTO message_queue (empresa_id, atendimento_id, phone_number, "
            "agent_id, thread_id, incoming_message, response, status) "
            "VALUES (%s, %s, %s, 'vsa_tech', %s, 'ola', 'Olá!', 'done')",
            (eid, ids["resolvido"], f"+5511{_RUN[:7]}", f"+5511{_RUN[:7]}:vsa_tech"),
        )

    yield {
        "empresa_id": eid,
        "user_id": uid,
        "empresa_id_b": eid_b,
        "user_id_b": uid_b,
        "atendimentos": ids,
        "cliente_id": cliente_id,
    }

    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = ANY(%s)", ([eid, eid_b],))
        cur.execute('DELETE FROM auth."user" WHERE id = ANY(%s)', ([uid, uid_b],))


class TestE2E:
    def test_1_lista_traz_os_3(self, setup):
        h = _headers(setup["user_id"], setup["empresa_id"])
        r = httpx.get(f"{API_BASE_URL}/api/historico", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 3
        statuses = {row["status"] for row in body["rows"]}
        assert {"resolvido", "abandonado", "aguardando"} <= statuses

    def test_2_filtra_status(self, setup):
        h = _headers(setup["user_id"], setup["empresa_id"])
        r = httpx.get(
            f"{API_BASE_URL}/api/historico?status=resolvido", headers=h, timeout=10
        )
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert rows and all(x["status"] == "resolvido" for x in rows)
        assert any(x["nota_csat"] == 10 for x in rows)

    def test_3_busca_por_nome(self, setup):
        h = _headers(setup["user_id"], setup["empresa_id"])
        r = httpx.get(f"{API_BASE_URL}/api/historico?q=Maria", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["total"] >= 3

    def test_4_detalhe(self, setup):
        h = _headers(setup["user_id"], setup["empresa_id"])
        aid = setup["atendimentos"]["resolvido"]
        r = httpx.get(f"{API_BASE_URL}/api/historico/{aid}", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["avaliacao"]["nota"] == 10
        assert len(d["mensagens"]) >= 1
        assert any(e["tipo"] == "fechado" for e in d["eventos"])

    def test_5_export_csv(self, setup):
        h = _headers(setup["user_id"], setup["empresa_id"])
        r = httpx.get(
            f"{API_BASE_URL}/api/historico/export?formato=csv", headers=h, timeout=15
        )
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")
        assert "Protocolo" in r.text

    def test_6_export_xlsx(self, setup):
        h = _headers(setup["user_id"], setup["empresa_id"])
        r = httpx.get(
            f"{API_BASE_URL}/api/historico/export?formato=xlsx", headers=h, timeout=15
        )
        assert r.status_code == 200, r.text
        assert "spreadsheetml" in r.headers.get("content-type", "")
        assert r.content[:2] == b"PK"  # assinatura ZIP/XLSX


class TestE2EIsolamento:
    def test_empresa_b_nao_ve_dados_de_a(self, setup):
        h = _headers(setup["user_id_b"], setup["empresa_id_b"])
        r = httpx.get(f"{API_BASE_URL}/api/historico?q=Maria", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 0

    def test_detalhe_cross_empresa_404(self, setup):
        h = _headers(setup["user_id_b"], setup["empresa_id_b"])
        aid = setup["atendimentos"]["resolvido"]
        r = httpx.get(f"{API_BASE_URL}/api/historico/{aid}", headers=h, timeout=10)
        assert r.status_code == 404, r.text


class TestE2ERelatorios:
    def test_resumo(self, setup):
        h = _headers(setup["user_id"], setup["empresa_id"])
        r = httpx.get(
            f"{API_BASE_URL}/api/historico/relatorios/resumo?dias=30",
            headers=h,
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kpis"]["total"] >= 3
        assert body["kpis"]["csat_medio"] is not None  # tem a avaliação nota 10
        assert isinstance(body["serie_diaria"], list)

    def test_por_canal(self, setup):
        h = _headers(setup["user_id"], setup["empresa_id"])
        r = httpx.get(
            f"{API_BASE_URL}/api/historico/relatorios/por-canal?dias=30",
            headers=h,
            timeout=10,
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert items and items[0]["total"] >= 3

    def test_por_operador_e_departamento_ok(self, setup):
        h = _headers(setup["user_id"], setup["empresa_id"])
        for rota in ("por-operador", "por-departamento"):
            r = httpx.get(
                f"{API_BASE_URL}/api/historico/relatorios/{rota}?dias=30",
                headers=h,
                timeout=10,
            )
            assert r.status_code == 200, r.text
            assert isinstance(r.json()["items"], list)
