"""Testes do TwilioClient assíncrono.

Usa httpx mock para simular respostas da API do Twilio
sem fazer chamadas HTTP reais.
"""

from urllib.parse import parse_qs

import httpx
import pytest

from whatsapp_langchain.worker.twilio_client import (
    TwilioClient,
    TwilioSendError,
)

TEST_SID = "ACtest123"
TEST_API_KEY_SID = "SKtest456"
TEST_API_KEY_SECRET = "test_api_key_secret"
TEST_FROM = "whatsapp:+14155238886"
VALID_MESSAGE_SID = "SM1234567890abcdef1234567890abcdef"


@pytest.fixture
def client():
    """TwilioClient com credenciais de teste."""
    return TwilioClient(
        account_sid=TEST_SID,
        api_key_sid=TEST_API_KEY_SID,
        api_key_secret=TEST_API_KEY_SECRET,
        from_number=TEST_FROM,
    )


def mock_transport(status_code: int, body: dict) -> httpx.MockTransport:
    """Cria um transport mock que retorna a resposta configurada.

    Args:
        status_code: HTTP status code da resposta.
        body: Body JSON da resposta.

    Returns:
        MockTransport configurado.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            json=body,
        )

    return httpx.MockTransport(handler)


class TestTwilioClientInit:
    """Testes de inicialização do cliente."""

    def test_constructs_messages_url(self, client):
        """URL da Messages API inclui o account_sid."""
        assert TEST_SID in client.messages_url
        assert client.messages_url.endswith("/Messages.json")

    def test_stores_credentials(self, client):
        """Armazena credenciais para uso nas chamadas."""
        assert client.account_sid == TEST_SID
        assert client.api_key_sid == TEST_API_KEY_SID
        assert client.api_key_secret == TEST_API_KEY_SECRET
        assert client.from_number == TEST_FROM

    def test_rejects_empty_account_sid(self):
        """Fail-fast se account_sid vazio."""
        with pytest.raises(ValueError, match="account_sid"):
            TwilioClient("", TEST_API_KEY_SID, TEST_API_KEY_SECRET, TEST_FROM)

    def test_rejects_empty_api_key_sid(self):
        """Fail-fast se api_key_sid vazio."""
        with pytest.raises(ValueError, match="api_key_sid"):
            TwilioClient(TEST_SID, "", TEST_API_KEY_SECRET, TEST_FROM)

    def test_rejects_empty_api_key_secret(self):
        """Fail-fast se api_key_secret vazio."""
        with pytest.raises(ValueError, match="api_key_secret"):
            TwilioClient(TEST_SID, TEST_API_KEY_SID, "", TEST_FROM)

    def test_rejects_empty_from_number(self):
        """Fail-fast se from_number vazio."""
        with pytest.raises(ValueError, match="from_number"):
            TwilioClient(TEST_SID, TEST_API_KEY_SID, TEST_API_KEY_SECRET, "")

    def test_rejects_invalid_from_number_format(self):
        """Fail-fast se from_number não começa com whatsapp:+."""
        with pytest.raises(ValueError, match="whatsapp:\\+"):
            TwilioClient(
                TEST_SID, TEST_API_KEY_SID, TEST_API_KEY_SECRET, "+14155238886"
            )

    def test_rejects_from_number_without_plus(self):
        """Fail-fast se from_number tem whatsapp: mas sem +."""
        with pytest.raises(ValueError, match="whatsapp:\\+"):
            TwilioClient(
                TEST_SID, TEST_API_KEY_SID, TEST_API_KEY_SECRET, "whatsapp:14155238886"
            )

    def test_allows_mock_mode_without_real_credentials(self):
        """Modo mock não exige credenciais Twilio válidas."""
        client = TwilioClient("", "", "", "", delivery_mode="mock")
        assert client.delivery_mode == "mock"


class TestSendMessage:
    """Testes do envio de mensagem via Twilio Messages API."""

    async def test_sends_message_successfully(self, client, monkeypatch):
        """Envia mensagem e retorna o SID."""
        expected_sid = "SM1234567890abcdef"

        transport = mock_transport(
            201,
            {"sid": expected_sid, "status": "queued"},
        )

        # Substitui httpx.AsyncClient para usar o mock transport
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        sid = await client.send_message("+5511999999999", "Olá!")
        assert sid == expected_sid

    async def test_sends_correct_payload(self, client, monkeypatch):
        """Verifica que o payload enviado está correto."""
        captured_request = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_request["url"] = str(request.url)
            captured_request["content"] = request.content.decode()
            captured_request["auth"] = request.headers.get("authorization")
            return httpx.Response(
                201,
                json={"sid": "SM123", "status": "queued"},
            )

        transport = httpx.MockTransport(handler)
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        await client.send_message("+5511999999999", "Olá!")

        # Verifica URL
        assert client.messages_url in captured_request["url"]

        # Verifica payload form-encoded
        content = captured_request["content"]
        assert "From=whatsapp" in content
        assert "To=whatsapp" in content
        assert "Body=" in content

        # Verifica autenticação Basic com API Key (não auth_token)
        assert captured_request["auth"] is not None
        assert "Basic" in captured_request["auth"]

    async def test_raises_on_4xx_error(self, client, monkeypatch):
        """Levanta TwilioSendError em erro 4xx."""
        transport = mock_transport(
            400,
            {"code": 21211, "message": "Invalid 'To' Phone Number"},
        )
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        with pytest.raises(TwilioSendError) as exc_info:
            await client.send_message("+invalid", "Olá!")

        assert exc_info.value.status_code == 400
        assert "21211" in exc_info.value.detail

    async def test_raises_on_5xx_error(self, client, monkeypatch):
        """Levanta TwilioSendError em erro 5xx."""
        transport = mock_transport(
            500,
            {"message": "Internal Server Error"},
        )
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        with pytest.raises(TwilioSendError) as exc_info:
            await client.send_message("+5511999999999", "Olá!")

        assert exc_info.value.status_code == 500

    async def test_raises_on_401_auth_error(self, client, monkeypatch):
        """Levanta TwilioSendError com credenciais inválidas."""
        transport = mock_transport(
            401,
            {"code": 20003, "message": "Authenticate"},
        )
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        with pytest.raises(TwilioSendError) as exc_info:
            await client.send_message("+5511999999999", "Olá!")

        assert exc_info.value.status_code == 401

    async def test_splits_long_message_across_multiple_requests(
        self, client, monkeypatch
    ):
        """Bodies acima de 1600 chars são enviados em múltiplos chunks."""
        captured_bodies: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            params = parse_qs(request.content.decode())
            captured_bodies.append(params["Body"][0])
            return httpx.Response(
                201,
                json={
                    "sid": f"SM{len(captured_bodies):032d}",
                    "status": "queued",
                },
            )

        transport = httpx.MockTransport(handler)
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        long_body = ("bloco de texto " * 140).strip()

        sid = await client.send_message("+5511999999999", long_body)

        assert len(captured_bodies) >= 2
        assert all(len(chunk) <= 1600 for chunk in captured_bodies)
        assert sid == f"SM{len(captured_bodies):032d}"


class TestSendTyping:
    """Testes do typing indicator (Public Beta, best-effort)."""

    async def test_skips_without_message_sid(self, client):
        """Typing sem message_sid retorna False (nada a enviar)."""
        result = await client.send_typing("+5511999999999")
        assert result is False

    async def test_skips_with_none_message_sid(self, client):
        """Typing com message_sid=None retorna False."""
        result = await client.send_typing("+5511999999999", None)
        assert result is False

    async def test_sends_typing_successfully(self, client, monkeypatch):
        """Typing com message_sid faz POST e retorna True."""
        transport = mock_transport(200, {"success": True})
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        result = await client.send_typing("+5511999999999", VALID_MESSAGE_SID)
        assert result is True

    async def test_returns_false_on_error(self, client, monkeypatch):
        """Typing retorna False em erro HTTP (best-effort, sem exceção)."""
        transport = mock_transport(400, {"error": "bad request"})
        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = transport
            original_init(self_client, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        result = await client.send_typing("+5511999999999", VALID_MESSAGE_SID)
        assert result is False

    async def test_does_not_raise_on_exception(self, client, monkeypatch):
        """Typing nunca levanta exceção (best-effort)."""

        def raise_init(self_client, **kwargs):
            raise Exception("network error")

        monkeypatch.setattr(httpx.AsyncClient, "__init__", raise_init)

        result = await client.send_typing("+5511999999999", VALID_MESSAGE_SID)
        assert result is False

    async def test_skips_typing_with_invalid_message_sid_format(self, client):
        """Typing com SID fake/local invalido não chama o Twilio."""
        result = await client.send_typing("+5511999999999", "SM123abc")
        assert result is False


class TestMockMode:
    """Testes do modo mock local do cliente."""

    async def test_mock_send_message_returns_fake_sid(self):
        """Mock mode simula envio sem quota externa."""
        client = TwilioClient("", "", "", "", delivery_mode="mock")
        sid = await client.send_message("+5511999999999", "Olá!")
        assert sid.startswith("SM")
        assert len(sid) == 34
