"""Processador de mensagens — orquestra agente, typing e envio Twilio.

Responsável por:
1. Pré-processar entrada (mídia -> texto)
2. Enviar typing indicator (best-effort)
3. Carregar o agente via loader (com checkpointer PostgreSQL)
4. Executar o agente
5. Enviar resposta ao usuário via Twilio
6. Salvar no banco (mark_done somente após envio confirmado)

Decisões arquiteturais:
- Em production, o envio outbound usa Twilio real.
- Em desenvolvimento, o worker pode operar em modo mock para validar
  a via assincrona sem consumir cota externa.
- Typing e tentado quando o SID inbound tem formato valido (best-effort).
- Falha de typing NÃO interrompe o processamento.
- mark_done ocorre somente após envio outbound bem-sucedido
  (real ou simulado, dependendo do modo do worker).
- Falha de envio entra no fluxo de retry (mark_failed).

Uso:
    from whatsapp_langchain.worker.processor import process_message

    await process_message(
        message, pool,
        checkpointer=checkpointer,
        store=store,
        twilio=twilio,
    )
"""

import structlog
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.agents.loader import load_graph
from whatsapp_langchain.shared.atendimento import get_atendimento_by_id
from whatsapp_langchain.shared.llm import get_agent_llm_config
from whatsapp_langchain.shared.models import MessageQueue
from whatsapp_langchain.shared.queue import (
    mark_done,
    mark_failed,
    upsert_conversation,
)
from whatsapp_langchain.worker.media import (
    AUTO_RESPONSE_MEDIA_FAILURE,
    preprocess_incoming_message,
)
from whatsapp_langchain.worker.twilio_client import TwilioClient

logger = structlog.get_logger()


# Marcador na coluna `response` quando o worker pula o agente IA por
# handoff humano. O painel filtra rows com este marker pra não exibir
# como bolha de resposta automática.
HANDOFF_HUMANO_MARKER = "[handoff humano — operador respondendo]"


async def process_message(
    message: MessageQueue,
    pool: AsyncConnectionPool,
    *,
    checkpointer: BaseCheckpointSaver,
    store: BaseStore | None = None,
    twilio: TwilioClient,
) -> None:
    """Processa uma mensagem da fila com o agente apropriado.

    Faz download de mídia se presente, envia typing, carrega o grafo
    do agente com checkpointer PostgreSQL, executa, envia a resposta
    via Twilio e salva no banco.

    Nenhum mark_done ocorre sem envio outbound confirmado.

    Args:
        message: Mensagem a processar (já reservada via claim).
        pool: Pool de conexões do psycopg.
        checkpointer: Checkpointer LangGraph já inicializado no boot.
        store: Store LangGraph compartilhado (None se memória desabilitada).
        twilio: Cliente Twilio para envio (obrigatório).
    """
    logger.info(
        "processing_message",
        message_id=message.id,
        phone=message.phone_number,
        agent_id=message.agent_id,
        attempt=message.attempts,
    )

    try:
        # 0. Resolver modelos do agente escopados pela empresa da mensagem
        # (hot reload via DB; fallback pra env quando row ausente).
        _, midia_model = await get_agent_llm_config(
            pool, message.agent_id, message.empresa_id
        )

        # 1. Pré-processar entrada (mídia -> texto) antes do agente
        pre = await preprocess_incoming_message(
            body=message.incoming_message,
            media_url=message.media_url,
            media_type=message.media_type,
            midia_model=midia_model,
        )

        # Se mídia está desabilitada ou falhou, não chama o agente
        if not pre.should_invoke_agent:
            auto_response = pre.auto_response or AUTO_RESPONSE_MEDIA_FAILURE

            # Enviar auto-response via Twilio antes de marcar como done
            await twilio.send_message(message.phone_number, auto_response)

            await mark_done(
                pool,
                message.id,
                auto_response,
                normalized_input=None,
                media_processing_status=pre.media_processing_status,
                media_processing_error=pre.media_processing_error,
            )
            await upsert_conversation(
                pool,
                phone_number=message.phone_number,
                agent_id=message.agent_id,
                last_message=auto_response,
                empresa_id=message.empresa_id,
            )
            logger.info(
                "message_auto_responded",
                message_id=message.id,
                phone=message.phone_number,
                agent_id=message.agent_id,
                media_status=pre.media_processing_status,
            )
            return

        # 1.5. Handoff humano: se o atendimento foi claim'ado por um operador
        # (status=em_andamento + assigned_to_user_id), o worker pula a invocação
        # do agente IA — o humano responde manualmente via composer no painel.
        # A mensagem ainda é marcada como `done` pra liberar a fila e fica
        # visível na timeline do drawer (incoming_message preservado).
        if message.atendimento_id is not None:
            atd = await get_atendimento_by_id(pool, message.atendimento_id)
            if (
                atd is not None
                and atd.status == "em_andamento"
                and atd.assigned_to_user_id
            ):
                await mark_done(
                    pool,
                    message.id,
                    HANDOFF_HUMANO_MARKER,
                    normalized_input=pre.normalized_text,
                    media_processing_status=pre.media_processing_status,
                    media_processing_error=pre.media_processing_error,
                )
                logger.info(
                    "worker_skipped_agent_handoff",
                    message_id=message.id,
                    atendimento_id=message.atendimento_id,
                    assigned_to=atd.assigned_to_user_id,
                    phone=message.phone_number,
                )
                return

        # 2. Typing indicator (best-effort, falha não interrompe processamento)
        try:
            await twilio.send_typing(message.phone_number, message.message_id)
        except Exception as typing_err:
            logger.warning(
                "typing_failed",
                message_id=message.id,
                phone=message.phone_number,
                error=str(typing_err),
            )

        # 3. Carregar agente com checkpointer + store (se memória habilitada)
        normalized_text = pre.normalized_text or message.incoming_message
        human_message = HumanMessage(content=normalized_text)

        invoke_config = {
            "configurable": {
                "thread_id": message.thread_id,
                "user_id": message.phone_number,
            }
        }

        graph = await load_graph(
            message.agent_id,
            checkpointer=checkpointer,
            store=store,
            pool=pool,
            empresa_id=message.empresa_id,
        )
        result = await graph.ainvoke(
            {"messages": [human_message]},
            config=invoke_config,
        )

        # 4. Extrair resposta
        response_text = result["messages"][-1].content

        # 5. Enviar resposta outbound antes de mark_done
        await twilio.send_message(message.phone_number, response_text)

        # 6. mark_done somente após envio confirmado
        await mark_done(
            pool,
            message.id,
            response_text,
            normalized_input=pre.normalized_text,
            media_processing_status=pre.media_processing_status,
            media_processing_error=pre.media_processing_error,
        )
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=response_text,
            empresa_id=message.empresa_id,
        )

        logger.info(
            "message_processed",
            message_id=message.id,
            phone=message.phone_number,
            agent_id=message.agent_id,
            response_length=len(response_text),
        )

    except Exception as e:
        logger.error(
            "message_processing_error",
            message_id=message.id,
            phone=message.phone_number,
            agent_id=message.agent_id,
            error=str(e),
        )
        await mark_failed(pool, message.id, str(e))
