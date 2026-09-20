"""Smoke + E2E dos endpoints do Disparador (Task 2: verify_api_key + /status).

Smoke (sem DB): valida que /api/disparador/status existe e exige API key.
E2E (stack rodando): insere uma empresa_api_key real e valida que a chave
autentica, resolve a empresa correta e isola tenants.

Smoke:
    uv run pytest tests/integration/test_disparador_endpoints.py::TestSmoke -v

E2E (precisa make up + migração 118 aplicada):
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    uv run pytest tests/integration/test_disparador_endpoints.py::TestE2E -v -s
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.shared.api_key import generate_api_key

from .helpers import API_BASE_URL, get_db_url

# ============================================================================
# Smoke (TestClient — sem DB real, roda em CI)
# ============================================================================


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    """Rota registrada e exigindo API key (401 sem credencial)."""

    def test_status_sem_auth_401(self) -> None:
        resp = _client().get("/api/disparador/status")
        assert resp.status_code == 401, resp.text

    def test_status_bearer_vazio_401(self) -> None:
        # Header sem token → ainda 401 (não 404), prova que a rota existe.
        resp = _client().get(
            "/api/disparador/status", headers={"Authorization": "Basic xxx"}
        )
        assert resp.status_code == 401, resp.text

    def test_api_keys_list_sem_auth_401(self) -> None:
        assert _client().get("/api/disparador/api-keys").status_code == 401

    def test_api_keys_create_sem_auth_401(self) -> None:
        r = _client().post("/api/disparador/api-keys", json={"label": "x"})
        assert r.status_code == 401, r.text

    def test_api_keys_revoke_sem_auth_401(self) -> None:
        assert _client().post("/api/disparador/api-keys/1/revoke").status_code == 401


# ============================================================================
# E2E (stack real — precisa make up + migração 118)
# ============================================================================

_RUN = uuid.uuid4().hex[:8]


@pytest.mark.docker_demo
class TestE2E:
    """Insere chave real e valida autenticação + binding de empresa."""

    @pytest.fixture(scope="class")
    def empresa_a(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug, plano) VALUES (%s, %s, 'pro') RETURNING id",
                (f"disp-a-{_RUN}", f"disp-a-{_RUN}"),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    @pytest.fixture(scope="class")
    def empresa_b(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug, plano) VALUES (%s, %s, 'pro') RETURNING id",
                (f"disp-b-{_RUN}", f"disp-b-{_RUN}"),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    def _insert_key(self, empresa_id: int) -> str:
        """Cria uma chave ativa pra empresa e devolve o segredo em claro."""
        plain, prefix, key_hash = generate_api_key(empresa_id)
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            conn.execute(
                """
                INSERT INTO empresa_api_key
                    (empresa_id, label, key_prefix, key_hash, scopes)
                VALUES (%s, %s, %s, %s, ARRAY['capture','dispatch'])
                """,
                # label único por chave (UNIQUE empresa_id,label) — usa o prefixo
                (empresa_id, f"e2e-{prefix}", prefix, key_hash),
            )
        return plain

    def test_01_chave_valida_autentica_e_resolve_empresa(self, empresa_a) -> None:
        key = self._insert_key(empresa_a)
        r = httpx.get(
            f"{API_BASE_URL}/api/disparador/status",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["empresa_id"] == empresa_a, r.text
        assert "capture" in body["scopes"]

    def test_02_chave_invalida_401(self) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/disparador/status",
            headers={"Authorization": "Bearer nxs_1_" + "0" * 32},
            timeout=10,
        )
        assert r.status_code == 401, r.text

    def test_03_chave_revogada_401(self, empresa_a) -> None:
        key = self._insert_key(empresa_a)
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            conn.execute(
                "UPDATE empresa_api_key SET revoked_at = NOW() WHERE key_prefix = %s",
                (key.rsplit("_", 1)[0] + "_" + key.rsplit("_", 1)[1][:8],),
            )
        r = httpx.get(
            f"{API_BASE_URL}/api/disparador/status",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
        assert r.status_code == 401, r.text

    def test_04_binding_empresa_correto(self, empresa_b) -> None:
        # Chave da empresa B resolve a empresa B (e nunca a A).
        key = self._insert_key(empresa_b)
        r = httpx.get(
            f"{API_BASE_URL}/api/disparador/status",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["empresa_id"] == empresa_b


@pytest.mark.docker_demo
class TestApiKeysCrud:
    """CRUD via camada shared: segredo só na criação, lista sem expor, revoga."""

    @pytest.fixture(scope="class")
    def empresa(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug, plano) VALUES (%s, %s, 'pro') RETURNING id",
                (f"akcrud-{_RUN}", f"akcrud-{_RUN}"),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    async def test_create_list_revoke(self, empresa) -> None:
        from whatsapp_langchain.shared import api_key as ak
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        plain, meta = await ak.create_api_key(
            pool, empresa, label=f"chrome-{_RUN}", scopes=["capture", "dispatch"]
        )
        assert plain.startswith(f"nxs_{empresa}_")
        assert meta["scopes"] == ["capture", "dispatch"]

        # a chave resolve e autentica
        ctx = await ak.resolve_api_key(pool, plain)
        assert ctx is not None and ctx.empresa_id == empresa

        # listagem não expõe segredo nem hash
        itens = await ak.list_api_keys(pool, empresa)
        assert any(i["id"] == meta["id"] for i in itens)
        assert all("key_hash" not in i and "key" not in i for i in itens)

        # revoga → resolve passa a falhar
        assert await ak.revoke_api_key(pool, empresa, meta["id"]) is True
        assert await ak.resolve_api_key(pool, plain) is None
        # revogar de novo = no-op (já revogada)
        assert await ak.revoke_api_key(pool, empresa, meta["id"]) is False
