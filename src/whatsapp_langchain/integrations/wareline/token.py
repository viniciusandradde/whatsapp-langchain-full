"""Cache + refresh do JWT Wareline (OAuth2 password grant).

Token TTL real = 300s (5min). Guardamos com 30s de margem (`expires_at = NOW()
+ (expires_in - 30) seconds`) pra evitar race condition no expirar.

Race-safe via INSERT ON CONFLICT DO UPDATE — múltiplos workers podem
chamar `get_or_refresh_token` simultâneo; um deles refaz OAuth, outros
pegam o token novo na próxima leitura.
"""

from __future__ import annotations

import httpx
import structlog

from whatsapp_langchain.integrations.wareline.credentials import (
    get_credentials,
)
from whatsapp_langchain.integrations.wareline.errors import (
    WarelineAuthError,
    WarelineConfigError,
    WarelineUnavailableError,
)
from whatsapp_langchain.integrations.wareline.models import (
    TokenResponse,
    WarelineCredentials,
)

logger = structlog.get_logger()

# Endpoint OAuth Wareline (fixo na doc)
_TOKEN_PATH = "/services/auth/realms/conectew/protocol/openid-connect/token"

# Margem de segurança pra evitar race: expira no DB 30s antes do real
_SAFETY_MARGIN_SECONDS = 30

# Timeout httpx pra OAuth (deve ser rápido)
_OAUTH_TIMEOUT_SECONDS = 10.0


async def _request_new_token(creds: WarelineCredentials) -> TokenResponse:
    """Faz OAuth2 password grant. Lança WarelineAuthError em 401,
    WarelineUnavailableError em 5xx/rede."""
    url = f"{creds.base_url}{_TOKEN_PATH}"
    data = {
        "grant_type": "password",
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "username": creds.username,
        "password": creds.password,
    }
    try:
        async with httpx.AsyncClient(timeout=_OAUTH_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning(
            "wareline_oauth_network_failed",
            empresa_id=creds.empresa_id,
            error=str(exc),
        )
        raise WarelineUnavailableError(
            f"OAuth Wareline indisponível: {exc!s}"
        ) from exc

    if resp.status_code == 401:
        raise WarelineAuthError(
            "Credenciais Wareline inválidas (HTTP 401 no OAuth)."
        )
    if resp.status_code >= 500:
        raise WarelineUnavailableError(
            f"OAuth Wareline retornou {resp.status_code}: "
            f"{resp.text[:200]}"
        )
    if resp.status_code >= 400:
        raise WarelineAuthError(
            f"OAuth Wareline rejeitou request ({resp.status_code}): "
            f"{resp.text[:200]}"
        )

    return TokenResponse.model_validate(resp.json())


async def get_or_refresh_token(pool, empresa_id: int) -> str:
    """Retorna access_token válido pra empresa, refrescando se necessário.

    Ordem:
    1. Lê cache (`wareline_token_cache`). Se válido (expires_at > NOW()), retorna
    2. Senão carrega credenciais + faz OAuth + UPSERT no cache
    """
    # 1. Cache hit?
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT access_token, expires_at
              FROM wareline_token_cache
             WHERE empresa_id = %s AND expires_at > NOW()
            """,
            (empresa_id,),
        )
        cached = await cur.fetchone()
    if cached:
        return cached[0]

    # 2. Refresh
    creds = await get_credentials(pool, empresa_id)
    if creds is None:
        raise WarelineConfigError(
            f"Empresa {empresa_id} não tem credenciais Wareline configuradas."
        )
    if not creds.ativo:
        raise WarelineConfigError(
            f"Integração Wareline desativada pra empresa {empresa_id}."
        )

    token = await _request_new_token(creds)
    safe_seconds = max(60, token.expires_in - _SAFETY_MARGIN_SECONDS)

    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO wareline_token_cache (
                empresa_id, access_token, expires_at,
                refresh_token, refreshed_at
            ) VALUES (%s, %s, NOW() + (%s || ' seconds')::interval, %s, NOW())
            ON CONFLICT (empresa_id) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                expires_at = EXCLUDED.expires_at,
                refresh_token = EXCLUDED.refresh_token,
                refreshed_at = NOW()
            """,
            (empresa_id, token.access_token, safe_seconds, token.refresh_token),
        )
        await conn.commit()

    logger.info(
        "wareline_token_refreshed",
        empresa_id=empresa_id,
        expires_in_seconds=safe_seconds,
    )
    return token.access_token


async def invalidate_token(pool, empresa_id: int) -> None:
    """Apaga cache do token. Útil ao salvar credenciais novas ou
    quando 401 acontece após token cacheado (token revogado server-side)."""
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM wareline_token_cache WHERE empresa_id = %s",
            (empresa_id,),
        )
        await conn.commit()
