"""Testes de integração do webhook — FastAPI TestClient.

Testa o fluxo de webhook sem banco de dados real.
Usa mocking para simular pool e operações de fila.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain import __version__
from whatsapp_langchain.server.main import app
from whatsapp_langchain.shared.models import Atendimento, Cliente, Conexao

client = TestClient(app, raise_server_exceptions=False)
TEST_INTERNAL_SERVICE_TOKEN = "test-internal-token"


def _default_conexao() -> Conexao:
    """Conexão fake pra empresa 1, com o número padrão das fixtures."""
    now = datetime.now(UTC)
    return Conexao(
        id=1,
        empresa_id=1,
        provider="evolution",
        sid=None,
        from_number="+14155238886",
        display_name="Sandbox VSA Tech",
        default_agent_id="vsa_tech",
        status="active",
        is_default=True,
        payload_json={},
        created_at=now,
        updated_at=now,
    )


def _default_cliente(empresa_id: int = 1, telefone: str = "+5511999999999") -> Cliente:
    now = datetime.now(UTC)
    return Cliente(
        id=10,
        empresa_id=empresa_id,
        telefone=telefone,
        nome=None,
        created_at=now,
        updated_at=now,
    )


def _default_atendimento(empresa_id: int = 1) -> Atendimento:
    now = datetime.now(UTC)
    return Atendimento(
        id=20,
        empresa_id=empresa_id,
        cliente_id=10,
        conexao_id=1,
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    """Mock do banco de dados + lookup de conexão (M2)."""
    from whatsapp_langchain.shared.config import settings

    mock_pool = AsyncMock()
    monkeypatch.setattr(settings, "internal_service_token", TEST_INTERNAL_SERVICE_TOKEN)

    async def fake_lookup(_pool, from_number: str):
        if from_number == "+14155238886":
            return _default_conexao()
        return None

    with (
        patch(
            "whatsapp_langchain.server.routes.health.check_db_health",
            return_value=True,
        ),
        patch(
            "whatsapp_langchain.server.routes.webhook.get_pool",
            return_value=mock_pool,
        ),
        patch(
            "whatsapp_langchain.server.routes.webhook.get_conexao_by_from_number",
            side_effect=fake_lookup,
        ),
        patch(
            "whatsapp_langchain.server.routes.webhook.upsert_cliente",
            new=AsyncMock(return_value=_default_cliente()),
        ),
        patch(
            "whatsapp_langchain.server.routes.webhook.open_or_attach_atendimento",
            new=AsyncMock(return_value=(_default_atendimento(), True)),
        ),
        patch(
            "whatsapp_langchain.server.routes.webhook.dispatch_event",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "whatsapp_langchain.server.routes.admin.get_pool",
            return_value=mock_pool,
        ),
        patch("whatsapp_langchain.shared.db.get_pool", return_value=mock_pool),
        patch("whatsapp_langchain.shared.db.run_migrations"),
        patch("whatsapp_langchain.shared.db.close_pool"),
    ):
        yield mock_pool


class TestHealthCheck:
    """Testes do endpoint /health."""

    def test_health_ok(self):
        """Retorna 200 quando o banco está acessível."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "database": "connected",
            "version": __version__,
        }


class TestWebhookSync:
    """Testes do webhook síncrono."""

    def test_sync_requires_agent(self):
        """Deve exigir o query param 'agent'."""
        response = client.post(
            "/webhook/sync",
            json={"phone": "+5511999999999", "message": "Olá"},
        )
        # Sem agent= -> 422 (query param obrigatório)
        assert response.status_code == 422

    def test_sync_nonexistent_agent(self):
        """Deve retornar erro para agente inexistente."""
        response = client.post(
            "/webhook/sync?agent=nao_existe",
            json={"phone": "+5511999999999", "message": "Olá"},
        )
        assert response.status_code == 400


class TestAdminRoutes:
    """Testes das rotas administrativas."""

    auth_headers = {"Authorization": f"Bearer {TEST_INTERNAL_SERVICE_TOKEN}"}

    def test_list_agents(self):
        """Deve listar agentes disponíveis."""
        response = client.get("/api/agents", headers=self.auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert "vsa_tech" in data["agents"]

    def test_list_agents_requires_token(self):
        """Deve rejeitar requisição sem token de serviço."""
        response = client.get("/api/agents")
        assert response.status_code == 401
