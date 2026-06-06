"""Smoke — endpoints de config global Asaas (superadmin). Sem auth → 401."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeIntegracoesAsaas:
    def test_get_sem_auth_401(self) -> None:
        assert _client().get("/api/admin/integracoes/asaas").status_code == 401

    def test_put_sem_auth_401(self) -> None:
        resp = _client().put(
            "/api/admin/integracoes/asaas", json={"environment": "sandbox"}
        )
        assert resp.status_code == 401, resp.text

    def test_testar_sem_auth_401(self) -> None:
        assert _client().post("/api/admin/integracoes/asaas/testar").status_code == 401
