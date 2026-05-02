"""Testes dos helpers de Departamento, Horário e Feriado (M6.a)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from psycopg import errors as pg_errors

from whatsapp_langchain.shared import departamento as dep
from whatsapp_langchain.shared import horario as hor
from whatsapp_langchain.shared.models import (
    DepartamentoInput,
    FeriadoInput,
    HorarioFuncionamentoInput,
)


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
    return pool, conn, cur


# --- Departamento CRUD ---


def _dep_row(*, dep_id=1, empresa_id=1, nome="Suporte", ativo=True):
    now = datetime.now(UTC)
    return (dep_id, empresa_id, nome, None, ativo, None, now, now)


@pytest.mark.asyncio
async def test_get_departamento_filters_by_empresa():
    pool, conn, _ = _mock_pool(None)
    await dep.get_departamento_by_id(pool, 7, 99)
    sql, params = conn.execute.await_args.args
    assert "empresa_id = %s" in sql
    assert params == (99, 7)


@pytest.mark.asyncio
async def test_create_departamento_raises_on_duplicate():
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=pg_errors.UniqueViolation("dup"))
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    with pytest.raises(dep.DuplicateDepartamentoError):
        await dep.create_departamento(
            pool, 1, DepartamentoInput(nome="Suporte"), user_id="u"
        )


@pytest.mark.asyncio
async def test_update_departamento_returns_none_when_missing():
    pool, _, _ = _mock_pool(None)
    out = await dep.update_departamento(
        pool, 1, 99, DepartamentoInput(nome="X")
    )
    assert out is None


@pytest.mark.asyncio
async def test_delete_departamento_rowcount():
    pool, _, _ = _mock_pool(rowcount=1)
    assert await dep.delete_departamento(pool, 1, 1) is True
    pool, _, _ = _mock_pool(rowcount=0)
    assert await dep.delete_departamento(pool, 1, 99) is False


# --- Horario CRUD ---


def _hor_row(*, hor_id=1, dia=1, ini="09:00", fim="18:00"):
    now = datetime.now(UTC)
    return (hor_id, 1, dia, ini, fim, None, True, now)


@pytest.mark.asyncio
async def test_create_horario_returns_row():
    pool, _, _ = _mock_pool(_hor_row())
    out = await hor.create_horario(
        pool,
        1,
        HorarioFuncionamentoInput(dia_semana=1, hora_inicio="09:00", hora_fim="18:00"),
    )
    assert out.dia_semana == 1
    assert out.hora_inicio == "09:00"


# --- Feriado CRUD ---


def _fer_row(*, fer_id=1, data="2026-12-25"):
    now = datetime.now(UTC)
    return (fer_id, 1, data, "Natal", "u", now)


@pytest.mark.asyncio
async def test_create_feriado_raises_on_duplicate():
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=pg_errors.UniqueViolation("dup"))
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    with pytest.raises(hor.DuplicateFeriadoError):
        await hor.create_feriado(
            pool, 1, FeriadoInput(data="2026-12-25", descricao="Natal")
        )


# --- is_business_hours ---


def _build_pool_for_hours(
    *,
    timezone_row=("America/Sao_Paulo",),
    feriado_row=None,
    total_horarios=1,
    janela_match=True,
):
    """Mock pool com 4 fetchone consecutivas (timezone, feriado, count, janela)."""
    cur = AsyncMock()
    cur.fetchone = AsyncMock(
        side_effect=[
            timezone_row,
            feriado_row,
            (total_horarios,),
            (1,) if janela_match else None,
        ]
    )
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.mark.asyncio
async def test_is_business_hours_true_when_janela_match():
    pool = _build_pool_for_hours(janela_match=True)
    # Segunda 14h em SP — naive datetime convertido pra SP é tratado pela
    # função (passa now=ts; astimezone normaliza).
    ts = datetime(2026, 5, 4, 17, 0, tzinfo=UTC)  # = 14h em SP (UTC-3)
    out = await hor.is_business_hours(pool, 1, now=ts)
    assert out is True


@pytest.mark.asyncio
async def test_is_business_hours_false_outside_janela():
    pool = _build_pool_for_hours(janela_match=False)
    ts = datetime(2026, 5, 4, 23, 0, tzinfo=UTC)  # 20h em SP — fora
    assert await hor.is_business_hours(pool, 1, now=ts) is False


@pytest.mark.asyncio
async def test_is_business_hours_false_on_feriado():
    pool = _build_pool_for_hours(feriado_row=(1,))
    ts = datetime(2026, 12, 25, 14, 0, tzinfo=UTC)
    assert await hor.is_business_hours(pool, 1, now=ts) is False


@pytest.mark.asyncio
async def test_is_business_hours_true_when_no_horarios_cadastrados():
    """Sem cadastro = compat default sempre aberto."""
    pool = _build_pool_for_hours(total_horarios=0)
    ts = datetime(2026, 5, 4, 23, 0, tzinfo=UTC)
    assert await hor.is_business_hours(pool, 1, now=ts) is True


@pytest.mark.asyncio
async def test_is_business_hours_uses_default_timezone_when_none():
    pool = _build_pool_for_hours(timezone_row=None)
    # Garante que não levanta exceção em fallback
    ts = datetime(2026, 5, 4, 14, 0, tzinfo=UTC)
    out = await hor.is_business_hours(pool, 1, now=ts)
    assert isinstance(out, bool)


def test_parse_hhmm():
    assert hor._parse_hhmm("09:00").hour == 9
    assert hor._parse_hhmm("18:30").minute == 30
