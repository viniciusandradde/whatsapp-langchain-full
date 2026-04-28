"""Testes da validação criptográfica de assinatura Twilio.

Usa o RequestValidator do SDK oficial para gerar assinaturas válidas
e verifica que o middleware rejeita assinaturas inválidas com 403.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from whatsapp_langchain.server.main import app

client = TestClient(app, raise_server_exceptions=False)

# Token de teste (qualquer string serve para gerar/validar HMAC)
TEST_AUTH_TOKEN = "test_auth_token_for_signature_validation"
TEST_INTERNAL_SERVICE_TOKEN = "test-internal-token"
TEST_WEBHOOK_URL = "https://example.com"


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


def sign_request(
    url: str,
    params: dict[str, str],
    auth_token: str = TEST_AUTH_TOKEN,
) -> str:
    """Gera uma assinatura Twilio válida para os parâmetros dados.

    Usa o mesmo RequestValidator que o código de produção.

    Args:
        url: URL completa do webhook.
        params: Parâmetros POST form-encoded.
        auth_token: Token de autenticação do Twilio.

    Returns:
        Assinatura HMAC-SHA1 em base64.
    """
    validator = RequestValidator(auth_token)
    return validator.compute_signature(url, params)


class TestSignatureValidationDisabled:
    """Quando VALIDATE_TWILIO_SIGNATURE=false (padrão), bypass total."""

    @patch("whatsapp_langchain.server.routes.webhook.enqueue_or_buffer")
    def test_accepts_without_signature(self, mock_enqueue, monkeypatch):
        """Aceita requests sem header X-Twilio-Signature."""
        from whatsapp_langchain.shared.config import settings
        from whatsapp_langchain.shared.models import EnqueueResult

        monkeypatch.setattr(settings, "validate_twilio_signature", False)
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

    @patch("whatsapp_langchain.server.routes.webhook.enqueue_or_buffer")
    def test_accepts_with_invalid_signature(self, mock_enqueue, monkeypatch):
        """Aceita requests com assinatura inválida quando validação desabilitada."""
        from whatsapp_langchain.shared.config import settings
        from whatsapp_langchain.shared.models import EnqueueResult

        monkeypatch.setattr(settings, "validate_twilio_signature", False)
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
            headers={"X-Twilio-Signature": "assinatura_invalida"},
        )
        assert response.status_code == 200


class TestSignatureValidationEnabled:
    """Quando VALIDATE_TWILIO_SIGNATURE=true, validação criptográfica real."""

    def test_rejects_missing_signature(self, monkeypatch):
        """Rejeita com 403 quando header X-Twilio-Signature ausente."""
        from whatsapp_langchain.shared.config import settings

        monkeypatch.setattr(settings, "validate_twilio_signature", True)
        monkeypatch.setattr(settings, "twilio_auth_token", TEST_AUTH_TOKEN)

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
        assert response.status_code == 403
        assert "Missing" in response.json()["detail"]

    def test_rejects_invalid_signature(self, monkeypatch):
        """Rejeita com 403 quando assinatura HMAC-SHA1 não confere."""
        from whatsapp_langchain.shared.config import settings

        monkeypatch.setattr(settings, "validate_twilio_signature", True)
        monkeypatch.setattr(settings, "twilio_auth_token", TEST_AUTH_TOKEN)
        monkeypatch.setattr(settings, "twilio_webhook_url", TEST_WEBHOOK_URL)

        response = client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data={
                "MessageSid": "SM123",
                "From": "whatsapp:+5511999999999",
                "To": "whatsapp:+14155238886",
                "Body": "Olá",
                "NumMedia": "0",
            },
            headers={"X-Twilio-Signature": "assinatura_invalida"},
        )
        assert response.status_code == 403
        assert "Invalid" in response.json()["detail"]

    @patch("whatsapp_langchain.server.routes.webhook.enqueue_or_buffer")
    def test_accepts_valid_signature(self, mock_enqueue, monkeypatch):
        """Aceita request com assinatura HMAC-SHA1 válida."""
        from whatsapp_langchain.shared.config import settings
        from whatsapp_langchain.shared.models import EnqueueResult

        monkeypatch.setattr(settings, "validate_twilio_signature", True)
        monkeypatch.setattr(settings, "twilio_auth_token", TEST_AUTH_TOKEN)
        monkeypatch.setattr(settings, "twilio_webhook_url", TEST_WEBHOOK_URL)
        mock_enqueue.return_value = EnqueueResult(message_id=1, is_buffered=False)

        params = {
            "MessageSid": "SM123",
            "From": "whatsapp:+5511999999999",
            "To": "whatsapp:+14155238886",
            "Body": "Olá",
            "NumMedia": "0",
        }
        url = f"{TEST_WEBHOOK_URL}/webhook/twilio?agent=rhawk_assistant"
        signature = sign_request(url, params)

        response = client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data=params,
            headers={"X-Twilio-Signature": signature},
        )
        assert response.status_code == 200

    @patch("whatsapp_langchain.server.routes.webhook.enqueue_or_buffer")
    def test_valid_signature_with_media(self, mock_enqueue, monkeypatch):
        """Aceita assinatura válida em mensagem com mídia."""
        from whatsapp_langchain.shared.config import settings
        from whatsapp_langchain.shared.models import EnqueueResult

        monkeypatch.setattr(settings, "validate_twilio_signature", True)
        monkeypatch.setattr(settings, "twilio_auth_token", TEST_AUTH_TOKEN)
        monkeypatch.setattr(settings, "twilio_webhook_url", TEST_WEBHOOK_URL)
        mock_enqueue.return_value = EnqueueResult(message_id=1, is_buffered=False)

        params = {
            "MessageSid": "SM456",
            "From": "whatsapp:+5511999999999",
            "To": "whatsapp:+14155238886",
            "Body": "",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/img.jpg",
            "MediaContentType0": "image/jpeg",
        }
        url = f"{TEST_WEBHOOK_URL}/webhook/twilio?agent=rhawk_assistant"
        signature = sign_request(url, params)

        response = client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data=params,
            headers={"X-Twilio-Signature": signature},
        )
        assert response.status_code == 200

    def test_wrong_token_rejects(self, monkeypatch):
        """Assinatura gerada com token diferente é rejeitada."""
        from whatsapp_langchain.shared.config import settings

        monkeypatch.setattr(settings, "validate_twilio_signature", True)
        monkeypatch.setattr(settings, "twilio_auth_token", "token_correto_do_server")
        monkeypatch.setattr(settings, "twilio_webhook_url", TEST_WEBHOOK_URL)

        params = {
            "MessageSid": "SM123",
            "From": "whatsapp:+5511999999999",
            "To": "whatsapp:+14155238886",
            "Body": "Olá",
            "NumMedia": "0",
        }
        url = f"{TEST_WEBHOOK_URL}/webhook/twilio?agent=rhawk_assistant"
        # Assina com token diferente do configurado no server
        signature = sign_request(url, params, auth_token="token_errado_do_atacante")

        response = client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data=params,
            headers={"X-Twilio-Signature": signature},
        )
        assert response.status_code == 403

    def test_tampered_body_rejects(self, monkeypatch):
        """Rejeita quando body foi alterado após assinatura."""
        from whatsapp_langchain.shared.config import settings

        monkeypatch.setattr(settings, "validate_twilio_signature", True)
        monkeypatch.setattr(settings, "twilio_auth_token", TEST_AUTH_TOKEN)
        monkeypatch.setattr(settings, "twilio_webhook_url", TEST_WEBHOOK_URL)

        params = {
            "MessageSid": "SM123",
            "From": "whatsapp:+5511999999999",
            "To": "whatsapp:+14155238886",
            "Body": "Mensagem original",
            "NumMedia": "0",
        }
        url = f"{TEST_WEBHOOK_URL}/webhook/twilio?agent=rhawk_assistant"
        signature = sign_request(url, params)

        # Envia com body adulterado
        tampered_params = {**params, "Body": "Mensagem adulterada"}
        response = client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data=tampered_params,
            headers={"X-Twilio-Signature": signature},
        )
        assert response.status_code == 403

    def test_missing_auth_token_returns_500(self, monkeypatch):
        """Retorna 500 se validação habilitada mas token não configurado."""
        from whatsapp_langchain.shared.config import settings

        monkeypatch.setattr(settings, "validate_twilio_signature", True)
        monkeypatch.setattr(settings, "twilio_auth_token", "")

        response = client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data={
                "MessageSid": "SM123",
                "From": "whatsapp:+5511999999999",
                "To": "whatsapp:+14155238886",
                "Body": "Olá",
                "NumMedia": "0",
            },
            headers={"X-Twilio-Signature": "qualquer"},
        )
        assert response.status_code == 500
        assert "auth token" in response.json()["detail"].lower()


class TestBuildValidationUrl:
    """Testes da reconstrução de URL para validação."""

    def test_uses_webhook_url_when_configured(self, monkeypatch):
        """Usa TWILIO_WEBHOOK_URL como base quando configurada."""
        from whatsapp_langchain.server.dependencies import build_validation_url

        monkeypatch.setattr(
            "whatsapp_langchain.server.dependencies.settings",
            type(
                "MockSettings",
                (),
                {"twilio_webhook_url": "https://tunnel.example.com"},
            )(),
        )

        # Simula um Request com path e query
        mock_request = type(
            "MockRequest",
            (),
            {
                "url": type(
                    "MockURL",
                    (),
                    {
                        "path": "/webhook/twilio",
                        "query": "agent=rhawk_assistant",
                        "__str__": lambda self: "http://localhost:8000/webhook/twilio?agent=rhawk_assistant",
                    },
                )()
            },
        )()

        result = build_validation_url(mock_request)
        assert (
            result == "https://tunnel.example.com/webhook/twilio?agent=rhawk_assistant"
        )

    def test_falls_back_to_request_url(self, monkeypatch):
        """Usa request.url quando TWILIO_WEBHOOK_URL não está configurada."""
        from whatsapp_langchain.server.dependencies import build_validation_url

        monkeypatch.setattr(
            "whatsapp_langchain.server.dependencies.settings",
            type("MockSettings", (), {"twilio_webhook_url": ""})(),
        )

        mock_request = type(
            "MockRequest",
            (),
            {
                "url": type(
                    "MockURL",
                    (),
                    {
                        "path": "/webhook/twilio",
                        "query": "agent=rhawk_assistant",
                        "__str__": lambda self: "http://localhost:8000/webhook/twilio?agent=rhawk_assistant",
                    },
                )()
            },
        )()

        result = build_validation_url(mock_request)
        assert result == "http://localhost:8000/webhook/twilio?agent=rhawk_assistant"

    def test_strips_trailing_slash_from_base(self, monkeypatch):
        """Remove trailing slash da URL base para evitar duplicata."""
        from whatsapp_langchain.server.dependencies import build_validation_url

        monkeypatch.setattr(
            "whatsapp_langchain.server.dependencies.settings",
            type(
                "MockSettings",
                (),
                {"twilio_webhook_url": "https://tunnel.example.com/"},
            )(),
        )

        mock_request = type(
            "MockRequest",
            (),
            {
                "url": type(
                    "MockURL",
                    (),
                    {
                        "path": "/webhook/twilio",
                        "query": "",
                        "__str__": lambda self: "http://localhost:8000/webhook/twilio",
                    },
                )()
            },
        )()

        result = build_validation_url(mock_request)
        assert result == "https://tunnel.example.com/webhook/twilio"


class TestWaIdNormalization:
    """Normalização de identidade inbound com fallback WaId."""

    @patch("whatsapp_langchain.server.routes.webhook.enqueue_or_buffer")
    def test_uses_from_when_present(self, mock_enqueue, monkeypatch):
        """Usa From (sem prefixo whatsapp:) quando presente."""
        from whatsapp_langchain.shared.config import settings
        from whatsapp_langchain.shared.models import EnqueueResult

        monkeypatch.setattr(settings, "validate_twilio_signature", False)
        mock_enqueue.return_value = EnqueueResult(message_id=1, is_buffered=False)

        client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data={
                "MessageSid": "SM123",
                "From": "whatsapp:+5511999999999",
                "To": "whatsapp:+14155238886",
                "Body": "Olá",
                "NumMedia": "0",
                "WaId": "5511888888888",
            },
        )

        # From tem prioridade sobre WaId
        call_kwargs = mock_enqueue.call_args
        assert call_kwargs.kwargs["phone_number"] == "+5511999999999"

    @patch("whatsapp_langchain.server.routes.webhook.enqueue_or_buffer")
    def test_falls_back_to_waid_without_plus(self, mock_enqueue, monkeypatch):
        """Usa WaId como fallback quando From está vazio, normaliza com +."""
        from whatsapp_langchain.shared.config import settings
        from whatsapp_langchain.shared.models import EnqueueResult

        monkeypatch.setattr(settings, "validate_twilio_signature", False)
        mock_enqueue.return_value = EnqueueResult(message_id=1, is_buffered=False)

        client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data={
                "MessageSid": "SM123",
                "From": "",
                "To": "whatsapp:+14155238886",
                "Body": "Olá",
                "NumMedia": "0",
                "WaId": "5511999999999",
            },
        )

        # WaId sem + deve ser normalizado para +E.164
        call_kwargs = mock_enqueue.call_args
        assert call_kwargs.kwargs["phone_number"] == "+5511999999999"

    @patch("whatsapp_langchain.server.routes.webhook.enqueue_or_buffer")
    def test_falls_back_to_waid_with_plus(self, mock_enqueue, monkeypatch):
        """Usa WaId como fallback quando já tem +."""
        from whatsapp_langchain.shared.config import settings
        from whatsapp_langchain.shared.models import EnqueueResult

        monkeypatch.setattr(settings, "validate_twilio_signature", False)
        mock_enqueue.return_value = EnqueueResult(message_id=1, is_buffered=False)

        client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data={
                "MessageSid": "SM123",
                "From": "",
                "To": "whatsapp:+14155238886",
                "Body": "Olá",
                "NumMedia": "0",
                "WaId": "+5511999999999",
            },
        )

        call_kwargs = mock_enqueue.call_args
        assert call_kwargs.kwargs["phone_number"] == "+5511999999999"

    def test_rejects_missing_sender_identity(self, monkeypatch):
        """Retorna 400 quando From e WaId estão ambos vazios."""
        from whatsapp_langchain.shared.config import settings

        monkeypatch.setattr(settings, "validate_twilio_signature", False)

        response = client.post(
            "/webhook/twilio?agent=rhawk_assistant",
            data={
                "MessageSid": "SM123",
                "From": "",
                "To": "whatsapp:+14155238886",
                "Body": "Olá",
                "NumMedia": "0",
                "WaId": "",
            },
        )

        assert response.status_code == 400
        assert "Missing sender identity" in response.json()["detail"]
