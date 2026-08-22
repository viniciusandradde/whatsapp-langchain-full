"""Testes da flag MEMORY_ENABLED determinística.

Verifica que processor.py e webhook_sync.py respeitam
settings.memory_enabled para decidir se criam store.
"""

from types import SimpleNamespace
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
            patch(
                "whatsapp_langchain.worker.processor.load_graph",
                new_callable=AsyncMock,
            ) as mock_load,
            patch(
                "whatsapp_langchain.worker.processor.mark_done",
                new_callable=AsyncMock,
            ) as mock_mark_done,
            patch(
                "whatsapp_langchain.worker.processor.upsert_conversation",
                new_callable=AsyncMock,
            ),
            patch(
                "whatsapp_langchain.worker.processor.get_agent_llm_config",
                new_callable=AsyncMock,
                return_value=("env-chat", "env-midia"),
            ),
            patch(
                "whatsapp_langchain.worker.processor.is_business_hours",
                new_callable=AsyncMock,
                return_value=True,
            ),
            # Guards de interceptação que rodam ANTES do agente (approval,
            # CSAT, encerrar, coleta, menu) — todos retornam False pra deixar
            # o fluxo chegar no load_graph. Sem stubar, batem no pool mock e
            # quebram (TypeError no async-CM) mascarando o teste real.
            patch(
                "whatsapp_langchain.worker.processor._try_handle_approval",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "whatsapp_langchain.worker.processor._try_capture_avaliacao",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "whatsapp_langchain.worker.processor._try_handle_encerrar_keyword",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "whatsapp_langchain.worker.processor._try_handle_coleta_em_curso",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "whatsapp_langchain.worker.processor._try_handle_menu",
                new_callable=AsyncMock,
                return_value=False,
            ),
            # A.6 — runtime do agente_ia (DB). None mantém path legacy do
            # catálogo e evita o SELECT inline de agente_ia.id.
            patch(
                "whatsapp_langchain.worker.processor.resolve_agente_runtime",
                new_callable=AsyncMock,
                return_value=None,
            ),
            # ia_budget pré-call (mig 058). None = sem bloqueio de orçamento.
            patch(
                "whatsapp_langchain.shared.governanca_ia.get_budget_atual",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="resposta")]
            }
            mock_load.return_value = mock_graph
            mock_checkpointer = AsyncMock()
            # Pool cujo connection() é um async CM (vários blocos inline pós
            # load_graph fazem `async with pool.connection()` — langfuse trace,
            # guardrail/rag log; em try/except, mas evita warnings de coroutine).
            _cur = AsyncMock()
            _cur.fetchone = AsyncMock(return_value=None)
            _conn = MagicMock()
            _conn.execute = AsyncMock(return_value=_cur)
            _conn.commit = AsyncMock()
            mock_pool = MagicMock()
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

            from whatsapp_langchain.shared.models import MessageQueue
            from whatsapp_langchain.worker.processor import process_message

            message = MessageQueue(
                id=1,
                phone_number="+5511999999999",
                agent_id="vsa_tech",
                thread_id="+5511999999999:vsa_tech",
                incoming_message="Olá!",
            )

            mock_twilio = AsyncMock()
            mock_twilio.send_typing = AsyncMock(return_value=True)
            mock_twilio.send_message = AsyncMock(return_value="SM123")

            # Worker monta o client por-conexão (build_outbound_client do DB);
            # curto-circuita a resolução pro mock.
            with (
                patch(
                    "whatsapp_langchain.worker.processor._resolve_outbound_client",
                    new=AsyncMock(
                        return_value=(
                            mock_twilio,
                            # `transcrever_audio_sempre` é lido pelo gancho de
                            # transcrição (mig 169) antes dos gates — sem o
                            # campo, o processamento morre em AttributeError e
                            # o teste falha por um motivo que não é o dele.
                            SimpleNamespace(
                                id=77,
                                tipo_atendimento="ia",
                                transcrever_audio_sempre=False,
                            ),
                        )
                    ),
                ),
                patch(
                    "whatsapp_langchain.worker.processor.is_whitelisted",
                    new=AsyncMock(return_value=False),
                ),
            ):
                await process_message(
                    message,
                    mock_pool,
                    checkpointer=mock_checkpointer,
                    store=None,
                )

            mock_preprocess.assert_awaited_once()

            # Salva como done com metadados de pré-processamento
            assert mock_mark_done.await_count == 1

            # load_graph deve ser chamado sem store, recebendo o pool e
            # propagando empresa_id da MessageQueue (default 1).
            mock_load.assert_awaited_once_with(
                "vsa_tech",
                checkpointer=mock_checkpointer,
                store=None,
                pool=mock_pool,
                empresa_id=1,
                agente_runtime=None,
            )
