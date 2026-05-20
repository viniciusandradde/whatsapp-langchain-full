"""Cliente outbound WhatsApp Cloud API (Meta WABA).

Implementa o `OutboundClient` Protocol — mesma interface que `TwilioClient`
e `EvolutionClient`. O worker resolve qual cliente usar via `Conexao.provider`.

Diferente do Twilio (API Key) e do Evolution (apikey header), WABA usa
Bearer token (system user token) específico de cada conexão. Cada `WabaClient`
é instanciado por conexão (com credenciais decifradas) — não há singleton
global.
"""

from __future__ import annotations

import re

import httpx
import structlog

from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()


WABA_BASE_URL = "https://graph.facebook.com/{version}"
WABA_MESSAGE_BODY_LIMIT = 4096  # Meta limita body de texto a 4096 chars


class WabaSendError(Exception):
    """Erro ao enviar mensagem via WABA Cloud."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"WABA API error {status_code}: {detail}")


def _normalize_to(to: str) -> str:
    """Meta espera só dígitos no campo `to`."""
    cleaned = to.strip().lstrip("+")
    if cleaned.startswith("whatsapp:"):
        cleaned = cleaned[len("whatsapp:") :].lstrip("+")
    return "".join(c for c in cleaned if c.isdigit())


def _split_long_body(body: str, limit: int = WABA_MESSAGE_BODY_LIMIT) -> list[str]:
    """Quebra body em chunks <= limit char (Meta corta sem aviso)."""
    if len(body) <= limit:
        return [body]

    chunks: list[str] = []
    remaining = body
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        # Tenta quebrar em boundary de palavra
        cut = remaining.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    return chunks


class WabaClient:
    """Cliente assíncrono WhatsApp Cloud API (Meta).

    Args:
        access_token: System User token (long-lived), decifrado de
            `conexao.credentials_encrypted`.
        phone_id: phone_number_id da Meta.
        delivery_mode: `real` ou `mock`.
    """

    def __init__(
        self,
        access_token: str,
        phone_id: str,
        *,
        delivery_mode: str = "real",
    ):
        if delivery_mode not in {"real", "mock"}:
            raise ValueError(f"delivery_mode inválido: {delivery_mode}")
        if delivery_mode == "real":
            if not access_token:
                raise ValueError("access_token não pode ser vazio")
            if not phone_id:
                raise ValueError("phone_id não pode ser vazio")

        self.access_token = access_token
        self.phone_id = phone_id
        self.delivery_mode = delivery_mode
        self.base_url = WABA_BASE_URL.format(version=settings.waba_graph_api_version)

    async def send_message(self, to: str, body: str) -> str:
        """Envia mensagem de texto. Retorna message_id (wamid.xxx)."""
        to_clean = _normalize_to(to)

        if self.delivery_mode == "mock":
            import uuid

            mock_id = f"wamid.MOCK_{uuid.uuid4().hex[:12]}"
            logger.info(
                "waba_outbound_mock",
                to=to_clean,
                body=body[:80],
                message_id=mock_id,
            )
            return mock_id

        chunks = _split_long_body(body)
        last_id = ""
        url = f"{self.base_url}/{self.phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=20) as client:
            for chunk in chunks:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": to_clean,
                    "type": "text",
                    "text": {"body": chunk},
                }
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    raise WabaSendError(resp.status_code, resp.text[:400])
                data = resp.json()
                messages = data.get("messages", [])
                if messages:
                    last_id = messages[0].get("id", "")

        return last_id

    async def send_typing(self, to: str, message_id: str | None = None) -> bool:
        """Marca mensagem como lida + indicator de digitação.

        WABA Cloud (jul/2024+) suporta typing indicator via PATCH na mensagem
        inbound: marca status=read + retorna ack ao cliente. Best-effort —
        falha silenciosa.
        """
        if self.delivery_mode == "mock" or not message_id:
            return False

        url = f"{self.base_url}/{self.phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {"type": "text"},
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, headers=headers, json=payload)
                return resp.status_code == 200
        except Exception:
            return False


WAMID_RE = re.compile(r"^wamid\.[A-Za-z0-9_\-=]+$")


def is_valid_wamid(s: str) -> bool:
    """Valida formato wamid retornado pela Meta."""
    return bool(WAMID_RE.match(s))
