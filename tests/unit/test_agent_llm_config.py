"""Testes do helper get_agent_llm_config (resolução por agente com fallback)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.llm import get_agent_llm_config


def _mock_pool(row: tuple[str | None, str | None] | None) -> MagicMock:
    """Constrói um pool psycopg async cujo SELECT retorna `row`."""
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=row)
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.mark.asyncio
async def test_fallback_to_env_when_no_row(monkeypatch):
    """Sem row no DB → ambos os modelos vêm das envs."""
    monkeypatch.setattr(
        "whatsapp_langchain.shared.config.settings.openrouter_model",
        "env-chat",
    )
    monkeypatch.setattr(
        "whatsapp_langchain.shared.config.settings.openrouter_midia_model",
        "env-midia",
    )

    pool = _mock_pool(row=None)
    chat, midia = await get_agent_llm_config(pool, "vsa_tech")

    assert chat == "env-chat"
    assert midia == "env-midia"


@pytest.mark.asyncio
async def test_returns_db_row_when_present(monkeypatch):
    """Row com ambos os modelos populados → usa valores do DB."""
    monkeypatch.setattr(
        "whatsapp_langchain.shared.config.settings.openrouter_model",
        "env-chat",
    )
    monkeypatch.setattr(
        "whatsapp_langchain.shared.config.settings.openrouter_midia_model",
        "env-midia",
    )

    pool = _mock_pool(row=("custom-chat", "custom-midia"))
    chat, midia = await get_agent_llm_config(pool, "vsa_tech")

    assert chat == "custom-chat"
    assert midia == "custom-midia"


@pytest.mark.asyncio
async def test_partial_null_uses_env(monkeypatch):
    """Campo NULL no DB → fallback parcial pra env naquele campo."""
    monkeypatch.setattr(
        "whatsapp_langchain.shared.config.settings.openrouter_model",
        "env-chat",
    )
    monkeypatch.setattr(
        "whatsapp_langchain.shared.config.settings.openrouter_midia_model",
        "env-midia",
    )

    pool = _mock_pool(row=("custom-chat", None))
    chat, midia = await get_agent_llm_config(pool, "vsa_tech")

    assert chat == "custom-chat"
    assert midia == "env-midia"
