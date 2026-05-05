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
    "created_by_user_id, created_at, updated_at, parent_id"
)


def _row_to_departamento(row, users_count: int | None = None) -> Departamento:
    return Departamento(
        id=row[0],
        empresa_id=row[1],
        nome=row[2],
        descricao=row[3],
        ativo=row[4],
        created_by_user_id=row[5],
        created_at=row[6],
        updated_at=row[7],
        parent_id=row[8] if len(row) > 8 else None,
        users_count=users_count,
    )


async def list_departamentos(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    apenas_ativos: bool = False,
    com_users_count: bool = False,
) -> list[Departamento]:
    """Lista departamentos da empresa.

    `com_users_count=True` faz JOIN com usuario_departamento e popula
    o campo `users_count` em cada Departamento — usado pela UI tree
    pra mostrar quantos members em cada nó.
    """
    where = "d.empresa_id = %s"
    if apenas_ativos:
        where += " AND d.ativo"

    select_cols = ", ".join(f"d.{c.strip()}" for c in _SELECT_COLS.split(","))
    if com_users_count:
        sql = f"""
            SELECT {select_cols},
                   (SELECT COUNT(*) FROM usuario_departamento ud
                     WHERE ud.departamento_id = d.id) AS users_count
              FROM departamento d
             WHERE {where}
             ORDER BY d.nome ASC
        """
    else:
        sql = f"""
            SELECT {select_cols}
              FROM departamento d
             WHERE {where}
             ORDER BY d.nome ASC
        """

    async with pool.connection() as conn:
        cur = await conn.execute(sql, (empresa_id,))
        rows = await cur.fetchall()
    if com_users_count:
        return [_row_to_departamento(r[:-1], users_count=r[-1]) for r in rows]
    return [_row_to_departamento(r) for r in rows]


# ---- E2.B: hierarquia ----


async def get_descendant_ids(
    pool: AsyncConnectionPool,
    empresa_id: int,
    root_dep_ids: list[int],
) -> set[int]:
    """Resolve IDs descendentes (transitivos) de uma lista de departamentos.

    Inclui os roots passados. Usa recursive CTE pra explodir a árvore.
    Empresa scope no WHERE pra evitar leak entre tenants.
    """
    if not root_dep_ids:
        return set()

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            WITH RECURSIVE tree AS (
                SELECT id FROM departamento
                 WHERE empresa_id = %s AND id = ANY(%s)
                UNION
                SELECT d.id
                  FROM departamento d
                  JOIN tree t ON d.parent_id = t.id
                 WHERE d.empresa_id = %s
            )
            SELECT id FROM tree
            """,
            (empresa_id, list(root_dep_ids), empresa_id),
        )
        rows = await cur.fetchall()
    return {r[0] for r in rows}


# ---- E2.B: usuario_departamento (M:N) ----


async def list_user_departamento_ids(
    pool: AsyncConnectionPool, user_id: str, empresa_id: int
) -> list[int]:
    """IDs dos departamentos atribuídos diretamente ao user na empresa.

    Não inclui descendants — pra inferência de scope, combine com
    `get_descendant_ids` no caller.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT departamento_id
              FROM usuario_departamento
             WHERE user_id = %s AND empresa_id = %s
            """,
            (user_id, empresa_id),
        )
        rows = await cur.fetchall()
    return [r[0] for r in rows]


async def list_users_in_departamento(
    pool: AsyncConnectionPool, departamento_id: int, empresa_id: int
) -> list[dict]:
    """Lista users atribuídos ao departamento, com nome/email do auth.user."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT ud.user_id, u.email, u.name, ud.assigned_at
              FROM usuario_departamento ud
              LEFT JOIN auth."user" u ON u.id = ud.user_id
             WHERE ud.departamento_id = %s AND ud.empresa_id = %s
             ORDER BY u.name NULLS LAST
            """,
            (departamento_id, empresa_id),
        )
        rows = await cur.fetchall()
    return [
        {
            "user_id": r[0],
            "email": r[1],
            "name": r[2],
            "assigned_at": r[3].isoformat() if r[3] else None,
        }
        for r in rows
    ]


async def assign_user_to_departamento(
    pool: AsyncConnectionPool,
    *,
    user_id: str,
    departamento_id: int,
    empresa_id: int,
) -> bool:
    """Idempotente. Retorna True se inseriu, False se já existia."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO usuario_departamento (user_id, departamento_id, empresa_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, departamento_id, empresa_id) DO NOTHING
            """,
            (user_id, departamento_id, empresa_id),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0


async def unassign_user_from_departamento(
    pool: AsyncConnectionPool,
    *,
    user_id: str,
    departamento_id: int,
    empresa_id: int,
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            DELETE FROM usuario_departamento
             WHERE user_id = %s AND departamento_id = %s AND empresa_id = %s
            """,
            (user_id, departamento_id, empresa_id),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0


async def resolve_atendimento_scope(
    pool: AsyncConnectionPool,
    user_id: str,
    empresa_id: int,
) -> set[int] | None:
    """Resolve filtro de departamento_id pra atendimentos do user.

    Retorna:
    - None: user vê TODOS os atendimentos (sem scope ativo).
    - set vazio: user com scope mas sem departamento atribuído (vê NADA).
    - set com IDs: user só vê atendimentos cujo `departamento_id` ∈ set.

    O caller decide quando aplicar o filtro (geralmente SE
    `atendimento.scope.departamento` ∈ permissões do user).
    """
    direct = await list_user_departamento_ids(pool, user_id, empresa_id)
    if not direct:
        return set()
    return await get_descendant_ids(pool, empresa_id, direct)


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
    if data.parent_id is not None:
        # Valida que parent existe e é da mesma empresa (evita leak cross-tenant)
        parent = await get_departamento_by_id(pool, empresa_id, data.parent_id)
        if parent is None:
            raise ValueError(
                f"parent_id={data.parent_id} não existe nessa empresa"
            )
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                INSERT INTO departamento
                    (empresa_id, nome, descricao, ativo, created_by_user_id, parent_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING {_SELECT_COLS}
                """,
                (
                    empresa_id,
                    data.nome,
                    data.descricao,
                    data.ativo,
                    user_id,
                    data.parent_id,
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
    # Bloqueia ciclos: parent_id não pode ser o próprio dep_id nem um descendant
    if data.parent_id is not None:
        if data.parent_id == dep_id:
            raise ValueError("parent_id não pode ser o próprio departamento")
        descendants = await get_descendant_ids(pool, empresa_id, [dep_id])
        if data.parent_id in descendants:
            raise ValueError(
                "parent_id é descendente — criaria ciclo"
            )
        # Garante que parent existe + mesma empresa
        parent = await get_departamento_by_id(pool, empresa_id, data.parent_id)
        if parent is None:
            raise ValueError(
                f"parent_id={data.parent_id} não existe nessa empresa"
            )
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                UPDATE departamento
                   SET nome = %s,
                       descricao = %s,
                       ativo = %s,
                       parent_id = %s,
                       updated_at = NOW()
                 WHERE id = %s AND empresa_id = %s
                RETURNING {_SELECT_COLS}
                """,
                (
                    data.nome,
                    data.descricao,
                    data.ativo,
                    data.parent_id,
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
