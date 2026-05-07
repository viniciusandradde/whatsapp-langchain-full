"""Smoke tests dos endpoints de catálogo (modelo_llm + mcp_server).

Valida rotas registradas + auth required.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_modelos_llm_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/modelos-llm")
        assert resp.status_code == 401


def test_post_modelo_llm_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/modelos-llm",
            json={"provedor": "openai", "nome": "gpt-test", "tipo": "chat"},
        )
        assert resp.status_code == 401


def test_get_mcp_servers_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/mcp-servers")
        assert resp.status_code == 401


def test_post_mcp_server_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/mcp-servers",
            json={"nome": "test", "tipo_conexao": "stdio"},
        )
        assert resp.status_code == 401


def test_openapi_lista_endpoints_catalogo():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        paths = resp.json().get("paths", {})
        assert "/api/v1/modelos-llm" in paths
        assert "/api/v1/modelos-llm/{modelo_id}" in paths
        assert "/api/v1/mcp-servers" in paths
        assert "/api/v1/mcp-servers/{mcp_id}" in paths
