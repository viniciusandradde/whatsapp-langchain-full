"""Testes do helper de Variáveis de Ambiente (M5.d)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from psycopg import errors as pg_errors

from whatsapp_langchain.shared import variavel
from whatsapp_langchain.shared.models import VariavelAmbienteInput


def _row(
    *,
    var_id=1,
    empresa_id=1,
    nome="suporte_email",
    valor="suporte@empresa.com",
    descricao=None,
    ativo=True,
    user_id=None,
):
    now = datetime.now(UTC)
    return (
        var_id,
        empresa_id,
        nome,
        valor,
        descricao,
        ativo,
        user_id,
        now,
        now,
    )


def _mock_pool(*results, rowcount: int = 1, multi: bool = False, fetchall=None):
    cur = AsyncMock()
    if fetchall is not None:
        cur.fetchall = AsyncMock(return_value=fetchall)
    elif multi:
        cur.fetchall = AsyncMock(return_value=list(results))
    else:
        fetchone_seq = list(results) if results else [None]
        cur.fetchone = AsyncMock(side_effect=fetchone_seq)
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn, cur


# --- render_template ---


def test_render_simple_substitution():
    ctx = {"empresa.nome": "VSA Tech", "data.hoje": "2026-05-02"}
    out = variavel.render_template(
        "Olá da {{empresa.nome}} hoje ({{data.hoje}})!", ctx
    )
    assert out == "Olá da VSA Tech hoje (2026-05-02)!"


def test_render_missing_key_left_literal():
    ctx = {"empresa.nome": "X"}
    out = variavel.render_template("Oi {{var.algumacoisa}} fim", ctx)
    assert out == "Oi {{var.algumacoisa}} fim"


def test_render_handles_whitespace_inside_braces():
    ctx = {"empresa.nome": "X"}
    assert variavel.render_template("{{ empresa.nome }}", ctx) == "X"


def test_render_empty_string_passthrough():
    assert variavel.render_template("", {"empresa.nome": "X"}) == ""


def test_render_no_template_unchanged():
    assert variavel.render_template("texto puro", {"x": "y"}) == "texto puro"


def test_render_does_not_recurse():
    """Substituição não recursiva — ctx pode conter `{{...}}` sem looping."""
    ctx = {"var.x": "{{var.y}}"}
    assert variavel.render_template("eco: {{var.x}}", ctx) == "eco: {{var.y}}"


# --- CRUD ---


@pytest.mark.asyncio
async def test_get_variavel_filters_by_empresa():
    pool, conn, _ = _mock_pool(None)
    await variavel.get_variavel_by_id(pool, 7, 99)
    sql, params = conn.execute.await_args.args
    assert "empresa_id = %s" in sql
    assert params == (99, 7)


@pytest.mark.asyncio
async def test_list_variaveis_apenas_ativos_filters_in_sql():
    pool, conn, _ = _mock_pool(fetchall=[])
    await variavel.list_variaveis(pool, 1, apenas_ativos=True)
    sql = conn.execute.await_args.args[0]
    assert "AND ativo" in sql


@pytest.mark.asyncio
async def test_create_returns_variavel():
    pool, _, _ = _mock_pool(_row())
    out = await variavel.create_variavel(
        pool,
        1,
        VariavelAmbienteInput(
            nome="suporte_email", valor="x@y.com"
        ),
        user_id="u",
    )
    assert out.nome == "suporte_email"


@pytest.mark.asyncio
async def test_create_raises_duplicate_on_unique_violation():
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=pg_errors.UniqueViolation("dup"))
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    with pytest.raises(variavel.DuplicateNomeError):
        await variavel.create_variavel(
            pool,
            1,
            VariavelAmbienteInput(nome="x", valor="y"),
        )


@pytest.mark.asyncio
async def test_update_returns_none_when_missing():
    pool, _, _ = _mock_pool(None)
    out = await variavel.update_variavel(
        pool,
        1,
        99,
        VariavelAmbienteInput(nome="x", valor="y"),
    )
    assert out is None


@pytest.mark.asyncio
async def test_update_raises_duplicate_on_rename_conflict():
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=pg_errors.UniqueViolation("dup"))
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    with pytest.raises(variavel.DuplicateNomeError):
        await variavel.update_variavel(
            pool,
            1,
            5,
            VariavelAmbienteInput(nome="conflito", valor="y"),
        )


@pytest.mark.asyncio
async def test_delete_returns_true_when_deleted():
    pool, _, _ = _mock_pool(rowcount=1)
    assert await variavel.delete_variavel(pool, 1, 1) is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_missing():
    pool, _, _ = _mock_pool(rowcount=0)
    assert await variavel.delete_variavel(pool, 1, 99) is False


# --- build_render_context ---


@pytest.mark.asyncio
async def test_build_render_context_assembles_namespaces():
    """Sem atendimento_id, retorna empresa.*, var.*, data.*."""
    cur = AsyncMock()
    # fetchone (empresa) + fetchall (vars)
    cur.fetchone = AsyncMock(return_value=("VSA Tech", "vsa", "12345", "free"))
    cur.fetchall = AsyncMock(
        return_value=[
            ("suporte_email", "suporte@vsa.com"),
            ("horario", "9-18h"),
        ]
    )
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    ctx = await variavel.build_render_context(
        pool,
        1,
        now=datetime(2026, 5, 2, 14, 30, tzinfo=UTC),
    )
    assert ctx["empresa.nome"] == "VSA Tech"
    assert ctx["empresa.slug"] == "vsa"
    assert ctx["var.suporte_email"] == "suporte@vsa.com"
    assert ctx["var.horario"] == "9-18h"
    assert ctx["data.hoje"] == "2026-05-02"
    assert ctx["data.ano"] == "2026"
    # cliente.* não foi populado (nenhum atendimento_id)
    assert "cliente.nome" not in ctx


@pytest.mark.asyncio
async def test_build_render_context_inclui_cliente_quando_atendimento():
    cur = AsyncMock()
    # 3 fetchone (empresa, [fetchall vars], cliente) + fetchall (vars)
    cur.fetchone = AsyncMock(
        side_effect=[
            ("Empresa", "e", None, "free"),
            ("João", "+5511999999999", "joao@x.com", "12345"),
        ]
    )
    cur.fetchall = AsyncMock(return_value=[])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    ctx = await variavel.build_render_context(pool, 1, atendimento_id=42)
    assert ctx["cliente.nome"] == "João"
    assert ctx["cliente.telefone"] == "+5511999999999"
