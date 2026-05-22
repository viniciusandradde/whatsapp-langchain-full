"""Sprint B.4 — webhook ASAAS POST /webhook/asaas.

Auth: header `asaas-access-token` configurado no painel Asaas (mesmo
valor do env ASAAS_WEBHOOK_TOKEN). Asaas envia esse header em todo
POST de webhook como mecanismo simples de autenticação. Sem HMAC do
body — token compartilhado.

Eventos esperados (mais usados):
- PAYMENT_CONFIRMED — pago (cartão / PIX confirmado)
- PAYMENT_RECEIVED — boleto compensado
- PAYMENT_OVERDUE — vencido
- PAYMENT_REFUNDED — estornado
- SUBSCRIPTION_DELETED — assinatura cancelada via Asaas
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from whatsapp_langchain.shared.asaas import process_asaas_webhook
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(tags=["webhook"])


@router.post("/webhook/asaas")
async def webhook_asaas(
    request: Request,
    asaas_access_token: str | None = Header(default=None),
):
    """Recebe webhook do Asaas. Valida token, processa, retorna 200.

    Sempre retorna 200 (até em erros não-fatais) — Asaas retenta com
    backoff se receber não-2xx, e queremos evitar ciclo de retry pra
    bugs de aplicação. Erros vão pro structlog + billing_event_log
    pra retry manual.
    """
    if not settings.asaas_webhook_token:
        logger.error("asaas_webhook_token_missing_in_config")
        raise HTTPException(
            status_code=503,
            detail="ASAAS_WEBHOOK_TOKEN não configurado no servidor.",
        )

    expected = settings.asaas_webhook_token.get_secret_value()
    if asaas_access_token != expected:
        logger.warning(
            "asaas_webhook_invalid_token",
            provided=bool(asaas_access_token),
        )
        raise HTTPException(status_code=401, detail="Invalid asaas-access-token")

    try:
        event = await request.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("asaas_webhook_bad_json", error=str(exc))
        return {"status": "bad_json"}

    pool = await get_pool()
    try:
        result = await process_asaas_webhook(pool, event)
        return {"status": "ok", **result}
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "asaas_webhook_handler_error",
            event_type=event.get("event"),
            error=str(exc),
        )
        # 200 mesmo em erro pra não causar retry loop — log captura tudo
        return {"status": "error", "message": str(exc)[:200]}
