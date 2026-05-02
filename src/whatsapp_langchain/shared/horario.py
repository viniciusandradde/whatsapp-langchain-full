"""Horário de funcionamento + feriados + check de expediente (M6.a).

Este módulo cuida de 3 entidades acopladas:
- `horario_funcionamento`: janelas (dia_semana, hora_inicio, hora_fim) por
  empresa. Almoço = duas rows do mesmo dia.
- `feriado`: data específica em que a empresa está fechada o dia inteiro.
- `is_business_hours(empresa_id, ts)`: combina os dois e diz se está
  aberto agora.

Timezone: lê de `empresa_calendar_config.timezone` (M5.a) com fallback
`America/Sao_Paulo`. Sem horário cadastrado = sempre aberto (compat com
empresas pré-M6.a — só passam a fechar depois de cadastrarem expediente).
"""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import structlog
from psycopg import errors as pg_errors
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import (
    Feriado,
    FeriadoInput,
    HorarioFuncionamento,
    HorarioFuncionamentoInput,
)

if TYPE_CHECKING:  # pragma: no cover
    from datetime import date

logger = structlog.get_logger()

DEFAULT_TIMEZONE = "America/Sao_Paulo"


class DuplicateFeriadoError(ValueError):
    """Outra row já tem essa (empresa, data)."""


# --- Horário de funcionamento ---


_HORARIO_COLS = (
    "id, empresa_id, dia_semana, "
    "to_char(hora_inicio, 'HH24:MI'), to_char(hora_fim, 'HH24:MI'), "
    "departamento_id, ativo, created_at"
)


def _row_to_horario(row) -> HorarioFuncionamento:
    return HorarioFuncionamento(
        id=row[0],
        empresa_id=row[1],
        dia_semana=row[2],
        hora_inicio=row[3],
        hora_fim=row[4],
        departamento_id=row[5],
        ativo=row[6],
        created_at=row[7],
    )


async def list_horarios(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    departamento_id: int | None = None,
) -> list[HorarioFuncionamento]:
    """Lista horários da empresa. `departamento_id` filtra por departamento
    (None retorna apenas horários gerais — sem departamento)."""
    where = "empresa_id = %s"
    params: list = [empresa_id]
    if departamento_id is None:
        # Apenas horários gerais
        pass
    else:
        where += " AND departamento_id = %s"
        params.append(departamento_id)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_HORARIO_COLS} FROM horario_funcionamento "
            f"WHERE {where} ORDER BY dia_semana, hora_inicio",
            params,
        )
        rows = await cur.fetchall()
    return [_row_to_horario(r) for r in rows]


async def list_all_horarios(
    pool: AsyncConnectionPool, empresa_id: int
) -> list[HorarioFuncionamento]:
    """Retorna todos horários da empresa (gerais + por departamento)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_HORARIO_COLS} FROM horario_funcionamento "
            "WHERE empresa_id = %s ORDER BY dia_semana, hora_inicio",
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_horario(r) for r in rows]


async def get_horario_by_id(
    pool: AsyncConnectionPool, empresa_id: int, horario_id: int
) -> HorarioFuncionamento | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_HORARIO_COLS} FROM horario_funcionamento "
            "WHERE id = %s AND empresa_id = %s",
            (horario_id, empresa_id),
        )
        row = await cur.fetchone()
    return _row_to_horario(row) if row else None


async def create_horario(
    pool: AsyncConnectionPool,
    empresa_id: int,
    data: HorarioFuncionamentoInput,
) -> HorarioFuncionamento:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO horario_funcionamento
                (empresa_id, dia_semana, hora_inicio, hora_fim,
                 departamento_id, ativo)
            VALUES (%s, %s, %s::time, %s::time, %s, %s)
            RETURNING {_HORARIO_COLS}
            """,
            (
                empresa_id,
                data.dia_semana,
                data.hora_inicio,
                data.hora_fim,
                data.departamento_id,
                data.ativo,
            ),
        )
        row = await cur.fetchone()
    assert row is not None
    return _row_to_horario(row)


async def delete_horario(
    pool: AsyncConnectionPool, empresa_id: int, horario_id: int
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM horario_funcionamento "
            "WHERE id = %s AND empresa_id = %s",
            (horario_id, empresa_id),
        )
    return (cur.rowcount or 0) > 0


# --- Feriado ---


