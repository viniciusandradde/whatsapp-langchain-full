"""Rate limit em Postgres — sliding window por hora cheia.

Requer Postgres rodando (make db && make migrate). Skip se não acessível.
"""
import os
from contextlib import suppress

import psycopg
import pytest
from fastapi import HTTPException
from psycopg_pool import AsyncConnectionPool


@pytest.fixture
def db_url() -> str:
    """Valida que Postgres está acessível e migrations aplicadas."""
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/whatsapp_langchain",
    )
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM rate_limit_buckets LIMIT 1"
                )
    except psycopg.OperationalError:
        pytest.skip("Postgres não acessível. Rode: make db")
    except psycopg.errors.UndefinedTable:
        pytest.skip(
            "Tabela rate_limit_buckets ausente. Rode: make migrate"
        )
    return url


@pytest.fixture
def clean_buckets(db_url):
    """Limpa rate_limit_buckets antes/depois de cada teste."""
    with suppress(psycopg.errors.UndefinedTable):
        with psycopg.connect(db_url) as conn:
            conn.execute("TRUNCATE rate_limit_buckets")
            conn.commit()
    yield
    with suppress(psycopg.errors.UndefinedTable):
        with psycopg.connect(db_url) as conn:
            conn.execute("TRUNCATE rate_limit_buckets")
            conn.commit()


async def test_check_rate_limit_db_increments(db_url, clean_buckets):
    from whatsapp_langchain.server.dependencies import _check_rate_limit_db

    async with AsyncConnectionPool(db_url, min_size=1, max_size=2, open=False) as pool:
        await pool.open()
        for _ in range(3):
            await _check_rate_limit_db(pool, "+5511999990001", limit=10)

    with psycopg.connect(db_url) as conn:
        cur = conn.execute(
            "SELECT request_count FROM rate_limit_buckets WHERE phone_number=%s",
            ("+5511999990001",),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 3


async def test_check_rate_limit_db_blocks_over_limit(db_url, clean_buckets):
    from whatsapp_langchain.server.dependencies import _check_rate_limit_db

    async with AsyncConnectionPool(db_url, min_size=1, max_size=2, open=False) as pool:
        await pool.open()
        for _ in range(3):
            await _check_rate_limit_db(pool, "+5511999990002", limit=3)
        with pytest.raises(HTTPException) as exc:
            await _check_rate_limit_db(pool, "+5511999990002", limit=3)
        assert exc.value.status_code == 429
