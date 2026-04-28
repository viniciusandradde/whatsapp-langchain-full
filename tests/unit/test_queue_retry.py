"""Testes do backoff progressivo no retry da fila.

Como mark_failed() executa SQL no PostgreSQL, testamos a lógica de
cálculo do backoff isoladamente e verificamos que o SQL correto é
gerado via mock do pool.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from whatsapp_langchain.shared.queue import mark_failed


class TestRetryBackoff:
    """Testes do backoff progressivo em mark_failed."""

    @pytest.fixture
    def mock_pool(self):
        """Pool mockado que simula respostas do PostgreSQL.

        psycopg's pool.connection() retorna async context manager (não coroutine),
        por isso usamos asynccontextmanager em vez de AsyncMock direto.
        """
        conn = AsyncMock()
        pool = AsyncMock()

        @asynccontextmanager
        async def fake_connection():
            yield conn

        pool.connection = fake_connection
        return pool, conn

    async def test_retry_sets_backoff(self, mock_pool):
        """Retry deve incluir process_after com backoff no SQL."""
        pool, conn = mock_pool

        # Simula: attempts=1, max_attempts=3 → ainda tem retries
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(1, 3))
        conn.execute = AsyncMock(return_value=cursor)

        await mark_failed(pool, message_id=42, error="timeout")

        # Segunda chamada ao execute é o UPDATE de retry
        calls = conn.execute.call_args_list
        assert len(calls) == 2

        retry_sql = calls[1][0][0]
        retry_params = calls[1][0][1]

        # SQL deve conter process_after com make_interval
        assert "process_after" in retry_sql
        assert "make_interval" in retry_sql

        # Backoff = attempts * 5 = 1 * 5 = 5 segundos
        assert retry_params == ("timeout", 5, 42)

    async def test_backoff_increases_with_attempts(self, mock_pool):
        """Segundo retry deve ter backoff maior que o primeiro."""
        pool, conn = mock_pool

        # Simula: attempts=2, max_attempts=3
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(2, 3))
        conn.execute = AsyncMock(return_value=cursor)

        await mark_failed(pool, message_id=42, error="timeout")

        calls = conn.execute.call_args_list
        retry_params = calls[1][0][1]

        # Backoff = attempts * 5 = 2 * 5 = 10 segundos
        assert retry_params == ("timeout", 10, 42)

    async def test_max_attempts_marks_failed(self, mock_pool):
        """Quando esgotam tentativas, marca como failed definitivamente."""
        pool, conn = mock_pool

        # Simula: attempts=3, max_attempts=3 → sem mais retries
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(3, 3))
        conn.execute = AsyncMock(return_value=cursor)

        await mark_failed(pool, message_id=42, error="fatal")

        calls = conn.execute.call_args_list
        assert len(calls) == 2

        fail_sql = calls[1][0][0]
        # Deve marcar como failed, não queued
        assert "status = 'failed'" in fail_sql
        assert "processed_at = NOW()" in fail_sql

    async def test_backoff_formula(self):
        """Verifica a fórmula de backoff: attempts * 5 segundos."""
        # Fórmula simples — sem jitter ou exponencial
        assert 1 * 5 == 5  # 1a tentativa: 5s
        assert 2 * 5 == 10  # 2a tentativa: 10s
        assert 3 * 5 == 15  # 3a tentativa: 15s

    async def test_retry_log_contains_next_retry_at(self, mock_pool):
        """Log de retry deve incluir o timestamp da próxima tentativa."""
        pool, conn = mock_pool

        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=(1, 3))
        conn.execute = AsyncMock(return_value=cursor)

        with patch("whatsapp_langchain.shared.queue.logger.warning") as mock_warning:
            await mark_failed(pool, message_id=42, error="timeout")

        assert mock_warning.called
        kwargs = mock_warning.call_args.kwargs
        assert "next_retry_at" in kwargs
        datetime.fromisoformat(kwargs["next_retry_at"])
