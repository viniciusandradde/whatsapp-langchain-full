"""Operações de fila no PostgreSQL.

Módulo compartilhado entre API e Worker para manipular a tabela message_queue.
A API insere mensagens (enqueue), o Worker consome (claim) e
finaliza (mark_done/failed).

O debounce agrupa mensagens rápidas do mesmo remetente: se o usuário
envia 3 mensagens em 2 segundos, elas são concatenadas em uma única
entrada na fila.

Uso:
    from whatsapp_langchain.shared.queue import enqueue_or_buffer

    result = await enqueue_or_buffer(pool, phone="+55...", body="Olá")
    message = await claim_next(pool, lease_seconds=60)
"""

import hashlib
from datetime import UTC, datetime, timedelta

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import EnqueueResult, MessageQueue

logger = structlog.get_logger()


async def enqueue_or_buffer(
    pool: AsyncConnectionPool,
    phone_number: str,
    agent_id: str,
    body: str,
    media_url: str | None = None,
    media_type: str | None = None,
    to_number: str | None = None,
    message_id: str | None = None,
    buffer_seconds: float = 2.0,
) -> EnqueueResult:
    """Insere mensagem na fila ou agrupa com mensagem pendente (debounce).

    Regras de debounce (Fase 3):
    - Debounce somente para texto (media_url IS NULL).
    - Mensagem com mídia não faz debounce (entrada imediata).
    - Antes de inserir mídia, flush de texto pendente do mesmo phone+agent
      para que o worker processe o texto ANTES da mídia (ordenação por created_at).
    - Concorrência protegida por pg_advisory_xact_lock(hash(phone+agent)).

    Limitação conhecida: NumMedia > 1 no mesmo webhook fica fora do escopo.

    Args:
        pool: Pool de conexões do psycopg.
        phone_number: Telefone do remetente (E.164).
        agent_id: ID do agente que vai processar.
        body: Texto da mensagem.
        media_url: URL de mídia anexada (opcional).
        media_type: MIME type da mídia (opcional).
        to_number: Número destinatário (opcional).
        message_id: ID externo da mensagem, ex: Twilio MessageSid (opcional).
        buffer_seconds: Segundos de debounce. Default: 2.0.

    Returns:
        EnqueueResult com message_id e se foi buffered.
    """
    thread_id = f"{phone_number}:{agent_id}"
    has_media = media_url is not None

    # Hash determinístico para pg_advisory_xact_lock.
    # Usa os 8 bytes iniciais do SHA-256 convertidos para int64 signed,
    # garantindo chave única por phone+agent sem risco de colisão prática.
    lock_key = int.from_bytes(
        hashlib.sha256(thread_id.encode()).digest()[:8],
        byteorder="big",
        signed=True,
    )

    async with pool.connection() as conn:
        # Lock transacional: serializa debounce para o mesmo phone+agent.
        # Liberado automaticamente no commit/rollback da transação.
        await conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

        if has_media:
            # Mídia: flush texto pendente e inserir imediatamente.
            # O flush antecipa o process_after de textos aguardando debounce,
            # garantindo que o worker os processe antes da mídia (via created_at).
            flushed = await conn.execute(
                """
                UPDATE message_queue
                SET process_after = NOW(),
                    updated_at = NOW()
                WHERE phone_number = %s
                  AND agent_id = %s
                  AND status = 'queued'
                  AND process_after > NOW()
                  AND media_url IS NULL
                """,
                (phone_number, agent_id),
            )
            if flushed.rowcount and flushed.rowcount > 0:
                logger.info(
                    "text_flushed_for_media",
                    phone=phone_number,
                    agent_id=agent_id,
                    flushed_count=flushed.rowcount,
                )

            # Inserir mídia com process_after=NOW() (sem buffer)
            cursor = await conn.execute(
                """
                INSERT INTO message_queue
                    (message_id, phone_number, to_number, agent_id,
                     thread_id, incoming_message, media_url, media_type,
                     process_after)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
                """,
                (
                    message_id,
                    phone_number,
                    to_number,
                    agent_id,
                    thread_id,
                    body,
                    media_url,
                    media_type,
                ),
            )
            row = await cursor.fetchone()
            assert row is not None
            new_id = row[0]
            await conn.commit()

            logger.info(
                "media_message_enqueued",
                message_id=new_id,
                phone=phone_number,
                agent_id=agent_id,
            )
            return EnqueueResult(message_id=new_id, is_buffered=False)

        # Texto: debounce normal (agrupa com texto pendente se existir)
        process_after = datetime.now(UTC) + timedelta(seconds=buffer_seconds)

        # Busca texto pendente para debounce (media_url IS NULL garante
        # que não debounce texto dentro de uma mensagem de mídia)
        cursor = await conn.execute(
            """
            SELECT id, incoming_message
            FROM message_queue
            WHERE phone_number = %s
              AND agent_id = %s
              AND status = 'queued'
              AND process_after > NOW()
              AND media_url IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (phone_number, agent_id),
        )
        existing = await cursor.fetchone()

        if existing:
            # Debounce: concatena texto e reseta timer
            existing_id, existing_body = existing
            new_body = f"{existing_body}\n{body}"

            await conn.execute(
                """
                UPDATE message_queue
                SET incoming_message = %s,
                    process_after = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (new_body, process_after, existing_id),
            )
            await conn.commit()

            logger.info(
                "message_buffered",
                message_id=existing_id,
                phone=phone_number,
                agent_id=agent_id,
            )
            return EnqueueResult(message_id=existing_id, is_buffered=True)

        # Nova mensagem de texto na fila
        cursor = await conn.execute(
            """
            INSERT INTO message_queue
                (message_id, phone_number, to_number, agent_id, thread_id,
                 incoming_message, media_url, media_type, process_after)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                message_id,
                phone_number,
                to_number,
                agent_id,
                thread_id,
                body,
                None,
                None,
                process_after,
            ),
        )
        row = await cursor.fetchone()
        assert row is not None
        new_id = row[0]
        await conn.commit()

        logger.info(
            "message_enqueued",
            message_id=new_id,
            phone=phone_number,
            agent_id=agent_id,
        )
        return EnqueueResult(message_id=new_id, is_buffered=False)


async def claim_next(
    pool: AsyncConnectionPool,
    lease_seconds: int = 60,
) -> MessageQueue | None:
    """Busca e reserva a próxima mensagem pronta para processamento.

    Usa FOR UPDATE SKIP LOCKED para concorrência segura entre múltiplos workers.
    Só retorna mensagens com process_after <= NOW() (debounce concluído) e
    dentro do limite de tentativas.

    Args:
        pool: Pool de conexões do psycopg.
        lease_seconds: Segundos de lock para o worker processar.

    Returns:
        MessageQueue se houver mensagem disponível, None caso contrário.
    """
    lease_until = datetime.now(UTC) + timedelta(seconds=lease_seconds)

    async with pool.connection() as conn:
        # Evita mensagens presas eternamente em processing após crash:
        # se o lease expirou e não há mais tentativas, marca como failed.
        await conn.execute(
            """
            UPDATE message_queue
            SET status = 'failed',
                error = COALESCE(
                    error,
                    'Processing lease expired after max attempts'
                ),
                processed_at = NOW(),
                updated_at = NOW()
            WHERE status = 'processing'
              AND lease_until IS NOT NULL
              AND lease_until <= NOW()
              AND attempts >= max_attempts
            """
        )

        cursor = await conn.execute(
            """
            UPDATE message_queue
            SET status = 'processing',
                lease_until = %s,
                attempts = attempts + 1,
                updated_at = NOW()
            WHERE id = (
                SELECT id FROM message_queue
                WHERE (
                    status = 'queued'
                    AND process_after <= NOW()
                    AND attempts < max_attempts
                )
                OR (
                    status = 'processing'
                    AND lease_until IS NOT NULL
                    AND lease_until <= NOW()
                    AND attempts < max_attempts
                )
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, message_id, phone_number, to_number, agent_id, thread_id,
                      incoming_message, media_url, media_type,
                      normalized_input, media_processing_status, media_processing_error,
                      status,
                      process_after, attempts, max_attempts, lease_until,
                      response, error, created_at, updated_at, processed_at
            """,
            (lease_until,),
        )
        row = await cursor.fetchone()
        await conn.commit()

        if row is None:
            return None

        message = MessageQueue(
            id=row[0],
            message_id=row[1],
            phone_number=row[2],
            to_number=row[3],
            agent_id=row[4],
            thread_id=row[5],
            incoming_message=row[6],
            media_url=row[7],
            media_type=row[8],
            normalized_input=row[9],
            media_processing_status=row[10],
            media_processing_error=row[11],
            status=row[12],
            process_after=row[13],
            attempts=row[14],
            max_attempts=row[15],
            lease_until=row[16],
            response=row[17],
            error=row[18],
            created_at=row[19],
            updated_at=row[20],
            processed_at=row[21],
        )

        logger.info(
            "message_claimed",
            message_id=message.id,
            phone=message.phone_number,
            agent_id=message.agent_id,
            attempt=message.attempts,
        )
        return message


async def mark_done(
    pool: AsyncConnectionPool,
    message_id: int,
    response: str,
    normalized_input: str | None = None,
    media_processing_status: str | None = None,
    media_processing_error: str | None = None,
) -> None:
    """Marca mensagem como processada com sucesso.

    Args:
        pool: Pool de conexões do psycopg.
        message_id: ID da mensagem na fila.
        response: Resposta gerada pelo agente.
        normalized_input: Texto normalizado enviado ao agente.
        media_processing_status: Resultado do pré-processamento de mídia.
        media_processing_error: Erro do pré-processamento de mídia, se houver.
    """
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE message_queue
            SET status = 'done',
                response = %s,
                normalized_input = COALESCE(%s, normalized_input),
                media_processing_status = COALESCE(%s, media_processing_status),
                media_processing_error = COALESCE(%s, media_processing_error),
                processed_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                response,
                normalized_input,
                media_processing_status,
                media_processing_error,
                message_id,
            ),
        )
        await conn.commit()

    logger.info("message_done", message_id=message_id)


async def mark_failed(
    pool: AsyncConnectionPool,
    message_id: int,
    error: str,
) -> None:
    """Marca mensagem como falha.

    Se ainda tem tentativas restantes, volta para 'queued' para retry.
    Caso contrário, marca como 'failed' definitivamente.

    Args:
        pool: Pool de conexões do psycopg.
        message_id: ID da mensagem na fila.
        error: Descrição do erro.
    """
    async with pool.connection() as conn:
        # Verifica se ainda tem tentativas
        cursor = await conn.execute(
            "SELECT attempts, max_attempts FROM message_queue WHERE id = %s",
            (message_id,),
        )
        row = await cursor.fetchone()

        if row and row[0] < row[1]:
            # Ainda tem tentativas: volta para a fila com backoff progressivo
            # Cada tentativa espera attempts * 5s antes de ser reprocessada
            backoff_seconds = row[0] * 5
            next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
            await conn.execute(
                """
                UPDATE message_queue
                SET status = 'queued',
                    error = %s,
                    lease_until = NULL,
                    process_after = NOW() + make_interval(secs => %s),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (error, backoff_seconds, message_id),
            )
            logger.warning(
                "message_retry",
                message_id=message_id,
                attempt=row[0],
                max_attempts=row[1],
                backoff_seconds=backoff_seconds,
                next_retry_at=next_retry_at.isoformat(),
                error=error,
            )
        else:
            # Sem tentativas: falha definitiva
            await conn.execute(
                """
                UPDATE message_queue
                SET status = 'failed',
                    error = %s,
                    processed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (error, message_id),
            )
            logger.error(
                "message_failed",
                message_id=message_id,
                error=error,
            )

        await conn.commit()


async def upsert_conversation(
    pool: AsyncConnectionPool,
    phone_number: str,
    agent_id: str,
    last_message: str,
) -> None:
    """Atualiza ou cria registro de conversa.

    Usado após cada mensagem processada para manter o histórico
    de conversas atualizado (para o painel admin).

    Args:
        pool: Pool de conexões do psycopg.
        phone_number: Telefone do remetente.
        agent_id: ID do agente.
        last_message: Última mensagem processada.
    """
    thread_id = f"{phone_number}:{agent_id}"

    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO conversations (
                phone_number, agent_id, thread_id,
                last_message, last_message_at, message_count)
            VALUES (%s, %s, %s, %s, NOW(), 1)
            ON CONFLICT (phone_number, agent_id) DO UPDATE SET
                last_message = EXCLUDED.last_message,
                last_message_at = NOW(),
                message_count = conversations.message_count + 1,
                updated_at = NOW()
            """,
            (phone_number, agent_id, thread_id, last_message),
        )
        await conn.commit()
