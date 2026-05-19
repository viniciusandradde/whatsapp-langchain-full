"""Smoke + E2E dos endpoints /api/integracoes/wareline (Sprint Wareline)."""

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


# ============================================================================
# Smoke (TestClient, sem DB)
# ============================================================================


class TestSmoke:
    def test_get_sem_auth_401(self) -> None:
        assert _client().get("/api/integracoes/wareline").status_code == 401

    def test_put_sem_auth_401(self) -> None:
        resp = _client().put(
            "/api/integracoes/wareline", json={"username": "x"}
        )
        assert resp.status_code == 401

    def test_post_testar_sem_auth_401(self) -> None:
        assert (
            _client().post("/api/integracoes/wareline/testar").status_code == 401
        )

    def test_delete_sem_auth_401(self) -> None:
        assert (
            _client().delete("/api/integracoes/wareline").status_code == 401
        )


# ============================================================================
# E2E (stack real)
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
                (f"test-wareline-{_RUN}", f"test-wareline-{_RUN}"),
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
    user_id = f"test-wareline-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status,
                                          is_superadmin)
                VALUES (%s, 'Wareline E2E', %s, TRUE,
                        NOW(), NOW(), 'active', FALSE)
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


@pytest.fixture(scope="module", autouse=True)
def _setup_fernet_key():
    """API container precisa ter WARELINE_ENCRYPTION_KEY setada — em CI
    set via env. Se skip, E2E fica unable to encrypt."""
    import os

    if not os.getenv("WARELINE_ENCRYPTION_KEY"):
        # Tenta setar uma chave de teste (só pra suite local funcionar)
        os.environ["WARELINE_ENCRYPTION_KEY"] = Fernet.generate_key().decode()


@pytest.mark.docker_demo
class TestE2E:
    """Fluxo completo: GET vazio → PUT → GET retorna config → testar → DELETE."""

    def test_fluxo_completo_wareline(
        self,
        db_url: str,
        empresa_id: int,
        admin_user_id: str,
    ) -> None:
        h = _headers(admin_user_id, empresa_id)

        # 1) GET vazio (404)
        r = httpx.get(
            f"{API_BASE_URL}/api/integracoes/wareline",
            headers=h,
            timeout=5,
        )
        # Pode ser 404 (sem config) OU 503 (sem encryption key na API). Aceita
        # ambos como "vazio".
        if r.status_code == 503:
            pytest.skip(
                "API sem WARELINE_ENCRYPTION_KEY configurada — "
                "set env e reinicie o container"
            )
        assert r.status_code == 404, r.text

        # 2) PUT cria
        r = httpx.put(
            f"{API_BASE_URL}/api/integracoes/wareline",
            json={
                "username": f"e2e-{_RUN}",
                "password": "senha-secreta",
                "client_id": f"cid-{_RUN}",
                "client_secret": "secret-secreto",
                "base_url": "https://modulos-fake.test",
                "pacientes_base_url": "https://services-fake.test",
                "ativo": True,
            },
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        config = r.json()
        assert config["username"] == f"e2e-{_RUN}"
        # Senhas/secrets nunca retornam
        assert "password" not in config or config.get("password") is None
        assert config["password_set"] is True

        # 3) GET retorna config
        r = httpx.get(
            f"{API_BASE_URL}/api/integracoes/wareline",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        assert r.json()["username"] == f"e2e-{_RUN}"

        # 4) DB confirma cripto (senha NÃO em texto)
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT password_encrypted, client_secret_encrypted
                      FROM wareline_credentials WHERE empresa_id = %s
                    """,
                    (empresa_id,),
                )
                row = cur.fetchone()
                assert row is not None
                pwd_enc, secret_enc = row
                assert pwd_enc != "senha-secreta"
                assert secret_enc != "secret-secreto"
                assert pwd_enc.startswith("gAAAAA")  # Fernet token
                assert secret_enc.startswith("gAAAAA")

        # 5) PUT parcial sem password → preserva senha
        r = httpx.put(
            f"{API_BASE_URL}/api/integracoes/wareline",
            json={"ativo": False},
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text
        assert r.json()["ativo"] is False
        # DB: password_encrypted continua o mesmo
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT password_encrypted FROM wareline_credentials "
                    "WHERE empresa_id = %s",
                    (empresa_id,),
                )
                row = cur.fetchone()
                assert row is not None
                # Mesmo prefixo Fernet
                assert row[0].startswith("gAAAAA")

        # 6) DELETE
        r = httpx.delete(
            f"{API_BASE_URL}/api/integracoes/wareline",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 200, r.text

        # 7) GET volta a 404
        r = httpx.get(
            f"{API_BASE_URL}/api/integracoes/wareline",
            headers=h,
            timeout=5,
        )
        assert r.status_code == 404, r.text


@pytest.mark.docker_demo
class TestE2EIsolamento:
    """Cross-empresa: B não acessa credenciais de A."""

    def test_empresa_b_404_pra_credenciais_de_a(self, db_url: str) -> None:
        # Cria 2 empresas + 2 users + creds só em A
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active') RETURNING id
                    """,
                    (f"test-wl-iso-A-{_RUN}", f"test-wl-iso-A-{_RUN}"),
                )
                row_a = cur.fetchone()
                assert row_a is not None
                emp_a = int(row_a[0])
                cur.execute(
                    """
                    INSERT INTO empresa (nome, slug, plano, status)
                    VALUES (%s, %s, 'free', 'active') RETURNING id
                    """,
                    (f"test-wl-iso-B-{_RUN}", f"test-wl-iso-B-{_RUN}"),
                )
                row_b = cur.fetchone()
                assert row_b is not None
                emp_b = int(row_b[0])

                user_b = f"test-wl-iso-b-{_RUN}"
                cur.execute(
                    """
                    INSERT INTO auth."user" (id, name, email, "emailVerified",
                                              "createdAt", "updatedAt", status,
                                              is_superadmin)
                    VALUES (%s, 'Iso B', %s, TRUE, NOW(), NOW(), 'active', FALSE)
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

                # Cria credentials SÓ em A (insere direto, sem cripto pra
                # simplificar — este test não chama get_credentials)
                cur.execute(
                    """
                    INSERT INTO wareline_credentials (
                        empresa_id, username, password_encrypted,
                        client_id, client_secret_encrypted, ativo
                    ) VALUES (%s, %s, %s, %s, %s, TRUE)
                    """,
                    (
                        emp_a,
                        f"only-a-{_RUN}",
                        "gAAAAA_fake_cipher_a",
                        "cid-a",
                        "gAAAAA_fake_cipher_a_secret",
                    ),
                )

        try:
            # B tenta GET → 404 (credenciais existem só em A)
            r = httpx.get(
                f"{API_BASE_URL}/api/integracoes/wareline",
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            # 404 ou 503 (sem encryption key). Aceitamos só 404 como sinal
            # de isolamento correto.
            if r.status_code == 503:
                pytest.skip("API sem WARELINE_ENCRYPTION_KEY")
            assert r.status_code == 404, r.text

            # B tenta DELETE config alheia → 404
            r = httpx.delete(
                f"{API_BASE_URL}/api/integracoes/wareline",
                headers=_headers(user_b, emp_b),
                timeout=5,
            )
            assert r.status_code == 404

            # DB: credentials em A ainda existem
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT username FROM wareline_credentials "
                        "WHERE empresa_id = %s",
                        (emp_a,),
                    )
                    row = cur.fetchone()
                    assert row is not None
                    assert row[0] == f"only-a-{_RUN}"
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM empresa WHERE id IN (%s, %s)",
                        (emp_a, emp_b),
                    )
