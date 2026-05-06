"""Webhook inbound da Evolution API — M2.b.

Recebe notificações `messages.upsert` da Evolution e enfileira pra
processamento pelo Worker. Mesmo pipeline assíncrono do webhook Twilio:

    Evolution → POST /webhook/evolution → Fila (PG) → Worker → resposta

A Evolution dispara o webhook quando configurada via:

    POST /webhook/set/{instance}
    { "webhook": { "url": ".../webhook/evolution",
                   "events": ["messages.upsert"] } }

Validação opcional do header `apikey` quando
`EVOLUTION_VALIDATE_APIKEY=true` — obrigatório em produção.
"""

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, Response

from whatsapp_langchain.agents.loader import AgentNotFoundError, list_agents
from whatsapp_langchain.server.dependencies import check_rate_limit
from whatsapp_langchain.shared.agente import resolve_agente_runtime
from whatsapp_langchain.shared.atendimento import open_or_attach_atendimento
from whatsapp_langchain.shared.cliente import upsert_cliente
from whatsapp_langchain.shared.conexao import get_conexao_by_evolution_instance
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.hook_dispatcher import dispatch_event
from whatsapp_langchain.shared.queue import enqueue_or_buffer

logger = structlog.get_logger()

router = APIRouter(tags=["webhook"])


def _normalize_event_name(event: str) -> str:
    """Normaliza pra `messages.upsert` (Evolution usa essa forma OU
    `MESSAGES_UPSERT` dependendo da versão/config)."""
    return event.strip().lower().replace("_", ".")


def _phone_from_jid(jid: str) -> str:
    """Extrai número E.164 do JID Evolution.

    Aceita:
    - `5511999999999@s.whatsapp.net` → `+5511999999999`
    - `5511999999999@c.us`           → `+5511999999999`
    - `5511999999999`                → `+5511999999999`
    - `+5511999999999`               → `+5511999999999`

    NÃO usar diretamente quando `jid` é `@lid` — Linked Identity é um id
    interno do WhatsApp e não o número. Para esses casos o caller deve
    preferir `key.remoteJidAlt` antes de cair aqui.
    """
    digits = jid.split("@", 1)[0].lstrip("+")
    return f"+{digits}" if digits else ""


def _resolve_sender_phone(key: dict) -> str:
    """Resolve o telefone E.164 do remetente a partir do `key` Evolution.

    O WhatsApp introduziu `LID` (Linked Identity) — quando o `remoteJid`
    termina em `@lid`, o número real fica em `remoteJidAlt`
    (`<phone>@s.whatsapp.net`). Versões mais novas do Baileys/Evolution
    incluem `addressingMode: "lid"` no key. Preferimos `remoteJidAlt`
    sempre que disponível, com fallback pro `remoteJid` direto.
    """
    remote_alt = str(key.get("remoteJidAlt") or "").strip()
    remote_jid = str(key.get("remoteJid") or "").strip()
    addressing = str(key.get("addressingMode") or "").strip().lower()

    if remote_alt and (addressing == "lid" or remote_jid.endswith("@lid")):
        return _phone_from_jid(remote_alt)
    if remote_jid:
        return _phone_from_jid(remote_jid)
    if remote_alt:
        return _phone_from_jid(remote_alt)
    return ""


def _extract_text(message: dict) -> str:
    """Extrai texto de payloads suportados (MVP: só texto).

    Tipos cobertos: `conversation` (texto curto) e
    `extendedTextMessage.text` (texto com link/preview).
    Outros tipos (imageMessage, audioMessage, etc) ainda não
    são suportados — retorna string vazia e o processamento ignora.
    """
    if not isinstance(message, dict):
        return ""
    text = message.get("conversation")
    if isinstance(text, str) and text:
        return text
    extended = message.get("extendedTextMessage")
    if isinstance(extended, dict):
        et = extended.get("text")
        if isinstance(et, str):
            return et
    return ""


