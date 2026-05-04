"""Helpers de Hook (webhooks configuráveis) — M4.d.

CRUD da tabela `hook` e leitura de `hook_log`. O dispatcher
(`shared/hook_dispatcher.py`) usa `list_hooks_for_dispatch` para resolver
quais URLs disparar pra cada evento.
"""

from __future__ import annotations

from typing import Final

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Hook, HookInput, HookLog

logger = structlog.get_logger()


EVENTOS_VALIDOS: Final[frozenset[str]] = frozenset(
    {
        "mensagem.recebida",
        "atendimento.aberto",
        "atendimento.atendido",
        "atendimento.fechado",
        "atendimento.transferido",
        # S2 Calendar v2: dispatch quando agente/operador cria ou cancela
        # agendamento. Permite integração com sistemas externos
        # (Slack, ERP, BI) via webhook configurável em /hooks.
        "agendamento.criado",
        "agendamento.cancelado",
        # S4 Calendar v2: dispatch quando gestor aprova ou rejeita pedido
        # via WhatsApp (regex APROVAR/REJEITAR <token> em processor.py).
        "agendamento.aprovado",
        "agendamento.rejeitado",
    }
)


_SELECT_COLS = (
    "id, empresa_id, nome, evento, url, secret, ativo, "
    "created_by_user_id, created_at, updated_at"
)


def _row_to_hook(row) -> Hook:
    return Hook(
        id=row[0],
        empresa_id=row[1],
        nome=row[2],
        evento=row[3],
        url=row[4],
        secret=row[5],
        ativo=row[6],
        created_by_user_id=row[7],
        created_at=row[8],
        updated_at=row[9],
    )


async def list_hooks(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    evento: str | None = None,
) -> list[Hook]:
    """Lista hooks (ativos e inativos) — uso da UI."""
    params: list = [empresa_id]
    where = "WHERE empresa_id = %s"
    if evento:
        where += " AND evento = %s"
        params.append(evento)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM hook
            {where}
            ORDER BY evento ASC, nome ASC, id ASC
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_hook(r) for r in rows]


async def list_hooks_for_dispatch(
    pool: AsyncConnectionPool, empresa_id: int, evento: str
) -> list[Hook]:
    """Lookup do dispatcher: só hooks ativos pra um evento específico."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM hook
             WHERE empresa_id = %s AND evento = %s AND ativo = TRUE
             ORDER BY id ASC
            """,
            (empresa_id, evento),
        )
        rows = await cur.fetchall()
    return [_row_to_hook(r) for r in rows]


async def get_hook_by_id(pool: AsyncConnectionPool, hook_id: int) -> Hook | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM hook WHERE id = %s",
            (hook_id,),
        )
        row = await cur.fetchone()
    return _row_to_hook(row) if row else None


async def create_hook(
    pool: AsyncConnectionPool,
    empresa_id: int,
    data: HookInput,
    *,
    user_id: str | None = None,
) -> Hook:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO hook
                (empresa_id, nome, evento, url, secret, ativo, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING {_SELECT_COLS}
            """,
            (
                empresa_id,
                data.nome,
                data.evento,
                data.url,
                data.secret,
                data.ativo,
                user_id,
            ),
        )
        row = await cur.fetchone()
    assert row is not None
    return _row_to_hook(row)


async def update_hook(
    pool: AsyncConnectionPool,
    hook_id: int,
    data: HookInput,
) -> Hook | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE hook
               SET nome = %s, evento = %s, url = %s, secret = %s,
                   ativo = %s, updated_at = NOW()
             WHERE id = %s
            RETURNING {_SELECT_COLS}
            """,
            (data.nome, data.evento, data.url, data.secret, data.ativo, hook_id),
        )
        row = await cur.fetchone()
    return _row_to_hook(row) if row else None


async def delete_hook(pool: AsyncConnectionPool, hook_id: int) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute("DELETE FROM hook WHERE id = %s", (hook_id,))
    return (cur.rowcount or 0) > 0


