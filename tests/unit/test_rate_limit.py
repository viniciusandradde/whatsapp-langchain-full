"""Testes do rate limiter in-memory."""

import time

import pytest
from fastapi import HTTPException

from whatsapp_langchain.server.dependencies import check_rate_limit, request_history


@pytest.fixture(autouse=True)
def clear_history():
    """Limpa o histórico de requisições entre testes."""
    request_history.clear()
    yield
    request_history.clear()


class TestRateLimit:
    """Testes do sliding window rate limiter."""

    async def test_allows_within_limit(self):
        """Permite requisições dentro do limite."""
        # Limite padrão: 30/hora
        for _ in range(5):
            await check_rate_limit("+5511999999999")
        # Sem exceção = dentro do limite

    async def test_blocks_over_limit(self, monkeypatch):
        """Bloqueia quando excede o limite."""
        # Configura limite baixo para teste
        from whatsapp_langchain.shared.config import settings

        monkeypatch.setattr(settings, "rate_limit_per_hour", 3)

        # Primeiras 3 passam
        for _ in range(3):
            await check_rate_limit("+5511999999999")

        # A 4ª deve ser bloqueada
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit("+5511999999999")
        assert exc_info.value.status_code == 429

    async def test_different_phones_independent(self, monkeypatch):
        """Rate limit é independente por telefone."""
        from whatsapp_langchain.shared.config import settings

        monkeypatch.setattr(settings, "rate_limit_per_hour", 2)

        # Telefone A: 2 requisições (no limite)
        await check_rate_limit("+5511111111111")
        await check_rate_limit("+5511111111111")

        # Telefone B: ainda pode
        await check_rate_limit("+5522222222222")

    async def test_old_requests_expire(self, monkeypatch):
        """Requisições antigas (>1h) não contam no limite."""
        from whatsapp_langchain.shared.config import settings

        monkeypatch.setattr(settings, "rate_limit_per_hour", 2)

        # Simula requisições de 2 horas atrás
        old_time = time.time() - 7200
        request_history["+5511999999999"] = [old_time, old_time]

        # Deve permitir novas requisições (as antigas expiraram)
        await check_rate_limit("+5511999999999")
