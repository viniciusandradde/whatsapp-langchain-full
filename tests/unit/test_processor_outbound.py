"""Testes do fluxo send_message → mark_done / mark_failed no processor.

Garante que:
- mark_done NÃO roda quando send_message falha
- mark_failed É chamado no erro de envio
- auto-response de mídia também respeita a regra (envia antes de mark_done)
- Falha no auto-response entra em retry via mark_failed
"""

from types import SimpleNamespace
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
    """Dict provider→OutboundClient (legado — mantido p/ compat de assinatura)."""
    return {
        "twilio_sandbox": mock_twilio,
        "twilio_prod": mock_twilio,
        "waba": mock_twilio,
        "evolution": mock_evolution,
    }


@pytest.fixture(autouse=True)
def _patch_outbound_resolution(mock_twilio):
    """O worker agora monta o client de envio POR-CONEXÃO
    (`build_outbound_client` lê credenciais da conexão no DB). Nos testes,
    curto-circuitamos a resolução pra devolver o mock Twilio direto, junto
    com uma conexão em modo 'ia' (o gate de modo manual fica inerte e o
    fluxo segue pro agente — TestModoManual cobre o outro lado).
    """
    conexao_ia = SimpleNamespace(
        id=77, tipo_atendimento="ia", transcrever_audio_sempre=False
    )
    with patch(
        "whatsapp_langchain.worker.processor._resolve_outbound_client",
        new=AsyncMock(return_value=(mock_twilio, conexao_ia)),
    ):
        yield


@pytest.fixture(autouse=True)
def _sem_whitelist():
    """Default: nenhum número na whitelist (gate mig 133 não dispara).

    Sem este patch, o pool AsyncMock devolveria fetchone() truthy e TODOS os
    testes virariam "whitelisted". TestWhitelist re-patcha por cima nos casos
    de hit.
    """
    with patch(
        "whatsapp_langchain.worker.processor.is_whitelisted",
        new=AsyncMock(return_value=False),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_early_handlers():
    """Neutraliza os handlers que rodam ANTES do agente no `process_message`.

    O processor cresceu com gates de pré-agente (approval / CSAT / encerrar /
    wizard de coleta / menu chatbot), cada um abrindo `pool.connection()`.
    Como o pool nos testes é um AsyncMock puro (não é async CM real), qualquer
    um deles levantaria TypeError e o fluxo cairia em mark_failed antes de
    chegar no send/agente. Aqui forçamos todos a retornar False = "não tratei,
    siga adiante" — preservando o caminho normal (texto → agente → send).
    """
    with (
        patch(
            "whatsapp_langchain.worker.processor._try_handle_approval",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "whatsapp_langchain.worker.processor._try_capture_avaliacao",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "whatsapp_langchain.worker.processor._try_handle_encerrar_keyword",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "whatsapp_langchain.worker.processor._try_handle_coleta_em_curso",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "whatsapp_langchain.worker.processor._try_handle_menu",
            new=AsyncMock(return_value=False),
        ),
        # A.6 — resolução de agente via DB; None mantém o path legacy (catálogo)
        # e evita o lookup de agente_ia.id (que abriria pool.connection()).
        patch(
            "whatsapp_langchain.worker.processor.resolve_agente_runtime",
            new=AsyncMock(return_value=None),
        ),
        # ia_budget (mig 058) — None = sem orçamento estourado, não bloqueia.
        # Import é local dentro de process_message, então patcha-se na origem.
        patch(
            "whatsapp_langchain.shared.governanca_ia.get_budget_atual",
            new=AsyncMock(return_value=None),
        ),
    ):
        yield


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
            )

            # send_message foi chamado (e falhou)
            mock_twilio.send_message.assert_awaited_once()
            # mark_done NÃO chamado
            mock_done.assert_not_awaited()
            # mark_failed chamado com o erro SANITIZADO. A mensagem bruta
            # fica só no log; o que vai pra message_queue.error é
            # "processing_failed:<TipoExcecao>:<status>" (o status HTTP entra
            # junto quando a exception carrega um — diagnóstico sem log).
            mock_failed.assert_awaited_once()
            error_arg = mock_failed.call_args[0][2]
            assert error_arg == "processing_failed:TwilioSendError:500"

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
            )

            mock_done.assert_not_awaited()
            mock_failed.assert_awaited_once()
            # Erro sanitizado: tipo da exception, não a mensagem bruta.
            assert mock_failed.call_args[0][2] == "processing_failed:Exception"


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
            )

            # send_message foi chamado (e falhou)
            mock_twilio.send_message.assert_awaited_once()
            # mark_done NÃO chamado
            mock_done.assert_not_awaited()
            # mark_failed chamado com erro sanitizado (tipo + status HTTP).
            mock_failed.assert_awaited_once()
            assert (
                mock_failed.call_args[0][2] == "processing_failed:TwilioSendError:503"
            )


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
            )

            # get_atendimento_by_id NÃO foi consultado (atendimento_id é None)
            mock_atd.assert_not_awaited()
            mock_load.assert_awaited_once()
            mock_done.assert_awaited_once()
            mock_failed.assert_not_awaited()


