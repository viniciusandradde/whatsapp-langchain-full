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

from whatsapp_langchain.integrations.waba.models import (
    WabaAccountUpdate,
    WabaContato,
    WabaEcho,
    WabaHistoricoConversa,
    WabaHistoricoLote,
    WabaHistoricoMensagem,
    WabaInboundMessage,
)

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
            nomes = {
                str(c.get("wa_id") or "").lstrip("+"): (
                    (c.get("profile") or {}).get("name") or ""
                ).strip()
                for c in value.get("contacts", [])
            }

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
                    profile_name=nomes.get(msg.get("from", "").lstrip("+")) or None,
                    raw=msg,
                )

                if msg_type == "text":
                    inbound.text = msg.get("text", {}).get("body")
                elif msg_type in {"image", "audio", "video", "document", "sticker"}:
                    media = msg.get(msg_type, {})
                    inbound.media_id = media.get("id")
                    inbound.media_mime_type = media.get("mime_type")
                    inbound.media_caption = media.get("caption")
                    inbound.media_filename = (
                        str(media.get("filename") or "").strip() or None
                    )
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


# ---------- Coexistence (WhatsApp Business app + Cloud API, mig 200) ----------
#
# Payloads conferidos na doc da Meta "Onboard WhatsApp Business app users"
# (Graph v25.0, 22/09/2026). Parsers puros: sem banco, sem rede.

#: Histórico recusado pela empresa no app (`history[].errors[].code`).
ERRO_HISTORICO_RECUSADO = 2593109

_TIPOS_MIDIA = ("image", "video", "document", "audio", "sticker")


def _e164(numero: str | None) -> str:
    digitos = str(numero or "").lstrip("+")
    return "+" + digitos if digitos else ""


def _ts(valor: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(valor), tz=UTC)
    except (ValueError, TypeError):
        return datetime.now(UTC)


def _texto_da_mensagem(msg: dict[str, Any]) -> str | None:
    """Texto ou legenda de uma mensagem (echo/histórico); None se não houver."""
    tipo = msg.get("type", "")
    if tipo == "text":
        return (msg.get("text") or {}).get("body")
    if tipo in _TIPOS_MIDIA:
        return (msg.get(tipo) or {}).get("caption")
    return None


def _changes(payload: dict[str, Any], field: str):
    """Itera `(entry, value)` dos changes com o `field` pedido."""
    if payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == field:
                yield entry, change.get("value") or {}


def parse_message_echoes(payload: dict[str, Any]) -> list[WabaEcho]:
    """`smb_message_echoes` → o que a empresa mandou pelo celular."""
    ecos: list[WabaEcho] = []
    for _entry, value in _changes(payload, "smb_message_echoes"):
        phone_id = (value.get("metadata") or {}).get("phone_number_id", "")
        for msg in value.get("message_echoes", []):
            ecos.append(
                WabaEcho(
                    waba_phone_id=phone_id,
                    to_number=_e164(msg.get("to")),
                    message_id=msg.get("id", ""),
                    timestamp=_ts(msg.get("timestamp")),
                    type=msg.get("type", ""),
                    text=_texto_da_mensagem(msg),
                )
            )
    return ecos


def parse_history(payload: dict[str, Any]) -> list[WabaHistoricoLote]:
    """`history` → lotes de conversas dos últimos 180 dias (ou o erro)."""
    lotes: list[WabaHistoricoLote] = []
    for _entry, value in _changes(payload, "history"):
        metadata = value.get("metadata") or {}
        phone_id = metadata.get("phone_number_id", "")
        numero_empresa = str(metadata.get("display_phone_number") or "").lstrip("+")
        for item in value.get("history", []):
            meta_item = item.get("metadata") or {}
            lote = WabaHistoricoLote(
                waba_phone_id=phone_id,
                phase=meta_item.get("phase"),
                chunk_order=meta_item.get("chunk_order"),
                progress=meta_item.get("progress"),
                erros=[
                    int(e.get("code"))
                    for e in item.get("errors", [])
                    if str(e.get("code", "")).isdigit()
                ],
            )
            for thread in item.get("threads", []):
                cliente = _e164(thread.get("id"))
                if not cliente:
                    continue
                conversa = WabaHistoricoConversa(
                    waba_phone_id=phone_id, cliente_number=cliente
                )
                for msg in thread.get("messages", []):
                    remetente = str(msg.get("from") or "").lstrip("+")
                    conversa.mensagens.append(
                        WabaHistoricoMensagem(
                            message_id=msg.get("id", ""),
                            timestamp=_ts(msg.get("timestamp")),
                            type=msg.get("type", ""),
                            text=_texto_da_mensagem(msg),
                            # Sem o número da empresa no metadata, "não é o
                            # cliente" é o que sobra para decidir o lado.
                            da_empresa=(
                                remetente == numero_empresa
                                if numero_empresa
                                else remetente != cliente.lstrip("+")
                            ),
                        )
                    )
                lote.conversas.append(conversa)
            lotes.append(lote)
    return lotes


def parse_state_sync(payload: dict[str, Any]) -> list[WabaContato]:
    """`smb_app_state_sync` → contatos do WhatsApp Business."""
    contatos: list[WabaContato] = []
    for _entry, value in _changes(payload, "smb_app_state_sync"):
        phone_id = (value.get("metadata") or {}).get("phone_number_id", "")
        for item in value.get("state_sync", []):
            if item.get("type") != "contact":
                continue
            contato = item.get("contact") or {}
            numero = _e164(contato.get("phone_number"))
            if not numero:
                continue
            nome = (contato.get("full_name") or contato.get("first_name") or "").strip()
            contatos.append(
                WabaContato(
                    waba_phone_id=phone_id,
                    phone_number=numero,
                    nome=nome or None,
                    action=item.get("action", ""),
                )
            )
    return contatos


def parse_account_updates(payload: dict[str, Any]) -> list[WabaAccountUpdate]:
    """`account_update` → eventos da conta (PARTNER_REMOVED etc.)."""
    eventos: list[WabaAccountUpdate] = []
    for entry, value in _changes(payload, "account_update"):
        info = value.get("disconnection_info") or {}
        eventos.append(
            WabaAccountUpdate(
                waba_account_id=str(entry.get("id", "")),
                event=str(value.get("event", "")),
                phone_number=_e164(value.get("phone_number")) or None,
                reason=info.get("reason"),
                initiated_by=info.get("initiated_by"),
            )
        )
    return eventos
