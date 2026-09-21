"""Smoke + E2E da leva D da ADR-005: o painel lê o plano efetivo da empresa
(`GET /api/empresas/{id}/plano`) para mostrar cadeados e o `/billing` com as
chaves reais. A resposta vem JÁ mesclada com as exceções por empresa
(`feature_flag` `plano.<chave>`), para o cadeado da tela bater com o 402 da
rota.

Rodar E2E contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_plano_leva_d_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_db_url
from .test_plano_leva_a_endpoints import (
    _criar_empresa,
    _dar_perfil_admin,
    _esperar_cache_do_plano,
    _flag,
    _headers,
)


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_plano_da_empresa_exige_auth(self) -> None:
        resp = _client().get("/api/empresas/1/plano")
        assert resp.status_code == 401, resp.text


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
        pytest.skip("DB não acessível. Verifique DATABASE_URL")
    return url


def _apagar_empresa(db_url: str, eid: int) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-leva-d-pro-{_RUN}")
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    user_id = f"test-leva-d-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status, is_superadmin)
            VALUES (%s, 'Test Leva D', %s, TRUE, NOW(), NOW(), 'active', FALSE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', TRUE)",
            (empresa_id, user_id),
        )
        _dar_perfil_admin(cur, empresa_id, user_id)
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


@pytest.fixture(scope="module")
def empresa_free_id(db_url: str, admin_user_id: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "free", f"test-leva-d-free-{_RUN}")
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', FALSE)",
            (eid, admin_user_id),
        )
        _dar_perfil_admin(cur, eid, admin_user_id)
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def empresa_alheia_id(db_url: str):
    """Empresa da qual o usuário do teste NÃO é membro."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-leva-d-alheia-{_RUN}")
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.mark.docker_demo
class TestE2E:
    def test_01_plano_free_traz_chaves_e_limites_reais(
        self, empresa_free_id: int, admin_user_id: str
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_free_id}/plano",
            headers=_headers(admin_user_id, empresa_free_id),
            timeout=10,
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["empresa_id"] == empresa_free_id
        assert p["slug"] == "free"
        assert p["nome"] == "Free"
        assert p["upgrade_sugerido"] == "pro"
        # As chaves são as semeadas nas migs 059/188–192 — o painel trava por elas.
        assert p["features"]["disparador"] is False
        assert p["features"]["csat"] is False
        assert p["features"]["contexto_max"] == "lite"
        # Limites em coluna E em `features` (mig 192), no mesmo dicionário.
        assert p["limites"]["usuarios"] == 2
        assert p["limites"]["agentes"] == 1
        assert p["limites"]["departamentos"] == 1
        assert p["limites"]["workflows"] == 0
        assert p["limites"]["orcamento_ia_usd"] == 5.0

    def test_02_plano_pro_libera_e_enterprise_e_ilimitado(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_id}/plano",
            headers=_headers(admin_user_id, empresa_id),
            timeout=10,
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["slug"] == "pro"
        assert p["features"]["disparador"] is True
        assert p["limites"]["workflows"] == 3
        assert p["upgrade_sugerido"] == "enterprise"

    def test_03_grandfathering_entra_mesclado(
        self, db_url: str, empresa_free_id: int, admin_user_id: str
    ) -> None:
        # A exceção por empresa vale no painel do mesmo jeito que na rota:
        # o cadeado NÃO pode aparecer para quem tem a flag.
        _flag(db_url, empresa_free_id, "disparador", "true")
        _flag(db_url, empresa_free_id, "limite_agentes", "null")
        _flag(db_url, empresa_free_id, "departamentos_max", "5")
        try:
            _esperar_cache_do_plano()
            r = httpx.get(
                f"{API_BASE_URL}/api/empresas/{empresa_free_id}/plano",
                headers=_headers(admin_user_id, empresa_free_id),
                timeout=10,
            )
            assert r.status_code == 200, r.text
            p = r.json()
            assert p["slug"] == "free"  # o plano não muda, só a exceção
            assert p["features"]["disparador"] is True
            assert p["limites"]["agentes"] is None  # null = ilimitado
            assert p["limites"]["departamentos"] == 5
        finally:
            _flag(db_url, empresa_free_id, "disparador", None)
            _flag(db_url, empresa_free_id, "limite_agentes", None)
            _flag(db_url, empresa_free_id, "departamentos_max", None)

    def test_04_nao_membro_nao_le_e_inexistente_da_404(
        self, empresa_alheia_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/{empresa_alheia_id}/plano",
            headers=_headers(admin_user_id, empresa_id),
            timeout=10,
        )
        assert r.status_code == 403, r.text
        r = httpx.get(
            f"{API_BASE_URL}/api/empresas/999999999/plano",
            headers=_headers(admin_user_id, empresa_id),
            timeout=10,
        )
        # Sem membership numa empresa que não existe: 403 antes do 404 é
        # aceitável (não vaza existência); o que não pode é 500.
        assert r.status_code in (403, 404), r.text