# === Gate modo manual (mig 132 — IA desligada por conexão) ===


class TestModoManual:
    """Conexão `tipo_atendimento='manual'` não dispara resposta automática.

    Empresa nova nasce com a conexão em modo manual; o worker registra a
    mensagem (mark_done com marker), o atendimento segue na fila humana e
    NADA é enviado ao cliente — nem typing, nem transcrição de mídia.
    """

    @staticmethod
    def _resolve_manual(mock_twilio):
        conexao_manual = SimpleNamespace(
            id=77, tipo_atendimento="manual", transcrever_audio_sempre=False
        )
        return patch(
            "whatsapp_langchain.worker.processor._resolve_outbound_client",
            new=AsyncMock(return_value=(mock_twilio, conexao_manual)),
        )

    async def test_manual_marca_done_sem_responder(self, message, mock_twilio):
        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0] as mock_pre,
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            self._resolve_manual(mock_twilio),
        ):
            from whatsapp_langchain.worker.processor import (
                MODO_MANUAL_MARKER,
                process_message,
            )

            await process_message(
                message,
                AsyncMock(),
                checkpointer=AsyncMock(),
            )

            # Silêncio total: nada enviado, agente nem carregado, mídia
            # nem pré-processada (não gasta token de transcrição).
            mock_twilio.send_message.assert_not_awaited()
            mock_twilio.send_typing.assert_not_awaited()
            mock_load.assert_not_awaited()
            mock_pre.assert_not_awaited()
            # Fila liberada com o marker (drawer não renderiza como bolha).
            mock_done.assert_awaited_once()
            assert mock_done.await_args.args[2] == MODO_MANUAL_MARKER
            mock_failed.assert_not_awaited()

    async def test_hibrido_segue_fluxo_ia(self, message, mock_twilio):
        """`hibrido` (por ora) se comporta como `ia`: agente responde."""
        conexao_hibrido = SimpleNamespace(
            id=77, tipo_atendimento="hibrido", transcrever_audio_sempre=False
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
            patch(
                "whatsapp_langchain.worker.processor._resolve_outbound_client",
                new=AsyncMock(return_value=(mock_twilio, conexao_hibrido)),
            ),
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
            )

            mock_twilio.send_message.assert_awaited_once_with(
                "+5511999999999", "Resposta do agente"
            )
            mock_done.assert_awaited_once()
            mock_failed.assert_not_awaited()

    async def test_opt_out_tem_prioridade_sobre_modo_manual(self, message, mock_twilio):
        """STOP/PARAR é compliance anti-ban: responde mesmo com IA desligada."""
        parar = message.model_copy(update={"incoming_message": "PARAR"})
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
            self._resolve_manual(mock_twilio),
        ):
            from whatsapp_langchain.worker.processor import (
                MODO_MANUAL_MARKER,
                process_message,
            )

            await process_message(
                parar,
                AsyncMock(),
                checkpointer=AsyncMock(),
            )

            # Confirmação de opt-out enviada (única exceção ao silêncio).
            mock_twilio.send_message.assert_awaited_once()
            sent = mock_twilio.send_message.await_args.args[1]
            assert "não receberá mais mensagens" in sent
            # Agente não rodou e o marker de modo manual não foi usado.
            mock_load.assert_not_awaited()
            mock_done.assert_awaited_once()
            assert mock_done.await_args.args[2] != MODO_MANUAL_MARKER


