"""Testes dos helpers de aba (Sprint Atendimento UX, mig 085)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.aba import (
    cliente_ids_da_aba,
    count_atendimentos_por_aba,
    create_aba,
    delete_aba,
    get_aba,
    list_abas,
    reorder_abas,
    update_aba,
)


def _aba_row(
    *,
    id_=1,
    nome="Minha aba",
    cor=None,
    ordem=0,
    ativo=True,
    filtro=None,
):
    """8 cols: id, nome, cor, ordem, ativo, created_at, updated_at, filtro.

    `filtro` entrou por último e é o critério da aba (`{"cliente_tags": [...]}`).
    """
    now = datetime.now(UTC)
    return (id_, nome, cor, ordem, ativo, now, now, filtro)


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


# --- list_abas ---


@pytest.mark.asyncio
async def test_list_abas_filters_by_user_and_active():
    rows = [_aba_row(id_=1, nome="VIPs"), _aba_row(id_=2, nome="Hoje")]
    pool, conn = _mock_pool(rows)
    out = await list_abas(pool, user_id="user-x", empresa_id=1)
    assert len(out) == 2
    assert out[0]["descricao"] == "VIPs"  # API expõe como `descricao`
    sql = conn.execute.await_args.args[0]
    assert "user_id = %s" in sql
    assert "ativo = TRUE" in sql
    args = conn.execute.await_args.args[1]
    assert "user-x" in args
    assert 1 in args


@pytest.mark.asyncio
async def test_list_abas_empty():
    pool, _ = _mock_pool([])
    out = await list_abas(pool, user_id="u", empresa_id=1)
    assert out == []


# --- create_aba ---


@pytest.mark.asyncio
async def test_create_aba_inserts_and_returns_row():
    pool, conn = _mock_pool(_aba_row(id_=10, nome="Nova", cor="#ff0000"))
    out = await create_aba(
        pool,
        user_id="user-x",
        empresa_id=1,
        descricao="Nova",
        cor="#ff0000",
    )
    assert out["id"] == 10
    assert out["descricao"] == "Nova"
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO aba" in sql
    assert "COALESCE" in sql  # ordem auto-calculada
    conn.commit.assert_awaited()


# --- update_aba ---


@pytest.mark.asyncio
async def test_update_aba_partial_descricao_only():
    pool, conn = _mock_pool(_aba_row(id_=5, nome="Renomeada"))
    out = await update_aba(pool, aba_id=5, user_id="u", descricao="Renomeada")
    assert out is not None
    assert out["descricao"] == "Renomeada"
    sql = conn.execute.await_args.args[0]
    # API expõe `descricao`, banco usa coluna `nome`
    assert "UPDATE aba SET nome = %s" in sql
    assert "updated_at = NOW()" in sql


@pytest.mark.asyncio
async def test_update_aba_returns_none_when_not_owned():
    # fetchone retorna None — query não bateu por outro user
    pool, _ = _mock_pool(None)
    out = await update_aba(pool, aba_id=999, user_id="u", cor="#000")
    assert out is None


@pytest.mark.asyncio
async def test_update_aba_no_fields_returns_current():
    # Sem mudanças → get_aba é chamado
    pool, _ = _mock_pool(_aba_row(id_=1, nome="Já existente"))
    out = await update_aba(pool, aba_id=1, user_id="u")
    assert out is not None
    assert out["descricao"] == "Já existente"


# --- delete_aba (soft) ---


@pytest.mark.asyncio
async def test_delete_aba_nao_toca_em_atendimento():
    """Apagar a aba não mexe em conversa nenhuma (mig 150).

    Antes o delete precisava zerar `atendimento.aba_id` das conversas pinadas.
    Como a aba virou filtro salvo, não há vínculo a desfazer — e um UPDATE em
    `atendimento` aqui seria escrita a mais numa tabela quente, por nada.
    """
    pool, conn = _mock_pool((1,))
    ok = await delete_aba(pool, aba_id=1, user_id="u")
    assert ok is True
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert any("UPDATE aba SET ativo = FALSE" in s for s in sql_calls)
    assert not any("atendimento" in s for s in sql_calls)


@pytest.mark.asyncio
async def test_delete_aba_returns_false_when_not_owned():
    pool, _ = _mock_pool(None)
    ok = await delete_aba(pool, aba_id=999, user_id="u")
    assert ok is False


# --- reorder ---


@pytest.mark.asyncio
async def test_reorder_abas_updates_count():
    # 3 IDs, todos pertencem ao user (fetchone retorna row pra cada)
    pool, conn = _mock_pool((1,), (2,), (3,))
    count = await reorder_abas(pool, user_id="u", ordered_ids=[10, 20, 30])
    assert count == 3
    # 3 UPDATEs
    assert conn.execute.await_count == 3
    # Ordem 0, 1, 2 nos args
    ordens = [c.args[1][0] for c in conn.execute.await_args_list]
    assert ordens == [0, 1, 2]


@pytest.mark.asyncio
async def test_reorder_abas_empty_returns_zero():
    pool, _ = _mock_pool()
    count = await reorder_abas(pool, user_id="u", ordered_ids=[])
    assert count == 0


@pytest.mark.asyncio
async def test_reorder_abas_ignores_alheia():
    # Primeiro retorna row (user-x dono), segundo retorna None (outro user)
    pool, conn = _mock_pool((1,), None)
    count = await reorder_abas(pool, user_id="u", ordered_ids=[10, 20])
    assert count == 1
    assert conn.execute.await_count == 2  # tentou os 2


# --- cliente_ids_da_aba (o critério que substituiu a pinagem) ---


@pytest.mark.asyncio
async def test_aba_sem_criterio_nao_filtra_nada():
    """`None` significa "não filtre", e não "não mostre nada".

    Aba recém-criada não tem critério. Devolver lista vazia aqui a esconderia
    tudo; devolver None deixa o chamador mostrar a listagem inteira até o
    operador escolher as tags.
    """
    pool, conn = _mock_pool()
    out = await cliente_ids_da_aba(pool, filtro={}, empresa_id=1)
    assert out is None
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_aba_com_criterio_resolve_clientes():
    pool, conn = _mock_pool([(10,), (20,)])
    out = await cliente_ids_da_aba(
        pool, filtro={"cliente_tags": ["Mackenzie"]}, empresa_id=1
    )
    assert out == [10, 20]

    sql = conn.execute.await_args.args[0]
    # `cliente_tag`, não `cliente_tag_v2`: a v2 era órfã e foi removida na mig
    # 149 — filtrar por ela dava pasta sempre vazia, sem erro na tela.
    assert "FROM cliente_tag ct" in sql
    assert "cliente_tag_v2" not in sql
    # Escopo por empresa: nome de tag é livre, e "Financeiro" de uma empresa não
    # pode arrastar cliente de outra.
    assert "c.empresa_id = %s" in sql


@pytest.mark.asyncio
async def test_aba_com_criterio_sem_cliente_devolve_lista_vazia():
    """Vazio ≠ None: aqui o critério existe e ninguém casou."""
    pool, _ = _mock_pool([])
    out = await cliente_ids_da_aba(
        pool, filtro={"cliente_tags": ["Inexistente"]}, empresa_id=1
    )
    assert out == []


# --- count_atendimentos_por_aba ---


@pytest.mark.asyncio
async def test_count_atendimentos_por_aba_returns_dict():
    pool, conn = _mock_pool([(1, 3), (2, 1)])
    out = await count_atendimentos_por_aba(pool, user_id="u", empresa_id=1)
    assert out == {1: 3, 2: 1}
    sql = conn.execute.await_args.args[0]
    assert "GROUP BY ab.id" in sql
    assert "status IN ('aguardando', 'em_andamento')" in sql
    # Conta pelo critério da aba, não pela coluna que a mig 150 removeu.
    assert "cliente_tag" in sql
    assert "aba_id" not in sql


@pytest.mark.asyncio
async def test_count_atendimentos_por_aba_empty():
    pool, _ = _mock_pool([])
    out = await count_atendimentos_por_aba(pool, user_id="u", empresa_id=1)
    assert out == {}


# --- get_aba ---


@pytest.mark.asyncio
async def test_get_aba_filters_owner_and_active():
    pool, conn = _mock_pool(_aba_row(id_=7, nome="X"))
    out = await get_aba(pool, aba_id=7, user_id="u")
    assert out is not None
    assert out["id"] == 7
    sql = conn.execute.await_args.args[0]
    assert "user_id = %s" in sql
    assert "ativo = TRUE" in sql


@pytest.mark.asyncio
async def test_get_aba_returns_none_when_not_owned():
    pool, _ = _mock_pool(None)
    out = await get_aba(pool, aba_id=999, user_id="u")
    assert out is None
