"""Rate limit genérico por bucket key + janela.

Usado por:
- `server/middlewares.py::admin_rate_limit_middleware` — limita
  endpoints admin por user_id (60 req/min)
- `server/routes/auth_proxy.py` (futuro) — limita login Better Auth
  por IP (5 req/15min)
- Plugins futuros (convite por email, reset password, etc.)

Comportamento:
- UPSERT no bucket `(bucket_key, window_start)` incrementando contador
- Lança `RateLimitExceeded` (HTTPException 429) se contador > limit
- Cleanup inline ~1% das chamadas remove buckets >24h

Não usa cache em memória — sliding window distribuído via Postgres pra
funcionar em multi-instância (a stack roda 4+ workers + N réplicas API).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import HTTPException, status
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()

CLEANUP_PROBABILITY = 0.01
CLEANUP_KEEP_HOURS = 24


class RateLimitExceeded(HTTPException):
    """429 Too Many Requests com mensagem padronizada."""

    def __init__(self, *, bucket_key: str, limit: int, window_seconds: int):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Limite de {limit} requisições a cada {window_seconds}s "
                "excedido. Tente novamente em alguns instantes."
            ),
            headers={"Retry-After": str(window_seconds)},
        )
        self.bucket_key = bucket_key


def _window_start(now: datetime, window_seconds: int) -> datetime:
    """Trunca `now` pro início da janela (ex: window=60 → minuto cheio)."""
    epoch_seconds = int(now.timestamp())
    bucket_seconds = (epoch_seconds // window_seconds) * window_seconds
    return datetime.fromtimestamp(bucket_seconds, tz=timezone.utc)


async def enforce_bucket_limit(
    pool: AsyncConnectionPool,
    bucket_key: str,
    *,
    limit: int,
    window_seconds: int,
) -> int:
    """Incrementa o bucket; lança RateLimitExceeded se ultrapassar `limit`.

    Args:
        pool: Pool de conexões.
        bucket_key: Identificador do bucket (ex: "user:abc:admin",
            "ip:1.2.3.4:signin"). Convenção: `<scope>:<id>:<action>`.
        limit: Máximo de requisições permitidas na janela.
        window_seconds: Tamanho da janela em segundos.

    Returns:
        Quantidade atual de requisições no bucket (após incremento).

    Raises:
        RateLimitExceeded: HTTP 429 quando contador > limit.
    """
    now = datetime.now(timezone.utc)
    window = _window_start(now, window_seconds)

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO rate_limit_bucket (bucket_key, window_start, request_count)
            VALUES (%s, %s, 1)
            ON CONFLICT (bucket_key, window_start)
            DO UPDATE SET request_count = rate_limit_bucket.request_count + 1
            RETURNING request_count
            """,
            (bucket_key, window),
        )
        row = await cur.fetchone()
        await conn.commit()

        if random.random() < CLEANUP_PROBABILITY:
            cutoff = now - timedelta(hours=CLEANUP_KEEP_HOURS)
            await conn.execute(
                "DELETE FROM rate_limit_bucket WHERE window_start < %s",
                (cutoff,),
            )
            await conn.commit()

    count = row[0] if row else 0
    if count > limit:
        logger.warning(
            "rate_limit_exceeded",
            bucket_key=bucket_key,
            count=count,
            limit=limit,
            window_seconds=window_seconds,
        )
        raise RateLimitExceeded(
            bucket_key=bucket_key,
            limit=limit,
            window_seconds=window_seconds,
        )
    return count