# === Gate whitelist (mig 133 — bypass da IA por número) ===


class TestWhitelist:
    """Número na whitelist da empresa: bypass total da IA (silêncio).

    Mesmo contrato do modo manual, porém por número: mensagem registrada,
    atendimento na fila humana, nenhuma resposta automática.
    """

    async def test_whitelist_hit_silencio_total(self, message, mock_twilio):
        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0] as mock_pre,
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            patch(
                "whatsapp_langchain.worker.processor.is_whitelisted",
                new=AsyncMock(return_value=True),
            ),
        ):
            from whatsapp_langchain.worker.processor import (
                WHITELIST_BYPASS_MARKER,
                process_message,
            )

            await process_message(
                message,
                AsyncMock(),
                checkpointer=AsyncMock(),
            )

            # Silêncio total: nada enviado, agente nem carregado, mídia
            # nem pré-processada (não gasta token de transcrição).
            mock_twilio.send_message.assert_not_awaited()
            mock_twilio.send_typing.assert_not_awaited()
            mock_load.assert_not_awaited()
            mock_pre.assert_not_awaited()
            mock_done.assert_awaited_once()
            assert mock_done.await_args.args[2] == WHITELIST_BYPASS_MARKER
            mock_failed.assert_not_awaited()

    async def test_whitelist_miss_segue_fluxo_ia(self, message, mock_twilio):
        """Fora da whitelist (default da fixture autouse): agente responde."""
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
            )

            mock_twilio.send_message.assert_awaited_once_with(
                "+5511999999999", "Resposta do agente"
            )
            mock_done.assert_awaited_once()
            mock_failed.assert_not_awaited()

    async def test_modo_manual_ganha_da_whitelist(self, message, mock_twilio):
        """Ordem dos gates: conexão manual curto-circuita antes do SELECT da
        whitelist — marker gravado é o de modo manual (silêncio idêntico)."""
        conexao_manual = SimpleNamespace(
            id=77, tipo_atendimento="manual", transcrever_audio_sempre=False
        )
        patches = _patch_processor(TEXT_PREPROCESS)
        with (
            patches[0],
            patches[1],
            patches[2] as mock_done,
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            patch(
                "whatsapp_langchain.worker.processor._resolve_outbound_client",
                new=AsyncMock(return_value=(mock_twilio, conexao_manual)),
            ),
            patch(
                "whatsapp_langchain.worker.processor.is_whitelisted",
                new=AsyncMock(return_value=True),
            ) as mock_wl,
        ):
            from whatsapp_langchain.worker.processor import (
                MODO_MANUAL_MARKER,
                process_message,
            )

            await process_message(
                message,
                AsyncMock(),
                checkpointer=AsyncMock(),
            )

            mock_done.assert_awaited_once()
            assert mock_done.await_args.args[2] == MODO_MANUAL_MARKER
            mock_wl.assert_not_awaited()


# === Gatilho de voz do agente (mig 176 — resposta em áudio) ===


