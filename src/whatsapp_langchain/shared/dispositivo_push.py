"""Registro de dispositivos para push (mig 168).

O token FCM identifica o APARELHO. O UPSERT troca o dono quando o mesmo
celular reloga com outro usuário — sem isso, o aparelho de um ex-funcionário
continuaria recebendo notificação de conversa de cliente.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()


async def registrar_dispositivo(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    user_id: str,
    fcm_token: str,
    plataforma: str = "android",
) -> None:
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO dispositivo_push
                    (empresa_id, user_id, fcm_token, plataforma)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (fcm_token) DO UPDATE SET
                    empresa_id = EXCLUDED.empresa_id,
                    user_id = EXCLUDED.user_id,
                    plataforma = EXCLUDED.plataforma,
                    visto_at = NOW()
                """,
                (empresa_id, user_id, fcm_token, plataforma),
            )
            await conn.commit()


async def remover_dispositivo(
    pool: AsyncConnectionPool, *, empresa_id: int, fcm_token: str
) -> None:
    """Chamado no Sair do app. Idempotente."""
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            await conn.execute(
                "DELETE FROM dispositivo_push WHERE fcm_token = %s",
                (fcm_token,),
            )
            await conn.commit()


async def tokens_da_empresa(pool: AsyncConnectionPool, empresa_id: int) -> list[str]:
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT fcm_token FROM dispositivo_push WHERE empresa_id = %s",
                (empresa_id,),
            )
            rows = await cur.fetchall()
    return [r[0] for r in rows]


async def apagar_token_invalido(pool: AsyncConnectionPool, fcm_token: str) -> None:
    """FCM disse UNREGISTERED — o aparelho desinstalou. Limpa sem tenant:
    o token é globalmente único e o evento chega fora de request context."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                "DELETE FROM dispositivo_push WHERE fcm_token = %s",
                (fcm_token,),
            )
            await conn.commit()
    logger.info("push_token_invalido_removido")
