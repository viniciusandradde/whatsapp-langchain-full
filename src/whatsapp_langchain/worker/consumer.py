"""Consumidor de mensagens da fila.

Encapsula a lógica de polling da fila PostgreSQL.
O Worker chama claim_next_message() em loop para buscar mensagens.

Uso:
    from whatsapp_langchain.worker.consumer import claim_next_message

    message = await claim_next_message(pool, lease_seconds=60)
    if message:
        await process_message(message)
"""

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import MessageQueue
from whatsapp_langchain.shared.queue import claim_next

logger = structlog.get_logger()


async def claim_next_message(
    pool: AsyncConnectionPool,
    lease_seconds: int = 60,
) -> MessageQueue | None:
    """Busca a próxima mensagem pronta na fila.

    Wrapper sobre shared/queue.claim_next() com logging contextual
    para o Worker.

    Sprint A.2.6: claim é cross-tenant (worker precisa ver fila de TODAS
    as empresas). Envolve em `empresa_scope(None, bypass=True)` pra que
    `_RlsAwarePool` injete `SET app.bypass_rls = true` na conexão. Após
    o claim retornar, worker/main.py seta o context da empresa da msg via
    outro `empresa_scope(message.empresa_id)` antes de processar.

    Args:
        pool: Pool de conexões do psycopg.
        lease_seconds: Segundos de lock para processamento.

    Returns:
        MessageQueue se houver mensagem, None se a fila está vazia.
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope

    with empresa_scope(None, bypass=True):
        message = await claim_next(pool, lease_seconds=lease_seconds)

    if message is None:
        logger.debug("queue_empty")

    return message
