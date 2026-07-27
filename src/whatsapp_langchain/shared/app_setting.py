"""Preferências globais da plataforma (tabela `app_setting`, mig 141).

Texto puro, não-secreto. Segredo vai em `platform_integration_config`, que é
criptografado.

Hoje guarda só `observabilidade.provider`, mas a tabela é chave/valor de
propósito: a próxima preferência global não precisa de migration nova.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()

# Provider de observabilidade. `auto` mantém a resolução por env
# (Langfuse > LangSmith > nenhum); os outros dois forçam.
CHAVE_OBS_PROVIDER = "observabilidade.provider"
OBS_PROVIDER_VALIDOS = frozenset({"auto", "langfuse", "langsmith"})


async def get_setting(
    pool: AsyncConnectionPool, chave: str, default: str | None = None
) -> str | None:
    """Lê uma preferência. `default` quando a chave não existe.

    Best-effort: erro de leitura devolve o default em vez de propagar. Uma
    preferência de UI não pode derrubar a página que a consome.
    """
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT valor FROM app_setting WHERE chave = %s", (chave,)
            )
            row = await cur.fetchone()
        return row[0] if row else default
    except Exception as exc:
        logger.warning("app_setting_read_failed", chave=chave, error=str(exc))
        return default


async def set_setting(
    pool: AsyncConnectionPool,
    chave: str,
    valor: str,
    *,
    updated_by: str | None = None,
) -> None:
    """Grava (upsert) uma preferência."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO app_setting (chave, valor, updated_by, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (chave) DO UPDATE
               SET valor = EXCLUDED.valor,
                   updated_by = EXCLUDED.updated_by,
                   updated_at = NOW()
            """,
            (chave, valor, updated_by),
        )
        await conn.commit()
    logger.info("app_setting_updated", chave=chave, valor=valor, por=updated_by)


async def get_obs_provider_preferido(pool: AsyncConnectionPool) -> str:
    """Preferência de provider. Sempre devolve valor válido.

    Valor corrompido no banco cai pra `auto` — pior cenário é o comportamento
    de antes da mig 141, nunca uma página quebrada.
    """
    valor = await get_setting(pool, CHAVE_OBS_PROVIDER, "auto") or "auto"
    if valor not in OBS_PROVIDER_VALIDOS:
        logger.warning("obs_provider_invalido", valor=valor, usando="auto")
        return "auto"
    return valor
