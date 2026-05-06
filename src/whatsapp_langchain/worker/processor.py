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
from whatsapp_langchain.shared.agente import resolve_agente_runtime
from whatsapp_langchain.shared.atendimento import (
    close_atendimento,
    get_atendimento_by_id,
)
from whatsapp_langchain.shared.horario import is_business_hours
from whatsapp_langchain.shared.llm import get_agent_llm_config
from whatsapp_langchain.shared.menu_chatbot import (
    format_menu_message,
    get_menu_ativo_para_conexao,
    get_posicao_atual,
    is_trigger_keyword,
    list_children,
    parse_numero_opcao,
    registrar_historico,
)
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

        # Confere phone do remetente bate com gestor cadastrado.
        # Aceita variantes BR do "9 extra" mobile — phone gravado como
        # +5567996460034 bate com +556796460034 e vice-versa.
        from whatsapp_langchain.shared.phone_br import phone_equivalent

        if not phone_equivalent(message.phone_number, aprov["gestor_telefone"]):
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


async def _try_handle_menu(
    message: MessageQueue,
    pool: AsyncConnectionPool,
    outbound: OutboundClient,
) -> bool:
    """Sub-fase B — menu chatbot árvore.

    Retorna True quando processou a mensagem (cliente recebeu boas-vindas,
    escolheu opção, ou tentou opção inválida). Retorna False quando o
    fluxo deve seguir pro agente (sem menu cadastrado, operador humano
    em controle, ou cliente já saiu do menu).

    Decisões de prioridade:
    - Operador humano (atendimento.assigned_to_user_id + em_andamento) →
      ignora menu. Operador responde via composer.
    - `trigger_keyword` (ex: "menu") → reset pra raiz, mesmo se cliente
      já estava com agente_atual atribuído.
    - Sem histórico de menu E sem agente_atual ainda → primeira interação,
      envia boas-vindas + raiz.
    - Histórico existe E posição_atual definida → tenta interpretar texto
      como número de opção; texto livre vira "opção inválida".
    - Cliente saiu do menu (posicao_atual=None E agente_atual atribuído E
      texto não é trigger) → deixa pro agente.
    """
    if message.atendimento_id is None:
        return False

    atendimento = await get_atendimento_by_id(pool, message.atendimento_id)
    if atendimento is None:
        return False

    # Operador humano em controle — não interfere
    if atendimento.status == "em_andamento" and atendimento.assigned_to_user_id:
        return False

    menu = await get_menu_ativo_para_conexao(
        pool, message.empresa_id, atendimento.conexao_id
    )
    if menu is None:
        return False

    text = (message.incoming_message or "").strip()

    hist_menu_id, posicao_atual = await get_posicao_atual(pool, message.atendimento_id)

    # Trigger keyword sempre vence — reset pra raiz
    if is_trigger_keyword(text, menu.trigger_keywords):
        children = await list_children(pool, menu.id, None)
        msg = format_menu_message(menu.mensagem_boas_vindas, children)
        await outbound.send_message(message.phone_number, msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=None,
            posicao_atual_item_id=None,
        )
        await mark_done(pool, message.id, msg, normalized_input=text)
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=msg,
            empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_reset_via_keyword",
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
        )
        return True

    # Primeira interação: sem histórico de menu, agente ainda no default
    # da conexão — envia boas-vindas. Se atendimento já tem agente
    # customizado (não é o default), assume que cliente já passou pelo
    # menu antes — pula direto pro agente.
    if hist_menu_id is None:
        # Heurística: se atendimento foi criado AGORA mesmo (status='aguardando',
        # last_message_at == created_at), é primeira mensagem.
        if atendimento.status == "aguardando":
            children = await list_children(pool, menu.id, None)
            if not children:
                # Menu sem opções — config inválida, deixa pro agente
                logger.warning(
                    "menu_sem_opcoes_raiz",
                    menu_id=menu.id,
                    empresa_id=message.empresa_id,
                )
                return False
            msg = format_menu_message(menu.mensagem_boas_vindas, children)
            await outbound.send_message(message.phone_number, msg)
            await registrar_historico(
                pool,
                atendimento_id=message.atendimento_id,
                menu_id=menu.id,
                item_id=None,
                posicao_atual_item_id=None,
            )
            await mark_done(pool, message.id, msg, normalized_input=text)
            await upsert_conversation(
                pool,
                phone_number=message.phone_number,
                agent_id=message.agent_id,
                last_message=msg,
                empresa_id=message.empresa_id,
            )
            logger.info(
                "menu_welcome_sent",
                atendimento_id=message.atendimento_id,
                menu_id=menu.id,
                num_options=len(children),
            )
            return True
        # Em andamento sem histórico de menu → cliente nunca passou pelo menu
        # (atendimento legacy, ou menu cadastrado depois). Deixa pro agente.
        return False

    # Tem histórico — cliente está navegando o menu.
    children = await list_children(pool, menu.id, posicao_atual)
    numero = parse_numero_opcao(text)

    if numero is None or numero < 1 or numero > len(children):
        # Opção inválida — reenvia menu atual
        invalida_msg = menu.mensagem_opcao_invalida
        menu_msg = format_menu_message(None, children)
        full_msg = f"{invalida_msg}\n\n{menu_msg}"
        await outbound.send_message(message.phone_number, full_msg)
        await mark_done(pool, message.id, full_msg, normalized_input=text)
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=full_msg,
            empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_opcao_invalida",
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            input=text[:50],
        )
        return True

    item = children[numero - 1]
    payload = item.acao_payload or {}

    if item.acao_tipo == "submenu":
        sub_children = await list_children(pool, menu.id, item.id)
        if not sub_children:
            # Submenu vazio — config inválida. Trata como inválido.
            logger.warning(
                "menu_submenu_vazio",
                menu_id=menu.id,
                item_id=item.id,
            )
            invalida_msg = menu.mensagem_opcao_invalida
            menu_msg = format_menu_message(None, children)
            full_msg = f"{invalida_msg}\n\n{menu_msg}"
            await outbound.send_message(message.phone_number, full_msg)
            await mark_done(pool, message.id, full_msg, normalized_input=text)
            return True
        msg = format_menu_message(None, sub_children)
        await outbound.send_message(message.phone_number, msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=item.id,
        )
        await mark_done(pool, message.id, msg, normalized_input=text)
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=msg,
            empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_submenu_open",
            atendimento_id=message.atendimento_id,
            item_id=item.id,
        )
        return True

    if item.acao_tipo == "transferir_dep":
        dep_id = payload.get("departamento_id")
        msg_pre = (payload.get("mensagem_pre") or "").strip()
        if not isinstance(dep_id, int):
            logger.error(
                "menu_transferir_dep_payload_invalido",
                item_id=item.id,
                payload=payload,
            )
            return False
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE atendimento SET departamento_id = %s, updated_at = NOW() "
                "WHERE id = %s",
                (dep_id, message.atendimento_id),
            )
            await conn.commit()
        out_msg = msg_pre or "Você foi transferido. Aguarde, em breve um atendente irá te responder."
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None,  # saiu do menu
        )
        await mark_done(pool, message.id, out_msg, normalized_input=text)
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=out_msg,
            empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_transferir_dep",
            atendimento_id=message.atendimento_id,
            departamento_id=dep_id,
        )
        return True

    if item.acao_tipo == "chamar_agente":
        agente_slug = payload.get("agente_slug")
        msg_pre = (payload.get("mensagem_pre") or "").strip()
        if not isinstance(agente_slug, str) or not agente_slug:
            logger.error(
                "menu_chamar_agente_payload_invalido",
                item_id=item.id,
                payload=payload,
            )
            return False
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE atendimento SET agente_atual = %s, updated_at = NOW() "
                "WHERE id = %s",
                (agente_slug, message.atendimento_id),
            )
            await conn.commit()
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None,  # saiu do menu
        )
        if msg_pre:
            await outbound.send_message(message.phone_number, msg_pre)
            await mark_done(pool, message.id, msg_pre, normalized_input=text)
            await upsert_conversation(
                pool,
                phone_number=message.phone_number,
                agent_id=message.agent_id,
                last_message=msg_pre,
                empresa_id=message.empresa_id,
            )
        else:
            # Sem mensagem_pre, marca done sem outbound (próxima msg do
            # cliente vai pro agente normalmente)
            await mark_done(pool, message.id, "", normalized_input=text)
        logger.info(
            "menu_chamar_agente",
            atendimento_id=message.atendimento_id,
            agente_slug=agente_slug,
        )
        return True

    if item.acao_tipo == "enviar_msg":
        texto = (payload.get("texto") or "").strip()
        voltar_menu = bool(payload.get("voltar_menu", True))
        if not texto:
            logger.error(
                "menu_enviar_msg_payload_invalido",
                item_id=item.id,
                payload=payload,
            )
            return False
        out_msg = texto
        if voltar_menu:
            root_children = await list_children(pool, menu.id, None)
            if root_children:
                out_msg = f"{texto}\n\n{format_menu_message(None, root_children)}"
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None if voltar_menu else item.parent_id,
        )
        await mark_done(pool, message.id, out_msg, normalized_input=text)
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=out_msg,
            empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_enviar_msg",
            atendimento_id=message.atendimento_id,
            voltar_menu=voltar_menu,
        )
        return True

    # ---- Sub-fase B+ (mig 042) — 7 ações novas ----

    if item.acao_tipo == "transferir_atendente":
        # Atribui atendimento a usuário específico (operador humano).
        # Em vez de FK explícita usuario, aceitamos string (Better Auth user IDs).
        user_id = (item.acao_atendente_id or payload.get("acao_atendente_id") or "").strip()
        msg_pre = (payload.get("mensagem_pre") or "").strip()
        if not user_id:
            logger.error("menu_transferir_atendente_payload_invalido", item_id=item.id)
            return False
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE atendimento SET assigned_to_user_id = %s, "
                "status = 'em_andamento', updated_at = NOW() WHERE id = %s",
                (user_id, message.atendimento_id),
            )
            await conn.commit()
        out_msg = msg_pre or "Você foi transferido. Em breve um atendente irá te responder."
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None,
        )
        await mark_done(pool, message.id, out_msg, normalized_input=text)
        await upsert_conversation(
            pool, phone_number=message.phone_number, agent_id=message.agent_id,
            last_message=out_msg, empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_transferir_atendente",
            atendimento_id=message.atendimento_id, atendente_user_id=user_id,
        )
        return True

    if item.acao_tipo == "enviar_template":
        # Dispara template de modelo_mensagem como resposta.
        modelo_id = item.acao_modelo_mensagem_id or payload.get("acao_modelo_mensagem_id")
        voltar = bool(payload.get("voltar_menu", True))
        if not isinstance(modelo_id, int):
            logger.error("menu_enviar_template_payload_invalido", item_id=item.id)
            return False
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT conteudo FROM modelo_mensagem "
                "WHERE id = %s AND empresa_id = %s",
                (modelo_id, message.empresa_id),
            )
            row = await cur.fetchone()
        if not row:
            logger.error(
                "menu_enviar_template_modelo_nao_encontrado",
                modelo_id=modelo_id, empresa_id=message.empresa_id,
            )
            return False
        out_msg = row[0]
        if voltar:
            root_children = await list_children(pool, menu.id, None)
            if root_children:
                out_msg = f"{out_msg}\n\n{format_menu_message(None, root_children)}"
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool, atendimento_id=message.atendimento_id, menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None if voltar else item.parent_id,
        )
        await mark_done(pool, message.id, out_msg, normalized_input=text)
        await upsert_conversation(
            pool, phone_number=message.phone_number, agent_id=message.agent_id,
            last_message=out_msg, empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_enviar_template",
            atendimento_id=message.atendimento_id, modelo_id=modelo_id,
        )
        return True

    if item.acao_tipo == "chamar_webhook":
        # Fire-and-forget POST pra URL externa. Não bloqueia o cliente.
        # O hook_dispatcher trata retry+DLQ se houver hook_id (caso futuro).
        url = (item.webhook_url or payload.get("webhook_url") or "").strip()
        msg_pre = (payload.get("mensagem_pre") or "Ok, processando...").strip()
        voltar = bool(payload.get("voltar_menu", True))
        if not url:
            logger.error("menu_chamar_webhook_url_vazio", item_id=item.id)
            return False
        # Dispara em background — não esperamos resposta
        import asyncio as _asyncio  # local import pra não poluir top-level

        import httpx

        async def _fire_webhook(target_url: str, body: dict) -> None:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(target_url, json=body)
            except Exception as exc:
                logger.warning(
                    "menu_chamar_webhook_falhou", url=target_url, error=str(exc),
                )

        webhook_body = {
            "atendimento_id": message.atendimento_id,
            "empresa_id": message.empresa_id,
            "phone_number": message.phone_number,
            "menu_id": menu.id,
            "item_id": item.id,
            "item_label": item.label,
            "input_cliente": text,
        }
        _asyncio.create_task(_fire_webhook(url, webhook_body))

        out_msg = msg_pre
        if voltar:
            root_children = await list_children(pool, menu.id, None)
            if root_children:
                out_msg = f"{msg_pre}\n\n{format_menu_message(None, root_children)}"
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool, atendimento_id=message.atendimento_id, menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None if voltar else item.parent_id,
        )
        await mark_done(pool, message.id, out_msg, normalized_input=text)
        await upsert_conversation(
            pool, phone_number=message.phone_number, agent_id=message.agent_id,
            last_message=out_msg, empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_chamar_webhook",
            atendimento_id=message.atendimento_id, url=url,
        )
        return True

    if item.acao_tipo == "enviar_link":
        url = (item.link_url or payload.get("link_url") or "").strip()
        prefix = (payload.get("texto_pre") or "Aqui está o link:").strip()
        voltar = bool(payload.get("voltar_menu", True))
        if not url:
            logger.error("menu_enviar_link_url_vazio", item_id=item.id)
            return False
        out_msg = f"{prefix}\n{url}"
        if voltar:
            root_children = await list_children(pool, menu.id, None)
            if root_children:
                out_msg = f"{out_msg}\n\n{format_menu_message(None, root_children)}"
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool, atendimento_id=message.atendimento_id, menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None if voltar else item.parent_id,
        )
        await mark_done(pool, message.id, out_msg, normalized_input=text)
        await upsert_conversation(
            pool, phone_number=message.phone_number, agent_id=message.agent_id,
            last_message=out_msg, empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_enviar_link", atendimento_id=message.atendimento_id, url=url,
        )
        return True

    if item.acao_tipo == "pesquisa_csat":
        # Envia pergunta + escala. A resposta numérica do cliente vai vir na
        # próxima mensagem — captura via posicao_atual = item (resta como
        # filho do CSAT que não tem filhos → próxima opção numérica fica
        # "fora do range" e cai como inválida → reenvia menu).
        # MVP: envia e sai do menu (deixa pro agente IA capturar nota se
        # estiver atribuído, ou opera só como fire-and-forget).
        # TODO mig 045: capturar próxima resposta como input estruturado.
        pergunta = (item.nota_pergunta or payload.get("nota_pergunta") or
                   "Por favor, avalie nosso atendimento:").strip()
        nmin = item.nota_min or payload.get("nota_min") or 1
        nmax = item.nota_max or payload.get("nota_max") or 5
        escala = ", ".join(str(n) for n in range(int(nmin), int(nmax) + 1))
        out_msg = f"{pergunta}\n\nResponda com um número de {nmin} a {nmax}:\n{escala}"
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool, atendimento_id=message.atendimento_id, menu_id=menu.id,
            item_id=item.id, posicao_atual_item_id=None,
        )
        await mark_done(pool, message.id, out_msg, normalized_input=text)
        await upsert_conversation(
            pool, phone_number=message.phone_number, agent_id=message.agent_id,
            last_message=out_msg, empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_pesquisa_csat",
            atendimento_id=message.atendimento_id, escala=f"{nmin}-{nmax}",
        )
        return True

    if item.acao_tipo == "mudar_manual":
        # Sai do menu e marca atendimento como "aguardando" sem agente_atual
        # atribuído — operadores humanos pegam via UI.
        msg = (payload.get("mensagem_pre") or
              "Estou te transferindo para um atendente humano. Aguarde um momento.").strip()
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE atendimento SET status = 'aguardando', "
                "agente_atual = NULL, updated_at = NOW() WHERE id = %s",
                (message.atendimento_id,),
            )
            await conn.commit()
        await outbound.send_message(message.phone_number, msg)
        await registrar_historico(
            pool, atendimento_id=message.atendimento_id, menu_id=menu.id,
            item_id=item.id, posicao_atual_item_id=None,
        )
        await mark_done(pool, message.id, msg, normalized_input=text)
        await upsert_conversation(
            pool, phone_number=message.phone_number, agent_id=message.agent_id,
            last_message=msg, empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_mudar_manual", atendimento_id=message.atendimento_id,
        )
        return True

    if item.acao_tipo == "setar_nome":
        # Pergunta o nome do cliente. MVP: envia pergunta e sai do menu — a
        # próxima mensagem cliente cai no agente IA (que pode capturar nome
        # via tool save_memory ou update_cliente). Captura estruturada (sem
        # IA) requer mig 045 com posicao_atual = item.id + estado "captura".
        pergunta = (payload.get("pergunta") or "Qual é o seu nome?").strip()
        await outbound.send_message(message.phone_number, pergunta)
        await registrar_historico(
            pool, atendimento_id=message.atendimento_id, menu_id=menu.id,
            item_id=item.id, posicao_atual_item_id=None,
        )
        await mark_done(pool, message.id, pergunta, normalized_input=text)
        await upsert_conversation(
            pool, phone_number=message.phone_number, agent_id=message.agent_id,
            last_message=pergunta, empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_setar_nome", atendimento_id=message.atendimento_id,
        )
        return True

    if item.acao_tipo == "fechar":
        msg_final = (payload.get("mensagem_final") or "").strip() or (
            "Atendimento finalizado. Volte sempre!"
        )
        await outbound.send_message(message.phone_number, msg_final)
        await close_atendimento(pool, message.atendimento_id, "resolvido")
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None,
        )
        await mark_done(pool, message.id, msg_final, normalized_input=text)
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=msg_final,
            empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_fechar",
            atendimento_id=message.atendimento_id,
            motivo=payload.get("motivo"),
        )
        return True

    # acao_tipo desconhecido (CHECK do DB já barra, mas defesa em profundidade)
    logger.error(
        "menu_acao_tipo_desconhecido",
        item_id=item.id,
        acao_tipo=item.acao_tipo,
    )
    return False


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

        # B.3 — Menu chatbot árvore (Sub-fase B). Detecta cliente em
        # navegação de menu OU primeira mensagem precisando de boas-vindas.
        # Retorna True quando processou; False deixa fluxo seguir pro agente.
        if await _try_handle_menu(message, pool, outbound):
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

        # A.6 — resolve agente_ia DB; runtime=None mantém path legacy (catálogo).
        agente_runtime = await resolve_agente_runtime(
            pool, message.empresa_id, message.agent_id
        )
        graph = await load_graph(
            message.agent_id,
            checkpointer=checkpointer,
            store=store,
            pool=pool,
            empresa_id=message.empresa_id,
            agente_runtime=agente_runtime,
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
        # str(e) pode vir vazia em exceptions construídas sem args
        # (ex: HTTPError 4xx do provider sem detail). Garante que o
        # campo `error` na DB sempre tem informação útil pra debug —
        # antes ficavam rows com error='' e admins viam "falhou sem
        # explicação" no painel.
        err_msg = str(e) or f"{type(e).__name__}: <no message>"
        logger.error(
            "message_processing_error",
            message_id=message.id,
            phone=message.phone_number,
            agent_id=message.agent_id,
            error=err_msg,
            error_type=type(e).__name__,
        )
        await mark_failed(pool, message.id, err_msg)
