"""Base de conhecimento por empresa — RAG (M5.c).

Cada empresa cadastra documentos (FAQ, políticas, scripts) que o agente
busca via tool `search_knowledge_base` antes de responder. O embedding
é gerado no upsert e armazenado inline na coluna `vector(1536)` —
cosine similarity via pgvector.
"""

from __future__ import annotations

import json

import structlog
from langchain_openai import OpenAIEmbeddings
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.models import (
    DocumentoConhecimento,
    DocumentoConhecimentoInput,
)

logger = structlog.get_logger()


_SELECT_COLS = (
    "id, empresa_id, titulo, conteudo, tags, ativo, "
    "created_by_user_id, created_at, updated_at"
)


def _row_to_documento(row) -> DocumentoConhecimento:
    return DocumentoConhecimento(
        id=row[0],
        empresa_id=row[1],
        titulo=row[2],
        conteudo=row[3],
        tags=list(row[4] or []),
        ativo=row[5],
        created_by_user_id=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


_embeddings_singleton: OpenAIEmbeddings | None = None


def _get_embeddings() -> OpenAIEmbeddings:
    global _embeddings_singleton
    if _embeddings_singleton is None:
        api_key = settings.openrouter_api_key
        secret_key = SecretStr(api_key.get_secret_value()) if api_key else None
        _embeddings_singleton = OpenAIEmbeddings(
            model=settings.embedding_model,
            base_url=settings.openrouter_base_url,
            api_key=secret_key,
        )
    return _embeddings_singleton


async def _embed(texto: str) -> list[float]:
    """Gera embedding via OpenRouter. Retorna lista com `embedding_dims` floats."""
    embeddings = _get_embeddings()
    return await embeddings.aembed_query(texto)


def _vector_literal(vec: list[float]) -> str:
    """Serializa lista de floats no formato pgvector (`[1,2,3]`)."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def list_documentos(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    apenas_ativos: bool = False,
) -> list[DocumentoConhecimento]:
    where = "empresa_id = %s"
    params: list = [empresa_id]
    if apenas_ativos:
        where += " AND ativo"
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM documento_conhecimento "
            f"WHERE {where} ORDER BY updated_at DESC",
            params,
        )
        rows = await cur.fetchall()
    return [_row_to_documento(r) for r in rows]


async def get_documento(
    pool: AsyncConnectionPool, empresa_id: int, doc_id: int
) -> DocumentoConhecimento | None:
    """Lê doc filtrando por empresa — anti-cross-tenant."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM documento_conhecimento "
            "WHERE id = %s AND empresa_id = %s",
            (doc_id, empresa_id),
        )
        row = await cur.fetchone()
    return _row_to_documento(row) if row else None


async def has_active_documents(
    pool: AsyncConnectionPool, empresa_id: int
) -> bool:
    """Gate barato — usado pelo loader pra decidir se injeta a tool."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM documento_conhecimento "
            "WHERE empresa_id = %s AND ativo LIMIT 1",
            (empresa_id,),
        )
        row = await cur.fetchone()
    return row is not None


async def upsert_documento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    data: DocumentoConhecimentoInput,
    *,
    doc_id: int | None = None,
    user_id: str | None = None,
) -> DocumentoConhecimento:
    """Cria (doc_id=None) ou atualiza. Reembedeia sempre.

    Embedding usa `titulo + "\\n\\n" + conteudo` pra que título pese na
    similaridade. Em caso de falha do provider, propaga a exceção pro
    caller decidir (não grava embedding NULL silenciosamente).
    """
    texto = f"{data.titulo}\n\n{data.conteudo}"
    embedding = await _embed(texto)
    vec_lit = _vector_literal(embedding)
    tags = list(data.tags)

    async with pool.connection() as conn:
        if doc_id is None:
            cur = await conn.execute(
                f"""
                INSERT INTO documento_conhecimento
                    (empresa_id, titulo, conteudo, embedding, tags, ativo,
                     created_by_user_id)
                VALUES (%s, %s, %s, %s::vector, %s, %s, %s)
                RETURNING {_SELECT_COLS}
                """,
                (
                    empresa_id,
                    data.titulo,
                    data.conteudo,
                    vec_lit,
                    tags,
                    data.ativo,
                    user_id,
                ),
            )
        else:
            cur = await conn.execute(
                f"""
                UPDATE documento_conhecimento
                   SET titulo = %s,
                       conteudo = %s,
                       embedding = %s::vector,
                       tags = %s,
                       ativo = %s,
                       updated_at = NOW()
                 WHERE id = %s AND empresa_id = %s
                RETURNING {_SELECT_COLS}
                """,
                (
                    data.titulo,
                    data.conteudo,
                    vec_lit,
                    tags,
                    data.ativo,
                    doc_id,
                    empresa_id,
                ),
            )
        row = await cur.fetchone()
    if row is None:
        raise ValueError(
            f"documento {doc_id} não encontrado na empresa {empresa_id}"
        )
    logger.info(
        "documento_conhecimento_upserted",
        empresa_id=empresa_id,
        doc_id=row[0],
        titulo=row[2],
        ativo=row[5],
        novo=doc_id is None,
    )
    return _row_to_documento(row)


async def delete_documento(
    pool: AsyncConnectionPool, empresa_id: int, doc_id: int
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM documento_conhecimento "
            "WHERE id = %s AND empresa_id = %s",
            (doc_id, empresa_id),
        )
    deleted = (cur.rowcount or 0) > 0
    if deleted:
        logger.info(
            "documento_conhecimento_deleted",
            empresa_id=empresa_id,
            doc_id=doc_id,
        )
    return deleted


async def search_relevant(
    pool: AsyncConnectionPool,
    empresa_id: int,
    query: str,
    *,
    k: int = 3,
    min_score: float = 0.3,
) -> list[tuple[DocumentoConhecimento, float]]:
    """Busca top-k docs ativos por similaridade cosseno.

    Retorna lista de `(doc, score)` ordenada do mais relevante pro menos,
    com score em [0, 1] (1 = idêntico). Filtra resultados abaixo de
    `min_score` pra evitar contexto irrelevante.
    """
    embedding = await _embed(query)
    vec_lit = _vector_literal(embedding)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS},
                   1 - (embedding <=> %s::vector) AS score
              FROM documento_conhecimento
             WHERE empresa_id = %s AND ativo AND embedding IS NOT NULL
             ORDER BY embedding <=> %s::vector
             LIMIT %s
            """,
            (vec_lit, empresa_id, vec_lit, k),
        )
        rows = await cur.fetchall()
    results: list[tuple[DocumentoConhecimento, float]] = []
    for row in rows:
        score = float(row[-1])
        if score < min_score:
            continue
        results.append((_row_to_documento(row[:-1]), score))
    return results
