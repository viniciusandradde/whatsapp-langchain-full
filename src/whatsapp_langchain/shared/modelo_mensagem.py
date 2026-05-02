"""Helpers de ModeloMensagem (quick replies) — M4.b.

CRUD escopado por empresa. Cada modelo tem `titulo` único dentro da
empresa (UNIQUE composto), `conteudo` (texto que entra no composer) e
`atalho` opcional pra futura busca por digitação.
"""

from __future__ import annotations

import structlog
from psycopg.errors import UniqueViolation
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import ModeloMensagem, ModeloMensagemInput

logger = structlog.get_logger()


_SELECT_COLS = (
    "id, empresa_id, titulo, conteudo, atalho, "
    "created_by_user_id, created_at, updated_at"
)


def _row_to_modelo(row) -> ModeloMensagem:
    return ModeloMensagem(
        id=row[0],
        empresa_id=row[1],
        titulo=row[2],
        conteudo=row[3],
        atalho=row[4],
        created_by_user_id=row[5],
        created_at=row[6],
        updated_at=row[7],
    )


class DuplicateTituloError(Exception):
    """Já existe um modelo com este título na empresa."""


async def list_modelos(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    search: str | None = None,
    limit: int = 100,
) -> list[ModeloMensagem]:
    """Lista modelos da empresa em ordem alfabética por título.

    `search` filtra ILIKE em titulo OR conteudo OR atalho.
    """
    params: list = [empresa_id]
    where = "WHERE empresa_id = %s"
    if search:
        where += " AND (titulo ILIKE %s OR conteudo ILIKE %s OR atalho ILIKE %s)"
        like = f"%{search}%"
        params.extend([like, like, like])
    params.append(limit)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM modelo_mensagem
            {where}
            ORDER BY titulo ASC, id ASC
            LIMIT %s
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_modelo(r) for r in rows]


async def get_modelo_by_id(
    pool: AsyncConnectionPool, modelo_id: int
) -> ModeloMensagem | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM modelo_mensagem WHERE id = %s",
            (modelo_id,),
        )
        row = await cur.fetchone()
    return _row_to_modelo(row) if row else None


async def create_modelo(
    pool: AsyncConnectionPool,
    empresa_id: int,
    data: ModeloMensagemInput,
    *,
    user_id: str | None = None,
) -> ModeloMensagem:
    """Insere modelo. Levanta DuplicateTituloError se titulo conflita."""
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                INSERT INTO modelo_mensagem
                    (empresa_id, titulo, conteudo, atalho, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING {_SELECT_COLS}
                """,
                (empresa_id, data.titulo, data.conteudo, data.atalho, user_id),
            )
            row = await cur.fetchone()
    except UniqueViolation as e:
        raise DuplicateTituloError(
            f"Já existe um modelo com o título '{data.titulo}' nesta empresa."
        ) from e
    assert row is not None
    return _row_to_modelo(row)


async def update_modelo(
    pool: AsyncConnectionPool,
    modelo_id: int,
    data: ModeloMensagemInput,
) -> ModeloMensagem | None:
    """Atualiza modelo existente. Retorna None se id não existe."""
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                UPDATE modelo_mensagem
                   SET titulo = %s, conteudo = %s, atalho = %s, updated_at = NOW()
                 WHERE id = %s
                RETURNING {_SELECT_COLS}
                """,
                (data.titulo, data.conteudo, data.atalho, modelo_id),
            )
            row = await cur.fetchone()
    except UniqueViolation as e:
        raise DuplicateTituloError(
            f"Já existe um modelo com o título '{data.titulo}' nesta empresa."
        ) from e
    return _row_to_modelo(row) if row else None


async def delete_modelo(pool: AsyncConnectionPool, modelo_id: int) -> bool:
    """Remove modelo. Retorna True se algo foi deletado."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM modelo_mensagem WHERE id = %s",
            (modelo_id,),
        )
    return (cur.rowcount or 0) > 0
