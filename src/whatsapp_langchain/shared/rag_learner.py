"""Aprendizado contínuo do RAG (Sprint P.2).

Lê queries que falharam (hits=0 ou outcome ruim), clusteriza por
similaridade semântica de embeddings, e gera drafts de docs via LLM.
Admin aprova pela UI → vira documento_conhecimento.

Job rodável manualmente (`python -m whatsapp_langchain.shared.rag_learner`)
ou via endpoint admin que dispara on-demand.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass

import structlog
from langchain_core.messages import HumanMessage
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.base_conhecimento import (
    _embed,
    _vector_literal,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.llm import create_chat_model

logger = structlog.get_logger()


DRAFT_MODEL = "openai/gpt-4o-mini"
SIMILARITY_THRESHOLD = 0.75  # cosine — queries com similaridade >= entram no mesmo cluster
MIN_CLUSTER_SIZE = 2  # cluster precisa ter ≥ 2 queries pra virar sugestão
MAX_QUERIES_PER_CLUSTER = 20
DAYS_LOOKBACK = 7


@dataclass
class QueryMiss:
    id: int
    query_text: str
    pasta_ids: list[int]
    agente_slug: str | None
    embedding: list[float] | None  # populado lazy


@dataclass
class Cluster:
    centroid_query: str
    queries: list[str]
    pasta_id: int | None
    agente_slug: str | None


async def _fetch_misses(
    pool: AsyncConnectionPool,
    empresa_id: int,
    days: int,
) -> list[QueryMiss]:
    """Busca queries com sinal de falha: hits=0 OU outcome ruim."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, query_text, pasta_ids, agente_slug
            FROM rag_query_log
            WHERE empresa_id = %s
              AND created_at > NOW() - INTERVAL '%s days'
              AND (
                hits = 0
                OR outcome IN ('transferred','escalated','abandoned')
              )
              AND char_length(query_text) >= 4
            ORDER BY created_at DESC
            LIMIT 500
            """,
            (empresa_id, days),
        )
        rows = await cur.fetchall()
    return [
        QueryMiss(
            id=r[0],
            query_text=r[1],
            pasta_ids=list(r[2] or []),
            agente_slug=r[3],
        )
        for r in rows
    ]


def _cosine(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def _cluster_queries(misses: list[QueryMiss]) -> list[Cluster]:
    """Clusteriza por similaridade de embedding. Greedy single-linkage.

    Agrupa também por agente_slug — queries do mesmo agente ficam num
    cluster separado mesmo se semanticamente similares (provoca docs
    setor-específicos).
    """
    if not misses:
        return []

    # Embeddings em batch
    queries_text = [m.query_text for m in misses]
    logger.info("rag_learner_embedding", n=len(queries_text))
    from langchain_openai import OpenAIEmbeddings
    from pydantic import SecretStr

    api_key = settings.openrouter_api_key
    secret_key = SecretStr(api_key.get_secret_value()) if api_key else None
    embedder = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=secret_key,
        base_url=settings.openrouter_base_url,
    )
    vectors = await embedder.aembed_documents(queries_text)
    for m, v in zip(misses, vectors, strict=True):
        m.embedding = v

    # Bucket por agente_slug (separação setor)
    by_agent: dict[str | None, list[QueryMiss]] = defaultdict(list)
    for m in misses:
        by_agent[m.agente_slug].append(m)

    clusters: list[Cluster] = []
    for agent_slug, agent_misses in by_agent.items():
        # Greedy clustering: cada miss vira semente, anexa similares >= threshold
        used: set[int] = set()
        for i, seed in enumerate(agent_misses):
            if i in used:
                continue
            if seed.embedding is None:
                continue
            cluster_queries = [seed.query_text]
            cluster_pasta = seed.pasta_ids[0] if seed.pasta_ids else None
            used.add(i)
            for j, other in enumerate(agent_misses):
                if j <= i or j in used or other.embedding is None:
                    continue
                if _cosine(seed.embedding, other.embedding) >= SIMILARITY_THRESHOLD:
                    cluster_queries.append(other.query_text)
                    used.add(j)
                    if len(cluster_queries) >= MAX_QUERIES_PER_CLUSTER:
                        break
            if len(cluster_queries) >= MIN_CLUSTER_SIZE:
                clusters.append(
                    Cluster(
                        centroid_query=seed.query_text,
                        queries=cluster_queries,
                        pasta_id=cluster_pasta,
                        agente_slug=agent_slug,
                    )
                )

    clusters.sort(key=lambda c: -len(c.queries))
    return clusters


async def _generate_draft(cluster: Cluster) -> tuple[str, str]:
    """Gera (titulo, conteudo) via LLM a partir das queries do cluster."""
    queries_block = "\n".join(f"- {q}" for q in cluster.queries[:10])
    sector = (
        f" do setor {cluster.agente_slug}" if cluster.agente_slug else ""
    )
    prompt = f"""Você é especialista em criar FAQ pra atendimento ao cliente.

