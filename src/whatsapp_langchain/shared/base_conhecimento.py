"""Base de conhecimento por empresa — RAG (M5.c + M5.c.1).

Versão M5.c.1: documentos são quebrados em chunks (`shared/chunking.py`),
cada chunk ganha seu próprio embedding na tabela
`documento_conhecimento_chunk`. Busca acontece em chunks (cosine top-N)
e passa por LLM reranker pra retornar top-k com explicação.

Tool injetada quando empresa tem ≥1 doc ativo (compat M5.c — gate via
`has_active_documents`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import structlog
from langchain_openai import OpenAIEmbeddings
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr

from whatsapp_langchain.shared.chunking import split_text
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.llm import create_chat_model
from whatsapp_langchain.shared.models import (
    DocumentoConhecimento,
    DocumentoConhecimentoInput,
)

logger = structlog.get_logger()


_SELECT_COLS = (
    "id, empresa_id, titulo, conteudo, tags, ativo, "
    "created_by_user_id, created_at, updated_at"
)


# Modelo barato pro reranker. OpenRouter aceita esse alias direto.
RERANKER_MODEL = "openai/gpt-4o-mini"
RERANKER_TOP_K = 3
SEARCH_FETCH_K = 10


@dataclass(frozen=True)
class SearchResult:
    """Trecho relevante retornado pela busca + reranker — M5.c.1.

    `chunk_conteudo` é o texto do chunk (o que vai virar contexto pro
    agente); `score` é cosine similarity em [0,1]; `reason` aparece
    quando o LLM reranker explicou a escolha.
    """

    documento: DocumentoConhecimento
    chunk_idx: int
    chunk_conteudo: str
    score: float
    reason: str | None = None


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
    embeddings = _get_embeddings()
    return await embeddings.aembed_query(texto)


async def _embed_batch(textos: list[str]) -> list[list[float]]:
    """Indexação em batch (1 chamada por doc) — economiza round-trips."""
    embeddings = _get_embeddings()
    return await embeddings.aembed_documents(textos)


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


# --- CRUD documentos ---


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
    """Cria/atualiza doc e reindexa chunks (M5.c.1).

    Quando o doc é editado, todos os chunks antigos são deletados e
    reindexados — reduz complexidade vs diff incremental, e custo de
    embedding é baixo pra docs típicos (<10k chars).
    """
    chunks_text = split_text(data.conteudo)
    if not chunks_text:
        raise ValueError("conteudo não pode ficar vazio depois do chunker")

    # Prepende título no primeiro chunk pra melhorar relevância de buscas
    # cujo nome do doc é a melhor pista (ex: "Política de Trocas").
    chunks_text = [
        f"{data.titulo}\n\n{chunks_text[0]}",
        *chunks_text[1:],
    ]

    embeddings = await _embed_batch(chunks_text)
    tags = list(data.tags)

    async with pool.connection() as conn:
        async with conn.transaction():
            if doc_id is None:
                cur = await conn.execute(
                    f"""
                    INSERT INTO documento_conhecimento
                        (empresa_id, titulo, conteudo, tags, ativo,
                         created_by_user_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING {_SELECT_COLS}
                    """,
                    (
                        empresa_id,
                        data.titulo,
                        data.conteudo,
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
                           tags = %s,
                           ativo = %s,
                           updated_at = NOW()
                     WHERE id = %s AND empresa_id = %s
                    RETURNING {_SELECT_COLS}
                    """,
                    (
                        data.titulo,
                        data.conteudo,
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
            new_doc_id = row[0]

            # Limpa chunks antigos (no insert, não tem; no update, troca tudo)
            await conn.execute(
                "DELETE FROM documento_conhecimento_chunk WHERE documento_id = %s",
                (new_doc_id,),
            )

            # Bulk insert dos novos chunks com embedding
            for idx, (chunk, vec) in enumerate(zip(chunks_text, embeddings)):
                await conn.execute(
                    """
                    INSERT INTO documento_conhecimento_chunk
                        (documento_id, empresa_id, chunk_idx, conteudo, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    """,
                    (new_doc_id, empresa_id, idx, chunk, _vector_literal(vec)),
                )
    logger.info(
        "documento_conhecimento_upserted",
        empresa_id=empresa_id,
        doc_id=new_doc_id,
        titulo=row[2],
        ativo=row[5],
        novo=doc_id is None,
        num_chunks=len(chunks_text),
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


# --- Search ---


async def _cosine_search(
    pool: AsyncConnectionPool,
    empresa_id: int,
    query: str,
    *,
    fetch_k: int,
) -> list[tuple[DocumentoConhecimento, int, str, float]]:
    """Top-N chunks por cosine similarity. Tupla: (doc, chunk_idx, chunk_conteudo, score)."""
    embedding = await _embed(query)
    vec_lit = _vector_literal(embedding)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT d.id, d.empresa_id, d.titulo, d.conteudo, d.tags, d.ativo,
                   d.created_by_user_id, d.created_at, d.updated_at,
                   c.chunk_idx, c.conteudo,
                   1 - (c.embedding <=> %s::vector) AS score
              FROM documento_conhecimento_chunk c
              JOIN documento_conhecimento d ON d.id = c.documento_id
             WHERE d.empresa_id = %s AND d.ativo AND c.embedding IS NOT NULL
             ORDER BY c.embedding <=> %s::vector
             LIMIT %s
            """,
            (vec_lit, empresa_id, vec_lit, fetch_k),
        )
        rows = await cur.fetchall()
    out: list[tuple[DocumentoConhecimento, int, str, float]] = []
    for row in rows:
        doc = _row_to_documento(row[:9])
        chunk_idx = row[9]
        chunk_conteudo = row[10]
        score = float(row[11])
        out.append((doc, chunk_idx, chunk_conteudo, score))
    return out


async def _llm_rerank(
    query: str,
    candidates: list[tuple[DocumentoConhecimento, int, str, float]],
    *,
    top_k: int,
) -> list[SearchResult]:
    """Reordena candidatos usando LLM barato. Fallback pra cosine se falhar.

    O modelo recebe a pergunta + os trechos enumerados e devolve um JSON
    `{ranking: [{idx, reason}]}` com top_k. Se o output não der pra
    parsear, voltamos pros top_k cosine sem reason.
    """
    if not candidates:
        return []
    if len(candidates) <= top_k:
        # Sem ganho de chamar LLM se já temos ≤ top_k.
        return [
            SearchResult(
                documento=c[0],
                chunk_idx=c[1],
                chunk_conteudo=c[2],
                score=c[3],
            )
            for c in candidates
        ]

    bullets = "\n\n".join(
        f"[{i}] (Doc: {c[0].titulo}, trecho {c[1]})\n{c[2]}"
        for i, c in enumerate(candidates)
    )
    prompt = (
        "Você é um reranker de RAG. Dada a pergunta do cliente e os trechos "
        "candidatos, escolha os {top_k} MAIS úteis pra responder.\n\n"
        "PERGUNTA:\n{query}\n\n"
        "TRECHOS CANDIDATOS:\n{bullets}\n\n"
        "Responda APENAS com JSON no formato:\n"
        '{{"ranking": [{{"idx": <número>, "reason": "<uma frase>"}}]}}\n'
        "Onde `idx` é o número entre colchetes do trecho (0..N-1)."
    ).format(top_k=top_k, query=query, bullets=bullets)

    try:
        model = create_chat_model(model=RERANKER_MODEL, temperature=0.0)
        response = await model.ainvoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        # LLM às vezes embrulha em ```json — limpa.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        parsed = json.loads(cleaned)
        ranking = parsed.get("ranking", [])
    except Exception as e:
        logger.warning("rag_rerank_failed", error=str(e))
        # Fallback pros top_k cosine.
        return [
            SearchResult(
                documento=c[0],
                chunk_idx=c[1],
                chunk_conteudo=c[2],
                score=c[3],
            )
            for c in candidates[:top_k]
        ]

    seen: set[int] = set()
    out: list[SearchResult] = []
    for entry in ranking:
        try:
            idx = int(entry.get("idx"))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(candidates) or idx in seen:
            continue
        seen.add(idx)
        c = candidates[idx]
        out.append(
            SearchResult(
                documento=c[0],
                chunk_idx=c[1],
                chunk_conteudo=c[2],
                score=c[3],
                reason=str(entry.get("reason") or ""),
            )
        )
        if len(out) == top_k:
            break

    if not out:
        # Reranker degenerou — usa cosine puro.
        return [
            SearchResult(
                documento=c[0],
                chunk_idx=c[1],
                chunk_conteudo=c[2],
                score=c[3],
            )
            for c in candidates[:top_k]
        ]
    return out


async def search_relevant(
    pool: AsyncConnectionPool,
    empresa_id: int,
    query: str,
    *,
    k: int = RERANKER_TOP_K,
    min_score: float = 0.3,
    fetch_k: int = SEARCH_FETCH_K,
    rerank: bool = True,
) -> list[SearchResult]:
    """Pipeline RAG completo (M5.c.1): cosine top-N → LLM reranker → top-k.

    Retorna lista de `SearchResult` ordenada do mais relevante pro menos.
    Filtra candidatos abaixo de `min_score` antes do reranker. Quando
    `rerank=False`, pula o LLM (mais rápido, mais barato — útil pra UI
    de debug).
    """
    candidates = await _cosine_search(pool, empresa_id, query, fetch_k=fetch_k)
    candidates = [c for c in candidates if c[3] >= min_score]
    if not candidates:
        return []
    if not rerank:
        return [
            SearchResult(
                documento=c[0],
                chunk_idx=c[1],
                chunk_conteudo=c[2],
                score=c[3],
            )
            for c in candidates[:k]
        ]
    return await _llm_rerank(query, candidates, top_k=k)


__all__ = [
    "SearchResult",
    "delete_documento",
    "get_documento",
    "has_active_documents",
    "list_documentos",
    "search_relevant",
    "upsert_documento",
]
