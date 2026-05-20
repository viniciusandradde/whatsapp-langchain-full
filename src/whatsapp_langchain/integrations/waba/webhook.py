"""Validação + parsing de webhook inbound da WABA Cloud (Meta).

Meta envia POST pra nosso endpoint com header `X-Hub-Signature-256: sha256=<hex>`.
HMAC é calculado com `meta_app_secret` sobre o body raw.

Payload shape (simplificado):
{
    "object": "whatsapp_business_account",
    "entry": [{
        "id": "<waba_account_id>",
        "changes": [{
            "field": "messages",
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {"phone_number_id": "...", "display_phone_number": "..."},
                "contacts": [{"wa_id": "<from_number>", "profile": {"name": "..."}}],
                "messages": [{
                    "id": "wamid.xxx",
                    "from": "<from_number>",
                    "timestamp": "1234567890",
                    "type": "text",
                    "text": {"body": "..."}
                }]
            }
        }]
    }]
}
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

import structlog

from whatsapp_langchain.integrations.waba.models import WabaInboundMessage

logger = structlog.get_logger()


def verify_signature(body: bytes, header_sig: str, app_secret: str) -> bool:
    """Verifica HMAC-SHA256 do body com app_secret.

    Args:
        body: raw bytes do request body (NÃO o parsed json — Meta calcula
            sobre os bytes exatos enviados).
        header_sig: valor do header `X-Hub-Signature-256` no formato `sha256=<hex>`.
        app_secret: settings.meta_app_secret.

    Returns:
        True se assinatura bate. False qualquer outro caso (formato errado,
        secret vazio, mismatch).
    """
    if not header_sig or not app_secret:
        return False

    if not header_sig.startswith("sha256="):
        return False

    expected = hmac.new(
        app_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    received = header_sig[len("sha256=") :]
    # constant-time compare
    return hmac.compare_digest(expected, received)


def parse_inbound(payload: dict[str, Any]) -> list[WabaInboundMessage]:
    """Extrai mensagens de um webhook payload (pode ter N).

    Ignora updates de status (sent/delivered/read) — só pega messages reais.
    Eventos de template_status são tratados separadamente.
    """
    messages: list[WabaInboundMessage] = []

    if payload.get("object") != "whatsapp_business_account":
        return messages

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue

            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_id = metadata.get("phone_number_id", "")

            for msg in value.get("messages", []):
                msg_type = msg.get("type", "")
                try:
                    timestamp = datetime.fromtimestamp(
                        int(msg.get("timestamp", "0")), tz=UTC
                    )
                except (ValueError, TypeError):
                    timestamp = datetime.now(UTC)

                inbound = WabaInboundMessage(
                    waba_phone_id=phone_id,
                    from_number="+" + msg.get("from", "").lstrip("+"),
                    message_id=msg.get("id", ""),
                    timestamp=timestamp,
                    type=msg_type,
                    raw=msg,
                )

                if msg_type == "text":
                    inbound.text = msg.get("text", {}).get("body")
                elif msg_type in {"image", "audio", "video", "document", "sticker"}:
                    media = msg.get(msg_type, {})
                    inbound.media_id = media.get("id")
                    inbound.media_mime_type = media.get("mime_type")
                    inbound.media_caption = media.get("caption")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    # Botão clicado vira texto da label pro pipeline
                    if interactive.get("type") == "button_reply":
                        inbound.text = interactive.get("button_reply", {}).get("title")
                    elif interactive.get("type") == "list_reply":
                        inbound.text = interactive.get("list_reply", {}).get("title")
                elif msg_type == "button":
                    inbound.text = msg.get("button", {}).get("text")
                elif msg_type == "location":
                    loc = msg.get("location", {})
                    inbound.text = (
                        f"📍 Localização: {loc.get('latitude')}, {loc.get('longitude')}"
                    )

                messages.append(inbound)

    return messages


def parse_template_status_updates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrai eventos `message_template_status_update`.

    Retorna list de dicts: {meta_template_id, status, reason?, waba_account_id}
    Caller usa pra atualizar `waba_template.status` e `motivo_rejeicao`.
    """
    updates: list[dict[str, Any]] = []

    if payload.get("object") != "whatsapp_business_account":
        return updates

    for entry in payload.get("entry", []):
        waba_account_id = entry.get("id", "")
        for change in entry.get("changes", []):
            if change.get("field") != "message_template_status_update":
                continue

            value = change.get("value", {})
            updates.append(
                {
                    "waba_account_id": waba_account_id,
                    "meta_template_id": str(value.get("message_template_id", "")),
                    "template_name": value.get("message_template_name", ""),
                    "language": value.get("message_template_language", "pt_BR"),
                    "event": value.get("event", ""),  # APPROVED|REJECTED|PAUSED|etc
                    "reason": value.get("reason"),
                }
            )

    return updates
