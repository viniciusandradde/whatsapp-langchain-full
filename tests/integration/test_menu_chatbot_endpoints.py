"""Smoke tests dos endpoints de menu_chatbot (Sub-fase B).

Valida que rotas existem + auth required. Não testa CRUD completo
(precisaria fixture DB + empresa + permissões).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_menus_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/menus")
        assert resp.status_code == 401


def test_post_menu_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/menus",
            json={"nome": "X", "mensagem_boas_vindas": "Olá"},
        )
        assert resp.status_code == 401


def test_get_menu_byid_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/menus/1")
        assert resp.status_code == 401


def test_put_menu_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.put("/api/v1/menus/1", json={"nome": "Y"})
        assert resp.status_code == 401


def test_delete_menu_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.delete("/api/v1/menus/1")
        assert resp.status_code == 401


def test_get_items_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/menus/1/itens")
        assert resp.status_code == 401


def test_post_item_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/menus/1/itens",
            json={"label": "X", "acao_tipo": "submenu"},
        )
        assert resp.status_code == 401


def test_put_item_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.put("/api/v1/menus/1/itens/1", json={"label": "Y"})
        assert resp.status_code == 401


def test_delete_item_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.delete("/api/v1/menus/1/itens/1")
        assert resp.status_code == 401


def test_reorder_sem_auth_retorna_401():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/menus/1/itens/reorder",
            json={"parent_id": None, "ordered_ids": [1, 2]},
        )
        assert resp.status_code == 401


def test_openapi_lista_endpoints_menus():
    from whatsapp_langchain.server.main import app

    with TestClient(app) as client:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        paths = resp.json().get("paths", {})
        # Todos os endpoints essenciais registrados
        assert "/api/v1/menus" in paths
        assert "/api/v1/menus/{menu_id}" in paths
        assert "/api/v1/menus/{menu_id}/itens" in paths
        assert "/api/v1/menus/{menu_id}/itens/{item_id}" in paths
        assert "/api/v1/menus/{menu_id}/itens/reorder" in paths
