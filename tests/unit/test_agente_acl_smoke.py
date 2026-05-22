"""Sprint C — smoke tests dos endpoints de ACL por agente."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeAgenteAcl:
    def test_list_perfis_sem_auth_401(self) -> None:
        resp = _client().get("/api/v1/agentes/qualquer/perfis")
        assert resp.status_code == 401, resp.text

    def test_put_perfis_sem_auth_401(self) -> None:
        resp = _client().put(
            "/api/v1/agentes/qualquer/perfis",
            json={"entries": []},
        )
        assert resp.status_code == 401, resp.text
