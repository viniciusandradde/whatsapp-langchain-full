"""Smoke dos endpoints do catálogo OpenRouter (mig 178, Saúde de IA F1).

Sem DB: valida que as rotas existem e exigem service token. O E2E real
(sync contra a API do OpenRouter) roda no dev pelo procedimento do contrato —
não em CI, porque depende de rede externa e chave.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    """Rotas registradas + auth obrigatória (401 sem service token)."""

    def test_status_sem_auth_401(self) -> None:
        assert _client().get("/api/openrouter/status").status_code == 401

    def test_provedores_sem_auth_401(self) -> None:
        assert _client().get("/api/openrouter/provedores").status_code == 401

    def test_modelos_sem_auth_401(self) -> None:
        assert _client().get("/api/openrouter/modelos").status_code == 401

    def test_metricas_sem_auth_401(self) -> None:
        r = _client().get("/api/openrouter/modelos/google/gemini-2.5-flash/metricas")
        assert r.status_code == 401

    def test_sync_sem_auth_401(self) -> None:
        assert _client().post("/api/openrouter/sync").status_code == 401

    def test_promover_sem_auth_401(self) -> None:
        r = _client().post(
            "/api/openrouter/modelos/deepseek/deepseek-v3.2/promover",
            json={"tipo": "chat"},
        )
        assert r.status_code == 401

    def test_analise_sem_auth_401(self) -> None:
        r = _client().get("/api/openrouter/modelos/google/gemini-2.5-flash/analise")
        assert r.status_code == 401
