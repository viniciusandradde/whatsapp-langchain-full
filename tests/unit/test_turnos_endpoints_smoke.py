"""Sprint U (Fase 2) — smoke tests pros endpoints /api/turnos.

Sem service token o gateway nega tudo (401). Roda em CI (sem DB).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeTurnosEndpoints:
    def test_list_sem_auth_401(self) -> None:
        assert _client().get("/api/turnos").status_code == 401

    def test_create_sem_auth_401(self) -> None:
        r = _client().post("/api/turnos", json={"nome": "Comercial"})
        assert r.status_code == 401

    def test_get_sem_auth_401(self) -> None:
        assert _client().get("/api/turnos/1").status_code == 401

    def test_put_sem_auth_401(self) -> None:
        r = _client().put("/api/turnos/1", json={"nome": "x"})
        assert r.status_code == 401

    def test_delete_sem_auth_401(self) -> None:
        assert _client().delete("/api/turnos/1").status_code == 401

    def test_list_users_sem_auth_401(self) -> None:
        assert _client().get("/api/turnos/1/users").status_code == 401

    def test_set_users_sem_auth_401(self) -> None:
        r = _client().put("/api/turnos/1/users", json={"user_ids": []})
        assert r.status_code == 401
