"""Testes dos helpers de Cliente (M3 CRM Light)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.cliente import (
    add_anotacao,
    add_tag,
    get_cliente_by_id,
    get_cliente_by_telefone,
    list_clientes,
    remove_tag,
    update_cliente_partial,
    upsert_cliente,
)


def _row(
    *,
    id_=1,
    empresa_id=1,
    telefone="+5511999999999",
    nome="Fulano",
    email=None,
    doc=None,
    status="active",
    config=None,
):
    now = datetime.now(UTC)
    return (
        id_,
        empresa_id,
        telefone,
        nome,
        email,
        doc,
        status,
        config or {},
        now,
        now,
    )


def _anotacao_row(*, id_=1, cliente_id=1, user_id="user-1", conteudo="nota"):
    return (id_, cliente_id, user_id, conteudo, datetime.now(UTC))


def _mock_pool(*results) -> tuple[MagicMock, AsyncMock]:
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    fetchall_seq = [r for r in results if isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.fetchall = AsyncMock(side_effect=fetchall_seq if fetchall_seq else [[]])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.mark.asyncio
async def test_upsert_cliente_inserts_new_row():
    pool, conn = _mock_pool(_row(id_=10, telefone="+5511AAA", nome="Novo"))
    out = await upsert_cliente(pool, 1, "+5511AAA", nome="Novo")
    assert out.id == 10
    assert out.nome == "Novo"
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO cliente" in sql
    assert "ON CONFLICT (empresa_id, telefone)" in sql
    assert "COALESCE" in sql  # preserva nome existente


@pytest.mark.asyncio
async def test_upsert_cliente_passes_empresa_and_phone():
    pool, conn = _mock_pool(_row(id_=10, empresa_id=7, telefone="+551122"))
    await upsert_cliente(pool, 7, "+551122")
    args = conn.execute.await_args.args[1]
    assert args[0] == 7
    assert args[1] == "+551122"


@pytest.mark.asyncio
async def test_get_cliente_by_telefone_returns_none_when_missing():
    pool, _ = _mock_pool(None)
    out = await get_cliente_by_telefone(pool, 1, "+551100")
    assert out is None


@pytest.mark.asyncio
async def test_get_cliente_by_id_loads_tags():
    pool, _ = _mock_pool(_row(id_=42), [("vip",), ("retentor",)])
    out = await get_cliente_by_id(pool, 42)
    assert out is not None
    assert out.id == 42
    assert out.tags == ["vip", "retentor"]


@pytest.mark.asyncio
async def test_list_clientes_filters_by_empresa_only():
    rows = [_row(id_=1, empresa_id=2), _row(id_=2, empresa_id=2)]
    pool, conn = _mock_pool(rows)
    out = await list_clientes(pool, 2)
    assert len(out) == 2
    args = conn.execute.await_args.args[1]
    assert args[0] == 2
    # sem search → 3 params (empresa_id, limit, offset)
    assert len(args) == 3


@pytest.mark.asyncio
async def test_list_clientes_with_search_appends_ilike_params():
    pool, conn = _mock_pool([_row(id_=1, nome="Maria")])
    await list_clientes(pool, 1, search="Mar")
    sql = conn.execute.await_args.args[0]
    assert "ILIKE" in sql
    args = conn.execute.await_args.args[1]
    # empresa_id, %Mar%, %Mar%, limit, offset
    assert args[1] == "%Mar%"
    assert args[2] == "%Mar%"


@pytest.mark.asyncio
async def test_add_anotacao_persists_and_returns():
    pool, conn = _mock_pool(_anotacao_row(id_=99, conteudo="cliente VIP"))
    out = await add_anotacao(pool, 1, "user-x", "cliente VIP")
    assert out.id == 99
    assert out.conteudo == "cliente VIP"
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO cliente_anotacao" in sql


@pytest.mark.asyncio
async def test_add_tag_uses_on_conflict_do_nothing():
    pool, conn = _mock_pool()
    await add_tag(pool, 5, "vip")
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO cliente_tag" in sql
    assert "ON CONFLICT (cliente_id, tag) DO NOTHING" in sql


@pytest.mark.asyncio
async def test_remove_tag_runs_delete():
    pool, conn = _mock_pool()
    await remove_tag(pool, 5, "vip")
    sql = conn.execute.await_args.args[0]
    assert "DELETE FROM cliente_tag" in sql
    assert conn.execute.await_args.args[1] == (5, "vip")


# --- update_cliente_partial (M5.b.1) ---


@pytest.mark.asyncio
async def test_update_partial_only_touches_provided_fields():
    """Sem nada pra mudar → só lê o cliente atual; com nome → SET nome=..."""
    # 1ª call (UPDATE) + 2ª call (SELECT cliente) + 3ª call (SELECT tags)
    pool, conn = _mock_pool(
        _row(id_=5, nome="Novo Nome"),
        _row(id_=5, nome="Novo Nome"),
        [("vip",)],
    )
    out = await update_cliente_partial(pool, 1, 5, nome="Novo Nome")
    assert out is not None
    assert out.nome == "Novo Nome"
    # Primeira chamada foi UPDATE com nome no SET
    update_call = conn.execute.await_args_list[0]
    sql = update_call.args[0]
    assert "UPDATE cliente" in sql
    assert "nome = %s" in sql
    assert "email = %s" not in sql
    assert "doc = %s" not in sql


@pytest.mark.asyncio
async def test_update_partial_returns_none_when_missing():
    pool, _ = _mock_pool(None)  # UPDATE não retornou row
    out = await update_cliente_partial(pool, 1, 999, nome="X")
    assert out is None


@pytest.mark.asyncio
async def test_update_partial_filters_by_empresa():
    """Anti-cross-tenant: empresa_id no WHERE."""
    pool, conn = _mock_pool(
        _row(id_=5),
        _row(id_=5),
        [],
    )
    await update_cliente_partial(pool, 42, 5, nome="X")
    sql = conn.execute.await_args_list[0].args[0]
    params = conn.execute.await_args_list[0].args[1]
    assert "empresa_id = %s" in sql
    assert params[-1] == 42  # último param é empresa_id


@pytest.mark.asyncio
async def test_update_partial_no_fields_returns_current():
    """Sem campos pra atualizar → retorna cliente sem disparar UPDATE."""
    pool, conn = _mock_pool(_row(id_=5), [("vip",)])
    out = await update_cliente_partial(pool, 1, 5)
    assert out is not None
    assert out.id == 5
    # Nenhum UPDATE foi feito (só SELECTs)
    sqls = [c.args[0] for c in conn.execute.await_args_list]
    assert not any("UPDATE cliente" in s for s in sqls)
