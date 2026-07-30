"""Abas pessoais do painel de atendimento — FILTRO SALVO POR CLIENTE.

A aba agrupa **clientes**, não conversas: "Mackenzie" é o conjunto de pessoas
daquela instituição, e toda conversa delas aparece na pasta automaticamente. O
critério vive em `aba.filtro` (JSONB da mig 050), no formato
`{"cliente_tags": ["Mackenzie", "Unigran"]}`.

**Por que deixou de ser pinagem manual.** A mig 085 acrescentou
`atendimento.aba_id` para pinar conversa a conversa, e nenhuma tela chegou a
oferecer isso — em produção havia 6 abas criadas e ZERO conversas dentro. Mesmo
com o botão, o modelo não se sustentaria: cada nova conversa do mesmo cliente
nasceria fora da pasta, e o operador teria que re-pinar para sempre. A coluna
`aba_id` fica no schema (nada a migrar) mas não é mais lida pela listagem.

Abas são SEMPRE do próprio user — RBAC na query (`WHERE user_id = %s`), e é isso
que também fecha o furo antigo: a listagem filtrava `AND a.aba_id = %s` sem
checar posse, então bastava chutar o número para ler a pasta de outro operador.
Permissão `atendimento.aba.manage` libera o CRUD.
"""

from __future__ import annotations

import json

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
            SELECT id, nome, cor, ordem, ativo, created_at, updated_at, filtro
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
            "filtro": r[7] or {},
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
    cliente_tags: list[str] | None = None,
) -> dict:
    """Cria aba pessoal pro user. `descricao` vai pra coluna `nome`.

    `cliente_tags` é o CRITÉRIO: a aba mostra as conversas dos clientes
    marcados com essas tags. Sem critério a aba nasce vazia — e é isso que se
    quer, porque mostrar tudo faria a pasta recém-criada parecer cheia de
    trabalho que não é dela.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO aba (
                empresa_id, user_id, nome, cor, ordem,
                created_by_user_id, filtro
            )
            VALUES (%s, %s, %s, %s,
                    COALESCE(
                        (SELECT MAX(ordem) + 1 FROM aba WHERE user_id = %s),
                        0
                    ),
                    %s, %s::jsonb)
            RETURNING id, nome, cor, ordem, ativo, created_at, updated_at, filtro
            """,
            (
                empresa_id,
                user_id,
                descricao,
                cor,
                user_id,
                user_id,
                json.dumps({"cliente_tags": list(cliente_tags or [])}),
            ),
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
        "filtro": (row[7] if len(row) > 7 else None) or {},
    }


async def update_aba(
    pool: AsyncConnectionPool,
    *,
    aba_id: int,
    user_id: str,
    descricao: str | None = None,
    cor: str | None = None,
    icone: str | None = None,  # noqa: ARG001 — sem coluna no banco MVP
    cliente_tags: list[str] | None = None,
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
    if cliente_tags is not None:
        sets.append("filtro = %s::jsonb")
        args.append(json.dumps({"cliente_tags": list(cliente_tags)}))
    if not sets:
        return await get_aba(pool, aba_id=aba_id, user_id=user_id)
    sets.append("updated_at = NOW()")
    args.extend([aba_id, user_id])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE aba SET {", ".join(sets)}
             WHERE id = %s AND user_id = %s AND ativo = TRUE
             RETURNING id, nome, cor, ordem, ativo, created_at, updated_at, filtro
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
        "filtro": (row[7] if len(row) > 7 else None) or {},
    }


async def delete_aba(pool: AsyncConnectionPool, *, aba_id: int, user_id: str) -> bool:
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
            SELECT id, nome, cor, ordem, ativo, created_at, updated_at, filtro
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
        "filtro": row[7] or {},
    }


async def cliente_ids_da_aba(
    pool: AsyncConnectionPool, *, filtro: dict, empresa_id: int
) -> list[int] | None:
    """Clientes que casam com o filtro da aba.

    A aba agrupa **clientes**, não conversas: "Mackenzie" é o conjunto de
    pessoas daquela instituição, e toda conversa delas entra sozinha. Pinar
    conversa a conversa nunca funcionaria — em produção havia 6 abas criadas e
    ZERO conversas dentro, porque cada nova conversa do mesmo cliente começaria
    fora da pasta.

    O critério vive em `aba.filtro` (JSONB), coluna criada na mig 050 justamente
    pra isso e até agora sem uso.

    Usa `cliente_tag`, onde `POST /api/clientes/{id}/tags` grava e de onde
    `Cliente.tags` lê. Havia uma segunda tabela (`cliente_tag_v2`, com FK) que
    este filtro chegou a usar por engano — órfã, sem nenhuma escrita, teria dado
    pasta sempre vazia com o operador marcando o cliente e nada acontecendo.
    Removida na mig 149.

    Returns:
        Lista de `cliente_id`, possivelmente vazia (aba sem nenhum cliente).
        `None` quando a aba não tem critério — o chamador não deve filtrar,
        senão uma aba recém-criada esconderia tudo em vez de mostrar tudo.
    """
    tags = filtro.get("cliente_tags") or []
    if not tags:
        return None

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT DISTINCT ct.cliente_id
              FROM cliente_tag ct
              JOIN cliente c ON c.id = ct.cliente_id
             WHERE ct.tag = ANY(%s) AND c.empresa_id = %s
            """,
            (list(tags), empresa_id),
        )
        rows = await cur.fetchall()
    return [r[0] for r in rows]


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

    Conta pelo CRITÉRIO da aba (clientes marcados com as tags dela), não por
    `atendimento.aba_id`. Aba sem critério conta zero: mostrar o total da empresa
    numa pasta recém-criada faria o número dizer "há trabalho aqui" quando não
    há nada configurado.

    Uma query só, com LATERAL: uma por aba faria N idas ao banco a cada 30s do
    polling da sidebar.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT ab.id, COUNT(a.id)
              FROM aba ab
              LEFT JOIN LATERAL (
                  SELECT at.id
                    FROM atendimento at
                   WHERE at.empresa_id = %s
                     AND at.status IN ('aguardando', 'em_andamento')
                     AND at.cliente_id IN (
                         SELECT ct.cliente_id FROM cliente_tag ct
                          WHERE ct.tag = ANY(
                              SELECT jsonb_array_elements_text(
                                  COALESCE(ab.filtro->'cliente_tags', '[]'::jsonb)
                              )
                          )
                     )
              ) a ON TRUE
             WHERE ab.user_id = %s AND ab.empresa_id = %s AND ab.ativo = TRUE
             GROUP BY ab.id
            """,
            (empresa_id, user_id, empresa_id),
        )
        rows = await cur.fetchall()
    return {r[0]: r[1] for r in rows}
