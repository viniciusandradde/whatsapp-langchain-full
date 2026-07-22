"""Smoke + E2E dos endpoints da whitelist de números (mig 133).

Smoke (sem DB): valida que rotas existem e exigem service token.
E2E (com stack rodando): criar → listar → duplicado 409 → inválido 400 →
PATCH nome → DELETE, mais isolamento entre empresas (RLS).

Para rodar só smoke:
    uv run pytest tests/integration/test_whitelist_endpoints.py::TestSmoke -v

Para rodar E2E (precisa make up + migrações aplicadas):
    uv run pytest tests/integration/test_whitelist_endpoints.py -v -s
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
    """Verifica que as rotas estão registradas e exigem auth."""

    def test_get_whitelist_sem_auth_401(self) -> None:
        resp = _client().get("/api/whitelist")
        assert resp.status_code == 401

    def test_post_whitelist_sem_auth_401(self) -> None:
        resp = _client().post("/api/whitelist", json={"telefone": "+5511999999999"})
        assert resp.status_code == 401

    def test_patch_whitelist_sem_auth_401(self) -> None:
        resp = _client().patch("/api/whitelist/1", json={"nome": "X"})
        assert resp.status_code == 401

    def test_delete_whitelist_sem_auth_401(self) -> None:
        resp = _client().delete("/api/whitelist/1")
        assert resp.status_code == 401


# ============================================================================
# E2E (stack real — precisa make up)
# ============================================================================


pytestmark_e2e = pytest.mark.docker_demo

# Sufixo curto pra isolar dados deste run de testes paralelos/repetidos
_RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def db_url() -> str:
    """Skip se stack não tá rodando."""
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
        pytest.skip("DB não acessível. Verifique DATABASE_URL")
    return url


def _cria_empresa(db_url: str, slug: str) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status)
                VALUES (%s, %s, 'free', 'active')
                RETURNING id
                """,
                (slug, slug),
            )
            row = cur.fetchone()
            assert row is not None
            return int(row[0])


def _deleta_empresa(db_url: str, empresa_id: int) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))


def _cria_admin(db_url: str, empresa_id: int, user_id: str) -> None:
    """auth.user + membership admin + perfil Admin com todas as perms."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status,
                                          is_superadmin)
                VALUES (%s, 'Test WL User', %s, TRUE, NOW(), NOW(),
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
                    "SELECT id FROM perfil_acesso "
                    "WHERE empresa_id = %s AND nome = 'Admin'",
                    (empresa_id,),
                )
                row = cur.fetchone()
            assert row is not None
            perfil_id = int(row[0])
            cur.execute(
                """
                INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
                SELECT %s, codigo FROM permissao
                ON CONFLICT DO NOTHING
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


def _deleta_user(db_url: str, user_id: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    eid = _cria_empresa(db_url, f"test-wl-{_RUN}")
    yield eid
    _deleta_empresa(db_url, eid)


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    user_id = f"test-wl-user-{_RUN}"
    _cria_admin(db_url, empresa_id, user_id)
    yield user_id
    _deleta_user(db_url, user_id)


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.mark.docker_demo
class TestE2E:
    """Happy path completo do CRUD da whitelist."""

    def test_fluxo_completo(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        telefone = f"+55119{_RUN[:8]}"

        # 1. POST cria número
        r = httpx.post(
            f"{API_BASE_URL}/api/whitelist",
            headers=h,
            json={"telefone": telefone, "nome": "Mãe"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        criado = r.json()
        assert criado["telefone"] == telefone
        assert criado["nome"] == "Mãe"
        wl_id = criado["id"]

        # 2. GET lista contém o número
        r = httpx.get(f"{API_BASE_URL}/api/whitelist", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        telefones = [i["telefone"] for i in r.json()["items"]]
        assert telefone in telefones

        # 3. POST duplicado → 409
        r = httpx.post(
            f"{API_BASE_URL}/api/whitelist",
            headers=h,
            json={"telefone": telefone},
            timeout=10,
        )
        assert r.status_code == 409, r.text

        # 4. POST telefone inválido → 400
        r = httpx.post(
            f"{API_BASE_URL}/api/whitelist",
            headers=h,
            json={"telefone": "abcdefgh"},
            timeout=10,
        )
        assert r.status_code == 400, r.text

        # 5. PATCH nome → refletido
        r = httpx.patch(
            f"{API_BASE_URL}/api/whitelist/{wl_id}",
            headers=h,
            json={"nome": "Mainha"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["nome"] == "Mainha"

        # 6. DELETE → ok
        r = httpx.delete(f"{API_BASE_URL}/api/whitelist/{wl_id}", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        # 7. GET não contém mais
        r = httpx.get(f"{API_BASE_URL}/api/whitelist", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        telefones = [i["telefone"] for i in r.json()["items"]]
        assert telefone not in telefones


@pytest.mark.docker_demo
class TestE2EIsolamento:
    """RLS: empresa 2 não enxerga nem mexe na whitelist da empresa 1."""

    @pytest.fixture(scope="class")
    def empresa2(self, db_url: str):
        eid = _cria_empresa(db_url, f"test-wl2-{_RUN}")
        user_id = f"test-wl2-user-{_RUN}"
        _cria_admin(db_url, eid, user_id)
        yield eid, user_id
        _deleta_user(db_url, user_id)
        _deleta_empresa(db_url, eid)

    def test_cross_empresa_invisivel_e_404(
        self,
        db_url: str,
        empresa_id: int,
        admin_user_id: str,
        empresa2,
    ) -> None:
        e2_id, e2_user = empresa2
        h1 = _headers(admin_user_id, empresa_id)
        h2 = _headers(e2_user, e2_id)
        telefone = f"+55118{_RUN[:8]}"

        # Empresa 1 cadastra
        r = httpx.post(
            f"{API_BASE_URL}/api/whitelist",
            headers=h1,
            json={"telefone": telefone, "nome": "Só da empresa 1"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        wl_id = r.json()["id"]

        # Empresa 2 não vê
        r = httpx.get(f"{API_BASE_URL}/api/whitelist", headers=h2, timeout=10)
        assert r.status_code == 200, r.text
        telefones = [i["telefone"] for i in r.json()["items"]]
        assert telefone not in telefones

        # Empresa 2 não deleta (404)
        r = httpx.delete(
            f"{API_BASE_URL}/api/whitelist/{wl_id}", headers=h2, timeout=10
        )
        assert r.status_code == 404, r.text

        # Cleanup pela empresa 1
        r = httpx.delete(
            f"{API_BASE_URL}/api/whitelist/{wl_id}", headers=h1, timeout=10
        )
        assert r.status_code == 200, r.text
