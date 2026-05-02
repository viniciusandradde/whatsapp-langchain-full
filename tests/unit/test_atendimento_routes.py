"""Testes dos endpoints CRUD /api/atendimentos (M3 CRM Light)."""

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
from whatsapp_langchain.shared.models import Atendimento


def _atendimento(**overrides) -> Atendimento:
    now = datetime.now(UTC)
    base: dict = {
        "id": 1,
        "empresa_id": 1,
        "cliente_id": 10,
        "conexao_id": 1,
        "status": "aguardando",
        "last_message_at": now,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return Atendimento(**base)


@pytest.fixture
def client():
    """TestClient com auth desabilitada, empresa_id=1, user=user-x e
    dispatch_event mockado pra evitar HTTP real (M4.d).
    """
    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_empresa_context] = lambda: 1
    app.dependency_overrides[get_user_id_from_request] = lambda: "user-x"
    with patch(
        "whatsapp_langchain.server.routes.atendimento.dispatch_event",
        new=AsyncMock(return_value=None),
    ):
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.clear()


def test_list_atendimentos_default_aguardando(client):
    with patch(
        "whatsapp_langchain.server.routes.atendimento.list_atendimentos",
        new=AsyncMock(return_value=[_atendimento()]),
    ) as mock_list:
        response = client.get("/api/atendimentos")
    assert response.status_code == 200
    assert len(response.json()["atendimentos"]) == 1
    kwargs = mock_list.await_args.kwargs
    assert kwargs["tipo"] == "aguardando"
    assert kwargs["current_user_id"] == "user-x"


def test_list_atendimentos_with_tipo_meus(client):
    with patch(
        "whatsapp_langchain.server.routes.atendimento.list_atendimentos",
        new=AsyncMock(return_value=[]),
    ) as mock_list:
        response = client.get("/api/atendimentos?tipo=meus&limit=10&offset=5")
    assert response.status_code == 200
    kwargs = mock_list.await_args.kwargs
    assert kwargs["tipo"] == "meus"
    assert kwargs["limit"] == 10
    assert kwargs["offset"] == 5


def test_list_atendimentos_invalid_tipo_returns_422(client):
    response = client.get("/api/atendimentos?tipo=banana")
    assert response.status_code == 422


def test_read_atendimento_returns_detail(client):
    with patch(
        "whatsapp_langchain.server.routes.atendimento.get_atendimento_by_id",
        new=AsyncMock(return_value=_atendimento(id=42)),
    ):
        response = client.get("/api/atendimentos/42")
    assert response.status_code == 200
    assert response.json()["id"] == 42


def test_read_atendimento_404(client):
    with patch(
        "whatsapp_langchain.server.routes.atendimento.get_atendimento_by_id",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/api/atendimentos/99")
    assert response.status_code == 404


def test_read_atendimento_403_cross_tenant(client):
    with patch(
        "whatsapp_langchain.server.routes.atendimento.get_atendimento_by_id",
        new=AsyncMock(return_value=_atendimento(empresa_id=99)),
    ):
        response = client.get("/api/atendimentos/1")
    assert response.status_code == 403


def test_claim_returns_atendimento(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.atendimento.get_atendimento_by_id",
            new=AsyncMock(return_value=_atendimento()),
        ),
        patch(
            "whatsapp_langchain.server.routes.atendimento.claim_atendimento",
            new=AsyncMock(
                return_value=_atendimento(
                    status="em_andamento", assigned_to_user_id="user-x"
                )
            ),
        ) as mock_claim,
    ):
        response = client.post("/api/atendimentos/1/claim")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "em_andamento"
    assert data["assigned_to_user_id"] == "user-x"
    args = mock_claim.await_args.args
    assert args[1] == 1
    assert args[2] == "user-x"


