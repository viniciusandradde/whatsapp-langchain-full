"""Testes de integração do webhook — FastAPI TestClient.

Testa o fluxo de webhook sem banco de dados real.
Usa mocking para simular pool e operações de fila.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from whatsapp_langchain import __version__
from whatsapp_langchain.server.main import app

client = TestClient(app, raise_server_exceptions=False)
TEST_INTERNAL_SERVICE_TOKEN = "test-internal-token"


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    """Mock do banco de dados para testes sem PostgreSQL."""
    from whatsapp_langchain.shared.config import settings

    mock_pool = AsyncMock()
    monkeypatch.setattr(settings, "internal_service_token", TEST_INTERNAL_SERVICE_TOKEN)

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


class TestWebhookTwilio:
    """Testes do webhook Twilio."""

    def test_twilio_requires_agent(self):
        """Deve exigir o query param 'agent'."""
        response = client.post(
            "/webhook/twilio",
            data={
                "MessageSid": "SM123",
                "From": "whatsapp:+5511999999999",
                "To": "whatsapp:+14155238886",
                "Body": "Olá",
                "NumMedia": "0",
            },
        )
        # Sem agent= -> 422
        assert response.status_code == 422

    def test_twilio_nonexistent_agent(self):
        """Deve retornar erro para agente inexistente."""
        response = client.post(
            "/webhook/twilio?agent=nao_existe",
            data={
                "MessageSid": "SM123",
                "From": "whatsapp:+5511999999999",
                "To": "whatsapp:+14155238886",
                "Body": "Olá",
                "NumMedia": "0",
            },
        )
        assert response.status_code == 400

    @patch("whatsapp_langchain.server.routes.webhook.enqueue_or_buffer")
    def test_twilio_enqueues_message(self, mock_enqueue):
        """Deve enfileirar mensagem e retornar TwiML vazio."""
        from whatsapp_langchain.shared.models import EnqueueResult

        mock_enqueue.return_value = EnqueueResult(message_id=1, is_buffered=False)

        response = client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data={
                "MessageSid": "SM123",
                "From": "whatsapp:+5511999999999",
                "To": "whatsapp:+14155238886",
                "Body": "Olá",
                "NumMedia": "0",
            },
        )
        assert response.status_code == 200
        assert "Response" in response.text

    @patch("whatsapp_langchain.server.routes.webhook.enqueue_or_buffer")
    def test_webhook_enqueues_n_rows_for_num_media_2(self, mock_enqueue):
        """NumMedia=2 cria 1 row de texto + 2 rows de mídia com mesmo message_id."""
        from whatsapp_langchain.shared.models import EnqueueResult

        call_count = 0

        def fake_enqueue_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return EnqueueResult(message_id=call_count, is_buffered=False)

        mock_enqueue.side_effect = fake_enqueue_side_effect

        response = client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data={
                "MessageSid": "SM_MULTI_001",
                "From": "whatsapp:+5511999990050",
                "To": "whatsapp:+14155238886",
                "Body": "olha as fotos",
                "NumMedia": "2",
                "MediaUrl0": "https://example.com/img0.jpg",
                "MediaContentType0": "image/jpeg",
                "MediaUrl1": "https://example.com/img1.jpg",
                "MediaContentType1": "image/jpeg",
            },
        )
        assert response.status_code == 200, response.text

        # Deve ter chamado enqueue_or_buffer 3 vezes: 1 texto + 2 mídias
        assert mock_enqueue.call_count == 3, (
            f"Esperava 3 chamadas a enqueue_or_buffer, vi {mock_enqueue.call_count}"
        )

        calls_kwargs = [c.kwargs for c in mock_enqueue.call_args_list]

        media_rows = [k for k in calls_kwargs if k.get("media_url")]
        assert len(media_rows) == 2, (
            f"Esperava 2 rows de mídia, vi {len(media_rows)}: {calls_kwargs}"
        )
        assert {k["media_url"] for k in media_rows} == {
            "https://example.com/img0.jpg",
            "https://example.com/img1.jpg",
        }
        # Mesmo message_id em todas as chamadas
        assert all(k.get("message_id") == "SM_MULTI_001" for k in calls_kwargs), (
            f"Esperava message_id='SM_MULTI_001' em todas as chamadas: {calls_kwargs}"
        )

    def test_twilio_openapi_exposes_form_fields(self):
        """Swagger deve exibir body form-encoded para teste manual."""
        openapi = client.get("/openapi.json").json()
        post = openapi["paths"]["/webhook/twilio"]["post"]
        assert "requestBody" in post

        form_content = post["requestBody"]["content"][
            "application/x-www-form-urlencoded"
        ]
        schema = form_content["schema"]
        if "$ref" in schema:
            ref_name = schema["$ref"].split("/")[-1]
            schema = openapi["components"]["schemas"][ref_name]

        properties = schema["properties"]
        assert "MessageSid" in properties
        assert "From" in properties
        assert "To" in properties
        assert "Body" in properties
        assert "NumMedia" in properties


class TestAdminRoutes:
    """Testes das rotas administrativas."""

    auth_headers = {"Authorization": f"Bearer {TEST_INTERNAL_SERVICE_TOKEN}"}

    def test_list_agents(self):
        """Deve listar agentes disponíveis."""
        response = client.get("/api/agents", headers=self.auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert "rhawk_assistant" in data["agents"]

    def test_list_agents_requires_token(self):
        """Deve rejeitar requisição sem token de serviço."""
        response = client.get("/api/agents")
        assert response.status_code == 401
