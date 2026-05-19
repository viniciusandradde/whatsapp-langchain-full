"""Smoke + E2E do endpoint GET /clientes/{id}/atendimentos-anteriores (Sprint 1.4)."""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


# ============================================================================
# Smoke
# ============================================================================


class TestSmoke:
    def test_get_anteriores_sem_auth_401(self) -> None:
        resp = _client().get("/api/clientes/1/atendimentos-anteriores")
        assert resp.status_code == 401


# ============================================================================
# E2E
# ============================================================================


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
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível.")
    return url


@pytest.fixture(scope="module")
def empresa_id(db_url: str) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status)
                VALUES (%s, %s, 'free', 'active')
                RETURNING id
                """,
                (f"test-hist-{_RUN}", f"test-hist-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int) -> str:
    user_id = f"test-hist-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status,
                                          is_superadmin)
                VALUES (%s, 'Hist E2E', %s, TRUE, NOW(), NOW(),
                        'active', FALSE)
                """,
                (user_id, f"{user_id}@e2e.test"),
            )
            cur.execute(
                """
                INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
                VALUES (%s, %s, 'admin', TRUE)
                """,
                (empresa_id, user_id),
            )
            cur.execute(
                """
                INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system)
                VALUES (%s, 'Admin', 'Acesso total', TRUE)
                ON CONFLICT (empresa_id, nome) DO NOTHING
                RETURNING id
                """,
                (empresa_id,),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT id FROM perfil_acesso WHERE empresa_id = %s AND nome = 'Admin'",
                    (empresa_id,),
                )
                row = cur.fetchone()
            assert row is not None
            perfil_id = int(row[0])
            cur.execute(
                """
                INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
                SELECT %s, codigo FROM permissao ON CONFLICT DO NOTHING
                """,
                (perfil_id,),
            )
            cur.execute(
                """
                INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id,
                                            assigned_by_user_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (user_id, perfil_id, empresa_id, user_id),
            )
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.fixture(scope="module")
def cliente_com_atendimentos(db_url: str, empresa_id: int) -> dict:
    """Cria 1 cliente + 4 atendimentos (3 resolvidos antigos + 1 em andamento atual)."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Conexão
            cur.execute(
                """
                INSERT INTO conexao (empresa_id, provider, from_number,
                                      display_name, status)
                VALUES (%s, 'twilio_sandbox', %s, %s, 'active')
                RETURNING id
                """,
                (empresa_id, f"+155504{_RUN[:5]}", f"conn-hist-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            cid = int(row[0])

            # Cliente
            cur.execute(
                """
                INSERT INTO cliente (empresa_id, telefone, nome, status)
                VALUES (%s, %s, 'Cliente Histórico', 'active')
                RETURNING id
                """,
                (empresa_id, f"+5511993{_RUN[:5]}"),
            )
            row = cur.fetchone()
            assert row is not None
            cli_id = int(row[0])

            # 3 atendimentos antigos (status resolvido, created_at espaçados)
            anteriores: list[int] = []
            for i in range(3):
                cur.execute(
                    f"""
                    INSERT INTO atendimento (
                        empresa_id, cliente_id, conexao_id, status,
                        last_message_at, closed_at, created_at
                    )
                    VALUES (
                        %s, %s, %s, 'resolvido',
                        NOW() - INTERVAL '{i + 1} day',
                        NOW() - INTERVAL '{i + 1} day',
                        NOW() - INTERVAL '{i + 1} day'
                    )
                    RETURNING id
                    """,
                    (empresa_id, cli_id, cid),
                )
                row = cur.fetchone()
                assert row is not None
                anteriores.append(int(row[0]))

            # 1 atendimento atual (em andamento)
            cur.execute(
                """
                INSERT INTO atendimento (empresa_id, cliente_id, conexao_id,
                                          status, last_message_at)
                VALUES (%s, %s, %s, 'em_andamento', NOW())
                RETURNING id
                """,
                (empresa_id, cli_id, cid),
            )
            row = cur.fetchone()
            assert row is not None
            atual_id = int(row[0])

    return {
        "cliente_id": cli_id,
        "atendimento_atual": atual_id,
        "anteriores_ids": anteriores,
    }


@pytest.mark.docker_demo
class TestE2E:
    """Fluxo: cliente com 4 atendimentos → GET retorna histórico ordenado."""

    def test_lista_anteriores_ordenado_desc(
        self,
        db_url: str,
        empresa_id: int,
        admin_user_id: str,
        cliente_com_atendimentos: dict,
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        cli_id = cliente_com_atendimentos["cliente_id"]
        atual = cliente_com_atendimentos["atendimento_atual"]

        # --- 1. GET sem exclude — retorna todos (4)
        r = httpx.get(
            f"{API_BASE_URL}/api/clientes/{cli_id}/atendimentos-anteriores",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 4

        # Ordem: mais recente primeiro. O atual (NOW()) deve ser o primeiro
        assert items[0]["id"] == atual

        # --- 2. GET com exclude_id=atual → 3 (só anteriores)
        r = httpx.get(
            f"{API_BASE_URL}/api/clientes/{cli_id}/atendimentos-anteriores"
            f"?exclude_id={atual}",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 3
        assert all(it["id"] != atual for it in items)
        # Todos resolvidos
        assert all(it["status"] == "resolvido" for it in items)

        # --- 3. Paginação via limit
        r = httpx.get(
            f"{API_BASE_URL}/api/clientes/{cli_id}/atendimentos-anteriores"
            f"?limit=2&exclude_id={atual}",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 2

        # --- 4. Cliente inexistente → 404
        r = httpx.get(
            f"{API_BASE_URL}/api/clientes/99999999/atendimentos-anteriores",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 404

        # --- 5. limit fora de range → 422
        r = httpx.get(
            f"{API_BASE_URL}/api/clientes/{cli_id}/atendimentos-anteriores?limit=999",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 422


@pytest.mark.docker_demo
class TestE2EIsolamento:
    """Cliente de outra empresa → 403."""

    def test_cliente_cross_empresa_403(self, db_url: str) -> None:
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active')
                    RETURNING id
                    """,
                    (f"test-hist-iso-A-{_RUN}", f"test-hist-iso-A-{_RUN}"),
                )
                row_a = cur.fetchone()
                assert row_a is not None
                emp_a = int(row_a[0])
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active')
                    RETURNING id
                    """,
                    (f"test-hist-iso-B-{_RUN}", f"test-hist-iso-B-{_RUN}"),
                )
                row_b = cur.fetchone()
                assert row_b is not None
                emp_b = int(row_b[0])

                user_b = f"test-hist-iso-b-{_RUN}"
                cur.execute(
                    """
                    INSERT INTO auth."user" (id, name, email, "emailVerified",
                                              "createdAt", "updatedAt", status,
                                              is_superadmin)
                    VALUES (%s, 'Iso', %s, TRUE, NOW(), NOW(),
                            'active', FALSE)
                    """,
                    (user_b, f"{user_b}@iso.test"),
                )
                cur.execute(
                    """
                    INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
                    VALUES (%s, %s, 'admin', TRUE)
                    """,
                    (emp_b, user_b),
                )
                cur.execute(
                    """
                    INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system)
                    VALUES (%s, 'Admin', 'Acesso total', TRUE)
                    ON CONFLICT (empresa_id, nome) DO NOTHING
                    RETURNING id
                    """,
                    (emp_b,),
                )
                prow = cur.fetchone()
                if prow is None:
                    cur.execute(
                        "SELECT id FROM perfil_acesso WHERE empresa_id = %s AND nome = 'Admin'",
                        (emp_b,),
                    )
                    prow = cur.fetchone()
                assert prow is not None
                pf_id = int(prow[0])
                cur.execute(
                    """
                    INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
                    SELECT %s, codigo FROM permissao ON CONFLICT DO NOTHING
                    """,
                    (pf_id,),
                )
                cur.execute(
                    """
                    INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id,
                                                assigned_by_user_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (user_b, pf_id, emp_b, user_b),
                )

                # Cliente em A
                cur.execute(
                    """
                    INSERT INTO cliente (empresa_id, telefone, nome, status)
                    VALUES (%s, %s, 'Cliente A', 'active')
                    RETURNING id
                    """,
                    (emp_a, f"+5511994{_RUN[:5]}"),
                )
                cli_row = cur.fetchone()
                assert cli_row is not None
                cli_a = int(cli_row[0])

        try:
            # B (mesmo logado no emp_b) tenta ver cliente de A → 403
            r = httpx.get(
                f"{API_BASE_URL}/api/clientes/{cli_a}/atendimentos-anteriores",
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            assert r.status_code == 403, r.text
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM empresa WHERE id IN (%s, %s)",
                        (emp_a, emp_b),
                    )
