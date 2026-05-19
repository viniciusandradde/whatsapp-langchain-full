"""Read receipts por atendente (Sprint Atendimento UX 1.3, mig 052).

`atendimento_visualizacao` rastreia "última vez que cada user viu o
atendimento X". Permite badge "nova msg desde sua última visita" + UX
de fila menos confusa em equipes grandes.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


async def marcar_lido(
    pool: AsyncConnectionPool, *, atendimento_id: int, user_id: str
) -> None:
    """UPSERT em atendimento_visualizacao com NOW()."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO atendimento_visualizacao (atendimento_id, user_id,
                                                   ultima_visualizacao_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (atendimento_id, user_id)
            DO UPDATE SET ultima_visualizacao_at = NOW()
            """,
            (atendimento_id, user_id),
        )
        await conn.commit()


async def get_ultima_visualizacao(
    pool: AsyncConnectionPool, *, atendimento_id: int, user_id: str
) -> str | None:
    """Retorna ISO timestamp da última visualização do user no atendimento.

    None se user nunca abriu (badge "nova" aparece).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT ultima_visualizacao_at FROM atendimento_visualizacao
             WHERE atendimento_id = %s AND user_id = %s
            """,
            (atendimento_id, user_id),
        )
        row = await cur.fetchone()
    if row is None or row[0] is None:
        return None
    return row[0].isoformat()


async def count_unread_para_user(
    pool: AsyncConnectionPool,
    *,
    atendimento_ids: list[int],
    user_id: str,
) -> dict[int, int]:
    """Retorna {atendimento_id: count_msgs_novas_desde_ultima_visualizacao}.

    Conta apenas msgs com status='done' (chegou de fato). Quando user
    nunca abriu, conta todas as mensagens do atendimento.
    """
    if not atendimento_ids:
        return {}
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT m.atendimento_id, COUNT(*)
              FROM message_queue m
              LEFT JOIN atendimento_visualizacao v
                ON v.atendimento_id = m.atendimento_id
               AND v.user_id = %s
             WHERE m.atendimento_id = ANY(%s)
               AND m.status = 'done'
               AND (v.ultima_visualizacao_at IS NULL
                    OR m.created_at > v.ultima_visualizacao_at)
             GROUP BY m.atendimento_id
            """,
            (user_id, list(atendimento_ids)),
        )
        rows = await cur.fetchall()
    return {r[0]: r[1] for r in rows}
