"""CRUD de Departamento (M6.a)."""

from __future__ import annotations

import structlog
from psycopg import errors as pg_errors
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Departamento, DepartamentoInput

logger = structlog.get_logger()


class DuplicateDepartamentoError(ValueError):
    """Outra empresa já tem departamento com esse nome."""


_SELECT_COLS = (
    "id, empresa_id, nome, descricao, ativo, "
    "created_by_user_id, created_at, updated_at"
)


def _row_to_departamento(row) -> Departamento:
    return Departamento(
        id=row[0],
        empresa_id=row[1],
        nome=row[2],
        descricao=row[3],
        ativo=row[4],
        created_by_user_id=row[5],
        created_at=row[6],
        updated_at=row[7],
    )


async def list_departamentos(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    apenas_ativos: bool = False,
) -> list[Departamento]:
    where = "empresa_id = %s"
    if apenas_ativos:
        where += " AND ativo"
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM departamento "
            f"WHERE {where} ORDER BY nome ASC",
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_departamento(r) for r in rows]


async def get_departamento_by_id(
    pool: AsyncConnectionPool, empresa_id: int, dep_id: int
) -> Departamento | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM departamento "
            "WHERE id = %s AND empresa_id = %s",
            (dep_id, empresa_id),
        )
        row = await cur.fetchone()
    return _row_to_departamento(row) if row else None


async def create_departamento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    data: DepartamentoInput,
    *,
    user_id: str | None = None,
) -> Departamento:
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                INSERT INTO departamento
                    (empresa_id, nome, descricao, ativo, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING {_SELECT_COLS}
                """,
                (
                    empresa_id,
                    data.nome,
                    data.descricao,
                    data.ativo,
                    user_id,
                ),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as e:
        raise DuplicateDepartamentoError(
            f"departamento '{data.nome}' já existe na empresa"
        ) from e
    assert row is not None
    return _row_to_departamento(row)


async def update_departamento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    dep_id: int,
    data: DepartamentoInput,
) -> Departamento | None:
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                UPDATE departamento
                   SET nome = %s,
                       descricao = %s,
                       ativo = %s,
                       updated_at = NOW()
                 WHERE id = %s AND empresa_id = %s
                RETURNING {_SELECT_COLS}
                """,
                (
                    data.nome,
                    data.descricao,
                    data.ativo,
                    dep_id,
                    empresa_id,
                ),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as e:
        raise DuplicateDepartamentoError(
            f"departamento '{data.nome}' já existe na empresa"
        ) from e
    return _row_to_departamento(row) if row else None


async def delete_departamento(
    pool: AsyncConnectionPool, empresa_id: int, dep_id: int
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM departamento "
            "WHERE id = %s AND empresa_id = %s",
            (dep_id, empresa_id),
        )
    return (cur.rowcount or 0) > 0
