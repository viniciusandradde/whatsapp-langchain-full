"""Testes dos endpoints de gestão de empresas e membros (M1.x)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.server.dependencies import (
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.main import app
from whatsapp_langchain.shared.models import Empresa, EmpresaMembro


def _empresa(**overrides) -> Empresa:
    now = datetime.now(UTC)
    base: dict = {
        "id": 7,
        "nome": "Acme Inc",
        "slug": "acme",
        "doc": None,
        "plano": "free",
        "status": "active",
        "config": {},
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return Empresa(**base)


def _membro(**overrides) -> EmpresaMembro:
    base: dict = {
        "empresa_id": 7,
        "user_id": "user-x",
        "role": "operator",
        "is_default": False,
        "joined_at": datetime.now(UTC),
    }
    base.update(overrides)
    return EmpresaMembro(**base)


@pytest.fixture
def client():
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_user_id_from_request] = lambda: "user-admin"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_empresa_persists_and_makes_creator_admin(client):
    with patch(
        "whatsapp_langchain.server.routes.empresa_admin.create_empresa",
        new=AsyncMock(return_value=_empresa(id=10, nome="Nova", slug="nova")),
    ) as mock_create:
        response = client.post(
            "/api/empresas",
            json={"nome": "Nova", "slug": "nova", "plano": "pro"},
        )
    assert response.status_code == 200
    assert response.json()["id"] == 10
    # criador é o user-admin (do dependency override)
    args = mock_create.await_args.args
    assert args[5] == "user-admin"


def test_create_empresa_409_on_duplicate_slug(client):
    with patch(
        "whatsapp_langchain.server.routes.empresa_admin.create_empresa",
        new=AsyncMock(side_effect=Exception("duplicate key value violates unique")),
    ):
        response = client.post(
            "/api/empresas", json={"nome": "Acme", "slug": "acme"}
        )
    assert response.status_code == 409


def test_update_empresa_403_when_not_admin(client):
    with patch(
        "whatsapp_langchain.server.routes.empresa_admin.is_admin_of",
        new=AsyncMock(return_value=False),
    ):
        response = client.put("/api/empresas/7", json={"nome": "Outra"})
    assert response.status_code == 403


def test_update_empresa_404_when_missing(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.is_admin_of",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.update_empresa",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = client.put("/api/empresas/99", json={"nome": "Outra"})
    assert response.status_code == 404


def test_list_members_returns_list(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.is_superadmin",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.get_empresa_by_id",
            new=AsyncMock(return_value=_empresa()),
        ),
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.list_members",
            new=AsyncMock(
                return_value=[_membro(role="admin"), _membro(user_id="user-y")]
            ),
        ),
    ):
        response = client.get("/api/empresas/7/membros")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_add_member_403_when_not_admin(client):
    with patch(
        "whatsapp_langchain.server.routes.empresa_admin.is_admin_of",
        new=AsyncMock(return_value=False),
    ):
        response = client.post(
            "/api/empresas/7/membros",
            json={"user_id": "user-z", "role": "operator"},
        )
    assert response.status_code == 403


def test_add_member_validates_role(client):
    with patch(
        "whatsapp_langchain.server.routes.empresa_admin.is_admin_of",
        new=AsyncMock(return_value=True),
    ):
        response = client.post(
            "/api/empresas/7/membros",
            json={"user_id": "user-z", "role": "invalid"},
        )
    assert response.status_code == 400


def test_update_role_409_on_last_admin_demote(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.is_admin_of",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.update_member_role",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = client.put(
            "/api/empresas/7/membros/user-x", json={"role": "operator"}
        )
    assert response.status_code == 409


def test_remove_member_409_on_last_admin(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.is_admin_of",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.remove_member",
            new=AsyncMock(return_value=False),
        ),
    ):
        response = client.delete("/api/empresas/7/membros/user-x")
    assert response.status_code == 409


def test_remove_member_204_on_success(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.is_admin_of",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.remove_member",
            new=AsyncMock(return_value=True),
        ),
    ):
        response = client.delete("/api/empresas/7/membros/user-x")
    assert response.status_code == 204
