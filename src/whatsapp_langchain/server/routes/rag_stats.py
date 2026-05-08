"""Dashboard de qualidade do RAG (Sprint M.7).

Endpoints admin pra monitorar uso da knowledge base:
- KPIs gerais (queries últimas 24h/7d, miss rate, score médio)
- Top queries (mais frequentes + missadas)
- Distribuição por agente/pasta
- Histórico recente
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/admin/rag",
    tags=["rag-stats"],
    dependencies=[Depends(verify_service_token)],
)


class RAGSummary(BaseModel):
    queries_24h: int
    queries_7d: int
    miss_rate_24h: float  # 0.0-1.0
    avg_score_24h: float | None
    avg_duracao_ms_24h: float | None


class TopQuery(BaseModel):
    query_text: str
    n: int
    miss_rate: float
    avg_score: float | None
    last_seen: datetime


class AgenteStat(BaseModel):
    agente_slug: str | None
    queries: int
    miss_rate: float
    avg_score: float | None


class RecentQuery(BaseModel):
    id: int
    query_text: str
    agente_slug: str | None
    pasta_ids: list[int]
    hits: int
    top_score: float | None
    duracao_ms: int | None
    error: str | None
    created_at: datetime


@router.get("/summary", response_model=RAGSummary)
async def get_summary(
    empresa_id: int = Depends(get_empresa_context),
) -> RAGSummary:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') AS q24,
              COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') AS q7d,
              COALESCE(
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours' AND hits = 0)::float /
                NULLIF(COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours'), 0),
                0
              ) AS miss_rate,
              AVG(top_score) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours' AND hits > 0) AS avg_score,
              AVG(duracao_ms) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') AS avg_dur
            FROM rag_query_log
            WHERE empresa_id = %s
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
    assert row is not None
    return RAGSummary(
        queries_24h=int(row[0] or 0),
        queries_7d=int(row[1] or 0),
        miss_rate_24h=float(row[2] or 0),
        avg_score_24h=float(row[3]) if row[3] is not None else None,
        avg_duracao_ms_24h=float(row[4]) if row[4] is not None else None,
    )


@router.get("/top-queries", response_model=list[TopQuery])
async def top_queries(
    empresa_id: int = Depends(get_empresa_context),
    days: int = Query(default=7, ge=1, le=90),
    only_miss: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[TopQuery]:
    """Top queries por frequência. Quando only_miss, só as que retornaram 0 hits."""
    pool = await get_pool()
    miss_clause = " AND hits = 0" if only_miss else ""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT
              query_text,
              COUNT(*) AS n,
              COUNT(*) FILTER (WHERE hits = 0)::float / COUNT(*) AS miss_rate,
              AVG(top_score) FILTER (WHERE hits > 0) AS avg_score,
              MAX(created_at) AS last_seen
            FROM rag_query_log
            WHERE empresa_id = %s
              AND created_at > NOW() - INTERVAL '%s days'
              {miss_clause}
            GROUP BY query_text
            ORDER BY n DESC
            LIMIT %s
            """,
            (empresa_id, days, limit),
        )
        rows = await cur.fetchall()
    return [
        TopQuery(
            query_text=r[0],
            n=int(r[1]),
            miss_rate=float(r[2] or 0),
            avg_score=float(r[3]) if r[3] is not None else None,
            last_seen=r[4],
        )
        for r in rows
    ]


