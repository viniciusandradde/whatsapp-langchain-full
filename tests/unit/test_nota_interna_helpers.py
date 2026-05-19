"""Testes dos helpers de nota interna + read receipts (Sprint 1.3)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.atendimento_visualizacao import (
    count_unread_para_user,
    get_ultima_visualizacao,
    marcar_lido,
)
from whatsapp_langchain.shared.nota_interna import create_nota_interna


def _mock_pool(*results) -> tuple[MagicMock, AsyncMock]:
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    fetchall_seq = [r for r in results if isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.fetchall = AsyncMock(side_effect=fetchall_seq if fetchall_seq else [[]])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# ---------- nota_interna ----------


@pytest.mark.asyncio
async def test_create_nota_interna_resolve_metadados_e_insere_done():
    """Primeiro SELECT busca (conexao_id, agente, telefone), depois INSERT, depois UPDATE."""
    now = datetime.now(UTC)
    meta = (5, "vsa_tech", "+5511999")
    inserted = (100, now)
    pool, conn = _mock_pool(meta, inserted)
    out = await create_nota_interna(
        pool,
        atendimento_id=10,
        empresa_id=1,
        user_id="user-x",
        texto="Cliente confirmou agendamento por telefone",
    )
    assert out["id"] == 100
    assert out["interna"] is True
    assert out["criado_por_user_id"] == "user-x"
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    # 1) SELECT metadados, 2) INSERT, 3) UPDATE atendimento.last_message_at
    assert any("SELECT" in s and "FROM atendimento" in s for s in sql_calls)
    insert_sql = next(s for s in sql_calls if "INSERT INTO message_queue" in s)
    # status='done' garante que worker NÃO pega como queued
    assert "'done'" in insert_sql
    assert "TRUE" in insert_sql  # interna
    assert any(
        "UPDATE atendimento" in s and "last_message_at = NOW()" in s
        for s in sql_calls
    )


@pytest.mark.asyncio
async def test_create_nota_interna_erro_se_atendimento_de_outra_empresa():
    pool, _ = _mock_pool(None)  # SELECT metadados → None
    with pytest.raises(ValueError) as excinfo:
        await create_nota_interna(
            pool,
            atendimento_id=999,
            empresa_id=1,
            user_id="u",
            texto="X",
        )
    assert "não pertence" in str(excinfo.value)


# ---------- atendimento_visualizacao ----------


@pytest.mark.asyncio
async def test_marcar_lido_faz_upsert():
    pool, conn = _mock_pool()
    await marcar_lido(pool, atendimento_id=10, user_id="u")
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO atendimento_visualizacao" in sql
    assert "ON CONFLICT" in sql
    assert "ultima_visualizacao_at = NOW()" in sql


@pytest.mark.asyncio
async def test_get_ultima_visualizacao_retorna_iso():
    now = datetime.now(UTC)
    pool, _ = _mock_pool((now,))
    out = await get_ultima_visualizacao(pool, atendimento_id=10, user_id="u")
    assert out is not None
    assert "T" in out  # ISO format


@pytest.mark.asyncio
async def test_get_ultima_visualizacao_none_se_nunca_abriu():
    pool, _ = _mock_pool(None)
    out = await get_ultima_visualizacao(pool, atendimento_id=10, user_id="u")
    assert out is None


@pytest.mark.asyncio
async def test_count_unread_para_user():
    pool, conn = _mock_pool([(10, 3), (20, 1)])
    out = await count_unread_para_user(
        pool, atendimento_ids=[10, 20, 30], user_id="u"
    )
    assert out == {10: 3, 20: 1}  # 30 sem msg → não aparece
    sql = conn.execute.await_args.args[0]
    assert "LEFT JOIN atendimento_visualizacao" in sql
    assert "v.ultima_visualizacao_at IS NULL" in sql
    assert "m.created_at > v.ultima_visualizacao_at" in sql


@pytest.mark.asyncio
async def test_count_unread_lista_vazia_skip_query():
    pool, conn = _mock_pool()
    out = await count_unread_para_user(pool, atendimento_ids=[], user_id="u")
    assert out == {}
    conn.execute.assert_not_awaited()
