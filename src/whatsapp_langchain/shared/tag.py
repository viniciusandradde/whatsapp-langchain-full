"""CRUD de tags da empresa (Sprint Atendimento UX 1.2).

Tabela `tag` é da mig 052. Vocabulário compartilhado: as mesmas tags são
aplicadas em atendimento (`atendimento_tag`) e em cliente (`cliente_tag`).
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


async def list_opcoes_de_aba(
    pool: AsyncConnectionPool, *, empresa_id: int
) -> list[dict]:
    """Tags que a aba pode usar como critério: catálogo ∪ tags já nos clientes.

    Só o catálogo (`tag`) não serve. Quem marca cliente não é só o operador: a
    triagem do agente grava direto em `cliente_tag`, que guarda o NOME em texto
    livre e não exige cadastro. Em produção isso deixou as maiores agregações
    fora do alcance da aba — 21 clientes com `handoff` numa empresa onde
    `handoff` não está no catálogo, contra 2 na maior tag cadastrada.

    Oferecer só o catálogo repetiria o defeito que a mig 149 removeu: pasta que
    o operador configura e que nunca se enche, sem erro na tela.

    Ordenado por nº de clientes: a opção que agrupa mais gente vem primeiro.

    Returns:
        `[{"nome", "cor", "clientes", "no_catalogo"}]`. `cor` é None nas tags
        que só existem em `cliente_tag` (não têm cadastro de onde tirar cor).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            WITH cat AS (
                SELECT id, nome, cor FROM tag
                 WHERE empresa_id = %s AND ativo = TRUE
            ), uso AS (
                SELECT ct.tag AS nome, COUNT(DISTINCT ct.cliente_id) AS clientes
                  FROM cliente_tag ct
                  JOIN cliente c ON c.id = ct.cliente_id
                 WHERE c.empresa_id = %s
                 GROUP BY ct.tag
            )
            SELECT COALESCE(cat.nome, uso.nome) AS nome,
                   cat.cor,
                   COALESCE(uso.clientes, 0) AS clientes,
                   (cat.id IS NOT NULL) AS no_catalogo
              FROM cat
              FULL OUTER JOIN uso ON uso.nome = cat.nome
             ORDER BY clientes DESC, nome ASC
            """,
            # Os dois lados são filtrados por empresa ANTES do FULL OUTER JOIN.
            # Filtrar depois, no WHERE, descartaria a linha de uso que casasse
            # com uma tag homônima de outra empresa — o nome não é único global.
            (empresa_id, empresa_id),
        )
        rows = await cur.fetchall()
    return [
        {"nome": r[0], "cor": r[1], "clientes": r[2], "no_catalogo": r[3]} for r in rows
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
            UPDATE tag SET {", ".join(sets)}
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
    """Hard delete da tag, limpando também os clientes que a tinham.

    `atendimento_tag` some por CASCADE (tem FK). `cliente_tag` **não tem FK** —
    guarda o NOME em texto livre —, então precisa de DELETE explícito. Sem ele a
    tag sumia do catálogo e continuava colada nos clientes: invisível na UI de
    tags, viva na ficha de cada pessoa, e ainda capaz de alimentar a aba que
    filtrasse por aquele nome.

    Escopo por empresa nos DOIS lados: o nome da tag é livre, então "Financeiro"
    de uma empresa não pode limpar o "Financeiro" de outra.

    Retorna False se a tag não é da empresa.
    """
    async with pool.connection() as conn:
        # Nome ANTES de apagar — depois do DELETE não há de onde tirá-lo.
        cur = await conn.execute(
            "SELECT nome FROM tag WHERE id = %s AND empresa_id = %s",
            (tag_id, empresa_id),
        )
        achada = await cur.fetchone()
        if achada is None:
            return False
        nome = achada[0]

        cur = await conn.execute(
            """
            DELETE FROM tag WHERE id = %s AND empresa_id = %s
             RETURNING id
            """,
            (tag_id, empresa_id),
        )
        row = await cur.fetchone()
        if row is not None:
            cur = await conn.execute(
                """
                DELETE FROM cliente_tag ct
                 USING cliente c
                 WHERE ct.cliente_id = c.id
                   AND c.empresa_id = %s
                   AND ct.tag = %s
                """,
                (empresa_id, nome),
            )
            logger.info(
                "tag_removida_dos_clientes",
                empresa_id=empresa_id,
                tag=nome,
                clientes_afetados=cur.rowcount,
            )
        await conn.commit()
    return row is not None
