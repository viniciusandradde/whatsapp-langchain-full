"""Smoke tests pros endpoints /api/traces (observabilidade).

Sem service token o gateway nega tudo (401). Roda em CI (sem DB / sem
provider). Cobre os endpoints novos do provider-switch Langfuse/LangSmith.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeTracesEndpoints:
    def test_list_sem_auth_401(self) -> None:
        assert _client().get("/api/traces").status_code == 401

    def test_config_sem_auth_401(self) -> None:
        assert _client().get("/api/traces/config").status_code == 401

    def test_atendimento_link_sem_auth_401(self) -> None:
        assert _client().get("/api/traces/atendimento/1").status_code == 401