_FERIADO_COLS = (
    "id, empresa_id, to_char(data, 'YYYY-MM-DD'), descricao, "
    "created_by_user_id, created_at"
)


def _row_to_feriado(row) -> Feriado:
    return Feriado(
        id=row[0],
        empresa_id=row[1],
        data=row[2],
        descricao=row[3],
        created_by_user_id=row[4],
        created_at=row[5],
    )


async def list_feriados(
    pool: AsyncConnectionPool, empresa_id: int
) -> list[Feriado]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_FERIADO_COLS} FROM feriado "
            "WHERE empresa_id = %s ORDER BY data ASC",
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_feriado(r) for r in rows]


async def create_feriado(
    pool: AsyncConnectionPool,
    empresa_id: int,
    data: FeriadoInput,
    *,
    user_id: str | None = None,
) -> Feriado:
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                INSERT INTO feriado
                    (empresa_id, data, descricao, created_by_user_id)
                VALUES (%s, %s::date, %s, %s)
                RETURNING {_FERIADO_COLS}
                """,
                (empresa_id, data.data, data.descricao, user_id),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as e:
        raise DuplicateFeriadoError(
            f"feriado em {data.data} já existe nessa empresa"
        ) from e
    assert row is not None
    return _row_to_feriado(row)


async def delete_feriado(
    pool: AsyncConnectionPool, empresa_id: int, feriado_id: int
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM feriado WHERE id = %s AND empresa_id = %s",
            (feriado_id, empresa_id),
        )
    return (cur.rowcount or 0) > 0


# --- Business hours ---


async def _resolve_timezone(
    pool: AsyncConnectionPool, empresa_id: int
) -> str:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT timezone FROM empresa_calendar_config "
            "WHERE empresa_id = %s",
            (empresa_id,),
        )
        row = await cur.fetchone()
    if row and row[0]:
        return row[0]
    return DEFAULT_TIMEZONE


async def is_business_hours(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    now: datetime | None = None,
) -> bool:
    """True quando a empresa está aberta no instante `now` (default: agora).

    Regras (avaliadas no fuso da empresa):
    1. Se a data está em `feriado` → fechado.
    2. Se a empresa não tem nenhum `horario_funcionamento` ativo cadastrado
       → aberto (default: sempre aberto até admin cadastrar expediente).
    3. Se `now.time()` cai dentro de alguma janela `[hora_inicio, hora_fim)`
       no `dia_semana` correspondente → aberto.
    4. Caso contrário → fechado.
    """
    tz_name = await _resolve_timezone(pool, empresa_id)
    tz = ZoneInfo(tz_name)
    if now is None:
        now = datetime.now(tz)
    else:
        now = now.astimezone(tz)

    async with pool.connection() as conn:
        # Feriado?
        cur = await conn.execute(
            "SELECT 1 FROM feriado WHERE empresa_id = %s AND data = %s::date LIMIT 1",
            (empresa_id, now.date().isoformat()),
        )
        if await cur.fetchone() is not None:
            return False

        # Horários ativos da empresa (gerais — departamento_id IS NULL)
        # Python `weekday()`: 0=segunda .. 6=domingo
        # Nosso `dia_semana`:  0=domingo, 1=segunda .. 6=sábado
        # Conversão: dia_semana = (weekday() + 1) % 7
        dia_semana = (now.weekday() + 1) % 7

        cur = await conn.execute(
            "SELECT COUNT(*) FROM horario_funcionamento "
            "WHERE empresa_id = %s AND ativo "
            "AND departamento_id IS NULL",
            (empresa_id,),
        )
        row = await cur.fetchone()
        total_horarios = (row[0] if row else 0) or 0
        if total_horarios == 0:
            # Sem cadastro = sempre aberto (compat).
            return True

        # Tem janela ativa pra esse dia/horário?
        hora_str = now.strftime("%H:%M:%S")
        cur = await conn.execute(
            "SELECT 1 FROM horario_funcionamento "
            "WHERE empresa_id = %s AND ativo "
            "AND departamento_id IS NULL "
            "AND dia_semana = %s "
            "AND hora_inicio <= %s::time AND hora_fim > %s::time "
            "LIMIT 1",
            (empresa_id, dia_semana, hora_str, hora_str),
        )
        return await cur.fetchone() is not None


def _parse_hhmm(value: str) -> time:
    """Helper privado pra tests — converte 'HH:MM' em time."""
    h, m = value.split(":")
    return time(int(h), int(m))
