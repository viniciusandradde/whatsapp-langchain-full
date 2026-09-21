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

import asyncio
import re
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


def describe_key_source() -> str:
    """Qual env var fornece a key do header `apikey` (sem expor o segredo).

    Usado em logs/mensagens de erro pra apontar ONDE corrigir um 401, sem
    nunca devolver o valor da chave.
    """
    if settings.evolution_global_api_key:
        return "EVOLUTION_GLOBAL_API_KEY"
    if settings.evolution_api_key:
        return "EVOLUTION_API_KEY (fallback)"
    return "(nenhuma key configurada)"


def classify_admin_error(exc: EvolutionAdminError) -> str | None:
    """Traduz um erro de auth do Evolution numa mensagem acionável.

    Retorna None quando o erro NÃO é de autenticação (caller usa o genérico).
    401 = key errada; 403 "Missing global api key" = key vazia. Em ambos a
    causa é o header `apikey` enviado ≠ AUTHENTICATION_API_KEY do servidor.
    """
    if exc.status_code == 401 or (
        exc.status_code == 403
        and any(
            t in (exc.detail or "").lower()
            for t in ("api key", "apikey", "unauthorized")
        )
    ):
        return (
            f"API key do Evolution rejeitada ({exc.status_code}) — confira "
            f"{describe_key_source()} (Nexus) vs AUTHENTICATION_API_KEY do "
            f"servidor {_base()}. O header `apikey` enviado não corresponde à "
            f"chave do servidor."
        )
    return None


def _normalize_phone(number: str) -> str:
    """Só dígitos (tira `+`, espaços, traços) — formato do Baileys
    `requestPairingCode`: DDI+DDD+número, ex. 5511999999999."""
    return re.sub(r"\D", "", number or "")


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
        # byEvents=False: Evolution posta TODOS os eventos na rota BASE
        # (/webhook/evolution), que é onde nosso handler escuta e lê o `event`
        # do body. byEvents=True postaria em subpaths (/webhook/evolution/
        # messages-upsert) que NÃO existem → 404 → inbound nunca chega.
        webhook_cfg: dict[str, Any] = {
            "url": webhook_url,
            "byEvents": False,
            "base64": True,
            "events": [
                "MESSAGES_UPSERT",
                "MESSAGES_UPDATE",
                "CONNECTION_UPDATE",
                "QRCODE_UPDATED",
            ],
        }
        # Fix #448 (prod 2026-05-22) + recorrência 2026-05-31 — Evolution Server
        # NÃO injeta apikey nos webhooks por default. Sem headers.apikey aqui,
        # quando EVOLUTION_VALIDATE_APIKEY=true nosso /webhook/evolution rejeita
        # com 401 e mensagens nunca entram na fila.
        #
        # CRÍTICO: o header tem que carregar a MESMA chave que o handler valida
        # em webhook_evolution.py — `settings.evolution_api_key` (per-instance),
        # NÃO a global key. São direções distintas:
        #   - _headers() autentica nós→Evolution (admin)   → global key
        #   - este header autentica Evolution→nós (inbound) → evolution_api_key
        # Em prod as duas chaves diferem; usar a global aqui gerava mismatch
        # silencioso mesmo com o header presente.
        apikey = (
            settings.evolution_api_key.get_secret_value()
            if settings.evolution_api_key
            else ""
        )
        if apikey:
            webhook_cfg["headers"] = {
                "apikey": apikey,
                "Content-Type": "application/json",
            }
        payload["webhook"] = webhook_cfg

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        if resp.status_code not in (200, 201):
            raise EvolutionAdminError(resp.status_code, resp.text[:400])
        return resp.json()


