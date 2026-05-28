"""Twilio Content API — templates HSM (criação, aprovação, sync, importação).

Twilio é BSP (Business Solution Provider): templates não vão direto pra Meta
Graph API, e sim via Content API (content.twilio.com). Fluxo em 2 passos:

  1. POST /v1/Content → cria o Content, retorna ContentSid (HX...)
  2. POST /v1/Content/{sid}/ApprovalRequests/whatsapp → submete review Meta

Auth: Basic com account_sid:auth_token (mesmas creds do webhook signature).
Espelha o contrato de `integrations/waba/templates.py` pra que as rotas
unificadas (routes/waba_templates.py) roteiem por provider sem ramificar muito.

Status remoto (ApprovalRequests) → local:
  received/pending → pending · approved → approved · rejected → rejected
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

CONTENT_API_BASE = "https://content.twilio.com/v1"


class TwilioContentError(Exception):
    """Erro ao operar template via Twilio Content API."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Twilio Content API error {status_code}: {detail}")


def build_text_types(body: str) -> dict[str, Any]:
    """Monta o `types` mínimo (twilio/text) a partir do corpo do template.

    Variáveis usam `{{1}}`, `{{2}}` etc. — mesma convenção do WhatsApp/Meta.
    Pra cards/quick-reply/mídia, montar o dict manualmente no chamador.
    """
    return {"twilio/text": {"body": body}}


async def create_content(
    account_sid: str,
    auth_token: str,
    *,
    friendly_name: str,
    language: str,
    types: dict[str, Any],
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """POST /v1/Content → cria o Content template. Retorna dict com `sid` (HX...).

    `friendly_name` deve ser único na conta. `types` define o conteúdo
    (twilio/text, twilio/quick-reply, whatsapp/card, etc).
    """
    payload: dict[str, Any] = {
        "friendly_name": friendly_name,
        "language": language,
        "types": types,
    }
    if variables:
        payload["variables"] = variables

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{CONTENT_API_BASE}/Content",
            auth=(account_sid, auth_token),
            json=payload,
        )
    if resp.status_code not in (200, 201):
        raise TwilioContentError(resp.status_code, resp.text[:400])
    return resp.json()


async def submit_whatsapp_approval(
    account_sid: str,
    auth_token: str,
    content_sid: str,
    *,
    name: str,
    category: str,
) -> dict[str, Any]:
    """POST /v1/Content/{sid}/ApprovalRequests/whatsapp → submete pra review Meta.

    `name`: nome único do template (lowercase alfanumérico + underscore).
    `category`: UTILITY | MARKETING | AUTHENTICATION.
    """
    url = f"{CONTENT_API_BASE}/Content/{content_sid}/ApprovalRequests/whatsapp"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            url,
            auth=(account_sid, auth_token),
            json={"name": name, "category": category},
        )
    if resp.status_code not in (200, 201):
        raise TwilioContentError(resp.status_code, resp.text[:400])
    return resp.json()


async def fetch_approval_status(
    account_sid: str,
    auth_token: str,
    content_sid: str,
) -> dict[str, Any]:
    """GET /v1/Content/{sid}/ApprovalRequests → status atual + rejection_reason.

    Retorno típico:
      {"whatsapp": {"status": "approved", "category": "UTILITY",
                    "rejection_reason": "", "name": "..."}}
    O caller normaliza o status remoto pro enum local.
    """
    url = f"{CONTENT_API_BASE}/Content/{content_sid}/ApprovalRequests"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, auth=(account_sid, auth_token))
    if resp.status_code != 200:
        raise TwilioContentError(resp.status_code, resp.text[:400])
    return resp.json()


async def list_remote_contents(
    account_sid: str,
    auth_token: str,
    *,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """GET /v1/Content?PageSize=N → lista os Content templates da conta.

    Usado pela importação: traz templates já criados no Twilio pro DB local.
    Pagina via `meta.next_page_url` enquanto houver — limita em ~500 itens
    pra não rodar infinito em contas grandes.
    """
    contents: list[dict[str, Any]] = []
    url: str | None = f"{CONTENT_API_BASE}/Content?PageSize={page_size}"
    async with httpx.AsyncClient(timeout=20) as client:
        while url and len(contents) < 500:
            resp = await client.get(url, auth=(account_sid, auth_token))
            if resp.status_code != 200:
                raise TwilioContentError(resp.status_code, resp.text[:400])
            data = resp.json()
            contents.extend(data.get("contents", []))
            next_url = (data.get("meta") or {}).get("next_page_url")
            url = next_url or None
    return contents


def normalize_approval_status(remote: dict[str, Any]) -> tuple[str, str | None]:
    """Extrai (status_local, rejection_reason) do payload de ApprovalRequests.

    Mapeia o status remoto do Twilio/Meta pro enum local da waba_template:
      received/pending/in_review → pending
      approved                   → approved
      rejected                   → rejected
      (qualquer outro)           → pending (conservador)
    """
    wa = remote.get("whatsapp") or remote
    remote_status = str(wa.get("status") or "").lower()
    rejection = wa.get("rejection_reason") or None
    mapping = {
        "received": "pending",
        "pending": "pending",
        "in_review": "pending",
        "approved": "approved",
        "rejected": "rejected",
    }
    return mapping.get(remote_status, "pending"), rejection
