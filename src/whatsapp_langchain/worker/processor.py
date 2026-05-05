"""Processador de mensagens — orquestra agente, typing e envio outbound.

Responsável por:
1. Pré-processar entrada (mídia -> texto)
2. Enviar typing indicator (best-effort)
3. Carregar o agente via loader (com checkpointer PostgreSQL)
4. Executar o agente
5. Enviar resposta ao usuário via cliente outbound do provider correspondente
6. Salvar no banco (mark_done somente após envio confirmado)

Decisões arquiteturais:
- Provider abstraction (M2.b): o worker recebe um dict
  `{provider: OutboundClient}` e resolve por `message.conexao_provider`.
  Hoje suporta Twilio (sandbox/prod/WABA) e Evolution; novos providers
  só implementam o protocolo `OutboundClient`.
- Em production, o envio outbound usa cliente real.
- Em desenvolvimento, cada provider pode operar em modo mock para
  validar a via assíncrona sem consumir cota externa.
- Typing é tentado quando o SID inbound tem formato válido (best-effort).
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
        clients={"twilio_sandbox": twilio, "evolution": evolution, ...},
    )
"""

import re

import structlog
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.agents.loader import load_graph
from whatsapp_langchain.shared.atendimento import get_atendimento_by_id
from whatsapp_langchain.shared.horario import is_business_hours
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
from whatsapp_langchain.worker.outbound_client import OutboundClient

logger = structlog.get_logger()


