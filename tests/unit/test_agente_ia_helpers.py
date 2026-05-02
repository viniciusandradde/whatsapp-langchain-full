"""Testes dos helpers de AgenteIAConfig (M5.b)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.agente_ia import (
    delete_agente_ia_config,
    get_agente_ia_config,
    resolve_runtime_config,
    upsert_agente_ia_config,
)
from whatsapp_langchain.shared.models import AgenteIAConfigInput


def _row(
    *,
    empresa_id=1,
    agent_id="vsa_tech",
    prompt="custom prompt",
    temperatura=0.7,
    ativo=True,
    user_id=None,
):
    now = datetime.now(UTC)
    return (empresa_id, agent_id, prompt, temperatura, ativo, user_id, now, now)


def _mock_pool(*results, rowcount: int = 1) -> tuple[MagicMock, AsyncMock]:
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.mark.asyncio
async def test_get_returns_none_when_missing():
    pool, _ = _mock_pool(None)
    assert await get_agente_ia_config(pool, 1, "vsa_tech") is None


@pytest.mark.asyncio
async def test_get_returns_config_when_present():
    pool, _ = _mock_pool(_row(prompt="X"))
    out = await get_agente_ia_config(pool, 1, "vsa_tech")
    assert out is not None
    assert out.system_prompt_override == "X"
    assert out.temperatura == 0.7


@pytest.mark.asyncio
async def test_upsert_normalizes_empty_prompt_to_none():
    pool, conn = _mock_pool(_row(prompt=None))
    data = AgenteIAConfigInput(system_prompt_override="   ", temperatura=0.0)
    out = await upsert_agente_ia_config(pool, 1, "vsa_tech", data, user_id="u")
    assert out.system_prompt_override is None
    args = conn.execute.await_args.args[1]
    # prompt arg deve ter virado None (índice 2: empresa, agent, prompt, ...)
    assert args[2] is None


@pytest.mark.asyncio
async def test_upsert_persists_prompt_and_temperatura():
    pool, conn = _mock_pool(_row(prompt="Você é um assistente"))
    data = AgenteIAConfigInput(
        system_prompt_override="Você é um assistente",
        temperatura=0.3,
        ativo=True,
    )
    out = await upsert_agente_ia_config(pool, 1, "vsa_tech", data)
    assert out.system_prompt_override == "Você é um assistente"
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO agente_ia_config" in sql
    assert "ON CONFLICT (empresa_id, agent_id)" in sql


@pytest.mark.asyncio
async def test_delete_returns_true_when_deleted():
    pool, _ = _mock_pool(rowcount=1)
    assert await delete_agente_ia_config(pool, 1, "vsa_tech") is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_missing():
    pool, _ = _mock_pool(rowcount=0)
    assert await delete_agente_ia_config(pool, 1, "vsa_tech") is False


@pytest.mark.asyncio
async def test_resolve_returns_none_tuple_when_missing():
    pool, _ = _mock_pool(None)
    prompt, temp = await resolve_runtime_config(pool, 1, "vsa_tech")
    assert prompt is None
    assert temp is None


@pytest.mark.asyncio
async def test_resolve_returns_none_tuple_when_inactive():
    pool, _ = _mock_pool(_row(ativo=False))
    prompt, temp = await resolve_runtime_config(pool, 1, "vsa_tech")
    assert prompt is None
    assert temp is None


@pytest.mark.asyncio
async def test_resolve_returns_values_when_active():
    pool, _ = _mock_pool(_row(prompt="P", temperatura=0.5, ativo=True))
    prompt, temp = await resolve_runtime_config(pool, 1, "vsa_tech")
    assert prompt == "P"
    assert temp == 0.5