@router.get("/by-agente", response_model=list[AgenteStat])
async def stats_by_agente(
    empresa_id: int = Depends(get_empresa_context),
    days: int = Query(default=7, ge=1, le=90),
) -> list[AgenteStat]:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
              agente_slug,
              COUNT(*) AS n,
              COUNT(*) FILTER (WHERE hits = 0)::float / COUNT(*) AS miss_rate,
              AVG(top_score) FILTER (WHERE hits > 0) AS avg_score
            FROM rag_query_log
            WHERE empresa_id = %s
              AND created_at > NOW() - INTERVAL '%s days'
            GROUP BY agente_slug
            ORDER BY n DESC
            """,
            (empresa_id, days),
        )
        rows = await cur.fetchall()
    return [
        AgenteStat(
            agente_slug=r[0],
            queries=int(r[1]),
            miss_rate=float(r[2] or 0),
            avg_score=float(r[3]) if r[3] is not None else None,
        )
        for r in rows
    ]


class ModeStat(BaseModel):
    mode: str
    queries: int
    miss_rate: float
    avg_score: float | None
    avg_duracao_ms: float | None
    hyde_count: int


@router.get("/by-mode", response_model=list[ModeStat])
async def stats_by_mode(
    empresa_id: int = Depends(get_empresa_context),
    days: int = Query(default=7, ge=1, le=90),
) -> list[ModeStat]:
    """Distribuição por modo de busca (Sprint N.5).

    vector | hybrid | hybrid_hyde — útil pra ver qual estratégia
    funcionou melhor no período.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
              mode,
              COUNT(*) AS n,
              COUNT(*) FILTER (WHERE hits = 0)::float / COUNT(*) AS miss_rate,
              AVG(top_score) FILTER (WHERE hits > 0) AS avg_score,
              AVG(duracao_ms) AS avg_dur,
              COUNT(*) FILTER (WHERE hyde_query IS NOT NULL) AS hyde_count
            FROM rag_query_log
            WHERE empresa_id = %s
              AND created_at > NOW() - INTERVAL '%s days'
            GROUP BY mode
            ORDER BY n DESC
            """,
            (empresa_id, days),
        )
        rows = await cur.fetchall()
    return [
        ModeStat(
            mode=r[0] or "unknown",
            queries=int(r[1]),
            miss_rate=float(r[2] or 0),
            avg_score=float(r[3]) if r[3] is not None else None,
            avg_duracao_ms=float(r[4]) if r[4] is not None else None,
            hyde_count=int(r[5] or 0),
        )
        for r in rows
    ]


@router.get("/recent", response_model=list[RecentQuery])
async def recent_queries(
    empresa_id: int = Depends(get_empresa_context),
    limit: int = Query(default=50, ge=1, le=200),
    only_miss: bool = Query(default=False),
) -> list[RecentQuery]:
    pool = await get_pool()
    miss_clause = " AND hits = 0" if only_miss else ""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT id, query_text, agente_slug, pasta_ids, hits, top_score,
                   duracao_ms, error, created_at
            FROM rag_query_log
            WHERE empresa_id = %s
              {miss_clause}
            ORDER BY id DESC
            LIMIT %s
            """,
            (empresa_id, limit),
        )
        rows = await cur.fetchall()
    return [
        RecentQuery(
            id=int(r[0]),
            query_text=r[1],
            agente_slug=r[2],
            pasta_ids=list(r[3] or []),
            hits=int(r[4]),
            top_score=float(r[5]) if r[5] is not None else None,
            duracao_ms=int(r[6]) if r[6] is not None else None,
            error=r[7],
            created_at=r[8],
        )
        for r in rows
    ]


class PreviewRequest(BaseModel):
    query: str
    pasta_ids: list[int] | None = None
    modes: list[str] | None = None  # default: ["hybrid"]


class PreviewHit(BaseModel):
    doc_id: int
    titulo: str
    chunk_idx: int
    score: float
    reason: str | None
    snippet: str
    pasta_id: int | None


class PreviewModeResult(BaseModel):
    mode: str
    hyde_query: str | None
    duracao_ms: int
    hits: list[PreviewHit]


@router.post("/preview", response_model=list[PreviewModeResult])
async def preview_search(
    body: PreviewRequest,
    empresa_id: int = Depends(get_empresa_context),
) -> list[PreviewModeResult]:
    """Playground: simula a busca RAG sem chamar o agente (Sprint N.4).

    Quando `modes` tem múltiplos valores, retorna 1 conjunto por modo
    pra UI comparar lado a lado:
        ["vector", "hybrid", "hybrid_hyde"]
    """
    import time

    from whatsapp_langchain.shared import base_conhecimento

    if not body.query.strip():
        raise HTTPException(status_code=422, detail="Query vazia.")

    modes = body.modes or ["hybrid"]
    valid_modes = {"vector", "hybrid", "hybrid_hyde"}
    invalid = [m for m in modes if m not in valid_modes]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Modes inválidos: {invalid}. Use: {sorted(valid_modes)}",
        )

    pool = await get_pool()
    out: list[PreviewModeResult] = []
    for mode in modes:
        started = time.perf_counter()
        hyde_q: str | None = None
        try:
            if mode == "hybrid_hyde":
                hyde_q = await base_conhecimento._hyde_expand(body.query)
            results = await base_conhecimento.search_relevant(
                pool, empresa_id, body.query,
                pasta_ids=body.pasta_ids,
                mode=mode,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{mode}: {e}") from e
        duracao = int((time.perf_counter() - started) * 1000)
        out.append(
            PreviewModeResult(
                mode=mode,
                hyde_query=hyde_q,
                duracao_ms=duracao,
                hits=[
                    PreviewHit(
                        doc_id=r.documento.id,
                        titulo=r.documento.titulo,
                        chunk_idx=r.chunk_idx,
                        score=float(r.score),
                        reason=r.reason,
                        snippet=r.chunk_conteudo[:300]
                        + ("…" if len(r.chunk_conteudo) > 300 else ""),
                        pasta_id=r.documento.pasta_id,
                    )
                    for r in results
                ],
            )
        )
    return out
