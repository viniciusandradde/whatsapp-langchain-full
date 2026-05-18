"""CRUD de tags da empresa (Sprint Atendimento UX 1.2).

Tabela `tag` é da mig 052 — multi-tag por cliente (`cliente_tag_v2`).
Esta sprint amplia o uso pra atendimento via `atendimento_tag` (mig 086).

Permissões:
- `tag.manage` (Admin/Gestor): CRUD de tags da empresa
- `atendimento.tag.aplicar` (Operador+): aplicar/remover em atendimentos
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


async def list_tags(
    pool: AsyncConnectionPool, *, empresa_id: int, only_ativos: bool = True
) -> list[dict]:
    """Lista tags da empresa ordenadas por nome."""
    where = "WHERE empresa_id = %s"
    if only_ativos:
        where += " AND ativo = TRUE"
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT id, nome, cor, descricao, ativo,
                   created_at, updated_at
              FROM tag
              {where}
             ORDER BY nome ASC
            """,  # type: ignore[arg-type]
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "nome": r[1],
            "cor": r[2],
            "descricao": r[3],
            "ativo": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
            "updated_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


async def get_tag(
    pool: AsyncConnectionPool, *, tag_id: int, empresa_id: int
) -> dict | None:
    """Detalhe de uma tag da empresa (None se não é da empresa)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, nome, cor, descricao, ativo,
                   created_at, updated_at
              FROM tag
             WHERE id = %s AND empresa_id = %s
            """,
            (tag_id, empresa_id),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "nome": row[1],
        "cor": row[2],
        "descricao": row[3],
        "ativo": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
        "updated_at": row[6].isoformat() if row[6] else None,
    }


async def create_tag(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    nome: str,
    cor: str | None = None,
    descricao: str | None = None,
    created_by_user_id: str | None = None,
) -> dict:
    """Cria tag na empresa. UNIQUE (empresa_id, nome) — viola = exceção."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO tag (empresa_id, nome, cor, descricao, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, nome, cor, descricao, ativo, created_at, updated_at
            """,
            (empresa_id, nome, cor, descricao, created_by_user_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    logger.info("tag_created", empresa_id=empresa_id, tag_id=row[0], nome=nome)
    return {
        "id": row[0],
        "nome": row[1],
        "cor": row[2],
        "descricao": row[3],
        "ativo": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
        "updated_at": row[6].isoformat() if row[6] else None,
    }


async def update_tag(
    pool: AsyncConnectionPool,
    *,
    tag_id: int,
    empresa_id: int,
    nome: str | None = None,
    cor: str | None = None,
    descricao: str | None = None,
    ativo: bool | None = None,
) -> dict | None:
    """Atualiza tag da empresa. None se tag não pertence à empresa."""
    sets: list[str] = []
    args: list = []
    if nome is not None:
        sets.append("nome = %s")
        args.append(nome)
    if cor is not None:
        sets.append("cor = %s")
        args.append(cor)
    if descricao is not None:
        sets.append("descricao = %s")
        args.append(descricao)
    if ativo is not None:
        sets.append("ativo = %s")
        args.append(ativo)
    if not sets:
        return await get_tag(pool, tag_id=tag_id, empresa_id=empresa_id)
    sets.append("updated_at = NOW()")
    args.extend([tag_id, empresa_id])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE tag SET {', '.join(sets)}
             WHERE id = %s AND empresa_id = %s
             RETURNING id, nome, cor, descricao, ativo,
                       created_at, updated_at
            """,  # type: ignore[arg-type]
            tuple(args),
        )
        row = await cur.fetchone()
        await conn.commit()
    if row is None:
        return None
    return {
        "id": row[0],
        "nome": row[1],
        "cor": row[2],
        "descricao": row[3],
        "ativo": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
        "updated_at": row[6].isoformat() if row[6] else None,
    }


async def delete_tag(
    pool: AsyncConnectionPool, *, tag_id: int, empresa_id: int
) -> bool:
    """Hard delete da tag (CASCADE: remove de atendimento_tag e cliente_tag_v2).

    Retorna False se tag não é da empresa.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            DELETE FROM tag WHERE id = %s AND empresa_id = %s
             RETURNING id
            """,
            (tag_id, empresa_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    return row is not None
