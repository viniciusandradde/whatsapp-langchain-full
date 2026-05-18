"""CRUD de abas pessoais no painel de atendimento (Sprint 1.1).

A tabela `aba` foi criada na mig 050 com esquema de "filtro salvo".
Esta sprint reusa a tabela com semântica de "pasta pessoal" (estilo
ZigChat) — `aba.user_id NOT NULL` indica abas pessoais, atendimentos
são atribuídos via `atendimento.aba_id` (pinning manual, mig 085).

Abas são SEMPRE do próprio user — RBAC enforce na query
(WHERE user_id = %s). Permissão `atendimento.aba.manage` libera o CRUD.
O `filtro JSONB` da mig 050 fica disponível pra evolução futura mas o
MVP não usa.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


async def list_abas(
    pool: AsyncConnectionPool, *, user_id: str, empresa_id: int
) -> list[dict]:
    """Lista abas pessoais ativas do user (ordenadas por `ordem` ASC).

    `nome` da tabela é exposto como `descricao` no payload pra UI ficar
    independente do schema legacy.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, nome, cor, ordem, ativo, created_at, updated_at
              FROM aba
             WHERE user_id = %s AND empresa_id = %s AND ativo = TRUE
             ORDER BY ordem ASC NULLS LAST, id ASC
            """,
            (user_id, empresa_id),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "descricao": r[1],  # alias de nome
            "cor": r[2],
            "icone": None,  # mig 050 não tem coluna icone
            "ordem": r[3] or 0,
            "ativo": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
            "updated_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


async def create_aba(
    pool: AsyncConnectionPool,
    *,
    user_id: str,
    empresa_id: int,
    descricao: str,
    cor: str | None = None,
    icone: str | None = None,  # noqa: ARG001 — sem coluna no banco MVP
) -> dict:
    """Cria aba pessoal pro user. `descricao` vai pra coluna `nome`."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO aba (
                empresa_id, user_id, nome, cor, ordem,
                created_by_user_id
            )
            VALUES (%s, %s, %s, %s,
                    COALESCE(
                        (SELECT MAX(ordem) + 1 FROM aba WHERE user_id = %s),
                        0
                    ),
                    %s)
            RETURNING id, nome, cor, ordem, ativo, created_at, updated_at
            """,
            (empresa_id, user_id, descricao, cor, user_id, user_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    logger.info("aba_created", user_id=user_id, aba_id=row[0], nome=descricao)
    return {
        "id": row[0],
        "descricao": row[1],
        "cor": row[2],
        "icone": None,
        "ordem": row[3] or 0,
        "ativo": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
        "updated_at": row[6].isoformat() if row[6] else None,
    }


async def update_aba(
    pool: AsyncConnectionPool,
    *,
    aba_id: int,
    user_id: str,
    descricao: str | None = None,
    cor: str | None = None,
    icone: str | None = None,  # noqa: ARG001 — sem coluna no banco MVP
) -> dict | None:
    """Atualiza aba pessoal do user. None se aba não é do user ou inativa."""
    sets: list[str] = []
    args: list = []
    if descricao is not None:
        sets.append("nome = %s")
        args.append(descricao)
    if cor is not None:
        sets.append("cor = %s")
        args.append(cor)
    if not sets:
        return await get_aba(pool, aba_id=aba_id, user_id=user_id)
    sets.append("updated_at = NOW()")
    args.extend([aba_id, user_id])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE aba SET {', '.join(sets)}
             WHERE id = %s AND user_id = %s AND ativo = TRUE
             RETURNING id, nome, cor, ordem, ativo, created_at, updated_at
            """,  # type: ignore[arg-type]
            tuple(args),
        )
        row = await cur.fetchone()
        await conn.commit()
    if row is None:
        return None
    return {
        "id": row[0],
        "descricao": row[1],
        "cor": row[2],
        "icone": None,
        "ordem": row[3] or 0,
        "ativo": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
        "updated_at": row[6].isoformat() if row[6] else None,
    }


async def delete_aba(
    pool: AsyncConnectionPool, *, aba_id: int, user_id: str
) -> bool:
    """Soft delete (ativo=FALSE) + limpa pinning dos atendimentos.

    Retorna False se aba não é do user."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE aba SET ativo = FALSE, updated_at = NOW()
             WHERE id = %s AND user_id = %s AND ativo = TRUE
             RETURNING id
            """,
            (aba_id, user_id),
        )
        row = await cur.fetchone()
        if row:
            await conn.execute(
                "UPDATE atendimento SET aba_id = NULL WHERE aba_id = %s",
                (aba_id,),
            )
        await conn.commit()
    return row is not None


async def get_aba(
    pool: AsyncConnectionPool, *, aba_id: int, user_id: str
) -> dict | None:
    """Detalhe de uma aba pessoal do user (None se não é dele ou inativa)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, nome, cor, ordem, ativo, created_at, updated_at
              FROM aba
             WHERE id = %s AND user_id = %s AND ativo = TRUE
            """,
            (aba_id, user_id),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "descricao": row[1],
        "cor": row[2],
        "icone": None,
        "ordem": row[3] or 0,
        "ativo": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
        "updated_at": row[6].isoformat() if row[6] else None,
    }


async def reorder_abas(
    pool: AsyncConnectionPool, *, user_id: str, ordered_ids: list[int]
) -> int:
    """Atualiza `ordem` baseado na posição em `ordered_ids`.

    Só toca abas pessoais do user (ignora silenciosamente IDs alheios)."""
    if not ordered_ids:
        return 0
    async with pool.connection() as conn:
        count = 0
        for idx, aba_id in enumerate(ordered_ids):
            cur = await conn.execute(
                """
                UPDATE aba SET ordem = %s, updated_at = NOW()
                 WHERE id = %s AND user_id = %s AND ativo = TRUE
                 RETURNING id
                """,
                (idx, aba_id, user_id),
            )
            if await cur.fetchone():
                count += 1
        await conn.commit()
    return count


async def attach_atendimento_to_aba(
    pool: AsyncConnectionPool,
    *,
    atendimento_id: int,
    aba_id: int | None,
    user_id: str,
    empresa_id: int,
) -> bool:
    """Atribui atendimento a aba pessoal do user (ou desatribui se aba_id=None).

    Valida:
    - Atendimento existe e é da empresa.
    - Se aba_id != None: aba é do mesmo user.

    Retorna False se algo não bate.
    """
    if aba_id is not None:
        aba = await get_aba(pool, aba_id=aba_id, user_id=user_id)
        if aba is None:
            return False
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE atendimento SET aba_id = %s, updated_at = NOW()
             WHERE id = %s AND empresa_id = %s
             RETURNING id
            """,
            (aba_id, atendimento_id, empresa_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    return row is not None


async def count_atendimentos_por_aba(
    pool: AsyncConnectionPool, *, user_id: str, empresa_id: int
) -> dict[int, int]:
    """Retorna {aba_id: count} pras abas pessoais ativas do user.

    Atendimentos `resolvido` / `abandonado` não contam (foco em workload ativo).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT a.aba_id, COUNT(*)
              FROM atendimento a
             WHERE a.empresa_id = %s
               AND a.aba_id IN (
                   SELECT id FROM aba
                    WHERE user_id = %s AND ativo = TRUE
               )
               AND a.status IN ('aguardando', 'em_andamento')
             GROUP BY a.aba_id
            """,
            (empresa_id, user_id),
        )
        rows = await cur.fetchall()
    return {r[0]: r[1] for r in rows}
