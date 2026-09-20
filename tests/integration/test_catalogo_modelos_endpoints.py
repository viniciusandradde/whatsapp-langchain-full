"""Smoke + E2E do catálogo completo de modelos (ADR-004, mig 187).

Smoke (sem DB): a rota existe, exige service token e vem ANTES de
`/{modelo_id}` (senão `/catalogo` cairia em 422).
E2E (stack rodando): operador com `agente.config` lê o catálogo inteiro com
os 15 campos do card; salvar `contexto_tamanho` no agente zera
`janela_memoria`; tier inválido é 422.

Rodar E2E contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_catalogo_modelos_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

CHAVES_ITEM = {
    "slug",
    "provedor",
    "provedor_nome",
    "nome",
    "descricao",
    "context_length",
    "visao",
    "pensamento",
    "tools",
    "preco_prompt",
    "preco_completion",
    "novo",
    "tendencia",
    "promo",
    "curado",
}

# ============================================================================
# Smoke (TestClient — sem DB real, roda em CI)
# ============================================================================


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_catalogo_sem_auth_401(self) -> None:
        resp = _client().get("/api/v1/modelos-llm/catalogo")
        assert resp.status_code == 401

    def test_catalogo_declarado_antes_do_path_param(self) -> None:
        """`/{modelo_id}` é int: se casasse primeiro, `/catalogo` seria 422."""
        from whatsapp_langchain.server.main import app

        caminhos = [getattr(r, "path", "") for r in app.routes]
        assert caminhos.index("/api/v1/modelos-llm/catalogo") < caminhos.index(
            "/api/v1/modelos-llm/{modelo_id}"
        )


# ============================================================================
# E2E (stack real — precisa make up)
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
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Verifique DATABASE_URL")
    return url


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO empresa (nome, slug, plano, status) "
            "VALUES (%s, %s, 'free', 'active') RETURNING id",
            (f"test-catalogo-{_RUN}", f"test-catalogo-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    """User comum (não superadmin) com perfil Admin da empresa — tem `agente.config`."""
    user_id = f"test-catalogo-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status, is_superadmin)
            VALUES (%s, 'Test Catalogo', %s, TRUE, NOW(), NOW(), 'active', FALSE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', TRUE)",
            (empresa_id, user_id),
        )
        cur.execute(
            """
            INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system)
            VALUES (%s, 'Admin', 'Acesso total', TRUE)
            ON CONFLICT (empresa_id, nome) DO NOTHING
            """,
            (empresa_id,),
        )
        cur.execute(
            "SELECT id FROM perfil_acesso WHERE empresa_id = %s AND nome = 'Admin'",
            (empresa_id,),
        )
        row = cur.fetchone()
        assert row is not None
        perfil_id = int(row[0])
        cur.execute(
            "INSERT INTO perfil_permissao (perfil_id, permissao_codigo) "
            "SELECT %s, codigo FROM permissao ON CONFLICT DO NOTHING",
            (perfil_id,),
        )
        cur.execute(
            """
            INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id, assigned_by_user_id)
            VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
            """,
            (user_id, perfil_id, empresa_id, user_id),
        )
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.mark.docker_demo
class TestE2E:
    def test_01_catalogo_completo_com_os_15_campos(
        self, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/modelos-llm/catalogo", headers=h, timeout=15
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert "gerado_em" in corpo
        itens = corpo["itens"]
        assert len(itens) >= 1, "catálogo vazio — o sync do worker rodou?"
        for item in itens:
            assert set(item) == CHAVES_ITEM, item
            assert isinstance(item["visao"], bool)
            assert item["provedor"] == item["slug"].split("/")[0]
        # O dev tem o curado global (gemini/gpt) sincronizado no OpenRouter.
        assert any(i["curado"] for i in itens), "nenhum curado casou com o catálogo"
        assert all(i["promo"] for i in itens if i["slug"].endswith(":free"))

    def test_02_salvar_tier_zera_janela_memoria(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        slug = f"cat-{_RUN}"
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/agentes",
            headers=h,
            json={"slug": slug, "nome": "Catálogo", "template_catalog": "agente"},
            timeout=15,
        )
        assert r.status_code == 201, r.text
        # Agente novo nasce em `lite` (ADR-004) — a coluna não tem DEFAULT.
        assert r.json()["contexto_tamanho"] == "lite"

        r = httpx.put(
            f"{API_BASE_URL}/api/v1/agentes/{slug}",
            headers=h,
            json={"janela_memoria": 12},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["janela_memoria"] == 12

        r = httpx.put(
            f"{API_BASE_URL}/api/v1/agentes/{slug}",
            headers=h,
            json={"contexto_tamanho": "extended"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["contexto_tamanho"] == "extended"
        assert corpo["janela_memoria"] is None, "um só manda: o tier zera a janela"

        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT contexto_tamanho, janela_memoria FROM agente_ia "
                "WHERE empresa_id = %s AND slug = %s",
                (empresa_id, slug),
            )
            assert cur.fetchone() == ("extended", None)

    def test_03_tier_invalido_422(self, empresa_id: int, admin_user_id: str) -> None:
        h = _headers(admin_user_id, empresa_id)
        r = httpx.put(
            f"{API_BASE_URL}/api/v1/agentes/cat-{_RUN}",
            headers=h,
            json={"contexto_tamanho": "gigante"},
            timeout=15,
        )
        assert r.status_code == 422, r.text
