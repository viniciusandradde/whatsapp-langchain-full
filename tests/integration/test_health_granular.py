"""Smoke tests dos health endpoints granulares (Fase 0)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_db_endpoint(monkeypatch):
    """GET /api/health/db retorna status + latency."""
    # Mock check_db_health pra evitar conexão real em CI
    from whatsapp_langchain.shared import db as db_mod

    async def mock_healthy() -> bool:
        return True

    monkeypatch.setattr(db_mod, "check_db_health", mock_healthy)

    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/api/health/db")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["subsystem"] == "database"
        assert "latency_ms" in body


def test_metrics_endpoint_prometheus_format(monkeypatch):
    """GET /metrics retorna text/plain Prometheus."""
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        # Pelo menos a estrutura # HELP / # TYPE deve aparecer
        assert b"# HELP" in resp.content or b"# TYPE" in resp.content


def test_health_geral_compat(monkeypatch):
    """GET /health (legacy) ainda funciona."""
    from whatsapp_langchain.shared import db as db_mod

    async def mock_healthy() -> bool:
        return True

    monkeypatch.setattr(db_mod, "check_db_health", mock_healthy)

    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
