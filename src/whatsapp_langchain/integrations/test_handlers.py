"""Handlers de teste de conexão (`POST /api/integracoes/{id}/testar`).

Cada provider tem lógica própria pra validar que credenciais funcionam
sem efeitos colaterais. Padrão: faz 1 chamada read-only que valida auth.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
import structlog

from whatsapp_langchain.integrations.api_connection import (
    get_conexao_safe,
    get_credenciais_decrypted,
)

logger = structlog.get_logger()

_TIMEOUT = 10.0


async def test_asaas(creds: dict, conexao: dict) -> tuple[bool, str]:
    """GET /myAccount com header access_token. 401 = key inválida."""
    base_url = conexao.get("base_url") or "https://api.asaas.com/v3"
    if creds.get("ambiente") == "sandbox":
        base_url = "https://api-sandbox.asaas.com/v3"
    headers = {"access_token": creds["access_token"]}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{base_url}/myAccountStatement", headers=headers)
    except httpx.HTTPError as exc:
        return False, f"Erro de rede: {exc!s:.150}"
    if resp.status_code == 401:
        return False, "Access token Asaas inválido (401)."
    if resp.status_code >= 500:
        return False, f"Asaas retornou {resp.status_code} (provider down?)"
    if resp.status_code >= 400:
        return (
            False,
            f"Asaas rejeitou: HTTP {resp.status_code} — {resp.text[:200]}",
        )
    return True, "Asaas conectado com sucesso."


async def test_custom(creds: dict, conexao: dict) -> tuple[bool, str]:
    """Custom — faz GET na base_url + auth correto. 2xx = OK."""
    base_url = creds.get("base_url") or conexao.get("base_url")
    if not base_url:
        return False, "Base URL não configurada."

    method = (creds.get("auth_method") or "none").lower()
    headers: dict[str, str] = {}
    auth: tuple[str, str] | None = None
    if method == "bearer":
        token = creds.get("token") or ""
        if not token:
            return False, "Token Bearer vazio."
        headers["Authorization"] = f"Bearer {token}"
    elif method == "basic":
        username = creds.get("username") or ""
        password = creds.get("token") or ""
        if not username or not password:
            return False, "Basic auth exige username + senha."
        auth = (username, password)
        # Pra dar sanity também via header (alguns servers exigem)
        cred = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {cred}"
    elif method == "api_key_header":
        header_name = creds.get("header_name") or "X-API-Key"
        token = creds.get("token") or ""
        if not token:
            return False, "API Key vazia."
        headers[header_name] = token
    # method == "none": sem auth, só GET na URL

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(base_url, headers=headers, auth=auth)
    except httpx.HTTPError as exc:
        return False, f"Erro de rede: {exc!s:.150}"
    if 200 <= resp.status_code < 400:
        return True, f"Conexão OK (HTTP {resp.status_code})."
    if resp.status_code == 401:
        return False, "Autenticação rejeitada (HTTP 401)."
    return False, f"HTTP {resp.status_code} — {resp.text[:150]}"


_HANDLERS = {
    "asaas": test_asaas,
    "custom": test_custom,
}


async def run_test(
    pool: Any, *, connection_id: int, empresa_id: int
) -> tuple[bool, str]:
    """Roteia pra handler correto baseado em provider_slug.

    Retorna (ok, mensagem).
    """
    conexao = await get_conexao_safe(
        pool, connection_id=connection_id, empresa_id=empresa_id
    )
    if conexao is None:
        return False, "Conexão não encontrada."
    creds = await get_credenciais_decrypted(pool, connection_id=connection_id)
    if creds is None:
        return False, "Credenciais corrompidas."
    handler = _HANDLERS.get(conexao["provider_slug"])
    if handler is None:
        return (
            False,
            f"Provider {conexao['provider_slug']} sem handler de teste.",
        )
    try:
        return await handler(creds, conexao)
    except Exception as exc:
        logger.warning(
            "test_handler_exception",
            provider=conexao["provider_slug"],
            error=str(exc),
        )
        return False, f"Erro inesperado: {exc!s:.150}"
