"""Testes de claim da fila com recuperação de lease expirado."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from whatsapp_langchain.shared.queue import claim_next


class TestClaimNextLeaseRecovery:
    """Garante que mensagens não ficam presas em status processing."""

    @pytest.fixture
    def mock_pool(self):
        conn = AsyncMock()
        pool = AsyncMock()

        @asynccontextmanager
        async def fake_connection():
            yield conn

        pool.connection = fake_connection
        return pool, conn

    async def test_marks_expired_processing_as_failed_when_max_attempts_reached(
        self, mock_pool
    ):
        """Lease expirado sem retries restantes deve virar failed."""
        pool, conn = mock_pool

        stale_cursor = AsyncMock()
        claim_cursor = AsyncMock()
        claim_cursor.fetchone = AsyncMock(return_value=None)
        conn.execute = AsyncMock(side_effect=[stale_cursor, claim_cursor])

        result = await claim_next(pool, lease_seconds=60)

        assert result is None
        calls = conn.execute.call_args_list
        assert len(calls) == 2

        stale_sql = calls[0][0][0]
        assert "SET status = 'failed'" in stale_sql
        assert "status = 'processing'" in stale_sql
        assert "lease_until <= NOW()" in stale_sql
        assert "attempts >= max_attempts" in stale_sql

    async def test_reclaims_expired_processing_when_attempts_remain(self, mock_pool):
        """Claim deve considerar processing com lease expirado para retry."""
        pool, conn = mock_pool

        stale_cursor = AsyncMock()
        claim_cursor = AsyncMock()
        claim_cursor.fetchone = AsyncMock(return_value=None)
        conn.execute = AsyncMock(side_effect=[stale_cursor, claim_cursor])

        result = await claim_next(pool, lease_seconds=60)

        assert result is None
        calls = conn.execute.call_args_list
        assert len(calls) == 2

        claim_sql = calls[1][0][0]
        assert "status = 'queued'" in claim_sql
        assert "status = 'processing'" in claim_sql
        assert "lease_until <= NOW()" in claim_sql
        assert "attempts < max_attempts" in claim_sql
