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
    "created_by_user_id, created_at, updated_at, pasta_id"
)


# Modelo barato pro reranker. OpenRouter aceita esse alias direto.
RERANKER_MODEL = "openai/gpt-4o-mini"
RERANKER_TOP_K = 3
SEARCH_FETCH_K = 10

# Sprint N.2 — HyDE (Hypothetical Document Embeddings)
# Quando query é curta/keyword-like, expande pra parágrafo hipotético antes
# de embedar. Melhora recall em queries tipo "wifi?" / "estaciona?" / "preço".
HYDE_MODEL = "openai/gpt-4o-mini"
HYDE_MIN_QUERY_LEN = 50  # queries menores que isso ativam HyDE
HYDE_CACHE_TTL_SECONDS = 300

# Cache simples in-memory: {(query, agent_slug): (expanded, ts)}
_hyde_cache: dict[tuple[str, str | None], tuple[str, float]] = {}


async def _hyde_expand(query: str, agent_slug: str | None = None) -> str:
    """Expande query curta em parágrafo hipotético via LLM (Sprint N.2).

    Cache TTL 5min por (query, agent_slug). Falha gracefully — se LLM
    falhar, retorna query original.
    """
    import time

    now = time.time()
    cache_key = (query, agent_slug)
    cached = _hyde_cache.get(cache_key)
    if cached is not None and (now - cached[1]) < HYDE_CACHE_TTL_SECONDS:
        return cached[0]

    # Limpa cache antigo (best-effort, mantém max 200 entries)
    if len(_hyde_cache) > 200:
        for k in list(_hyde_cache.keys()):
            if (now - _hyde_cache[k][1]) > HYDE_CACHE_TTL_SECONDS:
                del _hyde_cache[k]

    sector_hint = f" do setor {agent_slug}" if agent_slug else ""
    prompt = (
        f"Você é um redator de FAQ. Reescreva a pergunta abaixo como um "
        f"parágrafo curto (80-150 caracteres) que SERIA a resposta ideal de "
        f"um documento de atendimento ao cliente{sector_hint}. NÃO responda "
        f"a pergunta — apenas reformule como se fosse o texto da resposta. "
        f"Use linguagem natural em português brasileiro.\n\n"
        f"Pergunta: {query}\n\nParágrafo hipotético:"
    )

    try:
        llm = create_chat_model(model=HYDE_MODEL, temperature=0.0, max_tokens=120)
        from langchain_core.messages import HumanMessage

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        expanded = (
            response.content if isinstance(response.content, str)
            else str(response.content)
        ).strip()
        # Combina query original + expansão pra preservar termos exatos
        combined = f"{query} {expanded}"[:500]
        _hyde_cache[cache_key] = (combined, now)
        logger.info(
            "hyde_expanded",
            query_chars=len(query),
            expanded_chars=len(expanded),
            agent_slug=agent_slug,
        )
        return combined
    except Exception as e:
        logger.warning("hyde_failed", error=str(e), query=query[:80])
        return query


