"""CRUD de agendamentos espelhados do Google Calendar (S2 Calendar v2).

Source-of-truth interno. `calendar_integration.create_event` insere aqui
ANTES de chamar o Google e atualiza com `evento_id_externo` retornado.
Em caso de falha do Google, marca `status='cancelado'` (drift compensado)
e dispara warning estruturado.

Padrão segue `shared/cliente.py` e outros módulos de domínio.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Final

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Agendamento

logger = structlog.get_logger()


VALID_STATUS: Final[frozenset[str]] = frozenset(
    {"pendente", "confirmado", "cancelado"}
)

_SELECT_COLS = (
    "id, empresa_id, calendar_id, user_id_criador, cliente_id, "
    "evento_id_externo, summary, descricao, data_inicio, data_fim, "
    "status, aprovado, gestor_notificado, payload_externo, "
    "created_at, updated_at"
)


def _row_to_agendamento(row) -> Agendamento:
    return Agendamento(
        id=row[0],
        empresa_id=row[1],
        calendar_id=row[2],
        user_id_criador=row[3],
        cliente_id=row[4],
        evento_id_externo=row[5],
        summary=row[6],
        descricao=row[7],
        data_inicio=row[8],
        data_fim=row[9],
        status=row[10],
        aprovado=row[11],
        gestor_notificado=row[12],
        payload_externo=row[13] or {},
        created_at=row[14],
        updated_at=row[15],
    )


async def create(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    calendar_id: str,
    summary: str,
    data_inicio: datetime,
    data_fim: datetime,
    user_id_criador: str | None = None,
    cliente_id: int | None = None,
    descricao: str | None = None,
    status: str = "confirmado",
    aprovado: bool = True,
) -> Agendamento:
    """Cria row em `agendamento`. Retorna o objeto persistido."""
    if status not in VALID_STATUS:
        raise ValueError(f"status inválido: {status!r}")

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO agendamento
                (empresa_id, calendar_id, user_id_criador, cliente_id,
                 summary, descricao, data_inicio, data_fim, status, aprovado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_SELECT_COLS}
            """,
            (
                empresa_id,
                calendar_id,
                user_id_criador,
                cliente_id,
                summary,
                descricao,
                data_inicio,
                data_fim,
                status,
                aprovado,
            ),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    return _row_to_agendamento(row)


async def get_by_id(
    pool: AsyncConnectionPool, agendamento_id: int, empresa_id: int
) -> Agendamento | None:
    """Busca por id, escopado por empresa pra anti-tenant escape."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS}
              FROM agendamento
             WHERE id = %s AND empresa_id = %s
            """,
            (agendamento_id, empresa_id),
        )
        row = await cur.fetchone()
    return _row_to_agendamento(row) if row else None


async def list_by_period(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    inicio: datetime,
    fim: datetime,
    status: str | None = None,
    cliente_id: int | None = None,
    limit: int = 100,
) -> list[Agendamento]:
    """Lista agendamentos da empresa cuja data_inicio está em [inicio, fim].

    Filtros opcionais: `status`, `cliente_id`. Ordenado por data_inicio asc.
    """
    where = ["empresa_id = %s", "data_inicio >= %s", "data_inicio <= %s"]
    params: list = [empresa_id, inicio, fim]
    if status:
        if status not in VALID_STATUS:
            raise ValueError(f"status inválido: {status!r}")
        where.append("status = %s")
        params.append(status)
    if cliente_id is not None:
        where.append("cliente_id = %s")
        params.append(cliente_id)
    params.append(limit)

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS}
              FROM agendamento
             WHERE {" AND ".join(where)}
             ORDER BY data_inicio ASC
             LIMIT %s
            """,
            params,
        )
        rows = await cur.fetchall()
    return [_row_to_agendamento(r) for r in rows]


async def update_external_event(
    pool: AsyncConnectionPool,
    agendamento_id: int,
    *,
    evento_id_externo: str,
    payload_externo: dict,
) -> None:
    """Atualiza com o id retornado pelo Google e snapshot do payload.

    Chamado logo após `events.insert` retornar com sucesso.
    """
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE agendamento
               SET evento_id_externo = %s,
                   payload_externo = %s::jsonb,
                   updated_at = NOW()
             WHERE id = %s
            """,
            (evento_id_externo, json.dumps(payload_externo), agendamento_id),
        )
        await conn.commit()


async def update_status(
    pool: AsyncConnectionPool,
    agendamento_id: int,
    empresa_id: int,
    *,
    status: str,
) -> bool:
    """Muda status (ex: confirmado → cancelado). Retorna True se afetou row."""
    if status not in VALID_STATUS:
        raise ValueError(f"status inválido: {status!r}")

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE agendamento
               SET status = %s, updated_at = NOW()
             WHERE id = %s AND empresa_id = %s
            """,
            (status, agendamento_id, empresa_id),
        )
        await conn.commit()
        return cur.rowcount > 0


async def cancel_local(
    pool: AsyncConnectionPool, agendamento_id: int, empresa_id: int
) -> bool:
    """Atalho pra `update_status(... 'cancelado')`."""
    return await update_status(
        pool, agendamento_id, empresa_id, status="cancelado"
    )


async def get_by_external_id(
    pool: AsyncConnectionPool, empresa_id: int, evento_id_externo: str
) -> Agendamento | None:
    """Lookup por Google event id — usado em S5 pra reconciliar drift."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS}
              FROM agendamento
             WHERE empresa_id = %s AND evento_id_externo = %s
             LIMIT 1
            """,
            (empresa_id, evento_id_externo),
        )
        row = await cur.fetchone()
    return _row_to_agendamento(row) if row else None
