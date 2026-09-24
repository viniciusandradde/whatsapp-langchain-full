"""Testes dos endpoints CRUD /api/clientes (M3 CRM Light)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.main import app
from whatsapp_langchain.shared.models import Cliente, ClienteAnotacao

# Requer Postgres real: cada request /api/* passa pelo middleware
# install_admin_rate_limit → enforce_bucket_limit → get_pool(), que tenta
# conectar no Postgres (host `db:5432`) e TRAVA sem DB. Os helpers de rota são
# mockados, mas o pool do middleware não. Marca o módulo como docker_demo
# (gate de CI unit roda sem DB).
pytestmark = pytest.mark.docker_demo


def _cliente(**overrides) -> Cliente:
    now = datetime.now(UTC)
    base: dict = {
        "id": 1,
        "empresa_id": 1,
        "telefone": "+5511999999999",
        "nome": "Fulano",
        "created_at": now,
        "updated_at": now,
        "tags": [],
    }
    base.update(overrides)
    return Cliente(**base)


def _anotacao(**overrides) -> ClienteAnotacao:
    base: dict = {
        "id": 1,
        "cliente_id": 1,
        "user_id": "user-x",
        "conteudo": "nota teste",
        "created_at": datetime.now(UTC),
    }
    base.update(overrides)
    return ClienteAnotacao(**base)


_PERMS_GESTOR = {"cliente.read.all", "cliente.write.all"}


@pytest.fixture
def client():
    """TestClient com auth desabilitada e empresa_id=1, user=user-x.

    Perfil com as variantes de escopo (como o Gestor system) — as rotas
    exigem `cliente.read`/`cliente.write` desde a mig 201.
    """
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_empresa_context] = lambda: 1
    app.dependency_overrides[get_user_id_from_request] = lambda: "user-x"
    try:
        with (
            patch(
                "whatsapp_langchain.server.routes.cliente.get_user_permissions",
                new=AsyncMock(return_value=_PERMS_GESTOR),
            ),
            patch(
                "whatsapp_langchain.server.routes.cliente.tags_por_cliente",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "whatsapp_langchain.server.routes.cliente.get_pool",
                new=AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "whatsapp_langchain.server.dependencies_rbac.get_user_permissions",
                new=AsyncMock(return_value=_PERMS_GESTOR),
            ),
            patch(
                "whatsapp_langchain.server.dependencies_rbac.get_pool",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_sem_permissao_de_escrita_recebe_403():
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_empresa_context] = lambda: 1
    app.dependency_overrides[get_user_id_from_request] = lambda: "user-x"
    try:
        with (
            patch(
                "whatsapp_langchain.server.routes.cliente.get_user_permissions",
                new=AsyncMock(return_value={"cliente.read.own"}),
            ),
            patch(
                "whatsapp_langchain.server.dependencies_rbac.get_user_permissions",
                new=AsyncMock(return_value={"cliente.read.own"}),
            ),
            patch(
                "whatsapp_langchain.server.dependencies_rbac.get_pool",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            r = TestClient(app).post("/api/clientes", json={"telefone": "67996460034"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 403


def test_list_clientes_returns_array(client):
    with patch(
        "whatsapp_langchain.server.routes.cliente.list_clientes",
        new=AsyncMock(return_value=[_cliente(), _cliente(id=2, telefone="+1555")]),
    ):
        response = client.get("/api/clientes")
    assert response.status_code == 200
    data = response.json()
    assert len(data["clientes"]) == 2
    assert data["clientes"][0]["telefone"] == "+5511999999999"


def test_list_clientes_passes_search_and_pagination(client):
    with patch(
        "whatsapp_langchain.server.routes.cliente.list_clientes",
        new=AsyncMock(return_value=[]),
    ) as mock_list:
        response = client.get("/api/clientes?search=fulano&limit=10&offset=20")
    assert response.status_code == 200
    kwargs = mock_list.await_args.kwargs
    assert kwargs == {
        "search": "fulano",
        "limit": 10,
        "offset": 20,
        "scope_departamento_ids": None,
        "lifecycle_stage": None,
        "temperatura": None,
    }


def test_read_cliente_returns_detail_with_anotacoes(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.cliente.get_cliente_by_id",
            new=AsyncMock(return_value=_cliente(tags=["vip"])),
        ),
        patch(
            "whatsapp_langchain.server.routes.cliente.list_anotacoes",
            new=AsyncMock(return_value=[_anotacao()]),
        ),
    ):
        response = client.get("/api/clientes/1")
    assert response.status_code == 200
    data = response.json()
    assert data["cliente"]["id"] == 1
    assert data["cliente"]["tags"] == ["vip"]
    assert len(data["anotacoes"]) == 1


def test_read_cliente_404_when_missing(client):
    with patch(
        "whatsapp_langchain.server.routes.cliente.get_cliente_by_id",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/api/clientes/99")
    assert response.status_code == 404


def test_read_cliente_403_cross_tenant(client):
    with patch(
        "whatsapp_langchain.server.routes.cliente.get_cliente_by_id",
        new=AsyncMock(return_value=_cliente(empresa_id=99)),
    ):
        response = client.get("/api/clientes/1")
    assert response.status_code == 403


def test_create_anotacao_persists(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.cliente.get_cliente_by_id",
            new=AsyncMock(return_value=_cliente()),
        ),
        patch(
            "whatsapp_langchain.server.routes.cliente.add_anotacao",
            new=AsyncMock(return_value=_anotacao(id=42, conteudo="cliente VIP")),
        ) as mock_add,
    ):
        response = client.post(
            "/api/clientes/1/anotacoes", json={"conteudo": "cliente VIP"}
        )
    assert response.status_code == 201
    assert response.json()["id"] == 42
    args = mock_add.await_args.args
    assert args[1] == 1  # cliente_id
    assert args[2] == "user-x"  # user_id do header
    assert args[3] == "cliente VIP"


def test_create_anotacao_404_for_unknown_cliente(client):
    with patch(
        "whatsapp_langchain.server.routes.cliente.get_cliente_by_id",
        new=AsyncMock(return_value=None),
    ):
        response = client.post("/api/clientes/99/anotacoes", json={"conteudo": "x"})
    assert response.status_code == 404


def test_create_tag_idempotente(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.cliente.get_cliente_by_id",
            new=AsyncMock(return_value=_cliente()),
        ),
        patch(
            "whatsapp_langchain.server.routes.cliente.add_tag",
            new=AsyncMock(return_value=None),
        ) as mock_add,
    ):
        response = client.post("/api/clientes/1/tags", json={"tag": "vip"})
    assert response.status_code == 204
    args = mock_add.await_args.args
    assert args[1] == 1
    assert args[2] == "vip"


def test_delete_tag_idempotente(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.cliente.get_cliente_by_id",
            new=AsyncMock(return_value=_cliente()),
        ),
        patch(
            "whatsapp_langchain.server.routes.cliente.remove_tag",
            new=AsyncMock(return_value=None),
        ) as mock_remove,
    ):
        response = client.delete("/api/clientes/1/tags/vip")
    assert response.status_code == 204
    args = mock_remove.await_args.args
    assert args[1] == 1
    assert args[2] == "vip"
