"""Webhook do Twilio — processamento assíncrono via fila.

Recebe mensagens do Twilio, valida, aplica rate limit, e coloca na fila
para processamento pelo Worker. Retorna 200 imediatamente (TwiML vazio).

Fluxo: Twilio -> POST /webhook/twilio -> Fila (PostgreSQL) -> Worker

Uso:
    curl -X POST ".../webhook/twilio?agent=rhawk_assistant" \
         -d "MessageSid=SM123&From=whatsapp:+5511..."
"""

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response

from whatsapp_langchain.agents.loader import AgentNotFoundError, list_agents
from whatsapp_langchain.server.dependencies import (
    check_rate_limit,
    validate_twilio_signature,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.queue import enqueue_or_buffer

logger = structlog.get_logger()

router = APIRouter(tags=["webhook"])

# TwiML vazio — indica ao Twilio que recebemos a mensagem
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@router.post("/webhook/twilio")
async def webhook_twilio(
    request: Request,
    agent: str = Query(
        description="ID do agente para processar a mensagem",
    ),
    # Parâmetros Form declarados para documentação OpenAPI (Swagger UI).
    # Os valores reais são lidos via request.form() para suportar
    # MediaUrl{i} dinâmicos (NumMedia > 1).
    message_sid: str = Form(
        default="",
        alias="MessageSid",
        description="ID da mensagem no Twilio (MessageSid).",
    ),
    from_number: str = Form(
        default="",
        alias="From",
        description="Número remetente no formato whatsapp:+55...",
    ),
    to_number_form: str = Form(
        default="",
        alias="To",
        description="Número de destino no formato whatsapp:+...",
    ),
    body: str = Form(
        default="",
        alias="Body",
        description="Texto da mensagem (pode ser vazio em mensagens de mídia).",
    ),
    num_media_raw: str = Form(
        default="0",
        alias="NumMedia",
        description="Quantidade de mídias anexadas (suporta até 10).",
    ),
    wa_id: str = Form(
        default="",
        alias="WaId",
        description="WhatsApp ID do remetente (fallback de From).",
    ),
    _signature: None = Depends(validate_twilio_signature),
) -> Response:
    """Recebe webhook do Twilio e enfileira para processamento.

    Suporta múltiplas mídias no mesmo webhook (NumMedia > 1): cada mídia vira
    1 row independente na fila com o mesmo message_sid; o worker processa cada
    uma como turn separado do agente. O checkpointer LangGraph agrega via thread_id.

    O Worker consome a mensagem da fila, executa o agente, e envia
    a resposta via Twilio. Assinatura validada via HMAC-SHA1 (SDK oficial)
    quando VALIDATE_TWILIO_SIGNATURE=true.

    Args:
        agent: ID do agente (query param).

    Returns:
        TwiML vazio com status 200.
    """
    # Lê form data via Request para acessar MediaUrl{i} dinâmicos.
    # Os parâmetros Form acima são mantidos para documentação OpenAPI;
    # aqui usamos request.form() para leitura real dos campos.
    form = await request.form()

    # Campos escalares — usa os valores já parseados pelos parâmetros Form
    # (ou lê do form diretamente para garantia de consistência).
    msg_sid = (form.get("MessageSid") or "").strip()
    from_raw = (form.get("From") or "").strip()
    to_raw = (form.get("To") or "").strip()
    body_raw = (form.get("Body") or "").strip()
    wa_id_raw = (form.get("WaId") or "").strip()

    try:
        num_media = int(form.get("NumMedia") or "0")
    except ValueError:
        num_media = 0
    # Twilio limita 10 mídias por mensagem WhatsApp
    num_media = max(0, min(num_media, 10))

    # Verifica se o agente existe
    available_agents = list_agents()
    if agent not in available_agents:
        raise AgentNotFoundError(agent)

    # Sanitização de campos do Twilio recebidos via x-www-form-urlencoded.
    # From vem como "whatsapp:+55...", WaId vem como "5511..." sem + (fallback).
    phone_number = from_raw.replace("whatsapp:", "")
    if not phone_number and wa_id_raw:
        # WaId pode vir sem + — normaliza para E.164
        phone_number = wa_id_raw if wa_id_raw.startswith("+") else f"+{wa_id_raw}"
    to_number = to_raw.replace("whatsapp:", "")

    # Rejeita webhook sem identidade de remetente (From e WaId ambos vazios)
    if not phone_number:
        logger.warning(
            "webhook_missing_sender",
            message_sid=msg_sid,
            from_raw=from_raw,
            wa_id_raw=wa_id_raw,
        )
        raise HTTPException(
            status_code=400,
            detail="Missing sender identity (From/WaId)",
        )

    # Rate limit
    await check_rate_limit(phone_number)

    # Enfileiramento:
    # - se há texto OU não há mídia: enfileira o texto como 1 row
    # - cada mídia (MediaUrl0..MediaUrl{NumMedia-1}) vira 1 row adicional
    #   com o mesmo message_sid (sem debounce, processada imediatamente)
    pool = await get_pool()

    if body_raw or num_media == 0:
        await enqueue_or_buffer(
            pool=pool,
            phone_number=phone_number,
            agent_id=agent,
            body=body_raw,
            media_url=None,
            media_type=None,
            to_number=to_number,
            message_id=msg_sid,
            buffer_seconds=settings.message_buffer_seconds,
        )

    for i in range(num_media):
        media_url = (form.get(f"MediaUrl{i}") or "").strip()
        media_type = (form.get(f"MediaContentType{i}") or "").strip()
        if not media_url:
            continue
        await enqueue_or_buffer(
            pool=pool,
            phone_number=phone_number,
            agent_id=agent,
            body="",  # Mídia sem texto adicional
            media_url=media_url,
            media_type=media_type or None,
            to_number=to_number,
            message_id=msg_sid,
            buffer_seconds=settings.message_buffer_seconds,
        )

    logger.info(
        "webhook_twilio_received",
        phone=phone_number,
        agent_id=agent,
        message_sid=msg_sid,
        num_media=num_media,
    )

    return Response(content=EMPTY_TWIML, media_type="application/xml")
