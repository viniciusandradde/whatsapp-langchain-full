"""Webhook inbound da WhatsApp Cloud API (Meta).

GET /webhook/waba — Handshake (Meta valida verify_token)
POST /webhook/waba — Recebe mensagens + status updates de templates.

Auth: HMAC-SHA256 do body com meta_app_secret (header X-Hub-Signature-256).
Não usa verify_service_token — Meta não envia esse header.
"""

from __future__ import annotations

import base64
import hmac

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from whatsapp_langchain.integrations.waba.client import download_media
from whatsapp_langchain.integrations.waba.webhook import (
    parse_inbound,
    parse_template_status_updates,
    verify_signature,
)
from whatsapp_langchain.shared.conexao import (
    get_conexao_by_waba_phone_id,
    get_credentials_decrypted,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.queue import detectar_fluxo_guiado, enqueue_or_buffer

logger = structlog.get_logger()

router = APIRouter(prefix="/webhook/waba", tags=["webhook-waba"])


async def _resolve_waba_media_url(pool, conexao, msg) -> str | None:
    """Baixa a mídia inbound do WABA e devolve como data-URL base64.

    Best-effort: sem media_id, sem creds, ou falha de download → None (a msg
    segue como texto/caption). Espelha o que o webhook Evolution faz.
    """
    media_id = getattr(msg, "media_id", None)
    if not media_id:
        return None
    try:
        creds = await get_credentials_decrypted(pool, conexao.id) or {}
        access_token = creds.get("access_token")
        if not access_token:
            return None
        content, mime = await download_media(access_token, media_id)
        b64 = base64.b64encode(content).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as exc:  # noqa: BLE001 — mídia é best-effort
        logger.warning(
            "waba_media_download_failed",
            media_id=media_id,
            error=str(exc),
        )
        return None


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
    if not expected or not hmac.compare_digest(token or "", expected):
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

    Retorna 200 no happy path. Assinatura inválida/ausente → 200 com status
    `rejected` (não dá pra forçar Meta a desistir de payload forjado). Mas
    FALHA de enfileiramento → 5xx, pra Meta retentar e não perder a mensagem do
    cliente (idempotência por message_id evita duplicar na redelivery).
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
            # Assinatura ausente com app_secret configurado = SEMPRE rejeita
            # (independente de is_production). Antes só rejeitava em prod, o que
            # deixava staging / env com ENVIRONMENT != 'production' aceitar
            # webhook WABA forjado sem HMAC (injeção de mensagem/empresa).
            return {"status": "rejected_no_signature"}
        elif not verify_signature(body, x_hub_signature_256, app_secret):
            logger.warning("waba_webhook_signature_invalid", body_size=len(body))
            return {"status": "rejected"}

    try:
        payload = await request.json()
    except Exception as exc:
        logger.warning("waba_webhook_bad_json", error=str(exc))
        return {"status": "bad_json"}

    # Mensagens inbound
    from whatsapp_langchain.shared.rls_context import set_request_context

    inbound_messages = parse_inbound(payload)
    template_updates = parse_template_status_updates(payload)

    # Sem nada a processar, não toca o banco. A Meta entrega vários eventos que
    # não são mensagem nem status de template, e abrir conexão só para
    # descartá-los é trabalho à toa.
    #
    # Também era o que travava a suíte: o pool é singleton e nascia preso ao
    # event loop efêmero de um `TestClient` sem lifespan, onde cada request cria
    # e destrói o próprio portal do anyio — que então esperava para sempre por
    # tasks que ninguém ia fechar. Ver docs/MIGRACAO_DEV.md.
    if not inbound_messages and not template_updates:
        logger.info("waba_webhook_sem_conteudo")
        return {"status": "received", "inbound_count": "0"}

    pool = await get_pool()
    enqueue_failed = False
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

        # Mídia inbound: baixa via Graph /{media_id} e embute como data-URL
        # base64 (igual Evolution) — o worker já sabe processar data URLs
        # (visão/transcrição). Best-effort: falha vira texto/caption.
        media_url = await _resolve_waba_media_url(pool, conexao, msg)

        # Agrupamento adaptativo (mig 144). Sem `atendimento` em mãos aqui, a
        # detecção cai no sinal de `origem_resposta` — que já cobre coleta e
        # CSAT, porque os handlers deles carimbam a row ao responder.
        grouping_seconds = float(conexao.resposta_agrupamento_segundos)
        is_guided_flow = grouping_seconds > 0 and await detectar_fluxo_guiado(
            pool,
            phone_number=msg.from_number,
            agent_id=conexao.default_agent_id,
        )

        try:
            await enqueue_or_buffer(
                pool,
                phone_number=msg.from_number,
                agent_id=conexao.default_agent_id,
                body=msg.text or msg.media_caption or f"[{msg.type}]",
                empresa_id=conexao.empresa_id,
                to_number=conexao.from_number,
                message_id=msg.message_id,
                conexao_id=conexao.id,
                media_url=media_url,
                media_type=msg.media_mime_type,
                media_filename=msg.media_filename,
                grouping_seconds=grouping_seconds,
                grouping_max_seconds=settings.message_grouping_max_seconds,
                is_guided_flow=is_guided_flow,
            )
        except Exception as exc:
            # NÃO engolir: marca falha e ao final retorna 5xx pra Meta retentar
            # (antes retornava 200 e a mensagem do cliente era perdida pra
            # sempre numa falha transitória de DB). O enqueue é idempotente por
            # message_id (ON CONFLICT DO NOTHING), então a redelivery é segura.
            logger.exception("waba_webhook_enqueue_failed", error=str(exc))
            enqueue_failed = True

    # Updates de template status (já lidos acima, junto do inbound)
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

    if enqueue_failed:
        # 5xx → Meta redelivera o webhook inteiro; idempotência por message_id
        # garante que os inbound já enfileirados não dupliquem.
        raise HTTPException(status_code=503, detail="enqueue failed; retry")

    return {"status": "received", "inbound_count": str(len(inbound_messages))}
