"""Helpers de Atendimento — fila estruturada de conversas (M3 CRM Light).

Cada inbound resolve um `atendimento` aberto por (empresa, cliente, conexão)
via `open_or_attach_atendimento`. Política:

- Se já existe um aberto (status `aguardando` ou `em_andamento`), **anexa**
  (atualiza `last_message_at` e retorna o id existente).
- Senão, **abre** um novo com status `aguardando`.
- Status final (`resolvido`/`abandonado`) sai do índice parcial único, então
  o próximo inbound abre um atendimento novo.

Painel: `list_atendimentos` aplica 4 tipos de visualização derivados em
runtime — "meus" (atribuídos ao operador), "aguardando" (sem dono),
"grupos" (futuro — placeholder vazio) e "outros" (catch-all dos abertos).
"""

from __future__ import annotations

from typing import Literal

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Atendimento

logger = structlog.get_logger()


_BASE_COLS = (
    "a.id, a.empresa_id, a.cliente_id, a.conexao_id, a.agente_atual, "
    "a.status, a.assigned_to_user_id, a.last_message_at, a.closed_at, "
    "a.created_at, a.updated_at"
)
_JOIN_COLS = f"{_BASE_COLS}, c.nome, c.telefone"


def _row_to_atendimento(row, *, with_cliente: bool = False) -> Atendimento:
    return Atendimento(
        id=row[0],
        empresa_id=row[1],
        cliente_id=row[2],
        conexao_id=row[3],
        agente_atual=row[4],
        status=row[5],
        assigned_to_user_id=row[6],
        last_message_at=row[7],
        closed_at=row[8],
        created_at=row[9],
        updated_at=row[10],
        cliente_nome=row[11] if with_cliente else None,
        cliente_telefone=row[12] if with_cliente else None,
    )


async def open_or_attach_atendimento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    conexao_id: int,
    *,
    agente: str = "vsa_tech",
) -> Atendimento:
    """Abre novo atendimento ou anexa ao já-aberto (fluxo do webhook).

    Usa o índice parcial `idx_atendimento_aberto_unique` (empresa+cliente+conexao
    WHERE status IN aguardando|em_andamento) pra garantir 1 atendimento aberto
    por tupla. Quando já existe, atualiza `last_message_at` e retorna o id
    existente em uma transação curta.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_BASE_COLS} FROM atendimento a
             WHERE a.empresa_id = %s
               AND a.cliente_id = %s
               AND a.conexao_id = %s
               AND a.status IN ('aguardando', 'em_andamento')
             FOR UPDATE
            """,
            (empresa_id, cliente_id, conexao_id),
        )
        row = await cur.fetchone()
        if row:
            cur = await conn.execute(
                f"""
                UPDATE atendimento
                   SET last_message_at = NOW(), updated_at = NOW()
                 WHERE id = %s
                RETURNING {_BASE_COLS}
                """,
                (row[0],),
            )
            updated = await cur.fetchone()
            assert updated is not None
            return _row_to_atendimento(updated)

        cur = await conn.execute(
            f"""
            INSERT INTO atendimento (empresa_id, cliente_id, conexao_id, agente_atual)
            VALUES (%s, %s, %s, %s)
            RETURNING {_BASE_COLS}
            """,
            (empresa_id, cliente_id, conexao_id, agente),
        )
        new = await cur.fetchone()
    assert new is not None
    return _row_to_atendimento(new)


TipoVisualizacao = Literal["meus", "aguardando", "grupos", "outros"]


async def list_atendimentos(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    tipo: TipoVisualizacao,
    current_user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Atendimento]:
    """Lista atendimentos filtrados por tipo de visualização.

    - `meus`: status='em_andamento' AND assigned_to_user_id=current_user_id
    - `aguardando`: status='aguardando'
    - `grupos`: placeholder (vazio até M-grupos chegar)
    - `outros`: status IN aguardando|em_andamento, fora dos meus

    Faz LEFT JOIN com cliente pra preencher nome/telefone na resposta.
    """
    if tipo == "grupos":
        return []

    where = "WHERE a.empresa_id = %s"
    params: list = [empresa_id]

    if tipo == "meus":
        if not current_user_id:
            return []
        where += " AND a.status = 'em_andamento' AND a.assigned_to_user_id = %s"
        params.append(current_user_id)
    elif tipo == "aguardando":
        where += " AND a.status = 'aguardando'"
    else:  # outros
        where += " AND a.status IN ('aguardando', 'em_andamento')"
        if current_user_id:
            where += (
                " AND (a.assigned_to_user_id IS NULL OR a.assigned_to_user_id <> %s)"
            )
            params.append(current_user_id)

    params.extend([limit, offset])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_JOIN_COLS}
              FROM atendimento a
              LEFT JOIN cliente c ON c.id = a.cliente_id
            {where}
            ORDER BY a.last_message_at DESC, a.id DESC
            LIMIT %s OFFSET %s
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_atendimento(r, with_cliente=True) for r in rows]


async def get_atendimento_by_id(
    pool: AsyncConnectionPool, atendimento_id: int
) -> Atendimento | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_JOIN_COLS}
              FROM atendimento a
              LEFT JOIN cliente c ON c.id = a.cliente_id
             WHERE a.id = %s
            """,
            (atendimento_id,),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row, with_cliente=True) if row else None


async def claim_atendimento(
    pool: AsyncConnectionPool, atendimento_id: int, user_id: str
) -> Atendimento | None:
    """Operador "puxa" o atendimento. status → em_andamento, assigned → user."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET status = 'em_andamento',
                   assigned_to_user_id = %s,
                   updated_at = NOW()
             WHERE id = %s AND status IN ('aguardando', 'em_andamento')
            RETURNING {_BASE_COLS}
            """,
            (user_id, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


async def close_atendimento(
    pool: AsyncConnectionPool,
    atendimento_id: int,
    status: Literal["resolvido", "abandonado"] = "resolvido",
) -> Atendimento | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET status = %s, closed_at = NOW(), updated_at = NOW()
             WHERE id = %s
            RETURNING {_BASE_COLS}
            """,
            (status, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


async def transfer_atendimento(
    pool: AsyncConnectionPool, atendimento_id: int, new_user_id: str
) -> Atendimento | None:
    """Transfere o atendimento para outro operador (mantém em_andamento)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET assigned_to_user_id = %s,
                   status = 'em_andamento',
                   updated_at = NOW()
             WHERE id = %s
            RETURNING {_BASE_COLS}
            """,
            (new_user_id, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None
