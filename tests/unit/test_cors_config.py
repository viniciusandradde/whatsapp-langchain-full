"""Verifica configuração de CORS no app FastAPI."""

import importlib

from fastapi.testclient import TestClient


def _build_app(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "x" * 32)
    from whatsapp_langchain.shared import config as config_mod

    importlib.reload(config_mod)
    from whatsapp_langchain.server import main as main_mod

    importlib.reload(main_mod)
    return main_mod.app


def test_cors_allows_listed_origin(monkeypatch):
    app = _build_app(monkeypatch, FRONTEND_ORIGINS="https://app.rhawk.pro")
    client = TestClient(app)
    r = client.options(
        "/health",
        headers={
            "Origin": "https://app.rhawk.pro",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "https://app.rhawk.pro"


def test_cors_rejects_unlisted_origin(monkeypatch):
    app = _build_app(monkeypatch, FRONTEND_ORIGINS="https://app.rhawk.pro")
    client = TestClient(app)
    r = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") is None