Os clientes fizeram as perguntas abaixo{sector} e o agente NÃO encontrou
resposta na base de conhecimento. Sua missão: criar UM documento que
responda essas perguntas de forma clara, completa e profissional.

Perguntas dos clientes:
{queries_block}

Gere um JSON com 2 campos:
- "titulo": título curto e descritivo (max 80 chars), sem bullets
- "conteudo": resposta completa (200-500 chars), em parágrafos. Pode usar
  listas com hífen "-". Tom profissional mas amigável. Use linguagem
  simples brasileira.

Importante:
- Não invente políticas/preços/horários específicos. Use placeholders
  tipo "[verificar com supervisor]" quando precisar de dado concreto.
- Foque no que é UNIVERSAL nessas perguntas.

Saída APENAS o JSON, sem markdown."""

    llm = create_chat_model(model=DRAFT_MODEL, temperature=0.3, max_tokens=600)
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = (
            response.content if isinstance(response.content, str)
            else str(response.content)
        ).strip()
        # Remove markdown fences se vier
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        data = json.loads(content)
        titulo = str(data.get("titulo", ""))[:200]
        conteudo = str(data.get("conteudo", ""))[:2000]
        return titulo, conteudo
    except Exception as e:
        logger.warning("draft_generation_failed", error=str(e))
        return f"FAQ: {cluster.centroid_query[:60]}", (
            f"Pergunta frequente:\n\n{cluster.centroid_query}\n\n"
            f"[Conteúdo a ser preenchido pelo administrador]"
        )


async def run_learner(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    days: int = DAYS_LOOKBACK,
) -> dict:
    """Pipeline completo: misses → clusters → drafts → INSERT documento_sugerido.

    Idempotente: pula clusters cujo título já existe como sugestão pendente.
    Retorna {misses, clusters, suggestions_created}.
    """
    misses = await _fetch_misses(pool, empresa_id, days)
    if not misses:
        return {"misses": 0, "clusters": 0, "suggestions_created": 0}

    clusters = await _cluster_queries(misses)
    if not clusters:
        return {"misses": len(misses), "clusters": 0, "suggestions_created": 0}

    # Existing pending titles (anti-dupe)
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT titulo FROM documento_sugerido WHERE empresa_id=%s AND status='pending'",
            (empresa_id,),
        )
        rows = await cur.fetchall()
    existing = {r[0] for r in rows}

    # Resolve pasta_id por agente_slug (busca o agente_ia.base_conhecimento_ids[0])
    async def _pasta_for_agent(slug: str | None) -> int | None:
        if not slug:
            return None
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT base_conhecimento_ids[1]
                  FROM agente_ia
                 WHERE empresa_id=%s AND slug=%s
                 LIMIT 1
                """,
                (empresa_id, slug),
            )
            row = await cur.fetchone()
        return int(row[0]) if row and row[0] else None

    created = 0
    for cluster in clusters[:10]:  # max 10 sugestões por run
        titulo, conteudo = await _generate_draft(cluster)
        if titulo in existing:
            continue
        pasta_id = cluster.pasta_id or await _pasta_for_agent(cluster.agente_slug)
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO documento_sugerido
                  (empresa_id, pasta_id, titulo, conteudo_draft,
                   queries_amostra, cluster_size, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                """,
                (
                    empresa_id, pasta_id, titulo, conteudo,
                    cluster.queries[:MAX_QUERIES_PER_CLUSTER],
                    len(cluster.queries),
                ),
            )
            await conn.commit()
        created += 1

    logger.info(
        "rag_learner_run",
        empresa_id=empresa_id,
        misses=len(misses),
        clusters=len(clusters),
        suggestions_created=created,
    )
    return {
        "misses": len(misses),
        "clusters": len(clusters),
        "suggestions_created": created,
    }


async def _main() -> None:
    """CLI: roda pra todas as empresas (ou EMPRESA_ID env)."""
    import os

    pool = await get_pool()
    empresa_id = int(os.environ.get("EMPRESA_ID", "1"))
    result = await run_learner(pool, empresa_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
