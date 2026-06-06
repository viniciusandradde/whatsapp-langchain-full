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


def _flatten_deps(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _flatten_deps(d)


def test_list_traces_is_empresa_scoped() -> None:
    """Regressão R2: GET /api/traces DEVE depender de get_empresa_context.

    Sem isso o endpoint vazava traces (e telefones embutidos no thread_id) de
    todas as empresas, pois o store Langfuse/LangSmith é global por instância.
    """
    from whatsapp_langchain.server.dependencies import get_empresa_context
    from whatsapp_langchain.server.main import app

    route = next(
        r
        for r in app.routes
        if getattr(r, "path", None) == "/api/traces"
        and "GET" in getattr(r, "methods", set())
    )
    assert get_empresa_context in set(_flatten_deps(route.dependant))
