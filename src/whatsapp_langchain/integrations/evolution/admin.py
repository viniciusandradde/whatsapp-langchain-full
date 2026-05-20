"""Operações admin no Evolution API server (provision, connect, disconnect, QR).

Diferente do `EvolutionClient` (que envia mensagens via api_key per-instance),
este módulo usa a `EVOLUTION_GLOBAL_API_KEY` pra gerenciar o LIFECYCLE de
instances no servidor Evolution.

Fluxo de criação de uma nova conexão Evolution no painel:
1. UI: user clica "+ Nova" → escolhe Evolution → `display_name`
2. Backend chama `provision_instance(instance_name, webhook_url)` → cria
3. Backend chama `connect_instance(instance_name)` → retorna QR base64
4. Front renderiza QR + polling `get_connection_state` cada 3s
5. User escaneia → state vira `open` → conexão ativa
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()


class EvolutionAdminError(Exception):
    """Erro em operação admin do Evolution server."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Evolution admin error {status_code}: {detail}")


def _headers() -> dict[str, str]:
    if not settings.evolution_admin_enabled:
        raise EvolutionAdminError(
            503,
            "EVOLUTION_API_URL/EVOLUTION_API_KEY (ou _ADMIN_URL/_GLOBAL_API_KEY) "
            "não configurados.",
        )
    key = settings.resolved_evolution_global_api_key
    return {
        "apikey": key.get_secret_value() if key else "",
        "Content-Type": "application/json",
    }


def _base() -> str:
    return settings.resolved_evolution_admin_url.rstrip("/")


async def provision_instance(
    instance_name: str,
    *,
    webhook_url: str | None = None,
    integration: str = "WHATSAPP-BAILEYS",
) -> dict[str, Any]:
    """POST /instance/create → cria nova instance no Evolution server.

    `webhook_url`: URL pra Evolution chamar nas mensagens inbound. Geralmente
    `{public_base_url}/webhook/evolution`.

    Returns dict da instance criada (inclui `instance.token` per-instance key).
    """
    url = f"{_base()}/instance/create"
    payload: dict[str, Any] = {
        "instanceName": instance_name,
        "qrcode": False,  # vamos chamar /connect separado pra ter mais controle
        "integration": integration,
    }
    if webhook_url:
        payload["webhook"] = {
            "url": webhook_url,
            "byEvents": True,
            "base64": True,
            "events": [
                "MESSAGES_UPSERT",
                "MESSAGES_UPDATE",
                "CONNECTION_UPDATE",
                "QRCODE_UPDATED",
            ],
        }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        if resp.status_code not in (200, 201):
            raise EvolutionAdminError(resp.status_code, resp.text[:400])
        return resp.json()


async def connect_instance(instance_name: str) -> dict[str, Any]:
    """POST /instance/connect/{name} → retorna QR base64 pra escanear.

    Returns: {"base64": "data:image/png;base64,...", "code": "<uri>", "count": int}
    """
    url = f"{_base()}/instance/connect/{instance_name}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers())
        if resp.status_code != 200:
            raise EvolutionAdminError(resp.status_code, resp.text[:400])
        return resp.json()


async def get_connection_state(instance_name: str) -> dict[str, Any]:
    """GET /instance/connectionState/{name} → estado atual.

    Returns: {"instance": {"instanceName": str, "state": str}}
    state: open | connecting | close
    """
    url = f"{_base()}/instance/connectionState/{instance_name}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=_headers())
        if resp.status_code != 200:
            raise EvolutionAdminError(resp.status_code, resp.text[:400])
        return resp.json()


async def disconnect_instance(instance_name: str) -> bool:
    """DELETE /instance/logout/{name} → desconecta sessão (mantém instance)."""
    url = f"{_base()}/instance/logout/{instance_name}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.delete(url, headers=_headers())
        return resp.status_code in (200, 204)


async def delete_instance(instance_name: str) -> bool:
    """DELETE /instance/delete/{name} → remove instance do server (irreversível)."""
    url = f"{_base()}/instance/delete/{instance_name}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.delete(url, headers=_headers())
        return resp.status_code in (200, 204)


async def refresh_qr(instance_name: str) -> dict[str, Any]:
    """Re-chama /instance/connect — Evolution regera QR se o anterior expirou."""
    return await connect_instance(instance_name)


def normalize_state(raw_state: dict[str, Any]) -> str:
    """Extrai string canônica do shape Evolution. Mapeia pro nosso CHECK.

    Evolution: open | connecting | close
    Nosso: open | connecting | disconnected | qr_pending | ready | error
    """
    inner = raw_state.get("instance", {}) if isinstance(raw_state, dict) else {}
    state = inner.get("state") if isinstance(inner, dict) else None
    if state is None and isinstance(raw_state, dict):
        state = raw_state.get("state")
    if state == "open":
        return "open"
    if state == "connecting":
        return "connecting"
    if state == "close":
        return "disconnected"
    return "error"
