"""Sprint A.2 — smoke tests do CRUD de empresa.

Garante que endpoints exigem auth (regressão do bug de 2026-05-22
onde POST /api/empresas dava 500 por RLS bloquear empresa_membro).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeEmpresaCrud:
    def test_post_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/empresas",
            json={"nome": "Acme Inc", "slug": "acme", "plano": "free"},
        )
        assert resp.status_code == 401, resp.text

    def test_get_list_sem_auth_401(self) -> None:
        # GET /api/empresas requer service_token + X-User-Id
        resp = _client().get("/api/empresas")
        assert resp.status_code == 401, resp.text

    def test_put_sem_auth_401(self) -> None:
        resp = _client().put("/api/empresas/1", json={"nome": "x"})
        assert resp.status_code == 401, resp.text
