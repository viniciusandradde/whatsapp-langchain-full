"""Smoke tests dos endpoints de agente_ia (Sub-fase A.5).

Valida que rotas existem + auth required. Não testa CRUD completo
(precisaria fixture DB + empresa + permissões — vem em iteração futura).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_agentes_sem_auth_retorna_401():
    """Endpoint existe e bloqueia request sem service token."""
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/agentes")
        assert resp.status_code == 401


def test_post_agente_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/agentes",
            json={
                "slug": "teste",
                "nome": "Teste",
                "template_catalog": "vsa_tech",
            },
        )
        assert resp.status_code == 401


def test_put_agente_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.put("/api/v1/agentes/algum-slug", json={"nome": "X"})
        assert resp.status_code == 401


def test_delete_agente_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.delete("/api/v1/agentes/algum-slug")
        assert resp.status_code == 401


def test_set_default_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.post("/api/v1/agentes/algum-slug/set-default")
        assert resp.status_code == 401


def test_openapi_lista_endpoints_agentes():
    """Confirma que os 5 endpoints estão registrados (regression)."""
    from whatsapp_langchain.server.main import app

    paths = app.openapi().get("paths", {})
    assert "/api/v1/agentes" in paths
    assert "/api/v1/agentes/{slug}" in paths
    assert "/api/v1/agentes/{slug}/set-default" in paths
    # Métodos esperados
    assert "get" in paths["/api/v1/agentes"]
    assert "post" in paths["/api/v1/agentes"]
    assert "put" in paths["/api/v1/agentes/{slug}"]
    assert "delete" in paths["/api/v1/agentes/{slug}"]
