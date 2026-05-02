"""Helpers de configuração do AgenteIA por empresa (M5.b).

Cada (empresa_id, agent_id) pode ter um override de `system_prompt`
e `temperatura`. O loader consulta `get_agente_ia_config` e propaga
pro `build_graph` do agente.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import AgenteIAConfig, AgenteIAConfigInput

logger = structlog.get_logger()


_SELECT_COLS = (
    "empresa_id, agent_id, system_prompt_override, temperatura, "
    "ativo, updated_by_user_id, created_at, updated_at"
)


def _row_to_config(row) -> AgenteIAConfig:
    return AgenteIAConfig(
        empresa_id=row[0],
        agent_id=row[1],
        system_prompt_override=row[2],
        temperatura=float(row[3]) if row[3] is not None else None,
        ativo=row[4],
        updated_by_user_id=row[5],
        created_at=row[6],
        updated_at=row[7],
    )


async def get_agente_ia_config(
    pool: AsyncConnectionPool, empresa_id: int, agent_id: str
) -> AgenteIAConfig | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM agente_ia_config
             WHERE empresa_id = %s AND agent_id = %s
            """,
            (empresa_id, agent_id),
        )
        row = await cur.fetchone()
    return _row_to_config(row) if row else None


async def upsert_agente_ia_config(
    pool: AsyncConnectionPool,
    empresa_id: int,
    agent_id: str,
    data: AgenteIAConfigInput,
    *,
    user_id: str | None = None,
) -> AgenteIAConfig:
    """Cria/atualiza override. Texto vazio é normalizado pra NULL."""
    prompt = (data.system_prompt_override or "").strip() or None
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO agente_ia_config
                (empresa_id, agent_id, system_prompt_override, temperatura,
                 ativo, updated_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (empresa_id, agent_id) DO UPDATE SET
                system_prompt_override = EXCLUDED.system_prompt_override,
                temperatura = EXCLUDED.temperatura,
                ativo = EXCLUDED.ativo,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = NOW()
            RETURNING {_SELECT_COLS}
            """,
            (
                empresa_id,
                agent_id,
                prompt,
                data.temperatura,
                data.ativo,
                user_id,
            ),
        )
        row = await cur.fetchone()
    assert row is not None
    return _row_to_config(row)


async def delete_agente_ia_config(
    pool: AsyncConnectionPool, empresa_id: int, agent_id: str
) -> bool:
    """Remove o override — agente volta a usar o SYSTEM_PROMPT do catálogo."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM agente_ia_config WHERE empresa_id = %s AND agent_id = %s",
            (empresa_id, agent_id),
        )
    return (cur.rowcount or 0) > 0


async def resolve_runtime_config(
    pool: AsyncConnectionPool, empresa_id: int, agent_id: str
) -> tuple[str | None, float | None]:
    """Resolve overrides ativos → (prompt, temperatura).

    Retorna `(None, None)` quando não há override ou ele está desativado.
    """
    config = await get_agente_ia_config(pool, empresa_id, agent_id)
    if config is None or not config.ativo:
        return None, None
    return config.system_prompt_override, config.temperatura
