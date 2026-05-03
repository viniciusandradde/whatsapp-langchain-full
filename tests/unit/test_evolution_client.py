"""Testes do EvolutionClient assíncrono.

Usa httpx mock para simular respostas da Evolution API
sem fazer chamadas HTTP reais.
"""

import json

import httpx
import pytest

from whatsapp_langchain.worker.evolution_client import (
    EVOLUTION_TYPING_DELAY_MS,
    EvolutionClient,
    EvolutionSendError,
    normalize_to_number,
)

TEST_API_URL = "https://evolution.example.com"
TEST_API_KEY = "6B46C86D-test-api-key"
TEST_INSTANCE = "vsa-tecnologia"


@pytest.fixture
def client():
    """EvolutionClient com credenciais de teste em modo real."""
    return EvolutionClient(
        api_url=TEST_API_URL,
        api_key=TEST_API_KEY,
        instance_name=TEST_INSTANCE,
    )


def mock_transport(status_code: int, body: dict) -> httpx.MockTransport:
    """Cria um transport mock que retorna a resposta configurada."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=body)

    return httpx.MockTransport(handler)


def patch_async_client(monkeypatch, transport: httpx.MockTransport) -> None:
    """Substitui httpx.AsyncClient.__init__ pra usar o transport mock."""
    original_init = httpx.AsyncClient.__init__

    def patched_init(self_client, **kwargs):
        kwargs["transport"] = transport
        original_init(self_client, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


class TestNormalizeNumber:
    """Helper que normaliza número pro formato Evolution (só dígitos)."""

    def test_strips_whatsapp_prefix(self):
        assert normalize_to_number("whatsapp:+5511999999999") == "5511999999999"

    def test_strips_plus_sign(self):
        assert normalize_to_number("+5511999999999") == "5511999999999"

    def test_passthrough_already_clean(self):
        assert normalize_to_number("5511999999999") == "5511999999999"

    def test_strips_spaces_and_punctuation(self):
        assert normalize_to_number("+55 (11) 99999-9999") == "5511999999999"


class TestEvolutionClientInit:
    """Testes de inicialização do cliente."""

    def test_stores_credentials(self, client):
        assert client.api_url == TEST_API_URL
        assert client.api_key == TEST_API_KEY
        assert client.instance_name == TEST_INSTANCE
        assert client.delivery_mode == "real"

    def test_constructs_send_text_url(self, client):
        assert client.send_text_url == (
            f"{TEST_API_URL}/message/sendText/{TEST_INSTANCE}"
        )

    def test_constructs_send_presence_url(self, client):
        assert client.send_presence_url == (
            f"{TEST_API_URL}/chat/sendPresence/{TEST_INSTANCE}"
        )

    def test_strips_trailing_slash_from_api_url(self):
        c = EvolutionClient(
            api_url=f"{TEST_API_URL}/",
            api_key=TEST_API_KEY,
            instance_name=TEST_INSTANCE,
        )
        assert c.api_url == TEST_API_URL
        assert "//message" not in c.send_text_url

    def test_rejects_empty_api_url(self):
        with pytest.raises(ValueError, match="api_url"):
            EvolutionClient("", TEST_API_KEY, TEST_INSTANCE)

    def test_rejects_empty_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            EvolutionClient(TEST_API_URL, "", TEST_INSTANCE)

    def test_rejects_empty_instance(self):
        with pytest.raises(ValueError, match="instance_name"):
            EvolutionClient(TEST_API_URL, TEST_API_KEY, "")

    def test_rejects_invalid_delivery_mode(self):
        with pytest.raises(ValueError, match="delivery_mode"):
            EvolutionClient(
                TEST_API_URL, TEST_API_KEY, TEST_INSTANCE, delivery_mode="lax"
            )

    def test_allows_mock_mode_without_real_credentials(self):
        c = EvolutionClient("", "", "", delivery_mode="mock")
        assert c.delivery_mode == "mock"


class TestSendMessage:
    """Testes do envio de mensagem via /message/sendText."""

    async def test_sends_message_successfully(self, client, monkeypatch):
        """Retorna o id de mensagem extraído de key.id no nível raiz."""
        expected_id = "BAE5F94E2C1A8F90"
        transport = mock_transport(
            201,
            {
                "key": {
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": True,
                    "id": expected_id,
                },
                "message": {"extendedTextMessage": {"text": "Olá!"}},
                "messageTimestamp": "1730000000",
                "status": "PENDING",
            },
        )
        patch_async_client(monkeypatch, transport)

        msg_id = await client.send_message("+5511999999999", "Olá!")
        assert msg_id == expected_id

    async def test_sends_correct_payload(self, client, monkeypatch):
        """POST inclui apikey header, JSON {number, text} e número normalizado."""
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["apikey"] = request.headers.get("apikey")
            captured["content_type"] = request.headers.get("content-type")
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(
                201,
                json={
                    "key": {
                        "remoteJid": "5511999999999@s.whatsapp.net",
                        "fromMe": True,
                        "id": "MSG123",
                    },
                    "status": "PENDING",
                },
            )

        patch_async_client(monkeypatch, httpx.MockTransport(handler))
        await client.send_message("whatsapp:+5511999999999", "Olá!")

        assert captured["method"] == "POST"
        assert captured["url"] == client.send_text_url
        assert captured["apikey"] == TEST_API_KEY
        assert "application/json" in (captured["content_type"] or "")
        assert captured["body"] == {"number": "5511999999999", "text": "Olá!"}

    async def test_raises_on_4xx_error(self, client, monkeypatch):
        transport = mock_transport(
            400, {"status": 400, "error": "Bad Request", "message": "invalid number"}
        )
        patch_async_client(monkeypatch, transport)

        with pytest.raises(EvolutionSendError) as exc_info:
            await client.send_message("+5511999999999", "Olá!")

        assert exc_info.value.status_code == 400
        assert "invalid number" in exc_info.value.detail

    async def test_raises_on_5xx_error(self, client, monkeypatch):
        transport = mock_transport(500, {"error": "Internal Server Error"})
        patch_async_client(monkeypatch, transport)

        with pytest.raises(EvolutionSendError) as exc_info:
            await client.send_message("+5511999999999", "Olá!")

        assert exc_info.value.status_code == 500

    async def test_raises_on_401_unauthorized(self, client, monkeypatch):
        transport = mock_transport(401, {"error": "Unauthorized"})
        patch_async_client(monkeypatch, transport)

        with pytest.raises(EvolutionSendError) as exc_info:
            await client.send_message("+5511999999999", "Olá!")

        assert exc_info.value.status_code == 401

    async def test_splits_long_message_across_multiple_requests(
        self, client, monkeypatch
    ):
        captured_bodies: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode())
            captured_bodies.append(payload["text"])
            return httpx.Response(
                201,
                json={
                    "key": {
                        "remoteJid": "5511999999999@s.whatsapp.net",
                        "fromMe": True,
                        "id": f"MSG{len(captured_bodies)}",
                    },
                    "status": "PENDING",
                },
            )

        patch_async_client(monkeypatch, httpx.MockTransport(handler))
        long_body = ("bloco de texto " * 140).strip()
        msg_id = await client.send_message("+5511999999999", long_body)

        assert len(captured_bodies) >= 2
        assert all(len(chunk) <= 1600 for chunk in captured_bodies)
        assert msg_id == f"MSG{len(captured_bodies)}"

    async def test_returns_empty_id_when_response_missing_key(
        self, client, monkeypatch
    ):
        """Resposta sem key.id não derruba o cliente — retorna string vazia."""
        transport = mock_transport(201, {"status": "PENDING"})
        patch_async_client(monkeypatch, transport)

        msg_id = await client.send_message("+5511999999999", "Olá!")
        assert msg_id == ""


class TestSendTyping:
    """Testes do typing indicator via /chat/sendPresence."""

    async def test_sends_typing_successfully(self, client, monkeypatch):
        transport = mock_transport(201, {})
        patch_async_client(monkeypatch, transport)

        result = await client.send_typing("+5511999999999")
        assert result is True

    async def test_sends_correct_presence_payload(self, client, monkeypatch):
        """Payload usa formato options{delay,presence,number} da doc oficial."""
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["apikey"] = request.headers.get("apikey")
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(201, json={})

        patch_async_client(monkeypatch, httpx.MockTransport(handler))
        await client.send_typing("whatsapp:+5511999999999")

        assert captured["url"] == client.send_presence_url
        assert captured["apikey"] == TEST_API_KEY
        assert captured["body"]["number"] == "5511999999999"
        assert captured["body"]["options"]["presence"] == "composing"
        assert captured["body"]["options"]["delay"] == EVOLUTION_TYPING_DELAY_MS
        assert captured["body"]["options"]["number"] == "5511999999999"

    async def test_returns_false_on_error(self, client, monkeypatch):
        """Typing best-effort — 4xx vira False sem levantar exceção."""
        transport = mock_transport(400, {"error": "bad"})
        patch_async_client(monkeypatch, transport)

        result = await client.send_typing("+5511999999999")
        assert result is False

    async def test_does_not_raise_on_network_exception(self, client, monkeypatch):
        """Exception no httpx vira False (best-effort)."""

        def raise_init(self_client, **kwargs):
            raise Exception("network down")

        monkeypatch.setattr(httpx.AsyncClient, "__init__", raise_init)
        result = await client.send_typing("+5511999999999")
        assert result is False

    async def test_skips_in_mock_mode(self, monkeypatch):
        """Mock mode não chama HTTP — retorna False direto."""
        c = EvolutionClient("", "", "", delivery_mode="mock")

        called = {"flag": False}

        def patched_init(self_client, **kwargs):
            called["flag"] = True

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await c.send_typing("+5511999999999")
        assert result is False
        assert called["flag"] is False

    async def test_accepts_message_id_param_for_protocol_compatibility(
        self, client, monkeypatch
    ):
        """`message_id` é aceito pra compat com OutboundClient (P3) e ignorado."""
        transport = mock_transport(201, {})
        patch_async_client(monkeypatch, transport)

        result = await client.send_typing("+5511999999999", message_id="anything")
        assert result is True


class TestMockMode:
    """Mock mode local pro dev sem credenciais."""

    async def test_mock_send_message_returns_synthetic_id(self):
        c = EvolutionClient("", "", "", delivery_mode="mock")
        msg_id = await c.send_message("+5511999999999", "Olá!")
        assert msg_id.startswith("mock-evo-")
        assert len(msg_id) > len("mock-evo-")

    async def test_mock_send_message_does_not_call_http(self, monkeypatch):
        """Mock mode pula httpx completamente — nenhuma chamada de rede."""
        called = {"flag": False}

        def patched_init(self_client, **kwargs):
            called["flag"] = True

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        c = EvolutionClient("", "", "", delivery_mode="mock")
        await c.send_message("+5511999999999", "Olá!")
        assert called["flag"] is False
