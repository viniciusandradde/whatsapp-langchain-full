"""Testes dos helpers de Atendimento (M3 CRM Light)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.atendimento import (
    claim_atendimento,
    close_atendimento,
    get_atendimento_by_id,
    list_atendimento_mensagens,
    list_atendimentos,
    open_or_attach_atendimento,
    transfer_atendimento,
)


def _row(
    *,
    id_=1,
    empresa_id=1,
    cliente_id=1,
    conexao_id=1,
    agente_atual="vsa_tech",
    status="aguardando",
    assigned_to_user_id=None,
    closed_at=None,
):
    now = datetime.now(UTC)
    return (
        id_,
        empresa_id,
        cliente_id,
        conexao_id,
        agente_atual,
        status,
        assigned_to_user_id,
        now,
        closed_at,
        now,
        now,
    )


def _row_with_cliente(*, nome="Fulano", telefone="+5511999", **kwargs):
    return _row(**kwargs) + (nome, telefone)


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
async def test_open_or_attach_inserts_when_no_open_row():
    # SELECT FOR UPDATE → None, INSERT → row
    pool, conn = _mock_pool(None, _row(id_=10, status="aguardando"))
    out, was_created = await open_or_attach_atendimento(
        pool, 1, 5, 7, agente="vsa_tech"
    )
    assert was_created is True
    assert out.id == 10
    assert out.status == "aguardando"
    # confirma que o segundo execute foi INSERT
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert any("SELECT" in s and "FOR UPDATE" in s for s in sql_calls)
    assert any("INSERT INTO atendimento" in s for s in sql_calls)


@pytest.mark.asyncio
async def test_open_or_attach_updates_when_already_open():
    # SELECT retorna row existente, UPDATE retorna row atualizado
    existing = _row(id_=42, status="em_andamento")
    pool, conn = _mock_pool(existing, _row(id_=42, status="em_andamento"))
    out, was_created = await open_or_attach_atendimento(pool, 1, 5, 7)
    assert was_created is False
    assert out.id == 42
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert any(
        "UPDATE atendimento" in s and "last_message_at = NOW()" in s for s in sql_calls
    )


@pytest.mark.asyncio
async def test_list_atendimentos_meus_requires_user_id():
    pool, _ = _mock_pool([])
    out = await list_atendimentos(pool, 1, tipo="meus", current_user_id=None)
    assert out == []


@pytest.mark.asyncio
async def test_list_atendimentos_aguardando_filters_status():
    rows = [_row_with_cliente(id_=1, status="aguardando")]
    pool, conn = _mock_pool(rows)
    out = await list_atendimentos(pool, 1, tipo="aguardando")
    assert len(out) == 1
    assert out[0].cliente_nome == "Fulano"
    sql = conn.execute.await_args.args[0]
    assert "a.status = 'aguardando'" in sql


@pytest.mark.asyncio
async def test_list_atendimentos_grupos_returns_empty():
    pool, _ = _mock_pool()
    out = await list_atendimentos(pool, 1, tipo="grupos")
    assert out == []


@pytest.mark.asyncio
async def test_list_atendimentos_outros_excludes_current_user():
    rows = [
        _row_with_cliente(id_=3, status="em_andamento", assigned_to_user_id="other")
    ]
    pool, conn = _mock_pool(rows)
    out = await list_atendimentos(pool, 1, tipo="outros", current_user_id="me")
    assert len(out) == 1
    sql = conn.execute.await_args.args[0]
    assert "IS NULL OR a.assigned_to_user_id <> %s" in sql
    args = conn.execute.await_args.args[1]
    assert "me" in args


@pytest.mark.asyncio
async def test_claim_atendimento_sets_em_andamento():
    pool, conn = _mock_pool(
        _row(id_=8, status="em_andamento", assigned_to_user_id="user-x")
    )
    out = await claim_atendimento(pool, 8, "user-x")
    assert out is not None
    assert out.status == "em_andamento"
    assert out.assigned_to_user_id == "user-x"
    sql = conn.execute.await_args.args[0]
    assert "UPDATE atendimento" in sql
    assert "status = 'em_andamento'" in sql


@pytest.mark.asyncio
async def test_claim_returns_none_when_already_closed():
    pool, _ = _mock_pool(None)  # WHERE status IN aberto não bate
    out = await claim_atendimento(pool, 99, "user-x")
    assert out is None


@pytest.mark.asyncio
async def test_close_atendimento_sets_status_and_closed_at():
    pool, conn = _mock_pool(_row(id_=8, status="resolvido"))
    out = await close_atendimento(pool, 8, status="resolvido")
    assert out is not None
    assert out.status == "resolvido"
    sql = conn.execute.await_args.args[0]
    assert "closed_at = NOW()" in sql
    assert conn.execute.await_args.args[1] == ("resolvido", 8)


@pytest.mark.asyncio
async def test_transfer_atendimento_changes_user():
    pool, conn = _mock_pool(
        _row(id_=8, status="em_andamento", assigned_to_user_id="bob")
    )
    out = await transfer_atendimento(pool, 8, "bob")
    assert out is not None
    assert out.assigned_to_user_id == "bob"
    sql = conn.execute.await_args.args[0]
    assert "assigned_to_user_id = %s" in sql


@pytest.mark.asyncio
async def test_get_atendimento_by_id_joins_cliente():
    pool, _ = _mock_pool(_row_with_cliente(id_=42, nome="Maria", telefone="+551133"))
    out = await get_atendimento_by_id(pool, 42)
    assert out is not None
    assert out.cliente_nome == "Maria"
    assert out.cliente_telefone == "+551133"


@pytest.mark.asyncio
async def test_list_atendimento_mensagens_filters_by_empresa_and_atendimento():
    now = datetime.now(UTC)
    rows = [
        (
            1,
            "vsa_tech",
            "oi",
            None,
            None,
            None,
            None,
            "olá! como posso ajudar?",
            "done",
            now,
            now,
            None,
            None,
        )
    ]
    pool, conn = _mock_pool(rows)
    out = await list_atendimento_mensagens(pool, 42, 7)
    assert len(out) == 1
    assert out[0]["incoming_message"] == "oi"
    assert out[0]["response"] == "olá! como posso ajudar?"
    sql = conn.execute.await_args.args[0]
    assert "WHERE empresa_id = %s" in sql
    assert "AND atendimento_id = %s" in sql
    args = conn.execute.await_args.args[1]
    assert args[0] == 7
    assert args[1] == 42
