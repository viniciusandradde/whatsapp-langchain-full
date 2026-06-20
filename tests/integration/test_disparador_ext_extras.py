"""Smoke + E2E dos extras da extensão: telemetria própria + limites por plano.

Endpoints: POST /api/disparador/ext/telemetria (auth API key) e o gating de
plano nos creates (`/ext/campanha`, `/ext/campanha-template`) + plano no /status.

Smoke (CI):
    uv run pytest tests/integration/test_disparador_ext_extras.py::TestSmoke -v

E2E (stack rodando, migrações 118/122/131 aplicadas):
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    API_BASE_URL=http://localhost:8081 \
    uv run pytest tests/integration/test_disparador_ext_extras.py::TestE2E -v -s
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.shared.api_key import generate_api_key

from .helpers import API_BASE_URL, get_db_url


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    """Rotas registradas e exigindo API key (401 sem credencial)."""

    def test_telemetria_sem_auth_401(self) -> None:
        r = _client().post("/api/disparador/ext/telemetria", json={"evento": "ativada"})
        assert r.status_code == 401, r.text

    def test_campanha_sem_auth_401(self) -> None:
        r = _client().post(
            "/api/disparador/ext/campanha",
            json={"nome": "x", "telefones": ["5511999990001"]},
        )
        assert r.status_code == 401, r.text


_RUN = uuid.uuid4().hex[:8]


@pytest.mark.docker_demo
class TestE2E:
    """Telemetria grava; /status traz plano; create acima do cap → 402."""

    @pytest.fixture(scope="class")
    def empresa_free(self):
        """Empresa num plano com cap baixo (features ficam na tabela `plano`,
        lidas via empresa.plano_id por get_plano_info)."""
        db = get_db_url()
        feats = (
            '{"disparador": true, "disparador_media": false, '
            '"disparador_max_contatos": 2}'
        )
        slug = f"free-ext-{_RUN}"
        with psycopg.connect(db, autocommit=True) as conn:
            prow = conn.execute(
                "INSERT INTO plano (nome, slug, features, ativo) "
                "VALUES (%s, %s, %s::jsonb, TRUE) RETURNING id",
                (f"Free Ext {_RUN}", slug, feats),
            ).fetchone()
            assert prow is not None
            plano_id = prow[0]
            # O trigger _sync_empresa_plano_id resolve plano_id a partir do
            # texto `empresa.plano` (slug, ativo=TRUE) — não do plano_id direto.
            row = conn.execute(
                "INSERT INTO empresa (nome, slug, plano) "
                "VALUES (%s, %s, %s) RETURNING id, plano_id",
                (f"extx-{_RUN}", f"extx-{_RUN}", slug),
            ).fetchone()
            assert row is not None and row[1] == plano_id, row
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))
            conn.execute("DELETE FROM plano WHERE id = %s", (plano_id,))

    def _key(self, empresa_id: int, scopes: list[str]) -> str:
        plain, prefix, key_hash = generate_api_key(empresa_id)
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            conn.execute(
                "INSERT INTO empresa_api_key "
                "(empresa_id, label, key_prefix, key_hash, scopes) "
                "VALUES (%s, %s, %s, %s, %s)",
                (empresa_id, f"e2e-{prefix}", prefix, key_hash, scopes),
            )
        return plain

    def _h(self, key: str) -> dict:
        return {"Authorization": f"Bearer {key}"}

    def test_01_telemetria_grava(self, empresa_free) -> None:
        key = self._key(empresa_free, ["capture", "dispatch"])
        r = httpx.post(
            f"{API_BASE_URL}/api/disparador/ext/telemetria",
            headers=self._h(key),
            json={"evento": "ativada", "meta": {"v": "0.2.0"}},
            timeout=10,
        )
        assert r.status_code == 204, r.text
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            n = conn.execute(
                "SELECT count(*) FROM disparador_ext_evento "
                "WHERE empresa_id = %s AND evento = 'ativada'",
                (empresa_free,),
            ).fetchone()
        assert n is not None and n[0] >= 1

    def test_02_telemetria_evento_invalido_descartado(self, empresa_free) -> None:
        key = self._key(empresa_free, ["capture"])
        r = httpx.post(
            f"{API_BASE_URL}/api/disparador/ext/telemetria",
            headers=self._h(key),
            json={"evento": "hackerman"},
            timeout=10,
        )
        # 204 (descartado silenciosamente), não grava
        assert r.status_code == 204, r.text
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            n = conn.execute(
                "SELECT count(*) FROM disparador_ext_evento "
                "WHERE empresa_id = %s AND evento = 'hackerman'",
                (empresa_free,),
            ).fetchone()
        assert n is not None and n[0] == 0

    def test_03_status_traz_plano(self, empresa_free) -> None:
        key = self._key(empresa_free, ["dispatch"])
        r = httpx.get(
            f"{API_BASE_URL}/api/disparador/status",
            headers=self._h(key),
            timeout=10,
        )
        assert r.status_code == 200, r.text
        plano = r.json().get("plano") or {}
        assert plano.get("max_contatos") == 2, r.text
        assert plano.get("midia") is False

    def test_04_create_acima_do_cap_402(self, empresa_free) -> None:
        key = self._key(empresa_free, ["dispatch"])
        r = httpx.post(
            f"{API_BASE_URL}/api/disparador/ext/campanha",
            headers=self._h(key),
            json={
                "nome": f"excede {_RUN}",
                "telefones": ["5511999990001", "5511999990002", "5511999990003"],
            },
            timeout=15,
        )
        assert r.status_code == 402, r.text
        assert "contatos por disparo" in r.text

    def test_05_create_dentro_do_cap_ok(self, empresa_free) -> None:
        key = self._key(empresa_free, ["dispatch"])
        r = httpx.post(
            f"{API_BASE_URL}/api/disparador/ext/campanha",
            headers=self._h(key),
            json={
                "nome": f"ok {_RUN}",
                "telefones": ["5511999990001", "5511999990002"],
            },
            timeout=15,
        )
        assert r.status_code == 201, r.text
        assert r.json()["total"] >= 1