@router.post("/webhook/evolution")
async def webhook_evolution(
    request: Request,
    apikey: str | None = Header(default=None),
) -> Response:
    """Recebe webhook Evolution e enfileira para processamento.

    Filtra apenas `messages.upsert` com `fromMe=false` (mensagens
    inbound). Outros eventos respondem 200 silently — Evolution
    retransmite todos os eventos configurados na rota base.

    Quando a instance vinda no payload não bate com nenhuma conexão
    cadastrada, responde 200 (não 404, pra evitar Evolution disparar
    retries em rota válida porém sem destinatário).
    """
    if settings.evolution_validate_apikey:
        expected = (
            settings.evolution_api_key.get_secret_value()
            if settings.evolution_api_key is not None
            else ""
        )
        if not expected or apikey != expected:
            logger.warning(
                "evolution_webhook_invalid_apikey",
                provided=bool(apikey),
            )
            raise HTTPException(status_code=401, detail="Invalid apikey")

    payload = await request.json()
    event = _normalize_event_name(str(payload.get("event") or ""))
    instance = str(payload.get("instance") or "").strip()

    if event != "messages.upsert":
        logger.debug(
            "evolution_webhook_event_ignored",
            received_event=event,
            instance=instance,
        )
        return Response(status_code=200)

    data = payload.get("data") or {}
    key = data.get("key") or {}
    if not isinstance(key, dict):
        return Response(status_code=200)

    if key.get("fromMe"):
        logger.debug(
            "evolution_webhook_skipped_fromMe",
            instance=instance,
            message_id=key.get("id"),
        )
        return Response(status_code=200)

    # Mensagens de grupo WhatsApp: remoteJid termina em @g.us (grupos),
    # @broadcast (lista) ou @newsletter (canal). Não atendemos esses
    # canais — o handler de outbound não sabe responder pro JID de grupo,
    # e o agente não tem contexto de "quem dentro do grupo está falando".
    # Resposta 200 (não 4xx) pra evitar retries do Evolution.
    remote_jid_check = str(key.get("remoteJid") or "")
    remote_alt_check = str(key.get("remoteJidAlt") or "")
    GROUP_JID_SUFFIXES = ("@g.us", "@broadcast", "@newsletter")
    if any(
        remote_jid_check.endswith(s) or remote_alt_check.endswith(s)
        for s in GROUP_JID_SUFFIXES
    ):
        logger.info(
            "evolution_webhook_group_ignored",
            instance=instance,
            remote_jid=remote_jid_check,
            participant=key.get("participant"),
        )
        return Response(status_code=200)

    if not instance:
        # Payload Evolution malformado — provável probe/teste.
        logger.info("evolution_webhook_missing_instance", payload_event=event)
        raise HTTPException(status_code=400, detail="Missing instance")

    pool = await get_pool()
    conexao = await get_conexao_by_evolution_instance(pool, instance)
    if conexao is None or conexao.status != "active":
        # Instância não cadastrada na empresa — esperado quando server
        # Evolution dispara pra múltiplos consumidores.
        logger.info(
            "evolution_webhook_unknown_instance",
            instance=instance,
            status=conexao.status if conexao else None,
        )
        return Response(status_code=200)

    phone_number = _resolve_sender_phone(key)
    if not phone_number:
        # Payload sem JID válido — raro, descartar silenciosamente.
        logger.info(
            "evolution_webhook_missing_sender",
            instance=instance,
            remote_jid=key.get("remoteJid"),
            remote_jid_alt=key.get("remoteJidAlt"),
        )
        raise HTTPException(status_code=400, detail="Missing sender JID")

    text = _extract_text(data.get("message") or {})
    if not text:
        # Mídia/sticker/áudio — fora do MVP. Loga e responde 200 pra Evolution
        # não retransmitir (a alternativa de 4xx geraria retries indesejados).
        logger.info(
            "evolution_webhook_unsupported_message_type",
            instance=instance,
            message_id=key.get("id"),
            keys=list((data.get("message") or {}).keys()),
        )
        return Response(status_code=200)

    empresa_id = conexao.empresa_id
    conexao_id = conexao.id
    requested_agent = conexao.default_agent_id

    # A.6 — resolve via agente_ia table primeiro; cai pro catálogo se ausente.
    runtime = await resolve_agente_runtime(pool, empresa_id, requested_agent)
    if runtime is not None:
        if runtime.template_catalog not in list_agents():
            raise AgentNotFoundError(runtime.template_catalog)
        resolved_agent = runtime.slug
    else:
        if requested_agent not in list_agents():
            raise AgentNotFoundError(requested_agent)
        resolved_agent = requested_agent

    await check_rate_limit(phone_number)

    push_name = data.get("pushName")
    profile_name = push_name.strip() if isinstance(push_name, str) else None

    cliente = await upsert_cliente(
        pool, empresa_id, phone_number, nome=profile_name
    )
    atendimento, atendimento_aberto = await open_or_attach_atendimento(
        pool,
        empresa_id=empresa_id,
        cliente_id=cliente.id,
        conexao_id=conexao_id,
        agente=resolved_agent,
    )

    msg_id = str(key.get("id") or "").strip() or None
    await enqueue_or_buffer(
        pool=pool,
        phone_number=phone_number,
        agent_id=resolved_agent,
        body=text,
        media_url=None,
        media_type=None,
        to_number=conexao.from_number,
        message_id=msg_id,
        buffer_seconds=settings.message_buffer_seconds,
        empresa_id=empresa_id,
        conexao_id=conexao_id,
        atendimento_id=atendimento.id,
    )

    logger.info(
        "webhook_evolution_received",
        phone=phone_number,
        agent_id=resolved_agent,
        empresa_id=empresa_id,
        conexao_id=conexao_id,
        cliente_id=cliente.id,
        atendimento_id=atendimento.id,
        atendimento_aberto=atendimento_aberto,
        message_id=msg_id,
        instance=instance,
    )

    if atendimento_aberto:
        await dispatch_event(
            pool,
            empresa_id,
            "atendimento.aberto",
            {
                "atendimento_id": atendimento.id,
                "cliente_id": cliente.id,
                "cliente_telefone": cliente.telefone,
                "cliente_nome": cliente.nome,
                "conexao_id": conexao_id,
                "agente_atual": atendimento.agente_atual,
            },
        )
    await dispatch_event(
        pool,
        empresa_id,
        "mensagem.recebida",
        {
            "atendimento_id": atendimento.id,
            "cliente_id": cliente.id,
            "cliente_telefone": cliente.telefone,
            "message_sid": msg_id,
            "body": text,
            "num_media": 0,
        },
    )

    return Response(status_code=200)