# S4 / E2.E: detecta resposta do gestor pra aprovação de agendamento.
# Dois padrões aceitos:
#   1. Explícito: "APROVAR <uuid>" ou "REJEITAR <uuid>" — sempre desambígua,
#      usado quando há múltiplas aprovações pendentes pro mesmo gestor.
#   2. Numérico: "1" (aprovar) ou "2" (rejeitar) — UX simplificada, só
#      funciona quando há exatamente 1 aprovação pendente pro gestor.
_APPROVAL_EXPLICIT_RE = re.compile(
    r"^\s*(APROVAR|REJEITAR)\s+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)
# Match estrito: texto inteiro é só "1" ou "2", com pontuação opcional.
# Evita disparar em conversa normal ("1 hora amanhã", "2 reuniões", etc).
_APPROVAL_NUMERIC_RE = re.compile(r"^\s*([12])[.\s]*$")


def _match_approval_intent(text: str) -> dict | None:
    """Decide se a mensagem é tentativa de aprovação. Retorna dict ou None.

    - {"kind": "explicit", "action": "APROVAR"|"REJEITAR", "token": str, "motivo": str|None}
    - {"kind": "numeric", "choice": "1"|"2"}
    """
    m = _APPROVAL_EXPLICIT_RE.match(text)
    if m:
        return {
            "kind": "explicit",
            "action": m.group(1).upper(),
            "token": m.group(2).lower(),
            "motivo": m.group(3).strip() or None,
        }
    m = _APPROVAL_NUMERIC_RE.match(text)
    if m:
        return {"kind": "numeric", "choice": m.group(1)}
    return None


async def _try_handle_approval(
    message: MessageQueue,
    pool: AsyncConnectionPool,
    outbound: OutboundClient,
) -> bool:
    """Detecta resposta APROVAR/REJEITAR <token> do gestor (S4 Calendar v2).

    Se a mensagem bate o padrão E o phone bate com `gestor_telefone` da
    aprovação pendente, processa a decisão (cria/cancela evento Google),
    responde confirmação ao gestor, marca done e retorna True (não chama
    agente).

    Retorna False quando não é resposta de aprovação OU token inválido
    (deixa cair no fluxo normal do agente).
    """
    from whatsapp_langchain.shared import (
        agendamento as _agendamento_helpers,
        calendar_integration as _cal,
    )

    text = (message.incoming_message or "").strip()
    intent = _match_approval_intent(text)
    if intent is None:
        return False

    if intent["kind"] == "numeric":
        # "1" ou "2" sozinho. Resolve via FIFO mas SÓ se houver exatamente
        # 1 pending — múltiplas pending exigem token explícito pra não
        # aprovar o errado silenciosamente.
        pending = await _agendamento_helpers.list_pending_approvals_by_phone(
            pool, message.phone_number
        )
        if not pending:
            logger.info(
                "approval_numeric_no_pending",
                phone=message.phone_number,
                choice=intent["choice"],
            )
            return False  # cai pro agente
        if len(pending) > 1:
            ambig = (
                f"Você tem {len(pending)} pedidos de aprovação pendentes. "
                "Pra não aprovar o errado, responda com o token explícito:\n\n"
                "APROVAR <token>\nou\nREJEITAR <token>\n\n"
                "Pedidos pendentes:\n"
                + "\n".join(
                    f"• {p['summary']} ({p['data_inicio'].strftime('%d/%m %H:%M')}) — {p['token']}"
                    for p in pending
                )
            )
            try:
                await outbound.send_message(message.phone_number, ambig)
            except Exception as e:  # noqa: BLE001
                logger.error("approval_ambiguous_send_failed", error=str(e))
            await mark_done(
                pool,
                message.id,
                ambig,
                normalized_input=text,
                media_processing_status=None,
                media_processing_error=None,
            )
            logger.info(
                "approval_ambiguous",
                phone=message.phone_number,
                pending_count=len(pending),
            )
            return True
        aprov = pending[0]
        decisao = "APROVAR" if intent["choice"] == "1" else "REJEITAR"
        token = aprov["token"]
        motivo = None
    else:
        # explicit
        decisao = intent["action"]
        token = intent["token"]
        motivo = intent["motivo"]

        aprov = await _agendamento_helpers.find_pending_approval_by_token(pool, token)
        if not aprov:
            # Token desconhecido — pode ser tentativa de fraude ou já decidido.
            # Não responde aqui; deixa cair pro agente que vai dizer "não entendi".
            logger.info(
                "approval_token_invalid",
                phone=message.phone_number,
                token=token,
            )
            return False

        # Confere phone do remetente bate com gestor cadastrado
        if message.phone_number != aprov["gestor_telefone"]:
            logger.warning(
                "approval_token_wrong_phone",
                expected=aprov["gestor_telefone"],
                got=message.phone_number,
                token=token,
            )
            return False

    if decisao == "APROVAR":
        # Atualiza aprovação + cria evento Google
        try:
            ev = await _cal.confirm_pending_event(
                pool, aprov["empresa_id"], aprov["agendamento_id"]
            )
            await _agendamento_helpers.update_approval_status(
                pool, aprov["aprovacao_id"], status="aprovado", motivo=motivo
            )
            resposta = (
                f"✅ Aprovado!\n\n"
                f"Evento criado: {aprov['summary']}\n"
                f"Data: {aprov['data_inicio'].strftime('%d/%m %H:%M')}"
            )
            if ev.get("htmlLink"):
                resposta += f"\nLink: {ev['htmlLink']}"
        except Exception as e:  # noqa: BLE001
            logger.error(
                "approval_confirm_failed",
                token=token,
                error=str(e),
            )
            resposta = (
                f"❌ Erro ao confirmar evento no Google: {e}\n\n"
                f"Aprovação registrada mas evento não foi criado. "
                "Tente reagendar manualmente ou verifique a conexão Calendar."
            )
    else:
        # REJEITAR
        await _agendamento_helpers.update_approval_status(
            pool, aprov["aprovacao_id"], status="rejeitado", motivo=motivo
        )
        await _agendamento_helpers.cancel_local(
            pool, aprov["agendamento_id"], aprov["empresa_id"]
        )
        # Hook agendamento.rejeitado
        from whatsapp_langchain.shared.hook_dispatcher import dispatch_event

        await dispatch_event(
            pool,
            aprov["empresa_id"],
            "agendamento.rejeitado",
            {
                "agendamento_id": aprov["agendamento_id"],
                "motivo": motivo,
                "status": "cancelado",
            },
        )
        resposta = (
            f"❌ Rejeitado.\n\n"
            f"Agendamento '{aprov['summary']}' cancelado."
        )
        if motivo:
            resposta += f"\nMotivo registrado: {motivo}"

    # Envia confirmação pro gestor
    try:
        await outbound.send_message(message.phone_number, resposta)
    except Exception as e:  # noqa: BLE001
        logger.error("approval_response_send_failed", error=str(e))

    # Marca message_queue como done (sem chamar agente)
    await mark_done(
        pool,
        message.id,
        resposta,
        normalized_input=text,
        media_processing_status=None,
        media_processing_error=None,
    )

    logger.info(
        "approval_handled",
        message_id=message.id,
        phone=message.phone_number,
        token=token,
        decisao=decisao,
        agendamento_id=aprov["agendamento_id"],
    )
    return True


# Marcador na coluna `response` quando o worker pula o agente IA por
# handoff humano. O painel filtra rows com este marker pra não exibir
# como bolha de resposta automática.
HANDOFF_HUMANO_MARKER = "[handoff humano — operador respondendo]"

# Provider default pra rows sem conexao_id ou com conexão deletada
# (mantém comportamento legado pré-M2.b).
DEFAULT_PROVIDER = "twilio_sandbox"


def _resolve_outbound_client(
    clients: dict[str, OutboundClient], message: MessageQueue
) -> OutboundClient:
    """Escolhe o cliente outbound certo pra mensagem.

    Cai no DEFAULT_PROVIDER quando `conexao_provider` é None (rows legacy
    ou conexão removida) ou quando o provider não tem cliente registrado
    (situação só possível por config inconsistente — logamos warning).
    """
    provider = message.conexao_provider or DEFAULT_PROVIDER
    client = clients.get(provider)
    if client is None:
        logger.warning(
            "outbound_provider_not_registered",
            provider=provider,
            message_id=message.id,
            fallback=DEFAULT_PROVIDER,
        )
        return clients[DEFAULT_PROVIDER]
    return client


async def process_message(
    message: MessageQueue,
    pool: AsyncConnectionPool,
    *,
    checkpointer: BaseCheckpointSaver,
    store: BaseStore | None = None,
    clients: dict[str, OutboundClient],
) -> None:
    """Processa uma mensagem da fila com o agente apropriado.

    Faz download de mídia se presente, envia typing, carrega o grafo
    do agente com checkpointer PostgreSQL, executa, envia a resposta
    via cliente outbound do provider e salva no banco.

    Nenhum mark_done ocorre sem envio outbound confirmado.

    Args:
        message: Mensagem a processar (já reservada via claim).
        pool: Pool de conexões do psycopg.
        checkpointer: Checkpointer LangGraph já inicializado no boot.
        store: Store LangGraph compartilhado (None se memória desabilitada).
        clients: Dict provider→OutboundClient (resolve via conexao_provider).
    """
    outbound = _resolve_outbound_client(clients, message)
    logger.info(
        "processing_message",
        message_id=message.id,
        phone=message.phone_number,
        agent_id=message.agent_id,
        attempt=message.attempts,
    )

    try:
        # S4: detecta resposta APROVAR/REJEITAR <token> do gestor ANTES de
        # tudo. Se for, processa a decisão (cria/cancela evento Google),
        # responde, marca done e retorna early (não chama agente).
        if await _try_handle_approval(message, pool, outbound):
            return

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
            await outbound.send_message(message.phone_number, auto_response)

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
            await outbound.send_typing(message.phone_number, message.message_id)
        except Exception as typing_err:
            logger.warning(
                "typing_failed",
                message_id=message.id,
                phone=message.phone_number,
                error=str(typing_err),
            )

        # 3. Carregar agente com checkpointer + store (se memória habilitada)
        normalized_text = pre.normalized_text or message.incoming_message

        # M6.a — sinalizamos pro agente quando estamos fora do expediente.
        # Wrapper textual no prompt do user é a forma menos invasiva: o
        # agente padrão simplesmente repassa "ok" e o admin pode treinar
        # seu prompt override pra reagir ao prefixo (ex: "responda que
        # voltamos no próximo dia útil").
        within_hours = await is_business_hours(pool, message.empresa_id)
        if not within_hours:
            normalized_text = f"[FORA DO EXPEDIENTE] {normalized_text}"

        human_message = HumanMessage(content=normalized_text)

        invoke_config = {
            "configurable": {
                "thread_id": message.thread_id,
                "user_id": message.phone_number,
                "empresa_id": message.empresa_id,
                "atendimento_id": message.atendimento_id,
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
        await outbound.send_message(message.phone_number, response_text)

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
