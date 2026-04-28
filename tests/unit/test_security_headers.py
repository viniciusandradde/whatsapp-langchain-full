"""Cabeçalhos de segurança aplicados a todas as respostas."""

import importlib

from fastapi.testclient import TestClient


def _build_app(monkeypatch, environment="development"):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "x" * 32)
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("VALIDATE_TWILIO_SIGNATURE", "true")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "abc")
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", "https://example.com")
    from whatsapp_langchain.shared import config as config_mod

    importlib.reload(config_mod)
    from whatsapp_langchain.server import main as main_mod

    importlib.reload(main_mod)
    return main_mod.app


def test_security_headers_present_in_dev(monkeypatch):
    monkeypatch.delenv("VALIDATE_TWILIO_SIGNATURE", raising=False)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "x" * 32)
    monkeypatch.setenv("ENVIRONMENT", "development")
    from whatsapp_langchain.shared import config as config_mod

    importlib.reload(config_mod)
    from whatsapp_langchain.server import main as main_mod

    importlib.reload(main_mod)
    client = TestClient(main_mod.app)
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "Strict-Transport-Security" not in r.headers


def test_hsts_only_in_production(monkeypatch):
    app = _build_app(monkeypatch, environment="production")
    client = TestClient(app)
    r = client.get("/health")
    assert "Strict-Transport-Security" in r.headers
    assert "max-age=" in r.headers["Strict-Transport-Security"]