def _should_use_hyde(query: str) -> bool:
    """Heurística: query curta ou só keywords ativa HyDE."""
    q = query.strip()
    if len(q) < HYDE_MIN_QUERY_LEN:
        return True
    # Sem pontuação + poucas palavras = provável keyword query
    word_count = len(q.split())
    has_punct = any(c in q for c in "?!.,;")
    return word_count <= 4 and not has_punct


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
        pasta_id=row[9] if len(row) > 9 else None,
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
    pasta_id: int | None = None,
    pasta_id_set: bool = False,
    pasta_ids: set[int] | None = None,
) -> list[DocumentoConhecimento]:
    """Lista docs da empresa.

    Filtros (E2.C):
    - `pasta_id_set=True` + `pasta_id=None` ⇒ só docs em RAIZ (pasta_id IS NULL).
    - `pasta_id_set=True` + `pasta_id=N` ⇒ só docs daquela pasta.
    - `pasta_ids` ⇒ docs em qualquer pasta do set (usado pra subárvore
      via `pasta.get_descendant_ids`).
    - Default ⇒ todos os docs da empresa.
    """
    where = "empresa_id = %s"
    params: list = [empresa_id]
    if apenas_ativos:
        where += " AND ativo"
    if pasta_ids is not None:
        where += " AND pasta_id = ANY(%s)"
        params.append(list(pasta_ids))
    elif pasta_id_set:
        if pasta_id is None:
            where += " AND pasta_id IS NULL"
        else:
            where += " AND pasta_id = %s"
            params.append(pasta_id)
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
                         created_by_user_id, pasta_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING {_SELECT_COLS}
                    """,
                    (
                        empresa_id,
                        data.titulo,
                        data.conteudo,
                        tags,
                        data.ativo,
                        user_id,
                        data.pasta_id,
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
                           pasta_id = %s,
                           updated_at = NOW()
                     WHERE id = %s AND empresa_id = %s
                    RETURNING {_SELECT_COLS}
                    """,
                    (
                        data.titulo,
                        data.conteudo,
                        tags,
                        data.ativo,
                        data.pasta_id,
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
    pasta_ids: list[int] | None = None,
) -> list[tuple[DocumentoConhecimento, int, str, float]]:
    """Top-N chunks por cosine similarity. Tupla: (doc, chunk_idx, chunk_conteudo, score).

    Quando `pasta_ids` é não-vazio, filtra docs apenas dessas pastas — usado
    pra knowledge base setor-específica (cada agente_ia aponta pras suas
    pastas via `agente_ia.base_conhecimento_ids`).
    """
    embedding = await _embed(query)
    vec_lit = _vector_literal(embedding)
    where_pasta = ""
    params_pasta: list = []
    if pasta_ids:
        where_pasta = " AND d.pasta_id = ANY(%s)"
        params_pasta = [list(pasta_ids)]
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
                   {where_pasta}
             ORDER BY c.embedding <=> %s::vector
             LIMIT %s
            """,
            (vec_lit, empresa_id, *params_pasta, vec_lit, fetch_k),
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


async def _hybrid_search(
    pool: AsyncConnectionPool,
    empresa_id: int,
    query: str,
    *,
    fetch_k: int,
    pasta_ids: list[int] | None = None,
) -> list[tuple[DocumentoConhecimento, int, str, float]]:
    """Busca híbrida via function SQL `kb_hybrid_search` (Sprint N.1).

    Combina cosine + FTS portuguese com Reciprocal Rank Fusion (K=60,
    pesos vector=1.0 + text=1.5). Mais robusto que cosine puro pra
    queries com termos exatos (códigos, nomes, números).

    Retorna no mesmo formato do `_cosine_search` (compat com reranker)
    com `score` = rrf_score normalizado.
    """
    embedding = await _embed(query)
    vec_lit = _vector_literal(embedding)
    pasta_arr = list(pasta_ids) if pasta_ids else []

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
                f.documento_id, d.empresa_id, d.titulo, d.conteudo,
                d.tags, d.ativo, d.created_by_user_id, d.created_at,
                d.updated_at, d.pasta_id,
                f.chunk_idx, f.conteudo, f.rrf_score,
                f.score_vector, f.score_text
            FROM kb_hybrid_search(%s::BIGINT, %s::BIGINT[], %s, %s::vector, %s) f
            JOIN documento_conhecimento d ON d.id = f.documento_id
            ORDER BY f.rrf_score DESC
            """,
            (empresa_id, pasta_arr, query, vec_lit, fetch_k),
        )
        rows = await cur.fetchall()

    out: list[tuple[DocumentoConhecimento, int, str, float]] = []
    for row in rows:
        doc = _row_to_documento(row[:10])
        chunk_idx = row[10]
        chunk_conteudo = row[11]
        # Normaliza rrf_score pra [0,1] dividindo pelo máximo teórico
        # (1/(60+1) * 2 ≈ 0.033). Multiplicamos por 30 pra ficar parecido
        # com cosine score em [0,1] — útil pro reranker comparar.
        score = float(row[12]) * 30.0
        out.append((doc, chunk_idx, chunk_conteudo, min(score, 1.0)))
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
    pasta_ids: list[int] | None = None,
    mode: str = "hybrid",
    agent_slug: str | None = None,
) -> list[SearchResult]:
    """Pipeline RAG completo: retrieval → LLM reranker → top-k.

    Args:
        mode: "vector" (cosine puro), "hybrid" (cosine+FTS RRF — default),
            "hybrid_hyde" (HyDE expand + hybrid). Sprint N.1+N.2.
        rerank: Se False, pula o LLM (debug/perf). Returns top-k sem `reason`.
        pasta_ids: Filtro setor-específico (Sprint M). Vazio = empresa inteira.
        agent_slug: Hint pro HyDE expandir com contexto do setor.
    """
    # Sprint N.2 — HyDE: expande query curta antes de embedar.
    # Modo "hybrid_hyde" SEMPRE expande; "auto" decide pela heurística.
    effective_query = query
    if mode == "hybrid_hyde" or (mode == "auto" and _should_use_hyde(query)):
        effective_query = await _hyde_expand(query, agent_slug=agent_slug)
        if mode == "auto":
            mode = "hybrid"  # após expandir, usa hybrid normal

    search_mode = "hybrid" if mode in ("hybrid", "hybrid_hyde", "auto") else "vector"

    if search_mode == "hybrid":
        try:
            candidates = await _hybrid_search(
                pool, empresa_id, effective_query,
                fetch_k=fetch_k, pasta_ids=pasta_ids,
            )
        except Exception as e:
            # Fallback pra cosine se a function SQL falhar (ex: mig 065
            # ainda não aplicada). Garante que o agente continua funcionando
            # durante deploy.
            logger.warning("hybrid_search_fallback_to_cosine", error=str(e))
            candidates = await _cosine_search(
                pool, empresa_id, effective_query,
                fetch_k=fetch_k, pasta_ids=pasta_ids,
            )
    else:
        candidates = await _cosine_search(
            pool, empresa_id, effective_query,
            fetch_k=fetch_k, pasta_ids=pasta_ids,
        )

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
    # Reranker recebe a query ORIGINAL (não a expandida) — semântica do user
    return await _llm_rerank(query, candidates, top_k=k)


