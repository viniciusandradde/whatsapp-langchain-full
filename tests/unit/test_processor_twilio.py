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
        agent_id="vsa_tech",
        thread_id="+5511999999999:vsa_tech",
        incoming_message="Olá!",
    )


@pytest.fixture
def media_message():
    """Mensagem com mídia desabilitada/falha para testar auto-response."""
    return MessageQueue(
        id=2,
        message_id="MM456",
        phone_number="+5511999999999",
        agent_id="vsa_tech",
        thread_id="+5511999999999:vsa_tech",
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


@pytest.fixture
def mock_evolution():
    """EvolutionClient mock com send_message e send_typing."""
    evo = AsyncMock()
    evo.send_typing = AsyncMock(return_value=True)
    evo.send_message = AsyncMock(return_value="EVO_RESPONSE_456")
    return evo


@pytest.fixture
def mock_clients(mock_twilio, mock_evolution):
    """Dict provider→OutboundClient consumido pelo process_message."""
    return {
        "twilio_sandbox": mock_twilio,
        "twilio_prod": mock_twilio,
        "waba": mock_twilio,
        "evolution": mock_evolution,
    }


# --- Helpers ---


def _patch_processor(preprocess_result, *, atendimento_lookup=None):
    """Retorna context managers para mockar dependências do processor.

    `atendimento_lookup`: AsyncMock pra get_atendimento_by_id; default
    retorna None (caminho normal — sem handoff).
    """
    return (
        patch(
            "whatsapp_langchain.worker.processor.preprocess_incoming_message",
            new_callable=AsyncMock,
            return_value=preprocess_result,
        ),
        patch(
            "whatsapp_langchain.worker.processor.load_graph",
            new_callable=AsyncMock,
        ),
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
        patch(
            "whatsapp_langchain.worker.processor.get_agent_llm_config",
            new_callable=AsyncMock,
            return_value=("env-chat", "env-midia"),
        ),
        patch(
            "whatsapp_langchain.worker.processor.get_atendimento_by_id",
            new=atendimento_lookup or AsyncMock(return_value=None),
        ),
        # M6.a — sempre dentro do expediente nos testes (gate ortogonal).
        patch(
            "whatsapp_langchain.worker.processor.is_business_hours",
            new_callable=AsyncMock,
            return_value=True,
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

    async def test_prefixes_message_when_outside_business_hours(
        self, message, mock_twilio, mock_clients
    ):
        """M6.a: is_business_hours=False prepende '[FORA DO EXPEDIENTE] '."""
        patches = _patch_processor(TEXT_PREPROCESS)
        # Override patches[7] (is_business_hours) pra retornar False
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patch(
                "whatsapp_langchain.worker.processor.is_business_hours",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="Voltamos em breve!")]
            }
            mock_load.return_value = mock_graph

            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                message,
                AsyncMock(),
                checkpointer=AsyncMock(),
                clients=mock_clients,
            )

            # Verifica o conteúdo passado pro agente
            call_args = mock_graph.ainvoke.await_args
            human_msg = call_args.args[0]["messages"][0]
            assert human_msg.content.startswith("[FORA DO EXPEDIENTE] ")
            assert "Olá!" in human_msg.content

    async def test_mark_done_after_successful_send(
        self, message, mock_twilio, mock_clients
    ):
        """Fluxo feliz: send_message ok → mark_done chamado."""
        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
            patches[5],
            patches[6],
            patches[7],
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
                clients=mock_clients,
            )

            # send_message chamado com a resposta do agente
            mock_twilio.send_message.assert_awaited_once_with(
                "+5511999999999", "Resposta do agente"
            )
            # mark_done chamado
            assert mock_done.await_count == 1
            # mark_failed NÃO chamado
            mock_failed.assert_not_awaited()

    async def test_mark_done_not_called_when_send_fails(
        self, message, mock_twilio, mock_clients
    ):
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
            patches[5],
            patches[6],
            patches[7],
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
                clients=mock_clients,
            )

            # send_message foi chamado (e falhou)
            mock_twilio.send_message.assert_awaited_once()
            # mark_done NÃO chamado
            mock_done.assert_not_awaited()
            # mark_failed chamado com o erro
            mock_failed.assert_awaited_once()
            error_arg = mock_failed.call_args[0][2]
            assert "500" in error_arg

    async def test_mark_failed_on_generic_send_exception(
        self, message, mock_twilio, mock_clients
    ):
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
            patches[5],
            patches[6],
            patches[7],
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
                clients=mock_clients,
            )

            mock_done.assert_not_awaited()
            mock_failed.assert_awaited_once()
            assert "Connection timeout" in mock_failed.call_args[0][2]


