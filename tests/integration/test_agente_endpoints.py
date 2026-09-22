"""Smoke tests dos endpoints de agente_ia (Sub-fase A.5).

Valida que rotas existem + auth required. Não testa CRUD completo
(precisaria fixture DB + empresa + permissões — vem em iteração futura).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_agentes_sem_auth_retorna_401():
    """Endpoint existe e bloqueia request sem service token."""
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/agentes")
        assert resp.status_code == 401


def test_post_agente_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/agentes",
            json={
                "slug": "teste",
                "nome": "Teste",
                "template_catalog": "vsa_tech",
            },
        )
        assert resp.status_code == 401


def test_put_agente_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.put("/api/v1/agentes/algum-slug", json={"nome": "X"})
        assert resp.status_code == 401


def test_delete_agente_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.delete("/api/v1/agentes/algum-slug")
        assert resp.status_code == 401


def test_set_default_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.post("/api/v1/agentes/algum-slug/set-default")
        assert resp.status_code == 401


def test_openapi_lista_endpoints_agentes():
    """Confirma que os 5 endpoints estão registrados (regression)."""
    from whatsapp_langchain.server.main import app

    paths = app.openapi().get("paths", {})
    assert "/api/v1/agentes" in paths
    assert "/api/v1/agentes/{slug}" in paths
    assert "/api/v1/agentes/{slug}/set-default" in paths
    # Métodos esperados
    assert "get" in paths["/api/v1/agentes"]
    assert "post" in paths["/api/v1/agentes"]
    assert "put" in paths["/api/v1/agentes/{slug}"]
    assert "delete" in paths["/api/v1/agentes/{slug}"]


# ---------------------------------------------------------------------------
# E2E (stack real): o modelo que a API mostra é o que o worker usa
# ---------------------------------------------------------------------------
#
# Incidente de 22/09/2026: o card de /agents lia `agente_ia.modelo` (coluna
# legada, parada desde 22/08) e dizia que o agente da VSA rodava
# gemini-2.5-flash-lite enquanto o worker usava o que o seletor gravou em
# `modelo_provedor/modelo_nome`. Agora a API expõe `modelo_efetivo` (a regra do
# runtime) e o PUT mantém a legada sincronizada.
#
# Rodar: DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
#        INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
#        uv run pytest tests/integration/test_agente_endpoints.py::TestE2EModeloEfetivo -m docker_demo -v

import uuid

import httpx
import psycopg
import pytest

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

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
            conn.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Verifique DATABASE_URL")
    return url


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    """Empresa isolada no plano Pro (Free só deixa 1 agente). CASCADE no fim."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO empresa (nome, slug, plano, status) "
            "VALUES (%s, %s, 'pro', 'active') RETURNING id",
            (f"test-agente-modelo-{_RUN}", f"test-agente-modelo-{_RUN}"),
        ).fetchone()
        assert row is not None
        eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    """auth.user + membro admin + perfil Admin com todas as permissões."""
    user_id = f"test-agente-modelo-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status, is_superadmin)
            VALUES (%s, 'Test Modelo', %s, TRUE, NOW(), NOW(), 'active', FALSE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )
        conn.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', TRUE)",
            (empresa_id, user_id),
        )
        row = conn.execute(
            "INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system) "
            "VALUES (%s, 'Admin', 'Acesso total', TRUE) "
            "ON CONFLICT (empresa_id, nome) DO NOTHING RETURNING id",
            (empresa_id,),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id FROM perfil_acesso WHERE empresa_id = %s AND nome = 'Admin'",
                (empresa_id,),
            ).fetchone()
        assert row is not None
        perfil_id = int(row[0])
        conn.execute(
            "INSERT INTO perfil_permissao (perfil_id, permissao_codigo) "
            "SELECT %s, codigo FROM permissao ON CONFLICT DO NOTHING",
            (perfil_id,),
        )
        conn.execute(
            "INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id, assigned_by_user_id) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (user_id, perfil_id, empresa_id, user_id),
        )
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.mark.docker_demo
class TestE2EModeloEfetivo:
    slug = f"modelo-{_RUN}"

    def _put(self, h: dict[str, str], body: dict) -> dict:
        r = httpx.put(
            f"{API_BASE_URL}/api/v1/agentes/{self.slug}",
            headers=h,
            json=body,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        return r.json()

    def _legada_no_banco(self, db_url: str, empresa_id: int) -> str | None:
        with psycopg.connect(db_url) as conn:
            row = conn.execute(
                "SELECT modelo FROM agente_ia WHERE empresa_id = %s AND slug = %s",
                (empresa_id, self.slug),
            ).fetchone()
        assert row is not None
        return row[0]

    def test_01_agente_novo_nasce_sem_modelo_efetivo(self, admin_user_id, empresa_id):
        h = _headers(admin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/agentes",
            headers=h,
            json={
                "slug": self.slug,
                "nome": "Modelo E2E",
                "template_catalog": "vsa_tech",
            },
            timeout=15,
        )
        assert r.status_code == 201, r.text
        assert r.json()["modelo_efetivo"] is None
        assert r.json()["modelo"] is None

    def test_02_put_provedor_e_nome_sincroniza_a_legada(
        self, admin_user_id, empresa_id, db_url
    ):
        h = _headers(admin_user_id, empresa_id)
        out = self._put(
            h, {"modelo_provedor": "google", "modelo_nome": "gemini-2.5-flash-lite"}
        )
        assert out["modelo_efetivo"] == "google/gemini-2.5-flash-lite"
        assert out["modelo"] == "google/gemini-2.5-flash-lite"
        assert (
            self._legada_no_banco(db_url, empresa_id) == "google/gemini-2.5-flash-lite"
        )

    def test_03_put_so_o_nome_reusa_o_provedor_gravado(
        self, admin_user_id, empresa_id, db_url
    ):
        h = _headers(admin_user_id, empresa_id)
        out = self._put(h, {"modelo_nome": "gemini-2.5-flash"})
        assert out["modelo_efetivo"] == "google/gemini-2.5-flash"
        assert self._legada_no_banco(db_url, empresa_id) == "google/gemini-2.5-flash"

    def test_04_lista_e_detalhe_expoem_o_mesmo_modelo_efetivo(
        self, admin_user_id, empresa_id
    ):
        h = _headers(admin_user_id, empresa_id)
        lista = httpx.get(f"{API_BASE_URL}/api/v1/agentes", headers=h, timeout=15)
        assert lista.status_code == 200, lista.text
        item = next(a for a in lista.json()["items"] if a["slug"] == self.slug)
        detalhe = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.slug}", headers=h, timeout=15
        )
        assert detalhe.status_code == 200, detalhe.text
        assert (
            item["modelo_efetivo"]
            == detalhe.json()["modelo_efetivo"]
            == "google/gemini-2.5-flash"
        )

    def test_05_limpar_provedor_e_nome_cai_na_legada_sincronizada(
        self, admin_user_id, empresa_id
    ):
        h = _headers(admin_user_id, empresa_id)
        out = self._put(h, {"modelo_provedor": None, "modelo_nome": None})
        # Sem o par, o runtime usa a legada — que ficou igual ao último modelo.
        assert out["modelo_provedor"] is None and out["modelo_nome"] is None
        assert out["modelo_efetivo"] == "google/gemini-2.5-flash"
