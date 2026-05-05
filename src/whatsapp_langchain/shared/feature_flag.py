"""Feature flags por empresa (Fase 0.2).

API simples:

    from whatsapp_langchain.shared.feature_flag import is_enabled, get_value

    if await is_enabled(pool, empresa_id, "mcp_beta"):
        # rola feature MCP só pra empresas opt-in

    variant = await get_value(pool, empresa_id, "dashboard_variant", default="A")
    # value pode ser qualquer JSON

Cache TTL 60s por (empresa_id, key) — evita 1 query/request. Invalida
manualmente via `invalidate_cache(empresa_id, key)` quando admin muda
o flag pelo painel.
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


_CACHE_TTL_SECONDS = 60
_cache: dict[tuple[int, str], tuple[float, Any]] = {}


def _cache_key(empresa_id: int, key: str) -> tuple[int, str]:
    return (empresa_id, key)


def invalidate_cache(empresa_id: int, key: str | None = None) -> None:
    """Invalida cache. `key=None` invalida todos os flags da empresa."""
    if key is None:
        to_delete = [k for k in _cache if k[0] == empresa_id]
        for k in to_delete:
            _cache.pop(k, None)
    else:
        _cache.pop(_cache_key(empresa_id, key), None)


async def get_value(
    pool: AsyncConnectionPool,
    empresa_id: int,
    key: str,
    default: Any = None,
) -> Any:
    """Retorna o valor do flag (qualquer JSON) ou `default` se inativo/inexistente."""
    ck = _cache_key(empresa_id, key)
    now = time.monotonic()
    cached = _cache.get(ck)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT value FROM feature_flag
             WHERE empresa_id = %s AND key = %s AND ativo = TRUE
             LIMIT 1
            """,
            (empresa_id, key),
        )
        row = await cur.fetchone()

    value = row[0] if row else default
    _cache[ck] = (now, value)
    return value


async def is_enabled(
    pool: AsyncConnectionPool,
    empresa_id: int,
    key: str,
) -> bool:
    """Atalho pra flags booleanos. value=true → True, qualquer outra coisa → False.

    Default False (feature desligada) — segurança: novo flag não vaza
    feature em prod até alguém ativar explicitamente.
    """
    v = await get_value(pool, empresa_id, key, default=False)
    return v is True


async def list_flags(
    pool: AsyncConnectionPool, empresa_id: int
) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, empresa_id, key, value, descricao, ativo,
                   created_by_user_id, created_at, updated_at
              FROM feature_flag
             WHERE empresa_id = %s
             ORDER BY key
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "empresa_id": r[1],
            "key": r[2],
            "value": r[3],
            "descricao": r[4],
            "ativo": r[5],
            "created_by_user_id": r[6],
            "created_at": r[7].isoformat() if r[7] else None,
            "updated_at": r[8].isoformat() if r[8] else None,
        }
        for r in rows
    ]


async def upsert_flag(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    key: str,
    value: Any,
    descricao: str | None = None,
    ativo: bool = True,
    user_id: str | None = None,
) -> dict:
    """Cria ou atualiza flag. Retorna a row final."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO feature_flag
                (empresa_id, key, value, descricao, ativo, created_by_user_id)
            VALUES (%s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT (empresa_id, key) DO UPDATE SET
                value = EXCLUDED.value,
                descricao = EXCLUDED.descricao,
                ativo = EXCLUDED.ativo,
                updated_at = NOW()
            RETURNING id, empresa_id, key, value, descricao, ativo,
                      created_by_user_id, created_at, updated_at
            """,
            (
                empresa_id,
                key,
                json.dumps(value),
                descricao,
                ativo,
                user_id,
            ),
        )
        row = await cur.fetchone()
        await conn.commit()

    invalidate_cache(empresa_id, key)
    assert row is not None
    return {
        "id": row[0],
        "empresa_id": row[1],
        "key": row[2],
        "value": row[3],
        "descricao": row[4],
        "ativo": row[5],
        "created_by_user_id": row[6],
        "created_at": row[7].isoformat() if row[7] else None,
        "updated_at": row[8].isoformat() if row[8] else None,
    }


async def delete_flag(
    pool: AsyncConnectionPool, empresa_id: int, key: str
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM feature_flag WHERE empresa_id = %s AND key = %s",
            (empresa_id, key),
        )
        await conn.commit()
        invalidate_cache(empresa_id, key)
        return (cur.rowcount or 0) > 0