# === Testes do fluxo auto-response (mídia) ===


class TestAutoResponseTwilio:
    """Garante que auto-response de mídia também envia via Twilio antes de mark_done."""

    async def test_auto_response_sends_via_twilio(
        self, media_message, mock_twilio, mock_clients
    ):
        """Auto-response de mídia desabilitada envia via Twilio antes de mark_done."""
        patches = _patch_processor(MEDIA_DISABLED_PREPROCESS)
        with (
            patches[0],
            patches[1],
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
            patches[5],
            patches[6],
            patches[7],
        ):
            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                media_message,
                AsyncMock(),
                checkpointer=AsyncMock(),
                clients=mock_clients,
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
        self, media_message, mock_twilio, mock_clients
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
            patches[5],
            patches[6],
            patches[7],
        ):
            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                media_message,
                AsyncMock(),
                checkpointer=AsyncMock(),
                clients=mock_clients,
            )

            # send_message foi chamado (e falhou)
            mock_twilio.send_message.assert_awaited_once()
            # mark_done NÃO chamado
            mock_done.assert_not_awaited()
            # mark_failed chamado
            mock_failed.assert_awaited_once()
            assert "503" in mock_failed.call_args[0][2]


# === Testes do handoff humano (M4.c) ===


class TestHandoffHumano:
    """Worker pula o agente IA quando atendimento está em_andamento+assigned."""

    @staticmethod
    def _atendimento(status: str, assigned_to: str | None = None):
        from datetime import UTC, datetime

        from whatsapp_langchain.shared.models import Atendimento

        now = datetime.now(UTC)
        return Atendimento(
            id=42,
            empresa_id=1,
            cliente_id=10,
            conexao_id=1,
            status=status,
            assigned_to_user_id=assigned_to,
            last_message_at=now,
            created_at=now,
            updated_at=now,
        )

    async def test_skips_agent_when_em_andamento_with_assignee(
        self, mock_twilio, mock_clients
    ):
        """Atendimento claim'ado: worker marca done com marker, sem invocar agente."""
        msg = MessageQueue(
            id=99,
            atendimento_id=42,
            phone_number="+5511999999999",
            agent_id="vsa_tech",
            thread_id="+5511999999999:vsa_tech",
            incoming_message="oi novamente",
        )
        atd = AsyncMock(
            return_value=self._atendimento("em_andamento", assigned_to="user-x")
        )
        patches = _patch_processor(TEXT_PREPROCESS, atendimento_lookup=atd)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
            patches[5],
            patches[6],
            patches[7],
        ):
            from whatsapp_langchain.worker.processor import (
                HANDOFF_HUMANO_MARKER,
                process_message,
            )

            await process_message(
                msg,
                AsyncMock(),
                checkpointer=AsyncMock(),
                clients=mock_clients,
            )

            # Agente NÃO carregado, Twilio NÃO chamado
            mock_load.assert_not_awaited()
            mock_twilio.send_message.assert_not_awaited()
            # mark_done com o marker de handoff
            mock_done.assert_awaited_once()
            response_arg = mock_done.call_args[0][2]
            assert response_arg == HANDOFF_HUMANO_MARKER
            mock_failed.assert_not_awaited()

    async def test_invokes_agent_when_atendimento_aguardando(
        self, mock_twilio, mock_clients
    ):
        """Atendimento ainda sem operador: agente IA continua respondendo."""
        msg = MessageQueue(
            id=100,
            atendimento_id=42,
            phone_number="+5511999999999",
            agent_id="vsa_tech",
            thread_id="+5511999999999:vsa_tech",
            incoming_message="oi",
        )
        atd = AsyncMock(return_value=self._atendimento("aguardando"))
        patches = _patch_processor(TEXT_PREPROCESS, atendimento_lookup=atd)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
            patches[5],
            patches[6],
            patches[7],
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="Resposta do agente")]
            }
            mock_load.return_value = mock_graph

            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                msg,
                AsyncMock(),
                checkpointer=AsyncMock(),
                clients=mock_clients,
            )

            # Agente carregado e Twilio chamado
            mock_load.assert_awaited_once()
            mock_twilio.send_message.assert_awaited_once_with(
                "+5511999999999", "Resposta do agente"
            )
            mock_done.assert_awaited_once()
            mock_failed.assert_not_awaited()

    async def test_invokes_agent_when_atendimento_id_is_none(
        self, message, mock_twilio, mock_clients
    ):
        """Mensagem legacy (atendimento_id=None): caminho normal do agente."""
        # message fixture já tem atendimento_id=None por default
        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
            patches[5],
            patches[6] as mock_atd,
            patches[7],
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
                clients=mock_clients,
            )

            # get_atendimento_by_id NÃO foi consultado (atendimento_id é None)
            mock_atd.assert_not_awaited()
            mock_load.assert_awaited_once()
            mock_done.assert_awaited_once()
            mock_failed.assert_not_awaited()


