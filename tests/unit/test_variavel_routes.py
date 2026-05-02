"""Testes dos endpoints CRUD /api/variaveis (M5.d)."""

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
from whatsapp_langchain.shared.models import VariavelAmbiente


def _var(**overrides) -> VariavelAmbiente:
    now = datetime.now(UTC)
    base: dict = {
        "id": 1,
        "empresa_id": 1,
        "nome": "suporte_email",
        "valor": "suporte@empresa.com",
        "descricao": None,
        "ativo": True,
        "created_by_user_id": "user-x",
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return VariavelAmbiente(**base)


@pytest.fixture
def client():
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_empresa_context] = lambda: 1
    app.dependency_overrides[get_user_id_from_request] = lambda: "user-x"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_variaveis(client):
    with patch(
        "whatsapp_langchain.server.routes.variavel.list_variaveis",
        new=AsyncMock(return_value=[_var(), _var(id=2, nome="horario")]),
    ):
        response = client.get("/api/variaveis")
    assert response.status_code == 200
    data = response.json()
    assert len(data["variaveis"]) == 2


def test_get_variavel_returns_row(client):
    with patch(
        "whatsapp_langchain.server.routes.variavel.get_variavel_by_id",
        new=AsyncMock(return_value=_var(id=10)),
    ):
        response = client.get("/api/variaveis/10")
    assert response.status_code == 200
    assert response.json()["id"] == 10


def test_get_variavel_404_when_missing(client):
    with patch(
        "whatsapp_langchain.server.routes.variavel.get_variavel_by_id",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/api/variaveis/99")
    assert response.status_code == 404


def test_create_returns_201(client):
    with patch(
        "whatsapp_langchain.server.routes.variavel.create_variavel",
        new=AsyncMock(return_value=_var(id=42)),
    ) as mock_create:
        response = client.post(
            "/api/variaveis",
            json={"nome": "suporte_email", "valor": "x@y.com"},
        )
    assert response.status_code == 201
    assert response.json()["id"] == 42
    kwargs = mock_create.await_args.kwargs
    assert kwargs == {"user_id": "user-x"}


def test_create_409_on_duplicate(client):
    from whatsapp_langchain.shared.variavel import DuplicateNomeError

    with patch(
        "whatsapp_langchain.server.routes.variavel.create_variavel",
        new=AsyncMock(side_effect=DuplicateNomeError("já existe")),
    ):
        response = client.post(
            "/api/variaveis", json={"nome": "x", "valor": "y"}
        )
    assert response.status_code == 409


def test_create_422_on_invalid_nome(client):
    """Nome com hífen quebra o regex `^[a-zA-Z][a-zA-Z0-9_]*$`."""
    response = client.post(
        "/api/variaveis", json={"nome": "x-y", "valor": "z"}
    )
    assert response.status_code == 422


def test_create_422_on_nome_starting_with_number(client):
    response = client.post(
        "/api/variaveis", json={"nome": "1foo", "valor": "z"}
    )
    assert response.status_code == 422


def test_update_returns_200(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.variavel.get_variavel_by_id",
            new=AsyncMock(return_value=_var()),
        ),
        patch(
            "whatsapp_langchain.server.routes.variavel.update_variavel",
            new=AsyncMock(return_value=_var(valor="novo@x.com")),
        ),
    ):
        response = client.put(
            "/api/variaveis/1",
            json={"nome": "suporte_email", "valor": "novo@x.com"},
        )
    assert response.status_code == 200
    assert response.json()["valor"] == "novo@x.com"


def test_update_404_when_missing(client):
    with patch(
        "whatsapp_langchain.server.routes.variavel.get_variavel_by_id",
        new=AsyncMock(return_value=None),
    ):
        response = client.put(
            "/api/variaveis/99",
            json={"nome": "x", "valor": "y"},
        )
    assert response.status_code == 404


def test_update_409_on_duplicate_rename(client):
    from whatsapp_langchain.shared.variavel import DuplicateNomeError

    with (
        patch(
            "whatsapp_langchain.server.routes.variavel.get_variavel_by_id",
            new=AsyncMock(return_value=_var()),
        ),
        patch(
            "whatsapp_langchain.server.routes.variavel.update_variavel",
            new=AsyncMock(side_effect=DuplicateNomeError("já existe")),
        ),
    ):
        response = client.put(
            "/api/variaveis/1",
            json={"nome": "outro_nome", "valor": "y"},
        )
    assert response.status_code == 409


def test_delete_returns_204(client):
    with patch(
        "whatsapp_langchain.server.routes.variavel.delete_variavel",
        new=AsyncMock(return_value=True),
    ):
        response = client.delete("/api/variaveis/1")
    assert response.status_code == 204


def test_delete_404_when_missing(client):
    with patch(
        "whatsapp_langchain.server.routes.variavel.delete_variavel",
        new=AsyncMock(return_value=False),
    ):
        response = client.delete("/api/variaveis/99")
    assert response.status_code == 404


def test_routes_require_service_token():
    app.dependency_overrides.clear()
    client = TestClient(app)
    response = client.get("/api/variaveis")
    assert response.status_code in (401, 403)
