"""Webhook inbound da WhatsApp Cloud API (Meta).

GET /webhook/waba — Handshake (Meta valida verify_token)
POST /webhook/waba — Recebe mensagens + status updates de templates.

Auth: HMAC-SHA256 do body com meta_app_secret (header X-Hub-Signature-256).
Não usa verify_service_token — Meta não envia esse header.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from whatsapp_langchain.integrations.waba.webhook import (
    parse_inbound,
    parse_template_status_updates,
    verify_signature,
)
from whatsapp_langchain.shared.conexao import get_conexao_by_waba_phone_id
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.queue import enqueue_or_buffer

logger = structlog.get_logger()

router = APIRouter(prefix="/webhook/waba", tags=["webhook-waba"])


@router.get("")
async def waba_webhook_verify(
    request: Request,
) -> int | dict[str, str]:
    """Handshake do Meta — retorna `hub.challenge` se verify_token bate.

    Aceita query strings `hub.mode`, `hub.verify_token`, `hub.challenge`.
    """
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    if mode != "subscribe":
        raise HTTPException(status_code=400, detail="hub.mode deve ser 'subscribe'")

    expected = (
        settings.waba_webhook_verify_token.get_secret_value()
        if settings.waba_webhook_verify_token
        else ""
    )
    if not expected or token != expected:
        logger.warning(
            "waba_webhook_verify_failed", token_received_len=len(token or "")
        )
        raise HTTPException(status_code=403, detail="verify_token inválido")

    logger.info("waba_webhook_verified")
    try:
        return int(challenge)
    except (TypeError, ValueError):
        return {"challenge": challenge}


@router.post("")
async def waba_webhook_post(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, str]:
    """Recebe mensagens + atualizações de status de templates.

    Sempre retorna 200 (Meta retenta agressivamente em erros). Validação
    de signature falha → log warning + 200 (não dá pra forçar Meta a desistir).
    """
    body = await request.body()

    app_secret = (
        settings.meta_app_secret.get_secret_value() if settings.meta_app_secret else ""
    )
    # Sprint D hardening: em produção com META_APP_SECRET configurado,
    # signature é OBRIGATÓRIA. Sem header ou inválida → reject. Webhook
    # sem HMAC = forgery trivial (Meta dispara payloads não autenticados
    # rejeitados pelo próprio Meta após N tentativas, mas atacante pode
    # forjar diretamente). Pré-Sprint D só rejeitava quando assinatura
    # inválida; ausência de header passava silenciosamente.
    if app_secret:
        if not x_hub_signature_256:
            logger.warning(
                "waba_webhook_signature_missing",
                body_size=len(body),
                production=settings.is_production,
            )
            if settings.is_production:
                return {"status": "rejected_no_signature"}
        elif not verify_signature(body, x_hub_signature_256, app_secret):
            logger.warning("waba_webhook_signature_invalid", body_size=len(body))
            return {"status": "rejected"}

    try:
        payload = await request.json()
    except Exception as exc:
        logger.warning("waba_webhook_bad_json", error=str(exc))
        return {"status": "bad_json"}

    pool = await get_pool()

    # Mensagens inbound
    from whatsapp_langchain.shared.rls_context import set_request_context

    inbound_messages = parse_inbound(payload)
    for msg in inbound_messages:
        conexao = await get_conexao_by_waba_phone_id(pool, msg.waba_phone_id)
        if conexao is None:
            logger.warning(
                "waba_webhook_no_conexao",
                phone_id=msg.waba_phone_id,
                from_number=msg.from_number,
            )
            continue

        # Sprint A.2 — seta RLS context da empresa após resolver conexão.
        set_request_context(conexao.empresa_id)

        try:
            await enqueue_or_buffer(
                pool,
                phone_number=msg.from_number,
                agent_id=conexao.default_agent_id,
                body=msg.text or f"[{msg.type}]",
                empresa_id=conexao.empresa_id,
                to_number=conexao.from_number,
                message_id=msg.message_id,
                conexao_id=conexao.id,
                media_url=None,  # WABA mídia via /media/{id} — sprint futura
                media_type=msg.media_mime_type,
            )
        except Exception as exc:
            logger.exception("waba_webhook_enqueue_failed", error=str(exc))

    # Updates de template status
    template_updates = parse_template_status_updates(payload)
    for upd in template_updates:
        event = upd.get("event", "").upper()
        # Mapeia evento Meta → status local
        status_map = {
            "APPROVED": "approved",
            "REJECTED": "rejected",
            "PAUSED": "paused",
            "DISABLED": "disabled",
            "PENDING": "pending",
            "FLAGGED": "approved",  # Flagged = aprovado mas quality baixa
        }
        new_status = status_map.get(event)
        if not new_status:
            continue

        async with pool.connection() as conn:
            await conn.execute(
                """
                UPDATE waba_template
                   SET status = %s,
                       motivo_rejeicao = COALESCE(%s, motivo_rejeicao),
                       ultimo_sync_at = NOW(),
                       updated_at = NOW()
                 WHERE meta_template_id = %s
                """,
                (new_status, upd.get("reason"), upd.get("meta_template_id")),
            )
        logger.info(
            "waba_template_status_updated",
            template_id=upd.get("meta_template_id"),
            event=event,
            new_status=new_status,
        )

    return {"status": "received", "inbound_count": str(len(inbound_messages))}