# === Provider abstraction (M2.b P3) ===


class TestProviderRouting:
    """conexao_provider escolhe o cliente outbound correto."""

    @staticmethod
    def _make_message(provider: str | None) -> MessageQueue:
        return MessageQueue(
            id=200,
            phone_number="+5511999999999",
            agent_id="vsa_tech",
            thread_id="+5511999999999:vsa_tech",
            incoming_message="Olá!",
            conexao_provider=provider,
        )

    async def test_routes_to_evolution_when_provider_evolution(
        self, mock_twilio, mock_evolution, mock_clients
    ):
        """Mensagem com provider=evolution sai pelo EvolutionClient, não pelo Twilio."""
        msg = self._make_message("evolution")
        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
            patches[5],
            patches[6],
            patches[7],
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="Resposta via Evolution")]
            }
            mock_load.return_value = mock_graph

            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                msg,
                AsyncMock(),
                checkpointer=AsyncMock(),
                clients=mock_clients,
            )

            mock_evolution.send_message.assert_awaited_once_with(
                "+5511999999999", "Resposta via Evolution"
            )
            mock_twilio.send_message.assert_not_awaited()
            mock_done.assert_awaited_once()
            mock_failed.assert_not_awaited()

    async def test_routes_to_twilio_when_provider_waba(
        self, mock_twilio, mock_evolution, mock_clients
    ):
        """provider=waba reusa o cliente Twilio (sandbox/prod/waba compartilham)."""
        msg = self._make_message("waba")
        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="Resposta via WABA")]
            }
            mock_load.return_value = mock_graph

            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                msg,
                AsyncMock(),
                checkpointer=AsyncMock(),
                clients=mock_clients,
            )

            mock_twilio.send_message.assert_awaited_once_with(
                "+5511999999999", "Resposta via WABA"
            )
            mock_evolution.send_message.assert_not_awaited()
            mock_done.assert_awaited_once()

    async def test_falls_back_to_default_when_provider_is_none(
        self, mock_twilio, mock_evolution, mock_clients
    ):
        """Row legacy sem conexao_provider cai no DEFAULT_PROVIDER (twilio_sandbox)."""
        msg = self._make_message(None)
        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="legado ok")]
            }
            mock_load.return_value = mock_graph

            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                msg,
                AsyncMock(),
                checkpointer=AsyncMock(),
                clients=mock_clients,
            )

            mock_twilio.send_message.assert_awaited_once()
            mock_evolution.send_message.assert_not_awaited()
            mock_done.assert_awaited_once()

    async def test_falls_back_to_default_when_provider_unknown(
        self, mock_twilio, mock_evolution, mock_clients
    ):
        """Provider sem cliente registrado (config inconsistente) cai no default."""
        msg = self._make_message("provider_inexistente")
        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
            patches[5],
            patches[6],
            patches[7],
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="resposta fallback")]
            }
            mock_load.return_value = mock_graph

            from whatsapp_langchain.worker.processor import process_message

            await process_message(
                msg,
                AsyncMock(),
                checkpointer=AsyncMock(),
                clients=mock_clients,
            )

            mock_twilio.send_message.assert_awaited_once()
            mock_evolution.send_message.assert_not_awaited()
            mock_done.assert_awaited_once()
            mock_failed.assert_not_awaited()