async def list_logs(
    pool: AsyncConnectionPool,
    hook_id: int,
    *,
    limit: int = 50,
) -> list[HookLog]:
    """Últimas tentativas (ordem decrescente por created_at)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, hook_id, evento, status_code, error, duration_ms, created_at
              FROM hook_log
             WHERE hook_id = %s
             ORDER BY created_at DESC, id DESC
             LIMIT %s
            """,
            (hook_id, limit),
        )
        rows = await cur.fetchall()
    return [
        HookLog(
            id=r[0],
            hook_id=r[1],
            evento=r[2],
            status_code=r[3],
            error=r[4],
            duration_ms=r[5],
            created_at=r[6],
        )
        for r in rows
    ]


async def insert_log(
    pool: AsyncConnectionPool,
    hook_id: int,
    evento: str,
    payload: dict,
    *,
    status_code: int | None,
    response_body: str | None,
    error: str | None,
    duration_ms: int | None,
) -> None:
    """Persiste resultado de uma tentativa de dispatch."""
    import json

    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO hook_log
                (hook_id, evento, payload, status_code, response_body,
                 error, duration_ms)
            VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
            """,
            (
                hook_id,
                evento,
                json.dumps(payload),
                status_code,
                response_body,
                error,
                duration_ms,
            ),
        )


# ---------------------------------------------------------------------------
# Dead Letter Queue (E1.4)
# ---------------------------------------------------------------------------

DLQ_VALID_STATUS: Final[frozenset[str]] = frozenset(
    {"pending", "retrying", "done", "archived"}
)

_DLQ_SELECT_COLS = (
    "id, empresa_id, hook_id, evento, payload, attempts, "
    "last_status_code, last_response_body, last_error, status, "
    "created_at, updated_at, last_retry_at"
)


async def list_dead_letter(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    status: str | None = "pending",
    limit: int = 100,
) -> list[dict]:
    """Lista entradas DLQ de uma empresa, opcionalmente filtradas por status."""
    params: list = [empresa_id]
    where = "WHERE empresa_id = %s"
    if status is not None:
        if status not in DLQ_VALID_STATUS:
            raise ValueError(f"status inválido: {status!r}")
        where += " AND status = %s"
        params.append(status)
    params.append(limit)

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_DLQ_SELECT_COLS}
              FROM hook_dead_letter
              {where}
             ORDER BY created_at DESC, id DESC
             LIMIT %s
            """,
            params,
        )
        rows = await cur.fetchall()

    return [_row_to_dlq(r) for r in rows]


async def get_dead_letter(
    pool: AsyncConnectionPool, dlq_id: int, empresa_id: int
) -> dict | None:
    """Busca uma entrada DLQ por id, escopada por empresa_id."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_DLQ_SELECT_COLS}
              FROM hook_dead_letter
             WHERE id = %s AND empresa_id = %s
            """,
            (dlq_id, empresa_id),
        )
        row = await cur.fetchone()
    return _row_to_dlq(row) if row else None


async def update_dead_letter_status(
    pool: AsyncConnectionPool,
    dlq_id: int,
    empresa_id: int,
    *,
    status: str,
    bump_retry_at: bool = False,
) -> bool:
    """Atualiza status (e opcionalmente last_retry_at). Retorna True se afetou row."""
    if status not in DLQ_VALID_STATUS:
        raise ValueError(f"status inválido: {status!r}")

    last_retry_clause = ", last_retry_at = NOW()" if bump_retry_at else ""

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE hook_dead_letter
               SET status = %s,
                   updated_at = NOW()
                   {last_retry_clause}
             WHERE id = %s AND empresa_id = %s
            """,
            (status, dlq_id, empresa_id),
        )
        await conn.commit()
        return cur.rowcount > 0


def _row_to_dlq(row) -> dict:
    """Converte row do hook_dead_letter pra dict serializável."""
    return {
        "id": row[0],
        "empresa_id": row[1],
        "hook_id": row[2],
        "evento": row[3],
        "payload": row[4],
        "attempts": row[5],
        "last_status_code": row[6],
        "last_response_body": row[7],
        "last_error": row[8],
        "status": row[9],
        "created_at": row[10].isoformat() if row[10] else None,
        "updated_at": row[11].isoformat() if row[11] else None,
        "last_retry_at": row[12].isoformat() if row[12] else None,
    }
