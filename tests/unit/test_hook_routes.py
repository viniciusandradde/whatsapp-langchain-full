"""Testes dos endpoints CRUD /api/hooks (M4.d)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.main import app
from whatsapp_langchain.shared.models import Hook, HookLog


def _hook(**overrides) -> Hook:
    now = datetime.now(UTC)
    base: dict = {
        "id": 1,
        "empresa_id": 1,
        "nome": "hook1",
        "evento": "mensagem.recebida",
        "url": "https://example.com/h",
        "secret": None,
        "ativo": True,
        "created_by_user_id": "user-x",
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return Hook(**base)


def _log(**overrides) -> HookLog:
    base: dict = {
        "id": 1,
        "hook_id": 1,
        "evento": "mensagem.recebida",
        "status_code": 200,
        "error": None,
        "duration_ms": 42,
        "created_at": datetime.now(UTC),
    }
    base.update(overrides)
    return HookLog(**base)


@pytest.fixture
def client():
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_empresa_context] = lambda: 1
    app.dependency_overrides[get_user_id_from_request] = lambda: "user-x"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_eventos_returns_known_set(client):
    response = client.get("/api/hooks/eventos")
    assert response.status_code == 200
    data = response.json()
    assert "mensagem.recebida" in data["eventos"]
    assert "atendimento.fechado" in data["eventos"]


def test_list_hooks_returns_array(client):
    with patch(
        "whatsapp_langchain.server.routes.hook.list_hooks",
        new=AsyncMock(return_value=[_hook(), _hook(id=2, nome="h2")]),
    ):
        response = client.get("/api/hooks")
    assert response.status_code == 200
    assert len(response.json()["hooks"]) == 2


def test_list_hooks_with_evento_filter(client):
    with patch(
        "whatsapp_langchain.server.routes.hook.list_hooks",
        new=AsyncMock(return_value=[]),
    ) as mock_list:
        response = client.get("/api/hooks?evento=atendimento.aberto")
    assert response.status_code == 200
    kwargs = mock_list.await_args.kwargs
    assert kwargs == {"evento": "atendimento.aberto"}


def test_list_hooks_with_invalid_evento_returns_422(client):
    response = client.get("/api/hooks?evento=banana")
    assert response.status_code == 422


def test_create_hook_201(client):
    with patch(
        "whatsapp_langchain.server.routes.hook.create_hook",
        new=AsyncMock(return_value=_hook(id=42)),
    ):
        response = client.post(
            "/api/hooks",
            json={
                "nome": "h",
                "evento": "mensagem.recebida",
                "url": "https://example.com/h",
            },
        )
    assert response.status_code == 201
    assert response.json()["id"] == 42


def test_create_hook_with_invalid_evento_422(client):
    response = client.post(
        "/api/hooks",
        json={"nome": "h", "evento": "banana", "url": "https://example.com/h"},
    )
    assert response.status_code == 422


def test_update_hook_200(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.hook.get_hook_by_id",
            new=AsyncMock(return_value=_hook()),
        ),
        patch(
            "whatsapp_langchain.server.routes.hook.update_hook",
            new=AsyncMock(return_value=_hook(ativo=False)),
        ),
    ):
        response = client.put(
            "/api/hooks/1",
            json={
                "nome": "h",
                "evento": "mensagem.recebida",
                "url": "https://example.com/h",
                "ativo": False,
            },
        )
    assert response.status_code == 200
    assert response.json()["ativo"] is False


def test_update_hook_403_cross_tenant(client):
    with patch(
        "whatsapp_langchain.server.routes.hook.get_hook_by_id",
        new=AsyncMock(return_value=_hook(empresa_id=99)),
    ):
        response = client.put(
            "/api/hooks/1",
            json={
                "nome": "h",
                "evento": "mensagem.recebida",
                "url": "https://example.com/h",
            },
        )
    assert response.status_code == 403


def test_delete_hook_204(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.hook.get_hook_by_id",
            new=AsyncMock(return_value=_hook()),
        ),
        patch(
            "whatsapp_langchain.server.routes.hook.delete_hook",
            new=AsyncMock(return_value=True),
        ),
    ):
        response = client.delete("/api/hooks/1")
    assert response.status_code == 204


def test_logs_returns_list(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.hook.get_hook_by_id",
            new=AsyncMock(return_value=_hook()),
        ),
        patch(
            "whatsapp_langchain.server.routes.hook.list_logs",
            new=AsyncMock(
                return_value=[
                    _log(),
                    _log(id=2, status_code=500, error="boom"),
                ]
            ),
        ),
    ):
        response = client.get("/api/hooks/1/logs")
    assert response.status_code == 200
    data = response.json()
    assert len(data["logs"]) == 2
    assert data["logs"][1]["error"] == "boom"
