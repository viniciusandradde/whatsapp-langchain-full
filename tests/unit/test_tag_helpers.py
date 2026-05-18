"""Testes dos helpers de tag (Sprint Atendimento UX 1.2, mig 086)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.atendimento_tag import (
    apply_tags_to_atendimento,
    list_atendimento_ids_com_tags,
    list_tags_de_atendimento,
)
from whatsapp_langchain.shared.tag import (
    create_tag,
    delete_tag,
    get_tag,
    list_tags,
    update_tag,
)


def _tag_row(*, id_=1, nome="Urgente", cor=None, descricao=None, ativo=True):
    now = datetime.now(UTC)
    return (id_, nome, cor, descricao, ativo, now, now)


def _mock_pool(*results) -> tuple[MagicMock, AsyncMock]:
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    fetchall_seq = [r for r in results if isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.fetchall = AsyncMock(side_effect=fetchall_seq if fetchall_seq else [[]])
    cur.rowcount = 1  # default pra UPDATE/DELETE/INSERT
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# ---------------- shared/tag.py ----------------


@pytest.mark.asyncio
async def test_list_tags_filtra_ativos_por_default():
    rows = [_tag_row(id_=1, nome="VIP"), _tag_row(id_=2, nome="Urgente")]
    pool, conn = _mock_pool(rows)
    out = await list_tags(pool, empresa_id=1)
    assert len(out) == 2
    assert out[0]["nome"] == "VIP"
    sql = conn.execute.await_args.args[0]
    assert "WHERE empresa_id = %s" in sql
    assert "ativo = TRUE" in sql


@pytest.mark.asyncio
async def test_list_tags_pode_incluir_inativos():
    pool, conn = _mock_pool([])
    await list_tags(pool, empresa_id=1, only_ativos=False)
    sql = conn.execute.await_args.args[0]
    assert "ativo = TRUE" not in sql


@pytest.mark.asyncio
async def test_get_tag_retorna_none_se_outra_empresa():
    pool, _ = _mock_pool(None)
    out = await get_tag(pool, tag_id=999, empresa_id=1)
    assert out is None


@pytest.mark.asyncio
async def test_create_tag_insert_e_retorna_dict():
    pool, conn = _mock_pool(_tag_row(id_=10, nome="Nova", cor="#ff0000"))
    out = await create_tag(
        pool, empresa_id=1, nome="Nova", cor="#ff0000", created_by_user_id="u"
    )
    assert out["id"] == 10
    assert out["nome"] == "Nova"
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO tag" in sql


@pytest.mark.asyncio
async def test_update_tag_partial_apenas_nome():
    pool, conn = _mock_pool(_tag_row(id_=5, nome="Renomeada"))
    out = await update_tag(
        pool, tag_id=5, empresa_id=1, nome="Renomeada"
    )
    assert out is not None
    sql = conn.execute.await_args.args[0]
    assert "UPDATE tag SET nome = %s" in sql


@pytest.mark.asyncio
async def test_update_tag_no_fields_returns_current():
    pool, _ = _mock_pool(_tag_row(id_=1, nome="Existente"))
    out = await update_tag(pool, tag_id=1, empresa_id=1)
    assert out is not None
    assert out["nome"] == "Existente"


@pytest.mark.asyncio
async def test_update_tag_returns_none_se_outra_empresa():
    pool, _ = _mock_pool(None)
    out = await update_tag(pool, tag_id=999, empresa_id=1, cor="#000")
    assert out is None


@pytest.mark.asyncio
async def test_delete_tag_hard_delete():
    pool, conn = _mock_pool((1,))
    ok = await delete_tag(pool, tag_id=1, empresa_id=1)
    assert ok is True
    sql = conn.execute.await_args.args[0]
    assert "DELETE FROM tag" in sql


@pytest.mark.asyncio
async def test_delete_tag_outra_empresa_retorna_false():
    pool, _ = _mock_pool(None)
    ok = await delete_tag(pool, tag_id=999, empresa_id=1)
    assert ok is False


# ---------------- shared/atendimento_tag.py ----------------


@pytest.mark.asyncio
async def test_list_tags_de_atendimento_ordena_por_data():
    now = datetime.now(UTC)
    rows = [
        (1, "VIP", "#ff0000", None, "user-x", False, now),
        (2, "Urgente", "#000", None, None, True, now),  # aplicada por IA
    ]
    pool, conn = _mock_pool(rows)
    out = await list_tags_de_atendimento(
        pool, atendimento_id=100, empresa_id=1
    )
    assert len(out) == 2
    assert out[0]["aplicado_por_user_id"] == "user-x"
    assert out[1]["aplicado_por_ia"] is True
    sql = conn.execute.await_args.args[0]
    assert "ORDER BY at.aplicado_at ASC" in sql


@pytest.mark.asyncio
async def test_apply_tags_atendimento_de_outra_empresa_retorna_ok_false():
    # SELECT 1 retorna None — atendimento não é da empresa
    pool, _ = _mock_pool(None)
    out = await apply_tags_to_atendimento(
        pool, atendimento_id=999, empresa_id=1, add_tag_ids=[1], remove_tag_ids=[]
    )
    assert out == {"added": 0, "removed": 0, "ok": False}


@pytest.mark.asyncio
async def test_apply_tags_add_e_remove_juntos():
    # SELECT 1 = atendimento existe, DELETE rowcount=1, INSERT rowcount=2
    pool, conn = _mock_pool((1,))
    # rowcount default é 1 — vou setar manualmente
    out = await apply_tags_to_atendimento(
        pool,
        atendimento_id=100,
        empresa_id=1,
        add_tag_ids=[2, 3],
        remove_tag_ids=[1],
        aplicado_por_user_id="user-x",
    )
    assert out["ok"] is True
    # 3 execs: SELECT 1, DELETE, INSERT
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert any("DELETE FROM atendimento_tag" in s for s in sql_calls)
    assert any("INSERT INTO atendimento_tag" in s for s in sql_calls)


@pytest.mark.asyncio
async def test_apply_tags_skip_se_listas_vazias():
    pool, conn = _mock_pool((1,))
    out = await apply_tags_to_atendimento(
        pool, atendimento_id=100, empresa_id=1, add_tag_ids=[], remove_tag_ids=[]
    )
    assert out["ok"] is True
    assert out["added"] == 0
    assert out["removed"] == 0
    # Só 1 exec (SELECT 1) — sem DELETE/INSERT
    assert conn.execute.await_count == 1


@pytest.mark.asyncio
async def test_list_atendimento_ids_com_tags_or():
    pool, conn = _mock_pool([(10,), (20,), (30,)])
    out = await list_atendimento_ids_com_tags(
        pool, empresa_id=1, tag_ids=[1, 2, 3]
    )
    assert out == [10, 20, 30]
    sql = conn.execute.await_args.args[0]
    assert "DISTINCT atendimento_id" in sql
    assert "tag_id = ANY(%s)" in sql


@pytest.mark.asyncio
async def test_list_atendimento_ids_com_tags_vazio_retorna_vazio_sem_query():
    pool, conn = _mock_pool()
    out = await list_atendimento_ids_com_tags(pool, empresa_id=1, tag_ids=[])
    assert out == []
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_tags_marca_aplicado_por_ia():
    pool, conn = _mock_pool((1,))
    await apply_tags_to_atendimento(
        pool,
        atendimento_id=100,
        empresa_id=1,
        add_tag_ids=[1],
        remove_tag_ids=[],
        aplicado_por_ia=True,
    )
    # INSERT inclui aplicado_por_ia
    insert_call = next(
        c for c in conn.execute.await_args_list if "INSERT" in c.args[0]
    )
    # Args do INSERT: (atendimento_id, empresa_id, user_id, por_ia, list, empresa_id)
    assert insert_call.args[1][3] is True
