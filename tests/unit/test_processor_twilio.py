"""Testes do fluxo send_message → mark_done / mark_failed no processor.

Garante que:
- mark_done NÃO roda quando send_message falha
- mark_failed É chamado no erro de envio
- auto-response de mídia também respeita a regra (envia antes de mark_done)
- Falha no auto-response entra em retry via mark_failed
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.shared.models import MessageQueue
from whatsapp_langchain.worker.media import MediaPreprocessResult
from whatsapp_langchain.worker.twilio_client import TwilioSendError

# --- Fixtures ---


@pytest.fixture
def message():
    """Mensagem de texto padrão para testes."""
    return MessageQueue(
        id=1,
        message_id="SM123",
        phone_number="+5511999999999",
        agent_id="rhawk_assistant",
        thread_id="+5511999999999:rhawk_assistant",
        incoming_message="Olá!",
    )


@pytest.fixture
def media_message():
    """Mensagem com mídia desabilitada/falha para testar auto-response."""
    return MessageQueue(
        id=2,
        message_id="MM456",
        phone_number="+5511999999999",
        agent_id="rhawk_assistant",
        thread_id="+5511999999999:rhawk_assistant",
        incoming_message="",
        media_url="https://api.twilio.com/media/test.jpg",
        media_type="image/jpeg",
    )


@pytest.fixture
def mock_twilio():
    """TwilioClient mock com send_message e send_typing."""
    twilio = AsyncMock()
    twilio.send_typing = AsyncMock(return_value=True)
    twilio.send_message = AsyncMock(return_value="SM_RESPONSE_123")
    return twilio


# --- Helpers ---


def _patch_processor(preprocess_result):
    """Retorna context managers para mockar dependências do processor."""
    return (
        patch(
            "whatsapp_langchain.worker.processor.preprocess_incoming_message",
            new_callable=AsyncMock,
            return_value=preprocess_result,
        ),
        patch("whatsapp_langchain.worker.processor.load_graph"),
        patch(
            "whatsapp_langchain.worker.processor.mark_done",
            new_callable=AsyncMock,
        ),
        patch(
            "whatsapp_langchain.worker.processor.mark_failed",
            new_callable=AsyncMock,
        ),
        patch(
            "whatsapp_langchain.worker.processor.upsert_conversation",
            new_callable=AsyncMock,
        ),
    )


TEXT_PREPROCESS = MediaPreprocessResult(
    should_invoke_agent=True,
    normalized_text="Olá!",
    media_processing_status="none",
)

MEDIA_DISABLED_PREPROCESS = MediaPreprocessResult(
    should_invoke_agent=False,
    normalized_text=None,
    media_processing_status="disabled",
    auto_response="Imagens estão desabilitadas neste momento.",
)


# === Testes do fluxo normal (texto) ===


class TestSendMessageMarkDone:
    """Garante que mark_done só ocorre após send_message bem-sucedido."""

    async def test_mark_done_after_successful_send(self, message, mock_twilio):
        """Fluxo feliz: send_message ok → mark_done chamado."""
        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="Resposta do agente")]
            }
            mock_load.return_value = mock_graph

            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                message,
                AsyncMock(),
                checkpointer=AsyncMock(),
                twilio=mock_twilio,
            )

            # send_message chamado com a resposta do agente
            mock_twilio.send_message.assert_awaited_once_with(
                "+5511999999999", "Resposta do agente"
            )
            # mark_done chamado
            assert mock_done.await_count == 1
            # mark_failed NÃO chamado
            mock_failed.assert_not_awaited()

    async def test_mark_done_not_called_when_send_fails(self, message, mock_twilio):
        """send_message falha → mark_done NÃO é chamado, mark_failed SIM."""
        mock_twilio.send_message = AsyncMock(
            side_effect=TwilioSendError(500, "Internal Server Error")
        )

        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="Resposta do agente")]
            }
            mock_load.return_value = mock_graph

            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                message,
                AsyncMock(),
                checkpointer=AsyncMock(),
                twilio=mock_twilio,
            )

            # send_message foi chamado (e falhou)
            mock_twilio.send_message.assert_awaited_once()
            # mark_done NÃO chamado
            mock_done.assert_not_awaited()
            # mark_failed chamado com o erro
            mock_failed.assert_awaited_once()
            error_arg = mock_failed.call_args[0][2]
            assert "500" in error_arg

    async def test_mark_failed_on_generic_send_exception(self, message, mock_twilio):
        """Exceção genérica no send_message → mark_failed."""
        mock_twilio.send_message = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="Resposta")]
            }
            mock_load.return_value = mock_graph

            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                message,
                AsyncMock(),
                checkpointer=AsyncMock(),
                twilio=mock_twilio,
            )

            mock_done.assert_not_awaited()
            mock_failed.assert_awaited_once()
            assert "Connection timeout" in mock_failed.call_args[0][2]


# === Testes do fluxo auto-response (mídia) ===


class TestAutoResponseTwilio:
    """Garante que auto-response de mídia também envia via Twilio antes de mark_done."""

    async def test_auto_response_sends_via_twilio(self, media_message, mock_twilio):
        """Auto-response de mídia desabilitada envia via Twilio antes de mark_done."""
        patches = _patch_processor(MEDIA_DISABLED_PREPROCESS)
        with (
            patches[0],
            patches[1],
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
        ):
            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                media_message,
                AsyncMock(),
                checkpointer=AsyncMock(),
                twilio=mock_twilio,
            )

            # Auto-response enviada via Twilio
            mock_twilio.send_message.assert_awaited_once_with(
                "+5511999999999",
                "Imagens estão desabilitadas neste momento.",
            )
            # mark_done chamado após envio
            assert mock_done.await_count == 1
            mock_failed.assert_not_awaited()

    async def test_auto_response_mark_failed_when_send_fails(
        self, media_message, mock_twilio
    ):
        """Auto-response falha no envio → mark_failed (retry)."""
        mock_twilio.send_message = AsyncMock(
            side_effect=TwilioSendError(503, "Service Unavailable")
        )

        patches = _patch_processor(MEDIA_DISABLED_PREPROCESS)
        with (
            patches[0],
            patches[1],
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
        ):
            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                media_message,
                AsyncMock(),
                checkpointer=AsyncMock(),
                twilio=mock_twilio,
            )

            # send_message foi chamado (e falhou)
            mock_twilio.send_message.assert_awaited_once()
            # mark_done NÃO chamado
            mock_done.assert_not_awaited()
            # mark_failed chamado
            mock_failed.assert_awaited_once()
            assert "503" in mock_failed.call_args[0][2]
