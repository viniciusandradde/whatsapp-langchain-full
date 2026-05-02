"""Testes dos helpers de ModeloMensagem (M4.b)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from psycopg.errors import UniqueViolation

from whatsapp_langchain.shared.modelo_mensagem import (
    DuplicateTituloError,
    create_modelo,
    delete_modelo,
    get_modelo_by_id,
    list_modelos,
    update_modelo,
)
from whatsapp_langchain.shared.models import ModeloMensagemInput


def _row(
    *,
    id_=1,
    empresa_id=1,
    titulo="Saudação",
    conteudo="Olá, tudo bem?",
    atalho=None,
    user_id=None,
):
    now = datetime.now(UTC)
    return (id_, empresa_id, titulo, conteudo, atalho, user_id, now, now)


def _mock_pool(
    *results, rowcount: int = 1, raise_on_execute: Exception | None = None
) -> tuple[MagicMock, AsyncMock]:
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    fetchall_seq = [r for r in results if isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.fetchall = AsyncMock(side_effect=fetchall_seq if fetchall_seq else [[]])
    cur.rowcount = rowcount
    conn = MagicMock()
    if raise_on_execute:
        conn.execute = AsyncMock(side_effect=raise_on_execute)
    else:
        conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.mark.asyncio
async def test_list_modelos_filters_by_empresa():
    pool, conn = _mock_pool([_row(id_=1, empresa_id=2), _row(id_=2, empresa_id=2)])
    out = await list_modelos(pool, 2)
    assert len(out) == 2
    args = conn.execute.await_args.args[1]
    assert args[0] == 2
    assert len(args) == 2  # empresa_id, limit


@pytest.mark.asyncio
async def test_list_modelos_with_search_appends_three_likes():
    pool, conn = _mock_pool([])
    await list_modelos(pool, 1, search="ola")
    sql = conn.execute.await_args.args[0]
    assert "ILIKE" in sql
    args = conn.execute.await_args.args[1]
    # empresa_id, %ola%, %ola%, %ola%, limit
    assert args[1] == "%ola%"
    assert args[2] == "%ola%"
    assert args[3] == "%ola%"


@pytest.mark.asyncio
async def test_get_modelo_by_id_returns_none_when_missing():
    pool, _ = _mock_pool(None)
    out = await get_modelo_by_id(pool, 99)
    assert out is None


@pytest.mark.asyncio
async def test_create_modelo_persists():
    pool, conn = _mock_pool(_row(id_=10, titulo="Saudação"))
    data = ModeloMensagemInput(titulo="Saudação", conteudo="Olá!")
    out = await create_modelo(pool, 1, data, user_id="user-x")
    assert out.id == 10
    assert out.titulo == "Saudação"
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO modelo_mensagem" in sql


@pytest.mark.asyncio
async def test_create_modelo_raises_duplicate_on_unique_violation():
    pool, _ = _mock_pool(raise_on_execute=UniqueViolation("dup"))
    data = ModeloMensagemInput(titulo="X", conteudo="y")
    with pytest.raises(DuplicateTituloError):
        await create_modelo(pool, 1, data)


@pytest.mark.asyncio
async def test_update_modelo_returns_updated_row():
    pool, conn = _mock_pool(_row(id_=5, titulo="Novo"))
    data = ModeloMensagemInput(titulo="Novo", conteudo="texto novo")
    out = await update_modelo(pool, 5, data)
    assert out is not None
    assert out.titulo == "Novo"
    sql = conn.execute.await_args.args[0]
    assert "UPDATE modelo_mensagem" in sql
    assert "updated_at = NOW()" in sql


@pytest.mark.asyncio
async def test_update_modelo_returns_none_when_missing():
    pool, _ = _mock_pool(None)
    data = ModeloMensagemInput(titulo="X", conteudo="y")
    out = await update_modelo(pool, 999, data)
    assert out is None


@pytest.mark.asyncio
async def test_delete_modelo_returns_true_when_deleted():
    pool, _ = _mock_pool(rowcount=1)
    assert await delete_modelo(pool, 5) is True


@pytest.mark.asyncio
async def test_delete_modelo_returns_false_when_not_found():
    pool, _ = _mock_pool(rowcount=0)
    assert await delete_modelo(pool, 999) is False