class TestVozDoAgente:
    """Voz só dispara com voz_ativa + inbound áudio + provedor com send_audio.

    E qualquer exceção na síntese cai no send_message de texto — o cliente
    nunca fica sem resposta porque a voz falhou.
    """

    # `plano_tem_voz` (mig 177): voz é feature de plano (Pro/Enterprise) —
    # get_empresa_voz_config traz a flag no mesmo SELECT da config.
    VOZ_CFG = {
        "voz_nome": "coral",
        "voz_estilo": "tom acolhedor",
        "plano_tem_voz": True,
    }
    OGG_FAKE = b"OggS" + b"\x00" * 32

    @staticmethod
    def _audio_message():
        return MessageQueue(
            id=7,
            message_id="AU789",
            phone_number="+5511999999999",
            agent_id="vsa_tech",
            thread_id="+5511999999999:vsa_tech",
            incoming_message="",
            media_url="https://evo/media/nota.ogg",
            media_type="audio/ogg",
        )

    @staticmethod
    def _outbound_com_audio():
        """Evolution-like: tem send_audio. `spec` evita o auto-atributo do
        AsyncMock, que faria TODO mock 'ter' send_audio por acidente."""
        evo = AsyncMock(spec=["send_message", "send_typing", "send_audio"])
        evo.send_typing = AsyncMock(return_value=True)
        evo.send_message = AsyncMock(return_value="EVO_MSG")
        evo.send_audio = AsyncMock(return_value="EVO_AUDIO")
        return evo

    @staticmethod
    def _outbound_sem_audio():
        """Twilio/WABA-like: sem send_audio (getattr devolve None)."""
        cli = AsyncMock(spec=["send_message", "send_typing"])
        cli.send_typing = AsyncMock(return_value=True)
        cli.send_message = AsyncMock(return_value="TW_MSG")
        return cli

    def _resolve(self, outbound):
        conexao_ia = SimpleNamespace(
            id=77, tipo_atendimento="ia", transcrever_audio_sempre=False
        )
        return patch(
            "whatsapp_langchain.worker.processor._resolve_outbound_client",
            new=AsyncMock(return_value=(outbound, conexao_ia)),
        )

    def _voz_patches(self, *, cfg, sintetizar_mock=None):
        return (
            patch(
                "whatsapp_langchain.worker.processor.get_empresa_voz_config",
                new=AsyncMock(return_value=cfg),
            ),
            patch(
                "whatsapp_langchain.worker.processor.sintetizar",
                new=sintetizar_mock or AsyncMock(return_value=TestVozDoAgente.OGG_FAKE),
            ),
            patch(
                "whatsapp_langchain.worker.processor._gravar_response_media_audio",
                new_callable=AsyncMock,
            ),
        )

    async def _roda(self, msg, outbound, *, cfg, sintetizar_mock=None):
        import base64

        patches = _patch_processor(TEXT_PREPROCESS)
        voz_cfg_p, sint_p, grava_p = self._voz_patches(
            cfg=cfg, sintetizar_mock=sintetizar_mock
        )
        with (
            patches[0],
            patches[1] as mock_load,
            patches[2] as mock_done,
            patches[3] as mock_failed,
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            self._resolve(outbound),
            voz_cfg_p as mock_cfg,
            sint_p as mock_sint,
            grava_p as mock_grava,
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke.return_value = {
                "messages": [MagicMock(content="Resposta do agente")]
            }
            mock_load.return_value = mock_graph

            from whatsapp_langchain.worker.processor import process_message

            await process_message(msg, AsyncMock(), checkpointer=AsyncMock())
        return SimpleNamespace(
            done=mock_done,
            failed=mock_failed,
            cfg=mock_cfg,
            sintetizar=mock_sint,
            grava=mock_grava,
            b64=base64.b64encode(self.OGG_FAKE).decode("ascii"),
        )

    async def test_dispara_com_voz_ativa_audio_e_send_audio(self):
        evo = self._outbound_com_audio()
        r = await self._roda(self._audio_message(), evo, cfg=self.VOZ_CFG)

        # Áudio enviado (e SÓ o áudio — sem duplicar em texto).
        evo.send_audio.assert_awaited_once_with("+5511999999999", r.b64)
        evo.send_message.assert_not_awaited()
        # Síntese recebeu voz/estilo da empresa.
        assert r.sintetizar.await_args.kwargs["voz"] == "coral"
        assert r.sintetizar.await_args.kwargs["estilo"] == "tom acolhedor"
        # mark_done grava o TEXTO (histórico legível) e o player é persistido.
        r.done.assert_awaited_once()
        assert r.done.await_args.args[2] == "Resposta do agente"
        r.grava.assert_awaited_once()
        r.failed.assert_not_awaited()

    async def test_nao_dispara_sem_voz_ativa(self):
        evo = self._outbound_com_audio()
        r = await self._roda(self._audio_message(), evo, cfg=None)

        evo.send_audio.assert_not_awaited()
        r.sintetizar.assert_not_awaited()
        evo.send_message.assert_awaited_once_with(
            "+5511999999999", "Resposta do agente"
        )
        r.done.assert_awaited_once()

    async def test_plano_sem_feature_voz_cai_em_texto(self):
        """Mig 177: downgrade de plano desliga a voz sem limpar a config.

        `voz_ativa=true` na empresa, mas o plano perdeu a feature 'voz'
        (ou a chave nem existe — seguro por default): pula a síntese,
        responde em texto e loga `voz_sem_feature_plano` uma vez.
        """
        evo = self._outbound_com_audio()
        cfg = {"voz_nome": "coral", "voz_estilo": "", "plano_tem_voz": False}
        with patch("whatsapp_langchain.worker.processor.logger") as mock_log:
            r = await self._roda(self._audio_message(), evo, cfg=cfg)

        r.sintetizar.assert_not_awaited()
        evo.send_audio.assert_not_awaited()
        evo.send_message.assert_awaited_once_with(
            "+5511999999999", "Resposta do agente"
        )
        r.done.assert_awaited_once()
        r.failed.assert_not_awaited()
        # Log info certo, UMA vez — sem erro/warning de voz.
        chamadas = [
            c
            for c in mock_log.info.call_args_list
            if c.args and c.args[0] == "voz_sem_feature_plano"
        ]
        assert len(chamadas) == 1
        assert chamadas[0].kwargs["empresa_id"] == 1

    async def test_nao_dispara_para_mensagem_de_texto(self):
        """Quem escreve recebe texto — nem o SELECT da config é pago."""
        evo = self._outbound_com_audio()
        msg = MessageQueue(
            id=8,
            message_id="TX1",
            phone_number="+5511999999999",
            agent_id="vsa_tech",
            thread_id="+5511999999999:vsa_tech",
            incoming_message="Oi!",
        )
        r = await self._roda(msg, evo, cfg=self.VOZ_CFG)

        r.cfg.assert_not_awaited()
        evo.send_audio.assert_not_awaited()
        evo.send_message.assert_awaited_once()

    async def test_nao_dispara_sem_send_audio_no_provedor(self):
        """WABA/Twilio: sem send_audio, segue texto sem sintetizar."""
        cli = self._outbound_sem_audio()
        r = await self._roda(self._audio_message(), cli, cfg=self.VOZ_CFG)

        r.sintetizar.assert_not_awaited()
        cli.send_message.assert_awaited_once_with(
            "+5511999999999", "Resposta do agente"
        )
        r.done.assert_awaited_once()

    async def test_excecao_na_sintese_cai_em_texto(self):
        from whatsapp_langchain.shared.voz import VozError

        evo = self._outbound_com_audio()
        r = await self._roda(
            self._audio_message(),
            evo,
            cfg=self.VOZ_CFG,
            sintetizar_mock=AsyncMock(side_effect=VozError("provedor caiu")),
        )

        evo.send_audio.assert_not_awaited()
        evo.send_message.assert_awaited_once_with(
            "+5511999999999", "Resposta do agente"
        )
        r.grava.assert_not_awaited()
        r.done.assert_awaited_once()
        r.failed.assert_not_awaited()

    async def test_falha_no_send_audio_cai_em_texto(self):
        """Sintetizou mas o Evolution recusou: fallback igual — nada perdido."""
        evo = self._outbound_com_audio()
        evo.send_audio = AsyncMock(side_effect=Exception("instância off"))
        r = await self._roda(self._audio_message(), evo, cfg=self.VOZ_CFG)

        evo.send_message.assert_awaited_once_with(
            "+5511999999999", "Resposta do agente"
        )
        r.grava.assert_not_awaited()
        r.done.assert_awaited_once()
        r.failed.assert_not_awaited()
