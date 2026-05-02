"""Testes dos endpoints CRUD /api/modelos (M4.b)."""

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
from whatsapp_langchain.shared.models import ModeloMensagem


def _modelo(**overrides) -> ModeloMensagem:
    now = datetime.now(UTC)
    base: dict = {
        "id": 1,
        "empresa_id": 1,
        "titulo": "Saudação",
        "conteudo": "Olá, tudo bem?",
        "atalho": None,
        "created_by_user_id": "user-x",
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return ModeloMensagem(**base)


@pytest.fixture
def client():
    """TestClient com auth desabilitada e empresa_id=1, user=user-x."""
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_empresa_context] = lambda: 1
    app.dependency_overrides[get_user_id_from_request] = lambda: "user-x"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_modelos(client):
    with patch(
        "whatsapp_langchain.server.routes.modelo_mensagem.list_modelos",
        new=AsyncMock(return_value=[_modelo(), _modelo(id=2, titulo="Despedida")]),
    ):
        response = client.get("/api/modelos")
    assert response.status_code == 200
    data = response.json()
    assert len(data["modelos"]) == 2


def test_list_modelos_passes_search(client):
    with patch(
        "whatsapp_langchain.server.routes.modelo_mensagem.list_modelos",
        new=AsyncMock(return_value=[]),
    ) as mock_list:
        response = client.get("/api/modelos?search=saud")
    assert response.status_code == 200
    kwargs = mock_list.await_args.kwargs
    assert kwargs == {"search": "saud"}


def test_create_modelo_returns_201(client):
    with patch(
        "whatsapp_langchain.server.routes.modelo_mensagem.create_modelo",
        new=AsyncMock(return_value=_modelo(id=42)),
    ) as mock_create:
        response = client.post(
            "/api/modelos", json={"titulo": "Saudação", "conteudo": "Olá!"}
        )
    assert response.status_code == 201
    assert response.json()["id"] == 42
    kwargs = mock_create.await_args.kwargs
    assert kwargs == {"user_id": "user-x"}


def test_create_modelo_409_on_duplicate(client):
    from whatsapp_langchain.shared.modelo_mensagem import DuplicateTituloError

    with patch(
        "whatsapp_langchain.server.routes.modelo_mensagem.create_modelo",
        new=AsyncMock(side_effect=DuplicateTituloError("já existe")),
    ):
        response = client.post("/api/modelos", json={"titulo": "X", "conteudo": "y"})
    assert response.status_code == 409


def test_create_modelo_422_on_empty_titulo(client):
    response = client.post("/api/modelos", json={"titulo": "", "conteudo": "x"})
    assert response.status_code == 422


def test_update_modelo_returns_200(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.modelo_mensagem.get_modelo_by_id",
            new=AsyncMock(return_value=_modelo()),
        ),
        patch(
            "whatsapp_langchain.server.routes.modelo_mensagem.update_modelo",
            new=AsyncMock(return_value=_modelo(titulo="Atualizado")),
        ),
    ):
        response = client.put(
            "/api/modelos/1",
            json={"titulo": "Atualizado", "conteudo": "novo"},
        )
    assert response.status_code == 200
    assert response.json()["titulo"] == "Atualizado"


def test_update_modelo_404_when_missing(client):
    with patch(
        "whatsapp_langchain.server.routes.modelo_mensagem.get_modelo_by_id",
        new=AsyncMock(return_value=None),
    ):
        response = client.put("/api/modelos/99", json={"titulo": "x", "conteudo": "y"})
    assert response.status_code == 404


def test_update_modelo_403_cross_tenant(client):
    with patch(
        "whatsapp_langchain.server.routes.modelo_mensagem.get_modelo_by_id",
        new=AsyncMock(return_value=_modelo(empresa_id=99)),
    ):
        response = client.put("/api/modelos/1", json={"titulo": "x", "conteudo": "y"})
    assert response.status_code == 403


def test_delete_modelo_returns_204(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.modelo_mensagem.get_modelo_by_id",
            new=AsyncMock(return_value=_modelo()),
        ),
        patch(
            "whatsapp_langchain.server.routes.modelo_mensagem.delete_modelo",
            new=AsyncMock(return_value=True),
        ),
    ):
        response = client.delete("/api/modelos/1")
    assert response.status_code == 204
