"""Memória estruturada por cliente — M5.b.2.

Reusa o singleton de embeddings de `base_conhecimento.py` (mesma chave
OpenRouter, mesmo modelo). Salvar memória chama `_embed`; buscar memória
chama `_embed` da query e roda cosine similarity scope a (empresa, cliente).

Dedupe semântico: ao salvar, se já existe row com cosine ≥ DEDUP_THRESHOLD,
o save vira no-op (retorna a row existente). Threshold default 0.92 cobre
o caso "agente repete o mesmo fato com palavras ligeiramente diferentes".
"""

from __future__ import annotations

import structlog
from psycopg import errors as pg_errors
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.base_conhecimento import (
    _embed,
    _vector_literal,
)
from whatsapp_langchain.shared.models import (
    ClienteMemoria,
    ClienteMemoriaInput,
)

logger = structlog.get_logger()


DEDUP_THRESHOLD = 0.92  # cosine ≥ → considera duplicata semântica
SEARCH_DEFAULT_K = 5
SEARCH_DEFAULT_MIN_SCORE = 0.35


_SELECT_COLS = (
    "id, empresa_id, cliente_id, categoria, conteudo, source, "
    "created_by_user_id, created_at, updated_at"
)


def _row_to_memoria(row) -> ClienteMemoria:
    return ClienteMemoria(
        id=row[0],
        empresa_id=row[1],
        cliente_id=row[2],
        categoria=row[3],
        conteudo=row[4],
        source=row[5],
        created_by_user_id=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


async def list_memorias(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    *,
    categoria: str | None = None,
    limit: int = 50,
) -> list[ClienteMemoria]:
    where = "empresa_id = %s AND cliente_id = %s"
    params: list = [empresa_id, cliente_id]
    if categoria is not None:
        where += " AND categoria = %s"
        params.append(categoria)
    params.append(limit)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM cliente_memoria
             WHERE {where}
             ORDER BY created_at DESC
             LIMIT %s
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_memoria(r) for r in rows]


async def get_memoria(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    memoria_id: int,
) -> ClienteMemoria | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM cliente_memoria "
            "WHERE id = %s AND empresa_id = %s AND cliente_id = %s",
            (memoria_id, empresa_id, cliente_id),
        )
        row = await cur.fetchone()
    return _row_to_memoria(row) if row else None


async def save_memoria(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    data: ClienteMemoriaInput,
    *,
    user_id: str | None = None,
    dedup_threshold: float = DEDUP_THRESHOLD,
) -> tuple[ClienteMemoria, bool]:
    """Salva fato com dedup semântico. Retorna `(memoria, was_created)`.

    Algoritmo:
    1. Embeddeia o `conteudo`.
    2. Busca top-1 memória existente da mesma (empresa, cliente, categoria)
       com cosine similarity ≥ `dedup_threshold`.
    3. Se achou → retorna a row existente, was_created=False.
    4. Se não achou → INSERT (com fallback gracioso pra UniqueViolation
       no índice md5 — caso race condition).
    """
    embedding = await _embed(data.conteudo)
    vec_lit = _vector_literal(embedding)

    async with pool.connection() as conn:
        # Dedup semântico: existe row similar?
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS},
                   1 - (embedding <=> %s::vector) AS score
              FROM cliente_memoria
             WHERE empresa_id = %s AND cliente_id = %s
               AND categoria = %s AND embedding IS NOT NULL
             ORDER BY embedding <=> %s::vector
             LIMIT 1
            """,
            (vec_lit, empresa_id, cliente_id, data.categoria, vec_lit),
        )
        row = await cur.fetchone()
        if row is not None and float(row[-1]) >= dedup_threshold:
            existing = _row_to_memoria(row[:-1])
            logger.info(
                "cliente_memoria_dedup_hit",
                empresa_id=empresa_id,
                cliente_id=cliente_id,
                memoria_id=existing.id,
                similarity=float(row[-1]),
            )
            return existing, False

        # Insert (md5 unique cobre race condition de duplicata textual exata)
        try:
            cur = await conn.execute(
                f"""
                INSERT INTO cliente_memoria
                    (empresa_id, cliente_id, categoria, conteudo, embedding,
                     source, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s::vector, %s, %s)
                RETURNING {_SELECT_COLS}
                """,
                (
                    empresa_id,
                    cliente_id,
                    data.categoria,
                    data.conteudo,
                    vec_lit,
                    data.source,
                    user_id,
                ),
            )
            row = await cur.fetchone()
        except pg_errors.UniqueViolation:
            # Race: alguém inseriu o mesmo conteúdo no meio. Retorna existente.
            cur = await conn.execute(
                f"""
                SELECT {_SELECT_COLS} FROM cliente_memoria
                 WHERE empresa_id = %s AND cliente_id = %s
                   AND categoria = %s AND md5(conteudo) = md5(%s)
                """,
                (empresa_id, cliente_id, data.categoria, data.conteudo),
            )
            row = await cur.fetchone()
            assert row is not None
            return _row_to_memoria(row), False

    assert row is not None
    out = _row_to_memoria(row)
    logger.info(
        "cliente_memoria_saved",
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        memoria_id=out.id,
        categoria=out.categoria,
        source=out.source,
    )
    return out, True


async def delete_memoria(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    memoria_id: int,
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM cliente_memoria "
            "WHERE id = %s AND empresa_id = %s AND cliente_id = %s",
            (memoria_id, empresa_id, cliente_id),
        )
    return (cur.rowcount or 0) > 0


async def search_relevant(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    query: str,
    *,
    k: int = SEARCH_DEFAULT_K,
    min_score: float = SEARCH_DEFAULT_MIN_SCORE,
    categoria: str | None = None,
) -> list[tuple[ClienteMemoria, float]]:
    """Busca memórias semanticamente relevantes pra o cliente atual.

    Filtra por (empresa, cliente) e opcionalmente por categoria. Aplica
    `min_score` pra evitar memórias irrelevantes.
    """
    embedding = await _embed(query)
    vec_lit = _vector_literal(embedding)
    where = "empresa_id = %s AND cliente_id = %s AND embedding IS NOT NULL"
    params: list = [empresa_id, cliente_id]
    if categoria is not None:
        where += " AND categoria = %s"
        params.append(categoria)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS},
                   1 - (embedding <=> %s::vector) AS score
              FROM cliente_memoria
             WHERE {where}
             ORDER BY embedding <=> %s::vector
             LIMIT %s
            """,  # type: ignore[arg-type]
            (vec_lit, *params, vec_lit, k),
        )
        rows = await cur.fetchall()
    out: list[tuple[ClienteMemoria, float]] = []
    for row in rows:
        score = float(row[-1])
        if score < min_score:
            continue
        out.append((_row_to_memoria(row[:-1]), score))
    return out


__all__ = [
    "DEDUP_THRESHOLD",
    "delete_memoria",
    "get_memoria",
    "list_memorias",
    "save_memoria",
    "search_relevant",
]