async def backfill_chunks(
    pool: AsyncConnectionPool, *, only_doc_id: int | None = None
) -> dict[str, int]:
    """One-shot backfill — chunkeia + indexa docs que ainda não têm chunks.

    Útil pra migrar dados de M5.c (1 vetor por doc) pra M5.c.1 (chunks).
    Idempotente: docs que já têm ≥1 chunk são pulados. Quando
    `only_doc_id` é fornecido, força re-indexação só desse doc (útil pra
    debug ou correção pontual).

    Retorna `{processed, skipped, failed}` pra logging/CLI.
    """
    async with pool.connection() as conn:
        if only_doc_id is not None:
            cur = await conn.execute(
                f"SELECT {_SELECT_COLS} FROM documento_conhecimento WHERE id = %s",
                (only_doc_id,),
            )
        else:
            cur = await conn.execute(
                f"""
                SELECT {_SELECT_COLS} FROM documento_conhecimento d
                 WHERE NOT EXISTS (
                       SELECT 1 FROM documento_conhecimento_chunk c
                        WHERE c.documento_id = d.id
                       )
                """
            )
        rows = await cur.fetchall()

    counters = {"processed": 0, "skipped": 0, "failed": 0}
    for row in rows:
        doc = _row_to_documento(row)
        try:
            chunks_text = split_text(doc.conteudo)
            if not chunks_text:
                counters["skipped"] += 1
                continue
            chunks_text = [
                f"{doc.titulo}\n\n{chunks_text[0]}",
                *chunks_text[1:],
            ]
            embeddings = await _embed_batch(chunks_text)
            async with pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "DELETE FROM documento_conhecimento_chunk WHERE documento_id = %s",
                        (doc.id,),
                    )
                    for idx, (chunk, vec) in enumerate(zip(chunks_text, embeddings)):
                        await conn.execute(
                            """
                            INSERT INTO documento_conhecimento_chunk
                                (documento_id, empresa_id, chunk_idx, conteudo, embedding)
                            VALUES (%s, %s, %s, %s, %s::vector)
                            """,
                            (doc.id, doc.empresa_id, idx, chunk, _vector_literal(vec)),
                        )
            counters["processed"] += 1
            logger.info(
                "rag_chunks_backfilled",
                doc_id=doc.id,
                empresa_id=doc.empresa_id,
                num_chunks=len(chunks_text),
            )
        except Exception as e:
            counters["failed"] += 1
            logger.warning(
                "rag_chunks_backfill_failed",
                doc_id=doc.id,
                empresa_id=doc.empresa_id,
                error=str(e),
            )
    return counters


__all__ = [
    "SearchResult",
    "backfill_chunks",
    "delete_documento",
    "get_documento",
    "has_active_documents",
    "list_documentos",
    "search_relevant",
    "upsert_documento",
]
