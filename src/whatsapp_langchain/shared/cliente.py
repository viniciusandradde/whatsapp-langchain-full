"""Helpers de Cliente — UPSERT por (empresa_id, telefone), anotações e tags.

Cada inbound do webhook resolve a empresa via conexão e em seguida garante
um `cliente` cadastrado pra aquela empresa+telefone (`upsert_cliente`). O
nome do cliente vem do ProfileName do Twilio quando ainda não existe — e
nunca é sobrescrito pelo webhook depois (operador edita pela UI).

Tags ficam em `cliente_tag` (PK composta cliente_id+tag, idempotente via
ON CONFLICT DO NOTHING). Anotações ficam em `cliente_anotacao` (append-only).
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Cliente, ClienteAnotacao

logger = structlog.get_logger()


_SELECT_COLS = (
    "id, empresa_id, telefone, nome, email, doc, status, config, created_at, updated_at"
)


def _row_to_cliente(row, tags: list[str] | None = None) -> Cliente:
    return Cliente(
        id=row[0],
        empresa_id=row[1],
        telefone=row[2],
        nome=row[3],
        email=row[4],
        doc=row[5],
        status=row[6],
        config=row[7] or {},
        created_at=row[8],
        updated_at=row[9],
        tags=tags or [],
    )


async def upsert_cliente(
    pool: AsyncConnectionPool,
    empresa_id: int,
    telefone: str,
    *,
    nome: str | None = None,
    email: str | None = None,
    doc: str | None = None,
) -> Cliente:
    """Cria/atualiza cliente pela UNIQUE (empresa_id, telefone).

    Política do webhook: nunca sobrescreve nome/email/doc já preenchidos.
    Usa COALESCE para preservar os valores existentes quando os argumentos
    chegam None ou quando a coluna já tem valor.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO cliente (empresa_id, telefone, nome, email, doc)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (empresa_id, telefone) DO UPDATE SET
                nome = COALESCE(cliente.nome, EXCLUDED.nome),
                email = COALESCE(cliente.email, EXCLUDED.email),
                doc = COALESCE(cliente.doc, EXCLUDED.doc),
                updated_at = NOW()
            RETURNING {_SELECT_COLS}
            """,
            (empresa_id, telefone, nome, email, doc),
        )
        row = await cur.fetchone()
    assert row is not None
    return _row_to_cliente(row)


async def get_cliente_by_id(
    pool: AsyncConnectionPool, cliente_id: int
) -> Cliente | None:
    """Carrega cliente + tags em duas queries (PK + agrega de tags)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM cliente WHERE id = %s",
            (cliente_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        cur = await conn.execute(
            "SELECT tag FROM cliente_tag WHERE cliente_id = %s ORDER BY tag ASC",
            (cliente_id,),
        )
        tag_rows = await cur.fetchall()
    return _row_to_cliente(row, tags=[r[0] for r in tag_rows])


async def update_cliente_partial(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    *,
    nome: str | None = None,
    email: str | None = None,
    doc: str | None = None,
) -> Cliente | None:
    """Update parcial — só campos não-None são tocados (M5.b.1).

    Usado pelas tools do agente quando o cliente diz nome/email durante a
    conversa. Filtra por (id, empresa_id) pra anti-cross-tenant.
    """
    sets: list[str] = []
    params: list = []
    if nome is not None:
        sets.append("nome = %s")
        params.append(nome)
    if email is not None:
        sets.append("email = %s")
        params.append(email)
    if doc is not None:
        sets.append("doc = %s")
        params.append(doc)
    if not sets:
        return await get_cliente_by_id(pool, cliente_id)
    sets.append("updated_at = NOW()")
    params.extend([cliente_id, empresa_id])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE cliente SET {", ".join(sets)}
             WHERE id = %s AND empresa_id = %s
            RETURNING {_SELECT_COLS}
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    # Re-lê tags pra retornar lista atualizada.
    return await get_cliente_by_id(pool, cliente_id)


async def get_cliente_by_telefone(
    pool: AsyncConnectionPool, empresa_id: int, telefone: str
) -> Cliente | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM cliente
             WHERE empresa_id = %s AND telefone = %s
            """,
            (empresa_id, telefone),
        )
        row = await cur.fetchone()
    return _row_to_cliente(row) if row else None


async def list_clientes(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Cliente]:
    """Lista clientes da empresa, ordenados por updated_at DESC.

    `search` filtra por substring case-insensitive em nome ou telefone.
    """
    params: list = [empresa_id]
    where = "WHERE empresa_id = %s"
    if search:
        where += " AND (nome ILIKE %s OR telefone ILIKE %s)"
        like = f"%{search}%"
        params.extend([like, like])
    params.extend([limit, offset])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM cliente
            {where}
            ORDER BY updated_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_cliente(r) for r in rows]


async def add_anotacao(
    pool: AsyncConnectionPool,
    cliente_id: int,
    user_id: str,
    conteudo: str,
) -> ClienteAnotacao:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO cliente_anotacao (cliente_id, user_id, conteudo)
            VALUES (%s, %s, %s)
            RETURNING id, cliente_id, user_id, conteudo, created_at
            """,
            (cliente_id, user_id, conteudo),
        )
        row = await cur.fetchone()
    assert row is not None
    return ClienteAnotacao(
        id=row[0],
        cliente_id=row[1],
        user_id=row[2],
        conteudo=row[3],
        created_at=row[4],
    )


async def list_anotacoes(
    pool: AsyncConnectionPool,
    cliente_id: int,
    *,
    limit: int | None = None,
) -> list[ClienteAnotacao]:
    """Anotações do cliente em ordem DESC. `limit` opcional pra tools do agente."""
    sql = """
        SELECT id, cliente_id, user_id, conteudo, created_at
          FROM cliente_anotacao
         WHERE cliente_id = %s
         ORDER BY created_at DESC, id DESC
    """
    params: tuple = (cliente_id,)
    if limit is not None:
        sql += " LIMIT %s"
        params = (cliente_id, int(limit))
    async with pool.connection() as conn:
        cur = await conn.execute(sql, params)
        rows = await cur.fetchall()
    return [
        ClienteAnotacao(
            id=r[0],
            cliente_id=r[1],
            user_id=r[2],
            conteudo=r[3],
            created_at=r[4],
        )
        for r in rows
    ]


async def add_tag(pool: AsyncConnectionPool, cliente_id: int, tag: str) -> None:
    """Adiciona tag (idempotente — não duplica par cliente_id+tag)."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO cliente_tag (cliente_id, tag)
            VALUES (%s, %s)
            ON CONFLICT (cliente_id, tag) DO NOTHING
            """,
            (cliente_id, tag),
        )


async def remove_tag(pool: AsyncConnectionPool, cliente_id: int, tag: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM cliente_tag WHERE cliente_id = %s AND tag = %s",
            (cliente_id, tag),
        )
