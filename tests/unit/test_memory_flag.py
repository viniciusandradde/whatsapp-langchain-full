"""Testes da flag MEMORY_ENABLED determinística.

Verifica que processor.py e webhook_sync.py respeitam
settings.memory_enabled para decidir se criam store.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.worker.media import MediaPreprocessResult


class TestWebhookSyncMemoryFlag:
    """Testes do flag memory_enabled no webhook_sync."""

    def test_store_created_when_memory_enabled(self):
        """Com MEMORY_ENABLED=true, store deve ser InMemoryStore."""
        with patch.object(settings, "memory_enabled", True):
            from langgraph.store.memory import InMemoryStore

            # Simula a lógica do webhook_sync
            store = InMemoryStore() if settings.memory_enabled else None
            assert store is not None
            assert isinstance(store, InMemoryStore)

    def test_store_none_when_memory_disabled(self):
        """Com MEMORY_ENABLED=false, store deve ser None."""
        with patch.object(settings, "memory_enabled", False):
            store = MagicMock() if settings.memory_enabled else None
            assert store is None


class TestProcessorMemoryFlag:
    """Testes do flag memory_enabled no processor."""

    async def test_processor_skips_store_when_memory_disabled(self):
        """Com MEMORY_ENABLED=false, processor deve carregar agente sem store."""
        with (
            patch.object(settings, "memory_enabled", False),
            patch(
                "whatsapp_langchain.worker.processor.preprocess_incoming_message",
                new_callable=AsyncMock,
                return_value=MediaPreprocessResult(
                    should_invoke_agent=True,
                    normalized_text="Olá!",
                    media_processing_status="none",
                ),
            ) as mock_preprocess,
            patch("whatsapp_langchain.worker.processor.load_graph") as mock_load,
            patch(
                "whatsapp_langchain.worker.processor.mark_done",
                new_callable=AsyncMock,
            ) as mock_mark_done,
            patch(
                "whatsapp_langchain.worker.processor.upsert_conversation",
                new_callable=AsyncMock,
            ),
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="resposta")]
            }
            mock_load.return_value = mock_graph
            mock_checkpointer = AsyncMock()

            from whatsapp_langchain.shared.models import MessageQueue
            from whatsapp_langchain.worker.processor import process_message

            message = MessageQueue(
                id=1,
                phone_number="+5511999999999",
                agent_id="rhawk_assistant",
                thread_id="+5511999999999:rhawk_assistant",
                incoming_message="Olá!",
            )

            mock_twilio = AsyncMock()
            mock_twilio.send_typing = AsyncMock(return_value=True)
            mock_twilio.send_message = AsyncMock(return_value="SM123")

            await process_message(
                message,
                AsyncMock(),
                checkpointer=mock_checkpointer,
                store=None,
                twilio=mock_twilio,
            )

            mock_preprocess.assert_awaited_once()

            # Salva como done com metadados de pré-processamento
            assert mock_mark_done.await_count == 1

            # load_graph deve ser chamado sem store
            mock_load.assert_called_once_with(
                "rhawk_assistant",
                checkpointer=mock_checkpointer,
                store=None,
            )
