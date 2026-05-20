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
from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.agents.loader import load_graph
from whatsapp_langchain.shared.agente import (
    get_agente_by_slug,
    resolve_agente_runtime,
)
from whatsapp_langchain.shared.atendimento import (
    clear_coleta_estado,
    close_atendimento,
    count_fila_departamento,
    get_atendimento_by_id,
    get_coleta_estado,
    set_coleta_estado,
    set_coleta_resumo,
)
from whatsapp_langchain.shared.cliente import (
    get_cliente_by_telefone,
    update_cliente_partial,
)
from whatsapp_langchain.shared.coleta import (
    build_coleta_render_ctx,
    is_em_andamento,
    make_estado_inicial,
    make_resumo_final,
    pergunta_atual,
    render_pergunta_label,
    validar_e_processar,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.departamento import get_departamento_by_id
from whatsapp_langchain.shared.empresa import get_empresa_csat_config
from whatsapp_langchain.shared.horario import is_business_hours
from whatsapp_langchain.shared.llm import get_agent_llm_config
from whatsapp_langchain.shared.menu_chatbot import (
    cliente_ja_saiu_do_menu,
    format_menu_message,
    get_item,
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

    - {"kind": "explicit", "action": "APROVAR"|"REJEITAR",
       "token": str, "motivo": str|None}
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
    )
    from whatsapp_langchain.shared import (
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
                    f"• {p['summary']} "
                    f"({p['data_inicio'].strftime('%d/%m %H:%M')}) "
                    f"— {p['token']}"
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
        resposta = f"❌ Rejeitado.\n\nAgendamento '{aprov['summary']}' cancelado."
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


def _attach_arquivo(msg: str, menu) -> str:
    """Anexa URL do arquivo de boas-vindas no topo da mensagem.

    Usado pra que o WhatsApp renderize preview/imagem inline (URL pública).
    Se `menu.arquivo_url` está vazio, retorna a mensagem inalterada — não
    requer mudança no protocolo `OutboundClient`.

    Pra suporte nativo a mídia (image/audio/pdf direto via Twilio
    `MediaUrl[]` ou Evolution `mediaMessage`), seria necessário expandir
    o Protocol — fora do escopo dessa iteração.
    """
    arq = getattr(menu, "arquivo_url", None)
    if arq and isinstance(arq, str) and arq.strip():
        return f"{arq.strip()}\n\n{msg}"
    return msg


_ENCERRAR_KEYWORDS = frozenset(
    {"encerrar atendimento", "encerrar", "finalizar atendimento", "finalizar"}
)


async def _try_handle_encerrar_keyword(
    message: MessageQueue,
    pool: AsyncConnectionPool,
    outbound: OutboundClient,
) -> bool:
    """Detecta "encerrar atendimento" e fecha como resolvido.

    Trigger explícito que o sistema ensina ao cliente na mensagem auto
    de transferência (Sprint E.1). Permite cliente sair da fila de
    atendimento humano sem precisar contato com agente.

    Retorna True quando processou (fechou + respondeu); False quando
    não é keyword OU atendimento já está fechado.
    """
    if message.atendimento_id is None:
        return False
    text = (message.incoming_message or "").strip().lower()
    if text not in _ENCERRAR_KEYWORDS:
        return False
    atd = await get_atendimento_by_id(pool, message.atendimento_id)
    if atd is None or atd.status not in ("aguardando", "em_andamento"):
        return False
    closed = await close_atendimento(
        pool, message.atendimento_id, "resolvido"
    )
    if closed is None:
        return False
    msg = (
        "Seu atendimento foi finalizado. Obrigado pelo contato! "
        "Caso precise novamente, é só mandar uma mensagem."
    )
    try:
        await outbound.send_message(message.phone_number, msg)
    except Exception as exc:
        logger.warning(
            "encerrar_outbound_failed",
            atendimento_id=message.atendimento_id,
            error=str(exc),
        )

    # Sprint F.3 — Pesquisa CSAT pós-fechamento (best-effort, não bloqueia)
    await _send_csat_se_configurado(message.empresa_id, message.phone_number, pool)

    await mark_done(pool, message.id, msg, normalized_input=text)
    await upsert_conversation(
        pool,
        phone_number=message.phone_number,
        agent_id=message.agent_id,
        last_message=msg,
        empresa_id=message.empresa_id,
    )
    logger.info(
        "atendimento_encerrado_via_keyword",
        atendimento_id=message.atendimento_id,
        empresa_id=message.empresa_id,
    )
    return True


async def _try_capture_avaliacao(
    message: MessageQueue,
    pool: AsyncConnectionPool,
    outbound: OutboundClient,
) -> bool:
    """Sprint X — captura resposta NPS pós-pesquisa CSAT.

    Fluxo:
    - Se cliente tem atendimento aguardando_avaliacao_at (≤24h) e mensagem
      é número 0-10 → grava nota + pergunta comentário (set
      aguardando_comentario_at) + early return.
    - Se cliente tem atendimento aguardando_comentario_at (≤60s) → grava
      texto como comentário + agradece + early return.
    - Caso contrário: return False (segue fluxo normal).
    """
    from whatsapp_langchain.shared.avaliacao import (
        clear_flags,
        find_aguardando_avaliacao,
        parse_nota,
        save_avaliacao,
        set_aguardando_comentario,
    )

    text = (message.incoming_message or "").strip()
    if not text:
        return False

    # Resolve cliente_id pelo telefone
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id FROM cliente WHERE empresa_id = %s AND telefone = %s LIMIT 1",
            (message.empresa_id, message.phone_number),
        )
        row = await cur.fetchone()
    if not row:
        return False
    cliente_id = int(row[0])

    aguardando = await find_aguardando_avaliacao(
        pool, empresa_id=message.empresa_id, cliente_id=cliente_id
    )
    if aguardando is None:
        return False

    atendimento_id = aguardando["atendimento_id"]

    # Resolve config da empresa pra customizar mensagens (agradecimento +
    # toggle solicita_comentario). Default fallback se não configurada.
    config = await get_empresa_csat_config(pool, message.empresa_id)
    msg_agradecimento = (
        config["agradecimento"]
        if config
        else "Obrigado pelo seu feedback! 😊"
    )
    solicita_comentario = bool(config["solicita_comentario"]) if config else True

    # Estado COMENTÁRIO tem prioridade (janela mais curta) — se cliente envia
    # texto livre dentro de 60s pós-nota, grava como comentário.
    if aguardando["aguardando_comentario_at"] is not None:
        try:
            await save_avaliacao(
                pool, atendimento_id=atendimento_id, comentario=text
            )
            await clear_flags(pool, atendimento_id)
            await outbound.send_message(message.phone_number, msg_agradecimento)
            await mark_done(
                pool,
                message.id,
                msg_agradecimento,
                normalized_input=text,
            )
            logger.info(
                "nps_comentario_capturado",
                atendimento_id=atendimento_id,
                empresa_id=message.empresa_id,
            )
            return True
        except Exception as exc:
            logger.warning(
                "nps_comentario_falhou",
                atendimento_id=atendimento_id,
                error=str(exc),
            )
            await clear_flags(pool, atendimento_id)
            return False

    # Estado AVALIAÇÃO — espera número 0-10
    if aguardando["aguardando_avaliacao_at"] is not None:
        nota = parse_nota(text)
        if nota is None:
            # Cliente respondeu mas sem número — ignora a flag e deixa cair
            # no fluxo normal (vai pro agente IA / menu como mensagem comum)
            return False
        try:
            await save_avaliacao(
                pool, atendimento_id=atendimento_id, nota=nota
            )
            if solicita_comentario:
                await set_aguardando_comentario(pool, atendimento_id)
                resposta = (
                    f"Obrigado pela sua nota *{nota}*! 🙏\n\n"
                    "Quer deixar um comentário sobre o atendimento? "
                    "(Opcional — basta responder a próxima mensagem)"
                )
            else:
                await clear_flags(pool, atendimento_id)
                resposta = msg_agradecimento
            await outbound.send_message(message.phone_number, resposta)
            await mark_done(
                pool, message.id, resposta, normalized_input=text
            )
            logger.info(
                "nps_nota_capturada",
                atendimento_id=atendimento_id,
                empresa_id=message.empresa_id,
                nota=nota,
                solicita_comentario=solicita_comentario,
            )
            return True
        except Exception as exc:
            logger.warning(
                "nps_nota_falhou",
                atendimento_id=atendimento_id,
                nota=nota,
                error=str(exc),
            )
            await clear_flags(pool, atendimento_id)
            return False

    return False


# Quais acoes do menu se beneficiam de coleta antes de despachar.
# Submenu e setar_nome não rodam wizard (submenu navega, setar_nome JÁ é
# coleta na sua semântica). Pesquisa_csat também não — ele coleta nota.
_ACAO_TIPOS_COM_COLETA = frozenset({
    "chamar_agente",
    "transferir_dep",
    "transferir_atendente",
    "mudar_manual",
    "enviar_template",
    "chamar_webhook",
    "enviar_link",
    "enviar_msg",
})


def _coleta_ja_executada_pro_item(atendimento, item_id: int) -> bool:
    """True se o atendimento já tem coleta_resumo populado pra esse item.

    Evita re-iniciar wizard quando o handler de coleta acabou de terminar
    e fez re-entry com texto sintético da ordem do item.
    """
    if atendimento is None:
        return False
    resumo = getattr(atendimento, "coleta_resumo", None)
    if not resumo:
        return False
    return resumo.get("item_id") == item_id


async def _iniciar_coleta_wizard(
    message: MessageQueue,
    pool: AsyncConnectionPool,
    outbound: OutboundClient,
    menu,
    item,
    text: str,
) -> None:
    """Inicia o wizard: grava estado idx=0 + envia primeira pergunta."""
    from whatsapp_langchain.shared.variavel import build_render_context

    perguntas = item.coleta_perguntas or []
    if not perguntas:
        return
    estado = make_estado_inicial(item.id, perguntas)
    try:
        base_ctx = await build_render_context(
            pool, empresa_id=message.empresa_id, cliente_phone=message.phone_number
        )
    except Exception:  # noqa: BLE001
        base_ctx = {}
    ctx = build_coleta_render_ctx(base_ctx, {})
    primeira = perguntas[0]
    label = render_pergunta_label(primeira.get("label", ""), ctx)
    await set_coleta_estado(pool, message.atendimento_id, estado)
    await outbound.send_message(message.phone_number, label)
    await registrar_historico(
        pool,
        atendimento_id=message.atendimento_id,
        menu_id=menu.id,
        item_id=item.id,
        posicao_atual_item_id=None,
        resposta=text,
    )
    await mark_done(pool, message.id, label, normalized_input=text)
    await upsert_conversation(
        pool,
        phone_number=message.phone_number,
        agent_id=message.agent_id,
        last_message=label,
        empresa_id=message.empresa_id,
    )
    logger.info(
        "coleta_wizard_iniciado",
        atendimento_id=message.atendimento_id,
        item_id=item.id,
        n_perguntas=len(perguntas),
    )


async def _try_handle_coleta_em_curso(
    message: MessageQueue,
    pool: AsyncConnectionPool,
    outbound: OutboundClient,
) -> bool:
    """Sprint Wizard Coleta — processa próxima pergunta se há wizard ativo.

    Lê `atendimento.coleta_estado`. Se existe e idx<len(perguntas),
    valida texto contra a pergunta atual:

    - inválido → manda retry, return True (consumiu turno)
    - válido + tem próxima → avança idx, manda próxima, return True
    - válido + última → grava resumo, limpa estado, RE-ENTRA no
      _try_handle_menu com texto sintético = ordem do item escolhido
      pra disparar acao_tipo original

    Retorna False quando NÃO há wizard ativo (deixa fluxo seguir
    normalmente pro _try_handle_workflow / _try_handle_menu).
    """
    atend_id = message.atendimento_id
    if atend_id is None:
        return False
    estado = await get_coleta_estado(pool, atend_id)
    if not is_em_andamento(estado):
        return False
    assert estado is not None  # narrow pro mypy

    text = (message.incoming_message or "").strip()
    ok, erro, novo_estado = validar_e_processar(estado, text)
    if not ok:
        # Inválido — manda retry, mantém estado, consome turno
        retry = erro or "Resposta inválida, tente novamente."
        await outbound.send_message(message.phone_number, retry)
        await mark_done(pool, message.id, retry, normalized_input=text)
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=retry,
            empresa_id=message.empresa_id,
        )
        logger.info(
            "coleta_resposta_invalida",
            atendimento_id=atend_id,
            idx=estado.get("idx"),
        )
        return True

    # Resposta válida — checa se tem próxima pergunta
    prox = pergunta_atual(novo_estado)
    if prox is not None:
        # Tem mais perguntas: salva estado + manda próxima
        # Render context: globais + respostas já dadas
        from whatsapp_langchain.shared.variavel import build_render_context

        try:
            base_ctx = await build_render_context(
                pool, empresa_id=message.empresa_id, cliente_phone=message.phone_number
            )
        except Exception:  # noqa: BLE001
            base_ctx = {}
        ctx = build_coleta_render_ctx(base_ctx, novo_estado.get("respostas") or {})
        label_render = render_pergunta_label(prox.get("label", ""), ctx)
        await set_coleta_estado(pool, atend_id, novo_estado)
        await outbound.send_message(message.phone_number, label_render)
        await mark_done(pool, message.id, label_render, normalized_input=text)
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=label_render,
            empresa_id=message.empresa_id,
        )
        logger.info(
            "coleta_proxima_pergunta",
            atendimento_id=atend_id,
            idx=novo_estado.get("idx"),
        )
        return True

    # Última pergunta — grava resumo, limpa estado, re-entra no menu
    # com texto sintético = ordem do item escolhido originalmente
    item_id = novo_estado.get("item_id")
    item = await get_item(pool, item_id) if item_id else None
    item_label = item.label if item else None
    resumo = make_resumo_final(novo_estado, item_label=item_label)
    await set_coleta_resumo(pool, atend_id, resumo)
    await clear_coleta_estado(pool, atend_id)
    logger.info(
        "coleta_concluida",
        atendimento_id=atend_id,
        item_id=item_id,
        n_respostas=len(novo_estado.get("respostas") or {}),
    )

    # Re-entra no menu com texto = ordem do item (cliente "escolhe de novo")
    if item is not None:
        sintetica = message.model_copy(
            update={"incoming_message": str(item.ordem)}
        )
        # `_try_handle_menu` agora não vai re-iniciar wizard porque
        # coleta_resumo está populado pro mesmo item_id.
        return await _try_handle_menu(sintetica, pool, outbound)
    # Sem item resolvido (raro): só consome turno
    return True


