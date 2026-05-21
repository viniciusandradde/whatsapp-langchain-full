"""Smoke tests dos endpoints de cleanup zumbis."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeCleanupZumbis:
    def test_preview_sem_auth_401(self) -> None:
        resp = _client().get("/api/atendimentos/cleanup-zumbis/preview")
        assert resp.status_code == 401

    def test_cleanup_sem_auth_401(self) -> None:
        resp = _client().post("/api/atendimentos/cleanup-zumbis")
        assert resp.status_code == 401

    def test_cleanup_dry_run_sem_auth_401(self) -> None:
        resp = _client().post("/api/atendimentos/cleanup-zumbis?dry_run=true")
        assert resp.status_code == 401
