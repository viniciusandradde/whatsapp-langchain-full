"""Smoke tests dos endpoints LGPD (rota admin)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeLGPD:
    def test_get_eventos_sem_auth_401(self) -> None:
        assert _client().get("/api/lgpd/eventos").status_code == 401

    def test_get_eventos_com_filtros_sem_auth_401(self) -> None:
        resp = _client().get("/api/lgpd/eventos?event_type=cpf_collected&limit=10")
        assert resp.status_code == 401

    def test_get_eventos_tipos_sem_auth_401(self) -> None:
        assert _client().get("/api/lgpd/eventos/tipos").status_code == 401
