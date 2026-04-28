"""Testes de validação dos modelos Pydantic."""

import pytest
from pydantic import ValidationError

from whatsapp_langchain.shared.models import (
    EnqueueResult,
    MessageQueue,
    MessageStatus,
    TwilioWebhookPayload,
)


class TestMessageStatus:
    """Testes do enum MessageStatus."""

    def test_status_values(self):
        """Verifica que todos os status esperados existem."""
        assert MessageStatus.QUEUED == "queued"
        assert MessageStatus.PROCESSING == "processing"
        assert MessageStatus.DONE == "done"
        assert MessageStatus.FAILED == "failed"


class TestMessageQueue:
    """Testes do modelo MessageQueue."""

    def test_minimal_message(self):
        """Cria mensagem com campos mínimos obrigatórios."""
        msg = MessageQueue(
            id=1,
            phone_number="+5511999999999",
            agent_id="rhawk_assistant",
            thread_id="+5511999999999:rhawk_assistant",
            incoming_message="Olá!",
        )
        assert msg.status == MessageStatus.QUEUED
        assert msg.attempts == 0
        assert msg.max_attempts == 3
        assert msg.media_url is None

    def test_message_with_media(self):
        """Cria mensagem com mídia anexada."""
        msg = MessageQueue(
            id=1,
            phone_number="+5511999999999",
            agent_id="rhawk_assistant",
            thread_id="+5511999999999:rhawk_assistant",
            incoming_message="Veja esta foto",
            media_url="https://example.com/image.jpg",
            media_type="image/jpeg",
        )
        assert msg.media_url == "https://example.com/image.jpg"
        assert msg.media_type == "image/jpeg"

    def test_message_missing_required_field(self):
        """Falha se campo obrigatório está ausente."""
        with pytest.raises(ValidationError):
            MessageQueue(
                id=1,
                phone_number="+5511999999999",
                # agent_id ausente
                thread_id="test",
                incoming_message="Olá!",
            )


class TestTwilioWebhookPayload:
    """Testes do modelo TwilioWebhookPayload."""

    def test_full_payload(self):
        """Payload completo do Twilio."""
        payload = TwilioWebhookPayload(
            MessageSid="SM123",
            From="whatsapp:+5511999999999",
            To="whatsapp:+14155238886",
            Body="Olá, tudo bem?",
            NumMedia="0",
        )
        assert payload.MessageSid == "SM123"
        assert payload.Body == "Olá, tudo bem?"

    def test_payload_with_media(self):
        """Payload com mídia anexada."""
        payload = TwilioWebhookPayload(
            MessageSid="SM456",
            From="whatsapp:+5511999999999",
            To="whatsapp:+14155238886",
            Body="",
            NumMedia="1",
            MediaUrl0="https://api.twilio.com/media/123",
            MediaContentType0="image/jpeg",
        )
        assert payload.MediaUrl0 == "https://api.twilio.com/media/123"
        assert payload.MediaContentType0 == "image/jpeg"

    def test_payload_defaults(self):
        """Campos opcionais têm defaults corretos."""
        payload = TwilioWebhookPayload(
            MessageSid="SM789",
            From="whatsapp:+5511999999999",
            To="whatsapp:+14155238886",
        )
        assert payload.Body == ""
        assert payload.NumMedia == "0"
        assert payload.MediaUrl0 is None


class TestEnqueueResult:
    """Testes do modelo EnqueueResult."""

    def test_new_message(self):
        """Resultado de nova mensagem na fila."""
        result = EnqueueResult(message_id=42)
        assert result.message_id == 42
        assert result.is_buffered is False

    def test_buffered_message(self):
        """Resultado de mensagem agrupada (debounce)."""
        result = EnqueueResult(message_id=42, is_buffered=True)
        assert result.is_buffered is True
