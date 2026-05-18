"""M:N atendimento × tag (Sprint Atendimento UX 1.2, mig 086).

Pode ser aplicada por:
- Humano: atendente clica no popover (aplicado_por_user_id setado)
- IA: triagem mapeia classificacao→tag.nome ILIKE (aplicado_por_ia=TRUE)
- Workflow: node de workflow LangGraph (futuro)

Sempre escopado por empresa_id (RBAC enforce via FK e query WHERE).
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


async def list_tags_de_atendimento(
    pool: AsyncConnectionPool, *, atendimento_id: int, empresa_id: int
) -> list[dict]:
    """Lista tags aplicadas em um atendimento, com origem (humano/IA)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT t.id, t.nome, t.cor, t.descricao,
                   at.aplicado_por_user_id, at.aplicado_por_ia, at.aplicado_at
              FROM atendimento_tag at
              JOIN tag t ON t.id = at.tag_id
             WHERE at.atendimento_id = %s
               AND at.empresa_id = %s
             ORDER BY at.aplicado_at ASC
            """,
            (atendimento_id, empresa_id),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "nome": r[1],
            "cor": r[2],
            "descricao": r[3],
            "aplicado_por_user_id": r[4],
            "aplicado_por_ia": r[5],
            "aplicado_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


async def apply_tags_to_atendimento(
    pool: AsyncConnectionPool,
    *,
    atendimento_id: int,
    empresa_id: int,
    add_tag_ids: list[int],
    remove_tag_ids: list[int],
    aplicado_por_user_id: str | None = None,
    aplicado_por_ia: bool = False,
) -> dict:
    """Aplica delta de tags em um atendimento (add + remove).

    Valida que:
    - Atendimento é da empresa.
    - Cada tag em add_tag_ids é da empresa (silenciosamente ignora alheias).

    `aplicado_por_user_id`/`aplicado_por_ia` ficam nas linhas inseridas.
    Retorna `{added: int, removed: int}`.
    """
    added = 0
    removed = 0
    async with pool.connection() as conn:
        # Confirma atendimento da empresa
        cur = await conn.execute(
            "SELECT 1 FROM atendimento WHERE id = %s AND empresa_id = %s",
            (atendimento_id, empresa_id),
        )
        if (await cur.fetchone()) is None:
            return {"added": 0, "removed": 0, "ok": False}

        # Remove primeiro (idempotente, sem erro se já removida)
        if remove_tag_ids:
            cur = await conn.execute(
                """
                DELETE FROM atendimento_tag
                 WHERE atendimento_id = %s
                   AND empresa_id = %s
                   AND tag_id = ANY(%s)
                """,
                (atendimento_id, empresa_id, list(remove_tag_ids)),
            )
            removed = cur.rowcount or 0

        # Adiciona — filtra IDs que pertencem à empresa
        if add_tag_ids:
            cur = await conn.execute(
                """
                INSERT INTO atendimento_tag (atendimento_id, tag_id, empresa_id,
                                              aplicado_por_user_id,
                                              aplicado_por_ia)
                SELECT %s, t.id, %s, %s, %s
                  FROM tag t
                 WHERE t.id = ANY(%s)
                   AND t.empresa_id = %s
                   AND t.ativo = TRUE
                ON CONFLICT DO NOTHING
                """,
                (
                    atendimento_id,
                    empresa_id,
                    aplicado_por_user_id,
                    aplicado_por_ia,
                    list(add_tag_ids),
                    empresa_id,
                ),
            )
            added = cur.rowcount or 0
        await conn.commit()
    logger.info(
        "atendimento_tags_aplicadas",
        atendimento_id=atendimento_id,
        added=added,
        removed=removed,
        por_ia=aplicado_por_ia,
    )
    return {"added": added, "removed": removed, "ok": True}


async def list_atendimento_ids_com_tags(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    tag_ids: list[int],
) -> list[int]:
    """Retorna IDs de atendimentos que têm QUALQUER uma das tags (OR).

    Usado pra filtro na lista de atendimentos. Filtro é OR — atendimento
    com pelo menos 1 das tags solicitadas. Multi-AND fica pra evolução.
    """
    if not tag_ids:
        return []
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT DISTINCT atendimento_id
              FROM atendimento_tag
             WHERE empresa_id = %s
               AND tag_id = ANY(%s)
            """,
            (empresa_id, list(tag_ids)),
        )
        rows = await cur.fetchall()
    return [r[0] for r in rows]
