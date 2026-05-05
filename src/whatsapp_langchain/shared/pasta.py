"""CRUD de Pasta — organização hierárquica da base de conhecimento (E2.C M7).

Pastas formam uma árvore por empresa. Documentos podem estar em qualquer
nó (ou em "raiz" = pasta_id NULL). A busca de RAG não usa pasta — é só
estrutura de UI/governança.
"""

from __future__ import annotations

import structlog
from psycopg import errors as pg_errors
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


class DuplicatePastaError(ValueError):
    """Já existe pasta com esse nome no mesmo nível (mesmo parent)."""


_COLS = (
    "id, empresa_id, nome, parent_id, descricao, "
    "created_by_user_id, created_at, updated_at"
)


def _row_to_dict(row, docs_count: int | None = None) -> dict:
    return {
        "id": row[0],
        "empresa_id": row[1],
        "nome": row[2],
        "parent_id": row[3],
        "descricao": row[4],
        "created_by_user_id": row[5],
        "created_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
        "docs_count": docs_count,
    }


async def list_pastas(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    com_docs_count: bool = False,
) -> list[dict]:
    sql = (
        f"""
        SELECT {_COLS},
               (SELECT COUNT(*) FROM documento_conhecimento d
                 WHERE d.pasta_id = p.id) AS docs_count
          FROM pasta p
         WHERE empresa_id = %s
         ORDER BY nome
        """
        if com_docs_count
        else (
            f"SELECT {_COLS} FROM pasta WHERE empresa_id = %s ORDER BY nome"
        )
    )
    async with pool.connection() as conn:
        cur = await conn.execute(sql, (empresa_id,))
        rows = await cur.fetchall()
    if com_docs_count:
        return [_row_to_dict(r[:-1], docs_count=r[-1]) for r in rows]
    return [_row_to_dict(r) for r in rows]


async def get_pasta(
    pool: AsyncConnectionPool, empresa_id: int, pasta_id: int
) -> dict | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM pasta WHERE id = %s AND empresa_id = %s",
            (pasta_id, empresa_id),
        )
        row = await cur.fetchone()
    return _row_to_dict(row) if row else None


async def get_descendant_ids(
    pool: AsyncConnectionPool, empresa_id: int, root_ids: list[int]
) -> set[int]:
    """Recursive CTE — IDs descendentes (inclui roots)."""
    if not root_ids:
        return set()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            WITH RECURSIVE tree AS (
                SELECT id FROM pasta
                 WHERE empresa_id = %s AND id = ANY(%s)
                UNION
                SELECT p.id FROM pasta p
                  JOIN tree t ON p.parent_id = t.id
                 WHERE p.empresa_id = %s
            )
            SELECT id FROM tree
            """,
            (empresa_id, list(root_ids), empresa_id),
        )
        rows = await cur.fetchall()
    return {r[0] for r in rows}


async def create_pasta(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    nome: str,
    parent_id: int | None = None,
    descricao: str | None = None,
    user_id: str | None = None,
) -> dict:
    if parent_id is not None:
        parent = await get_pasta(pool, empresa_id, parent_id)
        if parent is None:
            raise ValueError(
                f"parent_id={parent_id} não existe nessa empresa"
            )
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                INSERT INTO pasta
                    (empresa_id, nome, parent_id, descricao, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING {_COLS}
                """,
                (empresa_id, nome, parent_id, descricao, user_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    except pg_errors.UniqueViolation as e:
        raise DuplicatePastaError(
            f"pasta '{nome}' já existe nesse nível"
        ) from e
    assert row is not None
    return _row_to_dict(row)


async def update_pasta(
    pool: AsyncConnectionPool,
    empresa_id: int,
    pasta_id: int,
    *,
    nome: str,
    parent_id: int | None,
    descricao: str | None,
) -> dict | None:
    if parent_id is not None:
        if parent_id == pasta_id:
            raise ValueError("parent_id não pode ser a própria pasta")
        descendants = await get_descendant_ids(pool, empresa_id, [pasta_id])
        if parent_id in descendants:
            raise ValueError("parent_id é descendente — criaria ciclo")
        parent = await get_pasta(pool, empresa_id, parent_id)
        if parent is None:
            raise ValueError(
                f"parent_id={parent_id} não existe nessa empresa"
            )
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                UPDATE pasta
                   SET nome = %s, parent_id = %s, descricao = %s,
                       updated_at = NOW()
                 WHERE id = %s AND empresa_id = %s
                RETURNING {_COLS}
                """,
                (nome, parent_id, descricao, pasta_id, empresa_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    except pg_errors.UniqueViolation as e:
        raise DuplicatePastaError(
            f"pasta '{nome}' já existe nesse nível"
        ) from e
    return _row_to_dict(row) if row else None


async def delete_pasta(
    pool: AsyncConnectionPool, empresa_id: int, pasta_id: int
) -> bool:
    """Deleta pasta. Documentos da pasta viram pasta_id=NULL (raiz).
    Subpastas também viram parent_id=NULL (FK SET NULL)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM pasta WHERE id = %s AND empresa_id = %s",
            (pasta_id, empresa_id),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0


async def move_documento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    doc_id: int,
    *,
    pasta_id: int | None,
) -> bool:
    """Move documento pra outra pasta (None = raiz). Valida tenant."""
    if pasta_id is not None:
        p = await get_pasta(pool, empresa_id, pasta_id)
        if p is None:
            raise ValueError("pasta_id não existe nessa empresa")
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE documento_conhecimento
               SET pasta_id = %s, updated_at = NOW()
             WHERE id = %s AND empresa_id = %s
            """,
            (pasta_id, doc_id, empresa_id),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0