async def connect_instance(
    instance_name: str, phone_number: str | None = None
) -> dict[str, Any]:
    """GET /instance/connect/{name} → QR base64 (escanear) OU pairing code.

    Sem `phone_number`: retorna QR — `{"base64","code","count","pairingCode":null}`.
    Com `phone_number`: passa `?number=<dígitos>` e retorna o código de
    pareamento — `{"pairingCode":"WZYEH1YY","code","count"}` (sem `base64`).

    Gotcha do Evolution: num socket recém-criado o `pairingCode` às vezes volta
    null/`count:0`; re-tentamos 1× após um pequeno delay quando há número.
    """
    url = f"{_base()}/instance/connect/{instance_name}"
    params = {"number": _normalize_phone(phone_number)} if phone_number else None

    async def _call() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=_headers(), params=params)
            if resp.status_code != 200:
                raise EvolutionAdminError(resp.status_code, resp.text[:400])
            return resp.json()

    data = await _call()
    if phone_number and not (data or {}).get("pairingCode"):
        # socket pode não estar pronto — espera e tenta de novo (1×).
        await asyncio.sleep(2.0)
        data = await _call()
    return data


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


EVOLUTION_SONDA_TIMEOUT = 8.0


async def fetch_profile_picture(
    instance_name: str, number: str, *, timeout: float = EVOLUTION_SONDA_TIMEOUT
) -> dict[str, Any]:
    """POST /chat/fetchProfilePictureUrl/{name} — consulta REAL ao WhatsApp.

    Sonda de saúde (mig 196): diferente de `/chat/whatsappNumbers` (cache
    `IsOnWhatsapp` — respondeu 200 em 60 ms pela instância morta do incidente
    de 16/09), a foto de perfil é uma consulta IQ pelo socket; num socket
    zumbi ela pendura, e o timeout curto É o sinal. O conteúdo não importa
    (número sem foto volta 200 com `profilePictureUrl` null) — importa ter
    respondido no prazo. Levanta `httpx.TimeoutException` no estouro e
    `EvolutionAdminError` em resposta não-2xx.
    """
    url = f"{_base()}/chat/fetchProfilePictureUrl/{instance_name}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url, headers=_headers(), json={"number": _normalize_phone(number)}
        )
        if resp.status_code not in (200, 201):
            raise EvolutionAdminError(resp.status_code, resp.text[:400])
        return resp.json() if resp.content else {}


async def get_instance_owner_number(instance_name: str) -> str | None:
    """Número (E.164) do dono da instância, via `ownerJid` do fetchInstances.

    Retorna `+<dígitos>` (o JID do WhatsApp, ex. 556784249725@s.whatsapp.net →
    +556784249725) ou None se a instância não tem dono vinculado ainda / não
    achada. Best-effort — usado pra preencher o `from_number` real após o QR.
    """
    url = f"{_base()}/instance/fetchInstances"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            url, headers=_headers(), params={"instanceName": instance_name}
        )
        if resp.status_code != 200:
            raise EvolutionAdminError(resp.status_code, resp.text[:400])
        data = resp.json()
    items = data if isinstance(data, list) else [data]
    for it in items:
        if not isinstance(it, dict):
            continue
        # v2: campos no topo; tolera shapes antigos com .instance aninhada
        inner = it.get("instance")
        inst = inner if isinstance(inner, dict) else it
        name = inst.get("name") or inst.get("instanceName")
        if name != instance_name:
            continue
        jid = inst.get("ownerJid") or inst.get("owner") or ""
        digits = _normalize_phone(str(jid).split("@", 1)[0])
        return f"+{digits}" if digits else None
    return None


async def get_owner_numbers() -> dict[str, str]:
    """Mapa {instance_name: +número} de TODAS as instâncias com dono vinculado,
    em UMA chamada (pra backfill em lote do from_number na listagem)."""
    url = f"{_base()}/instance/fetchInstances"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_headers())
        if resp.status_code != 200:
            raise EvolutionAdminError(resp.status_code, resp.text[:400])
        data = resp.json()
    items = data if isinstance(data, list) else [data]
    out: dict[str, str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        inner = it.get("instance")
        inst = inner if isinstance(inner, dict) else it
        name = inst.get("name") or inst.get("instanceName")
        digits = _normalize_phone(str(inst.get("ownerJid") or "").split("@", 1)[0])
        if name and digits:
            out[str(name)] = f"+{digits}"
    return out


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


async def refresh_pairing_code(instance_name: str, phone_number: str) -> dict[str, Any]:
    """Re-chama /instance/connect?number= — gera um novo código de pareamento."""
    return await connect_instance(instance_name, phone_number=phone_number)


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