async def _try_handle_workflow(
    message: MessageQueue,
    pool: AsyncConnectionPool,
    outbound: OutboundClient,
    checkpointer: Any,
) -> bool:
    """Sprint Workflow-LangGraph — tenta processar via workflow ativo.

    Retorna True se workflow handled (mensagens enviadas + mark_done).
    Retorna False se: (a) atendimento já tem agente_atual setado
    (delegou pra IA via #6), (b) empresa não tem workflow ativo, ou
    (c) workflow já terminou (cliente já saiu).

    Quando False, fluxo cai pro _try_handle_menu / agente IA normal.
    """
    atend_id = message.atendimento_id
    if atend_id is None:
        return False

    # #6 — só pula workflow quando agente foi EXPLICITAMENTE delegado.
    # Como atendimento.agente_atual é NOT NULL com default 'vsa_tech' (e a
    # webhook ainda pode substituir pelo default da empresa via fallback),
    # comparamos contra: (a) literal 'vsa_tech' (default histórico do schema)
    # e (b) o agente default ativo da empresa (resolvido em DB).
    _SCHEMA_DEFAULT_AGENT = "vsa_tech"
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT a.agente_atual,
                   (SELECT slug FROM agente_ia
                     WHERE empresa_id = a.empresa_id
                       AND is_default = TRUE AND ativo = TRUE
                     LIMIT 1) AS empresa_default
              FROM atendimento a WHERE a.id = %s
            """,
            (atend_id,),
        )
        row = await cur.fetchone()
    if row and row[0]:
        agente_atual, empresa_default = row[0], row[1]
        is_initial = agente_atual in (_SCHEMA_DEFAULT_AGENT, empresa_default)
        if not is_initial:
            return False

    from whatsapp_langchain.workflows.loader import build_runner_for_empresa

    runner = await build_runner_for_empresa(pool, checkpointer, message.empresa_id)
    if runner is None:
        return False

    text = (message.incoming_message or "").strip()
    outbound_msgs = await runner.process(
        atendimento_id=atend_id,
        empresa_id=message.empresa_id,
        msg=text,
    )

    if not outbound_msgs:
        # Workflow terminou (END) — deixa caír pro fluxo normal
        return False

    # Envia mensagens ao cliente (text + media)
    sent_text_parts: list[str] = []
    for m in outbound_msgs:
        kind = m.get("kind", "text")
        if kind == "media":
            url = m.get("url", "")
            caption = m.get("caption", "")
            try:
                # Outbound clients podem ter send_media (Twilio/Evolution).
                # Sem suporte garantido pelo Protocol, fazemos getattr seguro.
                send_media = getattr(outbound, "send_media", None)
                if callable(send_media):
                    import inspect

                    result = send_media(message.phone_number, url, caption=caption)
                    if inspect.isawaitable(result):
                        await result
                else:
                    # Fallback: envia URL como texto se provider não suporta
                    fallback = f"{caption}\n{url}" if caption else url
                    await outbound.send_message(message.phone_number, fallback)
                    sent_text_parts.append(fallback)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "workflow_send_media_failed",
                    url=url,
                    error=str(exc),
                )
        else:
            text_out = m.get("text", "")
            if text_out:
                await outbound.send_message(message.phone_number, text_out)
                sent_text_parts.append(text_out)

    summary = "\n".join(sent_text_parts) if sent_text_parts else "[workflow]"
    await mark_done(pool, message.id, summary, normalized_input=text)
    logger.info(
        "workflow_handled",
        atendimento_id=message.atendimento_id,
        empresa_id=message.empresa_id,
        msgs_sent=len(outbound_msgs),
    )
    return True


async def _send_csat_se_configurado(
    empresa_id: int,
    phone_number: str,
    pool: AsyncConnectionPool,
) -> None:
    """Worker-side helper: resolve o atendimento mais recente do cliente
    pelo telefone, depois delega pra trigger_csat_se_ativo (shared).
    """
    from whatsapp_langchain.shared.avaliacao import trigger_csat_se_ativo

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id FROM atendimento
             WHERE empresa_id = %s
               AND cliente_id = (
                   SELECT id FROM cliente
                    WHERE empresa_id = %s AND telefone = %s
                    LIMIT 1
               )
             ORDER BY id DESC LIMIT 1
            """,
            (empresa_id, empresa_id, phone_number),
        )
        row = await cur.fetchone()
    if not row:
        return
    await trigger_csat_se_ativo(pool, empresa_id, int(row[0]))


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
        msg = _attach_arquivo(
            format_menu_message(menu.mensagem_boas_vindas, children), menu
        )
        await outbound.send_message(message.phone_number, msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=None,
            posicao_atual_item_id=None,
            resposta=text,
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
    # da conexão — envia boas-vindas (ou pergunta nome antes, se solicitar_nome).
    # Se atendimento já tem agente customizado (não é o default), assume que
    # cliente já passou pelo menu antes — pula direto pro agente.
    if hist_menu_id is None:
        # Heurística: se atendimento foi criado AGORA mesmo (status='aguardando',
        # last_message_at == created_at), é primeira mensagem.
        if atendimento.status == "aguardando":
            # Auto-navegar: admin marcou item alvo. Quando é chamar_agente,
            # configuramos atendimento e deixamos a mensagem original seguir
            # pro agente — sem boas-vindas, sem coleta de nome. Outros tipos
            # de auto-navegar (ex: enviar_msg) caem no fluxo normal abaixo.
            if menu.auto_navegar_para_item_id:
                from whatsapp_langchain.shared.menu_chatbot import get_item

                target = await get_item(pool, menu.auto_navegar_para_item_id)
                if (
                    target is not None
                    and target.menu_id == menu.id
                    and target.ativo
                    and target.acao_tipo == "chamar_agente"
                ):
                    auto_slug = (target.acao_payload or {}).get("agente_slug")
                    if isinstance(auto_slug, str) and auto_slug:
                        ag_db = await get_agente_by_slug(
                            pool, message.empresa_id, auto_slug
                        )
                        if ag_db is not None and ag_db.ativo:
                            async with pool.connection() as conn:
                                await conn.execute(
                                    "UPDATE atendimento SET agente_atual = %s, "
                                    "updated_at = NOW() WHERE id = %s",
                                    (auto_slug, message.atendimento_id),
                                )
                                await conn.commit()
                            await registrar_historico(
                                pool,
                                atendimento_id=message.atendimento_id,
                                menu_id=menu.id,
                                item_id=target.id,
                                posicao_atual_item_id=None,
                                resposta=text,
                            )
                            logger.info(
                                "menu_auto_navegar_chamar_agente",
                                atendimento_id=message.atendimento_id,
                                menu_id=menu.id,
                                item_id=target.id,
                                agente_slug=auto_slug,
                            )
                            # Deixa a mensagem original seguir pro agente
                            return False

            children = await list_children(pool, menu.id, None)
            if not children:
                # Menu sem opções — config inválida, deixa pro agente
                logger.warning(
                    "menu_sem_opcoes_raiz",
                    menu_id=menu.id,
                    empresa_id=message.empresa_id,
                )
                return False

            # Wizard de coleta nome pré-menu — quando solicitar_nome=true e
            # cliente ainda sem nome cadastrado, pergunta nome ANTES de exibir
            # o menu. Estado é derivado do histórico (ver segundo turno abaixo).
            if menu.solicitar_nome:
                cliente = await get_cliente_by_telefone(
                    pool, message.empresa_id, message.phone_number
                )
                if not (cliente and cliente.nome and cliente.nome.strip()):
                    pergunta = (
                        menu.mensagem_coleta
                        or "Olá! Antes de começarmos, qual seu nome?"
                    ).strip()
                    await outbound.send_message(message.phone_number, pergunta)
                    # Marca histórico de coleta — item_id NULL, posicao NULL.
                    # No próximo turno, hist_menu_id != None + posicao=NULL +
                    # cliente sem nome + solicitar_nome=true → estamos esperando
                    # a resposta do nome.
                    await registrar_historico(
                        pool,
                        atendimento_id=message.atendimento_id,
                        menu_id=menu.id,
                        item_id=None,
                        posicao_atual_item_id=None,
                        resposta=text,
                    )
                    await mark_done(pool, message.id, pergunta, normalized_input=text)
                    await upsert_conversation(
                        pool,
                        phone_number=message.phone_number,
                        agent_id=message.agent_id,
                        last_message=pergunta,
                        empresa_id=message.empresa_id,
                    )
                    logger.info(
                        "menu_coleta_nome_perguntou",
                        atendimento_id=message.atendimento_id,
                        menu_id=menu.id,
                    )
                    return True

            msg = _attach_arquivo(
                format_menu_message(menu.mensagem_boas_vindas, children), menu
            )
            await outbound.send_message(message.phone_number, msg)
            await registrar_historico(
                pool,
                atendimento_id=message.atendimento_id,
                menu_id=menu.id,
                item_id=None,
                posicao_atual_item_id=None,
                resposta=text,
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
            # Sprint 3: telemetria webhook — permite n8n rastrear funil
            from whatsapp_langchain.shared.hook_dispatcher import dispatch_event

            await dispatch_event(
                pool,
                message.empresa_id,
                "menu.boas_vindas_enviado",
                {
                    "atendimento_id": message.atendimento_id,
                    "menu_id": menu.id,
                    "num_options": len(children),
                    "phone": message.phone_number,
                },
            )
            return True
        # Em andamento sem histórico de menu → cliente nunca passou pelo menu
        # (atendimento legacy, ou menu cadastrado depois). Deixa pro agente.
        return False

    # Segundo turno do wizard de coleta — temos histórico mas posicao_atual=NULL
    # e cliente AINDA sem nome E menu pede solicitar_nome. Trata o texto como
    # resposta da pergunta de nome.
    if (
        posicao_atual is None
        and menu.solicitar_nome
        and atendimento.status == "aguardando"
    ):
        cliente = await get_cliente_by_telefone(
            pool, message.empresa_id, message.phone_number
        )
        if not (cliente and cliente.nome and cliente.nome.strip()):
            nome_capturado = text.strip()
            # Validação leve: 2+ chars, sem ser só dígitos (evita capturar
            # número de telefone ou opção de menu como nome).
            if len(nome_capturado) >= 2 and not nome_capturado.isdigit():
                if cliente is not None:
                    await update_cliente_partial(
                        pool,
                        cliente_id=cliente.id,
                        empresa_id=message.empresa_id,
                        nome=nome_capturado,
                    )
                # Manda confirma (com placeholder {nome}) + final + menu
                children = await list_children(pool, menu.id, None)
                confirma = (
                    (menu.mensagem_confirmar_coleta or "Obrigado, {nome}! 🙂")
                    .replace("{nome}", nome_capturado)
                    .strip()
                )
                final = (menu.mensagem_final_coleta or "").strip()
                menu_text = format_menu_message(menu.mensagem_boas_vindas, children)
                pieces = [confirma]
                if final:
                    pieces.append(final)
                pieces.append(menu_text)
                full_msg = "\n\n".join(pieces)
                await outbound.send_message(message.phone_number, full_msg)
                await registrar_historico(
                    pool,
                    atendimento_id=message.atendimento_id,
                    menu_id=menu.id,
                    item_id=None,
                    posicao_atual_item_id=None,
                    resposta=text,
                )
                await mark_done(pool, message.id, full_msg, normalized_input=text)
                await upsert_conversation(
                    pool,
                    phone_number=message.phone_number,
                    agent_id=message.agent_id,
                    last_message=full_msg,
                    empresa_id=message.empresa_id,
                )
                logger.info(
                    "menu_coleta_nome_capturado",
                    atendimento_id=message.atendimento_id,
                    menu_id=menu.id,
                    nome_chars=len(nome_capturado),
                )
                return True
            # Resposta inválida — pede nome de novo
            erro = "Hmm, não consegui entender seu nome. Pode digitar novamente?"
            await outbound.send_message(message.phone_number, erro)
            await mark_done(pool, message.id, erro, normalized_input=text)
            await upsert_conversation(
                pool,
                phone_number=message.phone_number,
                agent_id=message.agent_id,
                last_message=erro,
                empresa_id=message.empresa_id,
            )
            logger.info(
                "menu_coleta_nome_invalido",
                atendimento_id=message.atendimento_id,
                texto=text[:80],
            )
            return True

    # Cliente JÁ saiu do menu? (escolheu chamar_agente/transferir_dep/fechar/
    # mudar_manual antes). Próxima msg dele vai pro agente — NÃO trata como
    # navegação. Sem esse check, "Olá" depois de "3 → Vou te conectar com
    # Agendamentos…" caía em "Opção inválida" em vez de seguir pro agente.
    #
    # EXCEÇÃO: wizard de coleta acabou de terminar — `_try_handle_coleta_em_curso`
    # gravou `coleta_resumo` e re-entra aqui com texto sintético = ordem do
    # item escolhido. O histórico contém o item de coleta (com acao_tipo já
    # registrada em _ACOES_SAIDA_MENU), que faria `cliente_ja_saiu_do_menu`
    # retornar True. Pulamos pra despachar a ação original.
    coleta_resumo = getattr(atendimento, "coleta_resumo", None) or {}
    coleta_em_reentry = bool(coleta_resumo.get("item_id"))
    if (
        posicao_atual is None
        and not coleta_em_reentry
        and await cliente_ja_saiu_do_menu(pool, message.atendimento_id)
    ):
        logger.info(
            "menu_cliente_fora_segue_pro_agente",
            atendimento_id=message.atendimento_id,
            agente_atual=atendimento.agente_atual,
        )
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

    # Sprint 3: dispatch event antes de executar a ação. Permite n8n
    # rastrear qual opção foi escolhida mesmo se a ação subsequente falhar.
    from whatsapp_langchain.shared.hook_dispatcher import dispatch_event

    await dispatch_event(
        pool,
        message.empresa_id,
        "menu.opcao_escolhida",
        {
            "atendimento_id": message.atendimento_id,
            "menu_id": menu.id,
            "item_id": item.id,
            "label": item.label,
            "acao_tipo": item.acao_tipo,
            "ordem": item.ordem,
            "phone": message.phone_number,
        },
    )

    # Sprint Wizard Coleta — se item tem perguntas E ainda não rodamos
    # coleta pra ele neste atendimento, inicia o wizard antes de despachar
    # a acao_tipo. Quando wizard termina, _try_handle_coleta_em_curso
    # re-entra aqui (com mesma `text` numérica) e a verificação `coleta_resumo
    # já preenchido pro mesmo item` pula este bloco.
    if (
        item.coleta_perguntas
        and item.acao_tipo in _ACAO_TIPOS_COM_COLETA
        and not _coleta_ja_executada_pro_item(atendimento, item.id)
    ):
        await _iniciar_coleta_wizard(
            message, pool, outbound, menu, item, text
        )
        return True

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
            resposta=text,
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
        out_msg = (
            msg_pre
            or "Você foi transferido. Aguarde, em breve um atendente irá te responder."
        )
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None,  # saiu do menu
            resposta=text,
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
        # Valida que o agente_ia existe e está ativo na empresa.
        # Sem isso, atendimento.agente_atual = slug fantasma e o worker
        # cai no fallback legacy do catálogo (template hardcoded), gerando
        # respostas confusas.
        agente_db = await get_agente_by_slug(pool, message.empresa_id, agente_slug)
        if agente_db is None or not agente_db.ativo:
            logger.warning(
                "menu_chamar_agente_slug_invalido",
                item_id=item.id,
                agente_slug=agente_slug,
                empresa_id=message.empresa_id,
                ativo=getattr(agente_db, "ativo", None),
            )
            # Agente desativado: avisa cliente reapresentando o menu raiz.
            # NÃO tentar resetar `posicao_atual_item_id` em `atendimento` —
            # essa coluna mora em `atendimento_menu_historico` (mig 040), e
            # a confusão histórica gerava `column does not exist` que vazava
            # como bolha de erro técnico no drawer do operador.
            root_children = await list_children(pool, menu.id, None)
            erro_msg = (
                f"{menu.mensagem_opcao_invalida}\n\n"
                f"{format_menu_message(None, root_children)}"
                if root_children
                else menu.mensagem_opcao_invalida
            )
            await outbound.send_message(message.phone_number, erro_msg)
            await mark_done(pool, message.id, erro_msg, normalized_input=text)
            await upsert_conversation(
                pool,
                phone_number=message.phone_number,
                agent_id=message.agent_id,
                last_message=erro_msg,
                empresa_id=message.empresa_id,
            )
            return True
        # UPDATE atendimento.agente_atual + departamento_id (do agente)
        dep_id_resolvido = agente_db.departamento_default_id
        async with pool.connection() as conn:
            if dep_id_resolvido is not None:
                await conn.execute(
                    "UPDATE atendimento SET agente_atual = %s, "
                    "departamento_id = %s, updated_at = NOW() WHERE id = %s",
                    (agente_slug, dep_id_resolvido, message.atendimento_id),
                )
            else:
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
            resposta=text,
        )

        # Mensagem rica padrão de mercado: pre + transferência + encerrar +
        # posição na fila. Cada bloco em mensagens separadas pra parecer
        # natural no WhatsApp (pequenas bolhas em sequência).
        partes: list[str] = []
        if msg_pre:
            partes.append(msg_pre)
        # Resolve nome do departamento (pra "Você foi transferido para o
        # departamento de X")
        dep_nome: str | None = None
        if dep_id_resolvido is not None:
            dep = await get_departamento_by_id(
                pool, message.empresa_id, dep_id_resolvido
            )
            dep_nome = dep.nome if dep else None
        msg_transfer = (
            f"Você foi transferido para o departamento *{dep_nome}*. "
            "Aqui o agente irá fazer a triagem das informações."
            if dep_nome
            else "Você foi transferido. Aguarde, em breve um atendente "
            "irá te responder."
        )
        msg_transfer += (
            "\n\nCaso deseje finalizar o atendimento digite: "
            "*encerrar atendimento* e confirme."
        )
        partes.append(msg_transfer)

        # Posição na fila (1-based) — só quando há departamento resolvido
        if dep_id_resolvido is not None:
            try:
                pos = await count_fila_departamento(
                    pool,
                    empresa_id=message.empresa_id,
                    departamento_id=dep_id_resolvido,
                    atendimento_id=message.atendimento_id,
                )
                partes.append(
                    f"Você está na posição *{pos}* da fila de atendimento."
                )
            except Exception as exc:
                logger.warning(
                    "menu_chamar_agente_fila_failed",
                    atendimento_id=message.atendimento_id,
                    error=str(exc),
                )

        # Envia cada parte como msg separada (UX natural). A última fica
        # como `response` do row no message_queue (timeline drawer).
        for parte in partes[:-1]:
            await outbound.send_message(message.phone_number, parte)
        await outbound.send_message(message.phone_number, partes[-1])
        await mark_done(pool, message.id, partes[-1], normalized_input=text)
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=partes[-1],
            empresa_id=message.empresa_id,
        )

        # Sprint E.4 — Triagem proativa: enfileira mensagem sintética
        # `[NOVO_ATENDIMENTO_TRIAGEM]` que vai pro novo agente IA. SYSTEM_PROMPT
        # reconhece e cumprimenta + faz triagem inicial. Sem isso o agente só
        # responde após cliente mandar 2ª mensagem.
        try:
            import uuid

            sentinel_msg = "[NOVO_ATENDIMENTO_TRIAGEM]"
            thread_id = f"{message.phone_number}:{agente_slug}"
            # conexao_id vem do atendimento (não exposto no model MessageQueue).
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT conexao_id FROM atendimento WHERE id = %s",
                    (message.atendimento_id,),
                )
                row = await cur.fetchone()
                conexao_id = row[0] if row else None
                await conn.execute(
                    """
                    INSERT INTO message_queue (
                        empresa_id, conexao_id, atendimento_id, message_id,
                        phone_number, agent_id, thread_id,
                        incoming_message, normalized_input,
                        status, process_after
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        'queued', NOW() + INTERVAL '2 seconds'
                    )
                    """,
                    (
                        message.empresa_id,
                        conexao_id,
                        message.atendimento_id,
                        f"synthetic:triagem:{uuid.uuid4().hex[:16]}",
                        message.phone_number,
                        agente_slug,
                        thread_id,
                        sentinel_msg,
                        sentinel_msg,
                    ),
                )
                await conn.commit()
        except Exception as exc:
            logger.warning(
                "menu_chamar_agente_triagem_enqueue_failed",
                atendimento_id=message.atendimento_id,
                error=str(exc),
            )

        logger.info(
            "menu_chamar_agente",
            atendimento_id=message.atendimento_id,
            agente_slug=agente_slug,
        )
        from whatsapp_langchain.shared.hook_dispatcher import dispatch_event

        await dispatch_event(
            pool,
            message.empresa_id,
            "menu.acao_executada",
            {
                "atendimento_id": message.atendimento_id,
                "menu_id": menu.id,
                "item_id": item.id,
                "acao_tipo": "chamar_agente",
                "agente_slug": agente_slug,
                "phone": message.phone_number,
            },
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
            resposta=text,
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
        user_id = (
            item.acao_atendente_id or payload.get("acao_atendente_id") or ""
        ).strip()
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
        out_msg = (
            msg_pre or "Você foi transferido. Em breve um atendente irá te responder."
        )
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None,
            resposta=text,
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
            "menu_transferir_atendente",
            atendimento_id=message.atendimento_id,
            atendente_user_id=user_id,
        )
        return True

    if item.acao_tipo == "enviar_template":
        # Dispara template de modelo_mensagem como resposta.
        modelo_id = item.acao_modelo_mensagem_id or payload.get(
            "acao_modelo_mensagem_id"
        )
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
                modelo_id=modelo_id,
                empresa_id=message.empresa_id,
            )
            return False
        out_msg = row[0]
        if voltar:
            root_children = await list_children(pool, menu.id, None)
            if root_children:
                out_msg = f"{out_msg}\n\n{format_menu_message(None, root_children)}"
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None if voltar else item.parent_id,
            resposta=text,
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
            "menu_enviar_template",
            atendimento_id=message.atendimento_id,
            modelo_id=modelo_id,
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
                    "menu_chamar_webhook_falhou",
                    url=target_url,
                    error=str(exc),
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
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None if voltar else item.parent_id,
            resposta=text,
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
            "menu_chamar_webhook",
            atendimento_id=message.atendimento_id,
            url=url,
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
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None if voltar else item.parent_id,
            resposta=text,
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
            "menu_enviar_link",
            atendimento_id=message.atendimento_id,
            url=url,
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
        pergunta = (
            item.nota_pergunta
            or payload.get("nota_pergunta")
            or "Por favor, avalie nosso atendimento:"
        ).strip()
        nmin = item.nota_min or payload.get("nota_min") or 1
        nmax = item.nota_max or payload.get("nota_max") or 5
        escala = ", ".join(str(n) for n in range(int(nmin), int(nmax) + 1))
        out_msg = f"{pergunta}\n\nResponda com um número de {nmin} a {nmax}:\n{escala}"
        await outbound.send_message(message.phone_number, out_msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None,
            resposta=text,
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
            "menu_pesquisa_csat",
            atendimento_id=message.atendimento_id,
            escala=f"{nmin}-{nmax}",
        )
        return True

    if item.acao_tipo == "mudar_manual":
        # Sai do menu e marca atendimento como "aguardando" sem agente_atual
        # atribuído — operadores humanos pegam via UI.
        msg = (
            payload.get("mensagem_pre")
            or "Estou te transferindo para um atendente humano. Aguarde um momento."
        ).strip()
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE atendimento SET status = 'aguardando', "
                "agente_atual = NULL, updated_at = NOW() WHERE id = %s",
                (message.atendimento_id,),
            )
            await conn.commit()
        await outbound.send_message(message.phone_number, msg)
        await registrar_historico(
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None,
            resposta=text,
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
            "menu_mudar_manual",
            atendimento_id=message.atendimento_id,
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
            pool,
            atendimento_id=message.atendimento_id,
            menu_id=menu.id,
            item_id=item.id,
            posicao_atual_item_id=None,
            resposta=text,
        )
        await mark_done(pool, message.id, pergunta, normalized_input=text)
        await upsert_conversation(
            pool,
            phone_number=message.phone_number,
            agent_id=message.agent_id,
            last_message=pergunta,
            empresa_id=message.empresa_id,
        )
        logger.info(
            "menu_setar_nome",
            atendimento_id=message.atendimento_id,
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
            resposta=text,
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

        # X: captura resposta NPS pós-pesquisa CSAT (nota 0-10 + comentário).
        # Só intercepta se atendimento estiver aguardando avaliação/comentário
        # e mensagem encaixar no formato esperado.
        if await _try_capture_avaliacao(message, pool, outbound):
            return

        # E.1 — keyword "encerrar atendimento" → fecha como resolvido.
        # Avisada pelo sistema na transferência (mensagem rica menciona
        # "digite *encerrar atendimento* pra finalizar").
        if await _try_handle_encerrar_keyword(message, pool, outbound):
            return

        # Sprint Wizard Coleta — se há wizard em andamento no atendimento,
        # processa a próxima pergunta ANTES de tudo. Quando wizard termina,
        # ele mesmo re-entra no _try_handle_menu pra despachar a ação do
        # item escolhido originalmente (via `coleta_estado.item_id`).
        try:
            if await _try_handle_coleta_em_curso(message, pool, outbound):
                return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "coleta_handler_failed",
                atendimento_id=message.atendimento_id,
                error=str(exc),
            )

        # Sprint Workflow-LangGraph (opt-in via ENABLE_WORKFLOW_ENGINE).
        # Tenta workflow declarativo da empresa antes do menu_item legacy.
        # Se `atendimento.agente_atual` já estiver setado, não roda workflow
        # (#6 hand-off pro agente IA). Workflow ativo da empresa é detectado
        # via `workflow_chatbot.ativo` + slug='menu_principal'.
        if settings.enable_workflow_engine:
            try:
                if await _try_handle_workflow(
                    message, pool, outbound, checkpointer
                ):
                    return
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "workflow_runner_failed",
                    atendimento_id=message.atendimento_id,
                    error=str(exc),
                )

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

        # Sprint O — Guardrails de input
        try:
            from whatsapp_langchain.shared.guardrails import (
                check_input,
                redact_pii,
            )

            # O.1 — Content filter (jailbreak/injection)
            input_check = check_input(normalized_text)
            if input_check.blocked:
                import os as _os
                shadow = _os.environ.get(
                    "GUARDRAIL_INPUT_SHADOW", "true"
                ).lower() == "true"
                logger.warning(
                    "guardrail_input_blocked" + ("_shadow" if shadow else ""),
                    pattern=input_check.pattern,
                    atendimento_id=message.atendimento_id,
                )
                async with pool.connection() as _conn:
                    await _conn.execute(
                        """
                        INSERT INTO guardrail_log
                          (empresa_id, atendimento_id, layer, guardrail,
                           decision, pattern_matched, sample)
                        VALUES (%s, %s, 'input', 'content_filter',
                                %s, %s, %s)
                        """,
                        (
                            message.empresa_id, message.atendimento_id,
                            "shadow_block" if shadow else "block",
                            input_check.pattern, input_check.sample,
                        ),
                    )
                    await _conn.commit()
                if not shadow:
                    response_text = (
                        "Olá! Não consigo processar essa mensagem. "
                        "Vou te transferir para um atendente humano."
                    )
                    await outbound.send_message(
                        message.phone_number, response_text
                    )
                    await mark_done(
                        pool, message.id, response_text,
                        normalized_input=pre.normalized_text,
                    )
                    return
                # shadow=true: só registrou, deixa fluir normal

            # O.2 — PII redaction (input antes de LLM)
            redact_in = redact_pii(normalized_text, mode="mask")
            if redact_in.redacted_anything:
                logger.info(
                    "guardrail_pii_redacted_input",
                    counts=redact_in.counts,
                    atendimento_id=message.atendimento_id,
                )
                async with pool.connection() as _conn:
                    await _conn.execute(
                        """
                        INSERT INTO guardrail_log
                          (empresa_id, atendimento_id, layer, guardrail,
                           decision, metadata)
                        VALUES (%s, %s, 'input', 'pii_redact',
                                'redact', %s::jsonb)
                        """,
                        (
                            message.empresa_id, message.atendimento_id,
                            __import__("json").dumps(redact_in.counts),
                        ),
                    )
                    await _conn.commit()
                normalized_text = redact_in.text
        except Exception as guard_err:
            # Guardrails não devem quebrar o atendimento
            logger.warning("guardrail_input_failed", error=str(guard_err))

        human_message = HumanMessage(content=normalized_text)

        # A.6 — resolve agente_ia DB; runtime=None mantém path legacy (catálogo).
        agente_runtime = await resolve_agente_runtime(
            pool, message.empresa_id, message.agent_id
        )

        # Lookup agente_ia.id pra telemetria ia_execucao (best-effort)
        agente_ia_id: int | None = None
        if agente_runtime is not None:
            async with pool.connection() as _conn:
                _cur = await _conn.execute(
                    "SELECT id FROM agente_ia WHERE empresa_id = %s AND slug = %s",
                    (message.empresa_id, agente_runtime.slug),
                )
                _row = await _cur.fetchone()
                if _row:
                    agente_ia_id = int(_row[0])

        # ia_budget check pré-call (mig 058) — bloqueia ou alerta antes
        # de gastar token se empresa estourou orçamento mensal.
        from whatsapp_langchain.shared.governanca_ia import get_budget_atual

        budget = await get_budget_atual(pool, message.empresa_id)
        if (
            budget
            and budget.get("estourado")
            and budget.get("acao_estouro") == "bloquear"
        ):
            msg_block = (
                "Sistema temporariamente indisponível. Aguarde e tente "
                "novamente em algumas horas."
            )
            await outbound.send_message(message.phone_number, msg_block)
            await mark_done(
                pool,
                message.id,
                msg_block,
                normalized_input=pre.normalized_text,
            )
            logger.warning(
                "ia_budget_block",
                empresa_id=message.empresa_id,
                consumo=budget["consumo_usd"],
                limite=budget["limite_usd"],
            )
            return

        # Callback que registra ia_execucao + atualiza ia_budget após cada
        # chamada LLM (mig 057 + 058 padrão profissional).
        from whatsapp_langchain.shared.llm_callback import IaExecucaoCallback

        ia_callback = IaExecucaoCallback(
            pool,
            empresa_id=message.empresa_id,
            atendimento_id=message.atendimento_id,
            agente_ia_id=agente_ia_id,
        )

        invoke_config = {
            "configurable": {
                "thread_id": message.thread_id,
                "user_id": message.phone_number,
                "empresa_id": message.empresa_id,
                "atendimento_id": message.atendimento_id,
                # Fase 1 fix bug PDF — tools multimodais (analyze_image,
                # transcribe_audio, extract_document, summarize_document)
                # leem media_url daqui em vez do parâmetro do agente.
                # Evita alucinação de URL (agente não tem acesso à URL real).
                "media_url": message.media_url,
                "media_type": message.media_type,
                # Sprint M (RAG por setor) — search_knowledge_base usa pra
                # filtrar docs apenas das pastas do agente. Vazio = busca
                # global na empresa (fallback).
                "base_conhecimento_ids": (
                    agente_runtime.base_conhecimento_ids
                    if agente_runtime is not None else []
                ),
            },
            "callbacks": [ia_callback],
        }
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

        # Sprint O — Guardrails de output
        try:
            from whatsapp_langchain.shared.guardrails import redact_pii
            from whatsapp_langchain.shared.guardrails.output_judge import (
                judge_output,
            )

            # O.2 — PII redaction (output antes de enviar)
            redact_out = redact_pii(response_text, mode="mask")
            if redact_out.redacted_anything:
                logger.info(
                    "guardrail_pii_redacted_output",
                    counts=redact_out.counts,
                    atendimento_id=message.atendimento_id,
                )
                async with pool.connection() as _conn:
                    await _conn.execute(
                        """
                        INSERT INTO guardrail_log
                          (empresa_id, atendimento_id, layer, guardrail,
                           decision, metadata)
                        VALUES (%s, %s, 'output', 'pii_redact',
                                'redact', %s::jsonb)
                        """,
                        (
                            message.empresa_id, message.atendimento_id,
                            __import__("json").dumps(redact_out.counts),
                        ),
                    )
                    await _conn.commit()
                response_text = redact_out.text

            # O.4 — LLM judge condicional (busca último rag para contexto)
            rag_top_score: float | None = None
            rag_hits = 0
            try:
                async with pool.connection() as _conn:
                    _cur = await _conn.execute(
                        """
                        SELECT top_score, hits
                          FROM rag_query_log
                         WHERE atendimento_id = %s
                         ORDER BY id DESC LIMIT 1
                        """,
                        (message.atendimento_id,),
                    )
                    _row = await _cur.fetchone()
                    if _row:
                        rag_top_score = (
                            float(_row[0]) if _row[0] is not None else None
                        )
                        rag_hits = int(_row[1] or 0)
            except Exception:
                pass

            judge = await judge_output(
                user_query=normalized_text,
                response=response_text,
                rag_top_score=rag_top_score,
                rag_hits=rag_hits,
            )
            if not judge.skipped:
                async with pool.connection() as _conn:
                    await _conn.execute(
                        """
                        INSERT INTO guardrail_log
                          (empresa_id, atendimento_id, layer, guardrail,
                           decision, metadata, sample)
                        VALUES (%s, %s, 'output', 'llm_judge',
                                %s, %s::jsonb, %s)
                        """,
                        (
                            message.empresa_id, message.atendimento_id,
                            "allow" if judge.safe else "unsafe",
                            __import__("json").dumps({
                                "cached": judge.cached,
                                "reason": judge.reason,
                            }),
                            response_text[:500],
                        ),
                    )
                    await _conn.commit()
                if not judge.safe:
                    # Shadow mode: GUARDRAIL_OUTPUT_SHADOW=true só loga,
                    # NÃO substitui (default agora — coleta dados antes
                    # de bloquear de fato).
                    import os as _os
                    shadow = _os.environ.get(
                        "GUARDRAIL_OUTPUT_SHADOW", "true"
                    ).lower() == "true"
                    if shadow:
                        logger.warning(
                            "guardrail_output_unsafe_shadow_only",
                            atendimento_id=message.atendimento_id,
                        )
                    else:
                        logger.warning(
                            "guardrail_output_unsafe_replacing_response",
                            atendimento_id=message.atendimento_id,
                        )
                        response_text = (
                            "Olá! Não tenho certeza dessa informação no "
                            "momento. Vou te transferir para um atendente "
                            "humano que pode te ajudar com mais precisão."
                        )
        except Exception as guard_err:
            logger.warning("guardrail_output_failed", error=str(guard_err))

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
        # Detalhe técnico (stack-like) FICA APENAS NO LOG. O que vai
        # pra `message_queue.error` é uma string curta + sanitizada:
        # o drawer do operador renderiza isso como bolha de chat
        # (atendimento-drawer.tsx), então NUNCA pode conter mensagem
        # de exception bruta — vazaria SQL/Python pro humano.
        err_msg = str(e) or f"{type(e).__name__}: <no message>"
        logger.error(
            "message_processing_error",
            message_id=message.id,
            phone=message.phone_number,
            agent_id=message.agent_id,
            error=err_msg,
            error_type=type(e).__name__,
        )
        # Código curto + tipo da exception ajuda a correlacionar com
        # log via `error_type`, sem expor detalhe interno.
        safe_db_error = f"processing_failed:{type(e).__name__}"
        await mark_failed(pool, message.id, safe_db_error)
