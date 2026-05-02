"""Testes dos helpers de Hook (M4.d)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.hook import (
    create_hook,
    delete_hook,
    get_hook_by_id,
    insert_log,
    list_hooks,
    list_hooks_for_dispatch,
    list_logs,
    update_hook,
)
from whatsapp_langchain.shared.models import HookInput


def _row(
    *,
    id_=1,
    empresa_id=1,
    nome="hook1",
    evento="mensagem.recebida",
    url="https://example.com/h",
    secret=None,
    ativo=True,
    user_id=None,
):
    now = datetime.now(UTC)
    return (
        id_,
        empresa_id,
        nome,
        evento,
        url,
        secret,
        ativo,
        user_id,
        now,
        now,
    )


def _log_row(*, id_=1, hook_id=1, evento="x", status=200, error=None, duration=12):
    return (id_, hook_id, evento, status, error, duration, datetime.now(UTC))


def _mock_pool(*results, rowcount: int = 1) -> tuple[MagicMock, AsyncMock]:
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    fetchall_seq = [r for r in results if isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.fetchall = AsyncMock(side_effect=fetchall_seq if fetchall_seq else [[]])
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.mark.asyncio
async def test_list_hooks_filters_by_empresa():
    pool, conn = _mock_pool([_row(id_=1, empresa_id=2)])
    out = await list_hooks(pool, 2)
    assert len(out) == 1
    args = conn.execute.await_args.args[1]
    assert args == (2,)


@pytest.mark.asyncio
async def test_list_hooks_with_evento_filter():
    pool, conn = _mock_pool([])
    await list_hooks(pool, 1, evento="atendimento.aberto")
    sql = conn.execute.await_args.args[0]
    assert "AND evento = %s" in sql
    args = conn.execute.await_args.args[1]
    assert args == (1, "atendimento.aberto")


@pytest.mark.asyncio
async def test_list_hooks_for_dispatch_only_active():
    pool, conn = _mock_pool([_row(id_=1, ativo=True)])
    out = await list_hooks_for_dispatch(pool, 1, "mensagem.recebida")
    assert len(out) == 1
    sql = conn.execute.await_args.args[0]
    assert "ativo = TRUE" in sql


@pytest.mark.asyncio
async def test_get_hook_by_id_returns_none_when_missing():
    pool, _ = _mock_pool(None)
    assert await get_hook_by_id(pool, 99) is None


@pytest.mark.asyncio
async def test_create_hook_persists_and_returns():
    pool, conn = _mock_pool(_row(id_=10, nome="meu hook"))
    data = HookInput(
        nome="meu hook",
        evento="mensagem.recebida",
        url="https://example.com/h",
    )
    out = await create_hook(pool, 1, data, user_id="u")
    assert out.id == 10
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO hook" in sql


@pytest.mark.asyncio
async def test_update_hook_returns_updated_row():
    pool, _ = _mock_pool(_row(id_=5, ativo=False))
    data = HookInput(
        nome="x",
        evento="atendimento.fechado",
        url="https://example.com/h",
        ativo=False,
    )
    out = await update_hook(pool, 5, data)
    assert out is not None
    assert out.ativo is False


@pytest.mark.asyncio
async def test_update_hook_returns_none_when_missing():
    pool, _ = _mock_pool(None)
    data = HookInput(nome="x", evento="mensagem.recebida", url="https://x.io")
    out = await update_hook(pool, 999, data)
    assert out is None


@pytest.mark.asyncio
async def test_delete_hook_returns_true_when_deleted():
    pool, _ = _mock_pool(rowcount=1)
    assert await delete_hook(pool, 1) is True


@pytest.mark.asyncio
async def test_delete_hook_returns_false_when_missing():
    pool, _ = _mock_pool(rowcount=0)
    assert await delete_hook(pool, 999) is False


@pytest.mark.asyncio
async def test_list_logs_orders_desc():
    rows = [_log_row(id_=2), _log_row(id_=1)]
    pool, conn = _mock_pool(rows)
    out = await list_logs(pool, 1)
    assert len(out) == 2
    sql = conn.execute.await_args.args[0]
    assert "ORDER BY created_at DESC" in sql


@pytest.mark.asyncio
async def test_insert_log_serializes_payload():
    pool, conn = _mock_pool()
    await insert_log(
        pool,
        7,
        "mensagem.recebida",
        {"x": 1},
        status_code=200,
        response_body="ok",
        error=None,
        duration_ms=10,
    )
    args = conn.execute.await_args.args[1]
    assert args[0] == 7
    assert args[1] == "mensagem.recebida"
    assert '"x": 1' in args[2] or '{"x":1}' in args[2]
    assert args[3] == 200
