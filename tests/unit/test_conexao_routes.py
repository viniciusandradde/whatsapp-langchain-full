"""Testes dos endpoints CRUD /api/conexoes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.server.main import app
from whatsapp_langchain.shared.models import Conexao


def _conexao(**overrides) -> Conexao:
    now = datetime.now(UTC)
    base: dict = {
        "id": 1,
        "empresa_id": 1,
        "provider": "twilio_sandbox",
        "sid": None,
        "from_number": "+14155238886",
        "display_name": "Sandbox",
        "default_agent_id": "vsa_tech",
        "status": "active",
        "is_default": True,
        "payload_json": {},
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return Conexao(**base)


@pytest.fixture
def client():
    """TestClient com auth desabilitada e empresa_id=1 fixo."""
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_empresa_context] = lambda: 1
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_conexoes(client):
    with patch(
        "whatsapp_langchain.server.routes.conexao.list_conexoes",
        new=AsyncMock(return_value=[_conexao(), _conexao(id=2, from_number="+1555")]),
    ):
        response = client.get("/api/conexoes")
    assert response.status_code == 200
    data = response.json()
    assert len(data["conexoes"]) == 2
    assert data["conexoes"][0]["from_number"] == "+14155238886"


def test_read_conexao_returns_detail(client):
    with patch(
        "whatsapp_langchain.server.routes.conexao.get_conexao_by_id",
        new=AsyncMock(return_value=_conexao()),
    ):
        response = client.get("/api/conexoes/1")
    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_read_conexao_404_when_missing(client):
    with patch(
        "whatsapp_langchain.server.routes.conexao.get_conexao_by_id",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/api/conexoes/99")
    assert response.status_code == 404


def test_read_conexao_403_cross_tenant(client):
    """Conexão de empresa diferente → 403."""
    with patch(
        "whatsapp_langchain.server.routes.conexao.get_conexao_by_id",
        new=AsyncMock(return_value=_conexao(empresa_id=99)),
    ):
        response = client.get("/api/conexoes/1")
    assert response.status_code == 403


def test_create_conexao_persists(client):
    with patch(
        "whatsapp_langchain.server.routes.conexao.upsert_conexao",
        new=AsyncMock(
            return_value=_conexao(id=10, from_number="+1555NEW", display_name="Nova")
        ),
    ) as mock_upsert:
        response = client.post(
            "/api/conexoes",
            json={
                "provider": "twilio_prod",
                "from_number": "+1555NEW",
                "display_name": "Nova",
                "default_agent_id": "vsa_tech",
            },
        )
    assert response.status_code == 200
    assert response.json()["id"] == 10
    # empresa_id correto vai pra função
    assert mock_upsert.await_args.args[1] == 1


def test_update_conexao_404_when_missing(client):
    with patch(
        "whatsapp_langchain.server.routes.conexao.get_conexao_by_id",
        new=AsyncMock(return_value=None),
    ):
        response = client.put(
            "/api/conexoes/99",
            json={"provider": "twilio_prod", "from_number": "+1555"},
        )
    assert response.status_code == 404


def test_disable_conexao_calls_set_status(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.conexao.get_conexao_by_id",
            new=AsyncMock(return_value=_conexao()),
        ),
        patch(
            "whatsapp_langchain.server.routes.conexao.set_conexao_status",
            new=AsyncMock(return_value=None),
        ) as mock_set,
    ):
        response = client.delete("/api/conexoes/1")
    assert response.status_code == 204
    assert mock_set.await_args.args[1:] == (1, "disabled")


def test_disable_conexao_403_cross_tenant(client):
    with patch(
        "whatsapp_langchain.server.routes.conexao.get_conexao_by_id",
        new=AsyncMock(return_value=_conexao(empresa_id=99)),
    ):
        response = client.delete("/api/conexoes/1")
    assert response.status_code == 403
