"""Testes de validação dos modelos Pydantic."""

import pytest
from pydantic import ValidationError

from whatsapp_langchain.shared.models import (
    EnqueueResult,
    MessageQueue,
    MessageStatus,
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
            agent_id="vsa_tech",
            thread_id="+5511999999999:vsa_tech",
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
            agent_id="vsa_tech",
            thread_id="+5511999999999:vsa_tech",
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
