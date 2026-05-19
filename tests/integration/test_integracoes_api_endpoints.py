"""Smoke + E2E dos endpoints /api/integracoes (Sprint Conector API)."""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_get_providers_sem_auth_401(self) -> None:
        assert _client().get("/api/integracoes/providers").status_code == 401

    def test_list_sem_auth_401(self) -> None:
        assert _client().get("/api/integracoes").status_code == 401

    def test_post_sem_auth_401(self) -> None:
        assert (
            _client()
            .post(
                "/api/integracoes",
                json={"provider_slug": "asaas", "label": "X", "credentials": {}},
            )
            .status_code
            == 401
        )

    def test_test_sem_auth_401(self) -> None:
        assert (
            _client().post("/api/integracoes/1/testar").status_code == 401
        )


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
                VALUES (%s, %s, 'free', 'active') RETURNING id
                """,
                (f"test-int-{_RUN}", f"test-int-{_RUN}"),
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
    user_id = f"test-int-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status,
                                          is_superadmin)
                VALUES (%s, 'Int E2E', %s, TRUE, NOW(), NOW(), 'active', FALSE)
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
                VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
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


@pytest.fixture(scope="module", autouse=True)
def _setup_fernet():
    import os

    if not os.getenv("WARELINE_ENCRYPTION_KEY"):
        os.environ["WARELINE_ENCRYPTION_KEY"] = Fernet.generate_key().decode()


@pytest.mark.docker_demo
class TestE2E:
    def test_fluxo_completo_asaas(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_id)

        # 1) GET /providers — catálogo
        r = httpx.get(
            f"{API_BASE_URL}/api/integracoes/providers?include_legacy=false",
            headers=h,
            timeout=5,
        )
        if r.status_code == 503:
            pytest.skip("API sem WARELINE_ENCRYPTION_KEY")
        assert r.status_code == 200, r.text
        slugs = {p["slug"] for p in r.json()["items"]}
        assert "asaas" in slugs and "custom" in slugs

        # 2) GET — vazio
        r = httpx.get(
            f"{API_BASE_URL}/api/integracoes", headers=h, timeout=5
        )
        assert r.status_code == 200, r.text
        assert r.json()["items"] == []

        # 3) POST — cria Asaas
        r = httpx.post(
            f"{API_BASE_URL}/api/integracoes",
            json={
                "provider_slug": "asaas",
                "label": f"Asaas {_RUN}",
                "credentials": {
                    "access_token": f"$aact_e2e_{_RUN}",
                    "ambiente": "sandbox",
                },
                "ativo": True,
            },
            headers=h,
            timeout=5,
        )
        assert r.status_code == 201, r.text
        conn = r.json()
        conn_id = conn["id"]
        assert conn["provider_slug"] == "asaas"
        assert conn["auth_type"] == "api_key"
        # Sensitive masked
        assert conn["credentials"]["access_token"] == "••••••••"

        # 4) DB confirma cripto
        with psycopg.connect(db_url) as conn_db:
            with conn_db.cursor() as cur:
                cur.execute(
                    "SELECT credentials_encrypted FROM api_connection WHERE id = %s",
                    (conn_id,),
                )
                row = cur.fetchone()
                assert row is not None
                assert row[0].startswith("gAAAAA")
                # access_token plaintext NÃO na coluna
                assert f"$aact_e2e_{_RUN}" not in row[0]

        # 5) GET lista mostra a conexão
        r = httpx.get(
            f"{API_BASE_URL}/api/integracoes", headers=h, timeout=5
        )
        items = r.json()["items"]
        assert any(c["id"] == conn_id for c in items)

        # 6) POST duplicado (mesmo provider+label) → 409
        r = httpx.post(
            f"{API_BASE_URL}/api/integracoes",
            json={
                "provider_slug": "asaas",
                "label": f"Asaas {_RUN}",
                "credentials": {
                    "access_token": "outro",
                    "ambiente": "sandbox",
                },
            },
            headers=h,
            timeout=5,
        )
        assert r.status_code == 409

        # 7) PATCH parcial sem credentials → preserva ciphertext
        r = httpx.patch(
            f"{API_BASE_URL}/api/integracoes/{conn_id}",
            json={"label": f"Asaas Renomeada {_RUN}"},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        assert r.json()["label"] == f"Asaas Renomeada {_RUN}"

        # 8) POST testar (Asaas vai retornar 401 com token fake — esperado)
        r = httpx.post(
            f"{API_BASE_URL}/api/integracoes/{conn_id}/testar",
            headers=h,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # ok pode ser False (token fake é inválido) — só queremos confirmar
        # que o handler rodou
        assert "mensagem" in r.json()

        # 9) DELETE
        r = httpx.delete(
            f"{API_BASE_URL}/api/integracoes/{conn_id}",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200

        # 10) GET — sumiu
        r = httpx.get(
            f"{API_BASE_URL}/api/integracoes", headers=h, timeout=5
        )
        assert not any(c["id"] == conn_id for c in r.json()["items"])

    def test_create_provider_legacy_rejeita_422(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/integracoes",
            json={
                "provider_slug": "wareline",
                "label": "X",
                "credentials": {
                    "username": "u",
                    "password": "p",
                    "client_id": "c",
                    "client_secret": "s",
                },
            },
            headers=h,
            timeout=5,
        )
        # Esperado 422 (legacy_storage rejeita)
        if r.status_code == 503:
            pytest.skip("API sem WARELINE_ENCRYPTION_KEY")
        assert r.status_code == 422, r.text
        assert "legacy" in r.json().get("detail", "").lower()


@pytest.mark.docker_demo
class TestE2EIsolamento:
    def test_empresa_b_nao_ve_conexao_de_a(self, db_url: str) -> None:
        # Cria 2 empresas + 1 user em B + cria conexão direto em A
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active') RETURNING id
                    """,
                    (f"test-int-iso-A-{_RUN}", f"test-int-iso-A-{_RUN}"),
                )
                row_a = cur.fetchone()
                assert row_a is not None
                emp_a = int(row_a[0])
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active') RETURNING id
                    """,
                    (f"test-int-iso-B-{_RUN}", f"test-int-iso-B-{_RUN}"),
                )
                row_b = cur.fetchone()
                assert row_b is not None
                emp_b = int(row_b[0])

                user_b = f"test-int-iso-b-{_RUN}"
                cur.execute(
                    """
                    INSERT INTO auth."user" (id, name, email, "emailVerified",
                                              "createdAt", "updatedAt", status,
                                              is_superadmin)
                    VALUES (%s, 'Iso', %s, TRUE, NOW(), NOW(), 'active', FALSE)
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
                    VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
                    """,
                    (user_b, pf_id, emp_b, user_b),
                )
                # Connection só em A (Fernet fake — não usa cripto pra teste de
                # isolamento)
                cur.execute(
                    """
                    INSERT INTO api_connection (
                        empresa_id, provider_slug, label, base_url, auth_type,
                        credentials_encrypted
                    ) VALUES (%s, 'asaas', 'A-only', 'https://x', 'api_key',
                              'gAAAAA-fake')
                    RETURNING id
                    """,
                    (emp_a,),
                )
                conn_row = cur.fetchone()
                assert conn_row is not None
                conn_a_id = int(conn_row[0])

        try:
            # B lista — não vê
            r = httpx.get(
                f"{API_BASE_URL}/api/integracoes",
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            if r.status_code == 503:
                pytest.skip("API sem WARELINE_ENCRYPTION_KEY")
            assert r.status_code == 200
            assert all(c["id"] != conn_a_id for c in r.json()["items"])

            # B tenta GET direto → 404
            r = httpx.get(
                f"{API_BASE_URL}/api/integracoes/{conn_a_id}",
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            assert r.status_code == 404

            # B tenta DELETE → 404
            r = httpx.delete(
                f"{API_BASE_URL}/api/integracoes/{conn_a_id}",
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            assert r.status_code == 404
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM empresa WHERE id IN (%s, %s)",
                        (emp_a, emp_b),
                    )
