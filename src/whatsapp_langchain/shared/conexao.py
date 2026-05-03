"""Helpers de conexão WhatsApp — lookup, listagem e CRUD.

Cada `conexao` é uma linha (Twilio sandbox/prod, WABA) ligada a uma empresa.
O webhook resolve `empresa_id` + `default_agent_id` consultando
`get_conexao_by_from_number(to_number)` — um lookup por mensagem inbound.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Conexao, ConexaoInput

logger = structlog.get_logger()


def _row_to_conexao(row) -> Conexao:
    return Conexao(
        id=row[0],
        empresa_id=row[1],
        provider=row[2],
        sid=row[3],
        from_number=row[4],
        display_name=row[5],
        default_agent_id=row[6],
        status=row[7],
        is_default=row[8],
        payload_json=row[9] or {},
        created_at=row[10],
        updated_at=row[11],
    )


_SELECT_COLS = (
    "id, empresa_id, provider, sid, from_number, display_name, "
    "default_agent_id, status, is_default, payload_json, "
    "created_at, updated_at"
)


async def list_conexoes(
    pool: AsyncConnectionPool, empresa_id: int
) -> list[Conexao]:
    """Lista as conexões de uma empresa, default primeiro depois alfabética."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM conexao
             WHERE empresa_id = %s
             ORDER BY is_default DESC, display_name NULLS LAST, id ASC
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_conexao(r) for r in rows]


async def get_conexao_by_id(
    pool: AsyncConnectionPool, conexao_id: int
) -> Conexao | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM conexao WHERE id = %s", (conexao_id,)
        )
        row = await cur.fetchone()
    return _row_to_conexao(row) if row else None


async def get_conexao_by_from_number(
    pool: AsyncConnectionPool, from_number: str
) -> Conexao | None:
    """Resolve a conexão pelo número de destino do webhook (E.164, sem `whatsapp:`)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM conexao WHERE from_number = %s",
            (from_number,),
        )
        row = await cur.fetchone()
    return _row_to_conexao(row) if row else None


async def get_conexao_by_evolution_instance(
    pool: AsyncConnectionPool, instance_name: str
) -> Conexao | None:
    """Resolve a conexão Evolution pelo nome da instância (M2.b).

    O webhook Evolution traz `instance` no payload — buscamos a conexão
    com `provider='evolution'` cujo `payload_json.instance_name` casa.
    Multi-instância: cada conexão grava sua instance_name no JSONB.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM conexao
             WHERE provider = 'evolution'
               AND payload_json->>'instance_name' = %s
             LIMIT 1
            """,
            (instance_name,),
        )
        row = await cur.fetchone()
    return _row_to_conexao(row) if row else None


async def upsert_conexao(
    pool: AsyncConnectionPool, empresa_id: int, data: ConexaoInput
) -> Conexao:
    """Cria/atualiza conexão. UNIQUE (from_number) garante 1 row por número.

    Usa `ON CONFLICT (from_number)` pra atualizar quando o número já existe
    (o que cobre rename de display_name, troca de provider, etc).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO conexao (empresa_id, provider, sid, from_number,
                                 display_name, default_agent_id, status,
                                 is_default, payload_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (from_number) DO UPDATE SET
                empresa_id = EXCLUDED.empresa_id,
                provider = EXCLUDED.provider,
                sid = EXCLUDED.sid,
                display_name = EXCLUDED.display_name,
                default_agent_id = EXCLUDED.default_agent_id,
                status = EXCLUDED.status,
                is_default = EXCLUDED.is_default,
                payload_json = EXCLUDED.payload_json,
                updated_at = NOW()
            RETURNING {_SELECT_COLS}
            """,
            (
                empresa_id,
                data.provider,
                data.sid,
                data.from_number,
                data.display_name,
                data.default_agent_id,
                data.status,
                data.is_default,
                __import__("json").dumps(data.payload_json),
            ),
        )
        row = await cur.fetchone()
    assert row is not None
    return _row_to_conexao(row)


async def set_conexao_status(
    pool: AsyncConnectionPool, conexao_id: int, status: str
) -> None:
    """Atualiza status (active/disabled/error) — usado pelo soft-delete."""
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE conexao SET status = %s, updated_at = NOW() WHERE id = %s",
            (status, conexao_id),
        )