def test_claim_returns_409_when_already_closed(client):
    """Race: atendimento foi fechado entre load e claim."""
    with (
        patch(
            "whatsapp_langchain.server.routes.atendimento.get_atendimento_by_id",
            new=AsyncMock(return_value=_atendimento()),
        ),
        patch(
            "whatsapp_langchain.server.routes.atendimento.claim_atendimento",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = client.post("/api/atendimentos/1/claim")
    assert response.status_code == 409


def test_close_default_resolvido(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.atendimento.get_atendimento_by_id",
            new=AsyncMock(return_value=_atendimento()),
        ),
        patch(
            "whatsapp_langchain.server.routes.atendimento.close_atendimento",
            new=AsyncMock(return_value=_atendimento(status="resolvido")),
        ) as mock_close,
    ):
        response = client.post("/api/atendimentos/1/close", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "resolvido"
    kwargs = mock_close.await_args.kwargs
    assert kwargs["status"] == "resolvido"


def test_close_with_abandonado(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.atendimento.get_atendimento_by_id",
            new=AsyncMock(return_value=_atendimento()),
        ),
        patch(
            "whatsapp_langchain.server.routes.atendimento.close_atendimento",
            new=AsyncMock(return_value=_atendimento(status="abandonado")),
        ) as mock_close,
    ):
        response = client.post(
            "/api/atendimentos/1/close", json={"status": "abandonado"}
        )
    assert response.status_code == 200
    kwargs = mock_close.await_args.kwargs
    assert kwargs["status"] == "abandonado"


def test_responder_returns_persisted_row(client):
    persisted = {
        "id": 99,
        "agent_id": "vsa_tech",
        "incoming_message": "",
        "response": "olá!",
        "status": "done",
        "created_at": "2026-05-02T00:00:00Z",
        "processed_at": "2026-05-02T00:00:00Z",
    }
    with (
        patch(
            "whatsapp_langchain.server.routes.atendimento.build_render_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "whatsapp_langchain.server.routes.atendimento.send_outbound_manual",
            new=AsyncMock(return_value=persisted),
        ) as mock_send,
    ):
        response = client.post(
            "/api/atendimentos/1/responder", json={"conteudo": "olá!"}
        )
    assert response.status_code == 200
    assert response.json()["mensagem"]["id"] == 99
    kwargs = mock_send.await_args.kwargs
    assert kwargs == {
        "atendimento_id": 1,
        "empresa_id": 1,
        "user_id": "user-x",
        "conteudo": "olá!",
    }


def test_responder_renders_template_before_send(client):
    """M5.d: `{{cliente.nome}}` é resolvido server-side antes de ir pro Twilio."""
    persisted = {
        "id": 100,
        "agent_id": "vsa_tech",
        "incoming_message": "",
        "response": "Olá João!",
        "status": "done",
        "created_at": "2026-05-02T00:00:00Z",
        "processed_at": "2026-05-02T00:00:00Z",
    }
    with (
        patch(
            "whatsapp_langchain.server.routes.atendimento.build_render_context",
            new=AsyncMock(return_value={"cliente.nome": "João"}),
        ),
        patch(
            "whatsapp_langchain.server.routes.atendimento.send_outbound_manual",
            new=AsyncMock(return_value=persisted),
        ) as mock_send,
    ):
        response = client.post(
            "/api/atendimentos/1/responder",
            json={"conteudo": "Olá {{cliente.nome}}!"},
        )
    assert response.status_code == 200
    kwargs = mock_send.await_args.kwargs
    assert kwargs["conteudo"] == "Olá João!"


def test_responder_409_when_atendimento_closed(client):
    from whatsapp_langchain.shared.outbound import OutboundError

    with (
        patch(
            "whatsapp_langchain.server.routes.atendimento.build_render_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "whatsapp_langchain.server.routes.atendimento.send_outbound_manual",
            new=AsyncMock(side_effect=OutboundError("Atendimento já fechado")),
        ),
    ):
        response = client.post("/api/atendimentos/1/responder", json={"conteudo": "x"})
    assert response.status_code == 409


def test_responder_404_when_atendimento_missing(client):
    from whatsapp_langchain.shared.outbound import OutboundError

    with (
        patch(
            "whatsapp_langchain.server.routes.atendimento.build_render_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "whatsapp_langchain.server.routes.atendimento.send_outbound_manual",
            new=AsyncMock(side_effect=OutboundError("Atendimento não encontrado.")),
        ),
    ):
        response = client.post("/api/atendimentos/1/responder", json={"conteudo": "x"})
    assert response.status_code == 404


def test_read_mensagens_returns_list(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.atendimento.get_atendimento_by_id",
            new=AsyncMock(return_value=_atendimento()),
        ),
        patch(
            "whatsapp_langchain.server.routes.atendimento.list_atendimento_mensagens",
            new=AsyncMock(
                return_value=[
                    {
                        "id": 1,
                        "agent_id": "vsa_tech",
                        "incoming_message": "oi",
                        "response": "olá!",
                        "status": "done",
                    }
                ]
            ),
        ),
    ):
        response = client.get("/api/atendimentos/1/mensagens")
    assert response.status_code == 200
    data = response.json()
    assert data["atendimento_id"] == 1
    assert len(data["mensagens"]) == 1
    assert data["mensagens"][0]["incoming_message"] == "oi"


def test_read_mensagens_404_for_unknown_atendimento(client):
    with patch(
        "whatsapp_langchain.server.routes.atendimento.get_atendimento_by_id",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/api/atendimentos/99/mensagens")
    assert response.status_code == 404


def test_transfer_changes_assignee(client):
    with (
        patch(
            "whatsapp_langchain.server.routes.atendimento.get_atendimento_by_id",
            new=AsyncMock(return_value=_atendimento()),
        ),
        patch(
            "whatsapp_langchain.server.routes.atendimento.transfer_atendimento",
            new=AsyncMock(
                return_value=_atendimento(
                    status="em_andamento", assigned_to_user_id="bob"
                )
            ),
        ) as mock_transfer,
    ):
        response = client.post("/api/atendimentos/1/transfer", json={"user_id": "bob"})
    assert response.status_code == 200
    assert response.json()["assigned_to_user_id"] == "bob"
    args = mock_transfer.await_args.args
    assert args[1] == 1
    assert args[2] == "bob"
