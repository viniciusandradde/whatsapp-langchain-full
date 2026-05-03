"""Tests do helper de Memória estruturada por cliente (M5.b.2)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from psycopg import errors as pg_errors

from whatsapp_langchain.shared import cliente_memoria as cm
from whatsapp_langchain.shared.models import ClienteMemoriaInput


def _row(
    *,
    id_=1,
    empresa_id=1,
    cliente_id=10,
    categoria="fato",
    conteudo="Cliente comprou produto X",
    source="agent_explicit",
    user_id=None,
    score: float | None = None,
):
    now = datetime.now(UTC)
    base = (
        id_,
        empresa_id,
        cliente_id,
        categoria,
        conteudo,
        source,
        user_id,
        now,
        now,
    )
    return base if score is None else (*base, score)


def _mock_pool(*results, rowcount: int = 1, fetchall=None):
    cur = AsyncMock()
    if fetchall is not None:
        cur.fetchall = AsyncMock(return_value=fetchall)
    else:
        fetchone_seq = list(results) if results else [None]
        cur.fetchone = AsyncMock(side_effect=fetchone_seq)
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# --- list/get ---


@pytest.mark.asyncio
async def test_list_memorias_filters_by_empresa_e_cliente():
    pool, conn = _mock_pool(fetchall=[_row(id_=1), _row(id_=2)])
    out = await cm.list_memorias(pool, 1, 10)
    assert [m.id for m in out] == [1, 2]
    sql = conn.execute.await_args.args[0]
    assert "empresa_id = %s AND cliente_id = %s" in sql


@pytest.mark.asyncio
async def test_list_memorias_categoria_filter_in_sql():
    pool, conn = _mock_pool(fetchall=[])
    await cm.list_memorias(pool, 1, 10, categoria="preferencia")
    sql = conn.execute.await_args.args[0]
    assert "categoria = %s" in sql


@pytest.mark.asyncio
async def test_get_memoria_filters_anti_cross_tenant():
    pool, conn = _mock_pool(None)
    await cm.get_memoria(pool, 7, 10, 99)
    sql, params = conn.execute.await_args.args
    assert "empresa_id = %s" in sql
    assert "cliente_id = %s" in sql
    assert params == (99, 7, 10)


# --- save: dedup semântico ---


@pytest.mark.asyncio
async def test_save_dedup_when_existing_above_threshold():
    """Memória semelhante já existe → retorna existente, sem INSERT."""
    existing_with_score = _row(id_=42, score=0.95)
    pool, conn = _mock_pool(existing_with_score)
    with patch.object(cm, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out, created = await cm.save_memoria(
            pool,
            1,
            10,
            ClienteMemoriaInput(categoria="fato", conteudo="abc"),
        )
    assert created is False
    assert out.id == 42
    # Apenas 1 execute (SELECT pra dedup); nenhum INSERT
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert not any("INSERT INTO cliente_memoria" in s for s in sql_calls)


@pytest.mark.asyncio
async def test_save_creates_when_no_match():
    """Sem similar → INSERT + retorna nova row, was_created=True."""
    # 1ª fetchone: SELECT dedup retorna None
    # 2ª fetchone: INSERT RETURNING retorna row
    pool, _ = _mock_pool(None, _row(id_=99))
    with patch.object(cm, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out, created = await cm.save_memoria(
            pool,
            1,
            10,
            ClienteMemoriaInput(categoria="fato", conteudo="novo"),
        )
    assert created is True
    assert out.id == 99


@pytest.mark.asyncio
async def test_save_creates_when_existing_below_threshold():
    """Score baixo da row existente → não considera dedup, faz INSERT."""
    pool, _ = _mock_pool(_row(id_=42, score=0.5), _row(id_=99))
    with patch.object(cm, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out, created = await cm.save_memoria(
            pool,
            1,
            10,
            ClienteMemoriaInput(categoria="fato", conteudo="abc"),
        )
    assert created is True
    assert out.id == 99


@pytest.mark.asyncio
async def test_save_handles_unique_violation_race():
    """Race: alguém inseriu mesma row entre dedup e INSERT.

    Esperado: catch UniqueViolation + retorna existente, was_created=False.
    """
    cur = AsyncMock()
    # 1) dedup retorna None  2) INSERT raises  3) SELECT por md5 retorna row
    cur.fetchone = AsyncMock(side_effect=[None, _row(id_=1)])
    cur.rowcount = 1
    cur.execute_call_count = 0

    async def fake_execute(sql, params=None):
        cur.execute_call_count += 1
        if cur.execute_call_count == 2:
            # Simula UniqueViolation no INSERT
            raise pg_errors.UniqueViolation("dup")
        return cur

    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=fake_execute)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch.object(cm, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out, created = await cm.save_memoria(
            pool,
            1,
            10,
            ClienteMemoriaInput(categoria="fato", conteudo="abc"),
        )
    assert created is False
    assert out.id == 1


# --- delete ---


@pytest.mark.asyncio
async def test_delete_returns_true_when_deleted():
    pool, _ = _mock_pool(rowcount=1)
    assert await cm.delete_memoria(pool, 1, 10, 1) is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_missing():
    pool, _ = _mock_pool(rowcount=0)
    assert await cm.delete_memoria(pool, 1, 10, 99) is False


@pytest.mark.asyncio
async def test_delete_filters_anti_cross_tenant():
    pool, conn = _mock_pool(rowcount=1)
    await cm.delete_memoria(pool, 7, 10, 5)
    sql, params = conn.execute.await_args.args
    assert "empresa_id = %s" in sql
    assert "cliente_id = %s" in sql
    assert params == (5, 7, 10)


# --- search ---


@pytest.mark.asyncio
async def test_search_filters_min_score():
    rows = [
        _row(id_=1, score=0.9),
        _row(id_=2, score=0.5),
        _row(id_=3, score=0.1),  # cai
    ]
    pool, _ = _mock_pool(fetchall=rows)
    with patch.object(cm, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out = await cm.search_relevant(pool, 1, 10, "x")
    assert [m.id for m, _ in out] == [1, 2]


@pytest.mark.asyncio
async def test_search_categoria_filter():
    pool, conn = _mock_pool(fetchall=[])
    with patch.object(cm, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        await cm.search_relevant(pool, 1, 10, "x", categoria="preferencia")
    sql = conn.execute.await_args.args[0]
    assert "categoria = %s" in sql


@pytest.mark.asyncio
async def test_search_returns_empty_when_no_results():
    pool, _ = _mock_pool(fetchall=[])
    with patch.object(cm, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out = await cm.search_relevant(pool, 1, 10, "x")
    assert out == []
