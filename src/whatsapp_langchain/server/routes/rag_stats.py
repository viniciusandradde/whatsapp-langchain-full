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


class OutcomeStat(BaseModel):
    outcome: str
    queries: int
    avg_score: float | None
    avg_hits: float
    pct: float


@router.get("/by-outcome", response_model=list[OutcomeStat])
async def stats_by_outcome(
    empresa_id: int = Depends(get_empresa_context),
    days: int = Query(default=7, ge=1, le=90),
) -> list[OutcomeStat]:
    """Quebra por outcome do atendimento (Sprint P.1).

    Outcomes: success, transferred, abandoned, escalated, unknown.
    Permite ver: quando o RAG falha, qual o desfecho típico do atendimento?
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            WITH base AS (
                SELECT * FROM rag_query_log
                WHERE empresa_id = %s
                  AND created_at > NOW() - INTERVAL '%s days'
            ),
            total AS (SELECT COUNT(*) AS n FROM base)
            SELECT
              COALESCE(outcome, 'unknown') AS outcome,
              COUNT(*) AS queries,
              AVG(top_score) FILTER (WHERE hits > 0) AS avg_score,
              AVG(hits)::float AS avg_hits,
              (COUNT(*)::float / NULLIF((SELECT n FROM total), 0)) AS pct
            FROM base
            GROUP BY COALESCE(outcome, 'unknown')
            ORDER BY queries DESC
            """,
            (empresa_id, days),
        )
        rows = await cur.fetchall()
    return [
        OutcomeStat(
            outcome=r[0],
            queries=int(r[1]),
            avg_score=float(r[2]) if r[2] is not None else None,
            avg_hits=float(r[3] or 0),
            pct=float(r[4] or 0),
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


class Suggestion(BaseModel):
    id: int
    pasta_id: int | None
    pasta_nome: str | None
    titulo: str
    conteudo_draft: str
    queries_amostra: list[str]
    cluster_size: int
    status: str
    created_at: datetime


class RunLearnerResponse(BaseModel):
    misses: int
    clusters: int
    suggestions_created: int


class FewshotStats(BaseModel):
    total: int
    ready: int
    pending: int
    by_agente: dict[str, int]


@router.get("/fewshot/stats", response_model=FewshotStats)
async def fewshot_stats(
    empresa_id: int = Depends(get_empresa_context),
) -> FewshotStats:
    """Sprint P.3 — estatísticas de few-shot examples capturados."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE status = 'ready') AS ready,
              COUNT(*) FILTER (WHERE status = 'pending') AS pending,
              COUNT(*) AS total
            FROM fewshot_example
            WHERE empresa_id = %s
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
        cur = await conn.execute(
            """
            SELECT agente_slug, COUNT(*) AS n
              FROM fewshot_example
             WHERE empresa_id = %s AND status = 'ready'
             GROUP BY agente_slug
            """,
            (empresa_id,),
        )
        by_agent = {r[0]: int(r[1]) for r in await cur.fetchall()}
    assert row is not None
    return FewshotStats(
        total=int(row[2] or 0),
        ready=int(row[0] or 0),
        pending=int(row[1] or 0),
        by_agente=by_agent,
    )


@router.post("/fewshot/backfill")
async def fewshot_backfill(
    empresa_id: int = Depends(get_empresa_context),
    batch: int = Query(default=50, ge=1, le=500),
) -> dict:
    """Gera embeddings dos few-shots pending. Idempotente."""
    from whatsapp_langchain.shared.fewshot import backfill_embeddings

    pool = await get_pool()
    updated = await backfill_embeddings(pool, batch=batch)
    return {"ok": True, "updated": updated}


@router.post("/learner/run", response_model=RunLearnerResponse)
async def run_learner_endpoint(
    empresa_id: int = Depends(get_empresa_context),
    days: int = Query(default=7, ge=1, le=90),
) -> RunLearnerResponse:
    """Sprint P.2 — dispara pipeline de aprendizado on-demand.

    Lê queries que falharam, clusteriza, gera drafts via LLM, persiste
    em documento_sugerido. Demora ~10-30s dependendo do volume.
    """
    from whatsapp_langchain.shared.rag_learner import run_learner

    pool = await get_pool()
    result = await run_learner(pool, empresa_id, days=days)
    return RunLearnerResponse(**result)


@router.get("/suggestions", response_model=list[Suggestion])
async def list_suggestions(
    ctx_empresa_id: int = Depends(get_empresa_context),
    status: str = Query(default="pending"),
    empresa_id: int | None = Query(
        default=None,
        description="Override do contexto. Útil pra ver sandbox=999 sem trocar empresa ativa.",
    ),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[Suggestion]:
    """Lista sugestões. Default usa empresa do contexto (cookie); query
    param `empresa_id` força outra (ex: 999 sandbox).
    """
    eid = empresa_id if empresa_id is not None else ctx_empresa_id
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT s.id, s.pasta_id, p.nome, s.titulo, s.conteudo_draft,
                   s.queries_amostra, s.cluster_size, s.status, s.created_at
            FROM documento_sugerido s
            LEFT JOIN pasta p ON p.id = s.pasta_id
            WHERE s.empresa_id = %s AND s.status = %s
            ORDER BY s.cluster_size DESC, s.created_at DESC
            LIMIT %s
            """,
            (eid, status, limit),
        )
        rows = await cur.fetchall()
    return [
        Suggestion(
            id=r[0],
            pasta_id=r[1],
            pasta_nome=r[2],
            titulo=r[3],
            conteudo_draft=r[4],
            queries_amostra=list(r[5] or []),
            cluster_size=r[6],
            status=r[7],
            created_at=r[8],
        )
        for r in rows
    ]


class ApproveSuggestionRequest(BaseModel):
    titulo_final: str | None = None
    conteudo_final: str | None = None
    pasta_id: int | None = None


@router.post("/suggestions/{suggestion_id}/approve")
async def approve_suggestion(
    suggestion_id: int,
    body: ApproveSuggestionRequest,
    ctx_empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(__import__(
        "whatsapp_langchain.server.dependencies",
        fromlist=["get_user_id_from_request"]
    ).get_user_id_from_request),
) -> dict:
    """Aprova sugestão → cria documento_conhecimento + chunks + embeddings.

    Resolve empresa_id da própria sugestão (NÃO trava em ctx_empresa_id),
    permitindo aprovar sugestões da sandbox=999 sem trocar empresa ativa.
    """
    from whatsapp_langchain.shared.base_conhecimento import (
        backfill_chunks,
        upsert_documento,
    )
    from whatsapp_langchain.shared.models import DocumentoConhecimentoInput

    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT pasta_id, titulo, conteudo_draft, empresa_id
              FROM documento_sugerido
             WHERE id=%s AND status='pending'
            """,
            (suggestion_id,),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sugestão não encontrada.")

    pasta_id = body.pasta_id if body.pasta_id is not None else row[0]
    titulo = (body.titulo_final or row[1]).strip()
    conteudo = (body.conteudo_final or row[2]).strip()
    sug_empresa_id = int(row[3])  # empresa da sugestão (pode ser 999 sandbox)
    if not titulo or not conteudo:
        raise HTTPException(status_code=422, detail="Titulo+conteudo obrigatórios.")

    doc_input = DocumentoConhecimentoInput(
        titulo=titulo, conteudo=conteudo, pasta_id=pasta_id,
        ativo=True, tags=["auto-suggested"],
    )
    new_doc = await upsert_documento(pool, sug_empresa_id, doc_input, user_id=user_id)

    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE documento_sugerido
               SET status='approved', reviewed_by_user_id=%s, reviewed_at=NOW(),
                   promoted_doc_id=%s
             WHERE id=%s
            """,
            (user_id, new_doc.id, suggestion_id),
        )
        await conn.commit()

    # Backfill embeddings (best-effort)
    try:
        await backfill_chunks(pool, only_doc_id=new_doc.id)
    except Exception as e:
        logger.warning("backfill_after_approve_failed", error=str(e))

    return {"ok": True, "doc_id": new_doc.id}


@router.post("/suggestions/{suggestion_id}/reject")
async def reject_suggestion(
    suggestion_id: int,
    user_id: str = Depends(__import__(
        "whatsapp_langchain.server.dependencies",
        fromlist=["get_user_id_from_request"]
    ).get_user_id_from_request),
) -> dict:
    """Rejeita sugestão. Sem filtro empresa_id — qualquer admin com sessão
    pode rejeitar qualquer sugestão (sandbox 999 incluso)."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE documento_sugerido
               SET status='rejected', reviewed_by_user_id=%s, reviewed_at=NOW()
             WHERE id=%s AND status='pending'
             RETURNING id
            """,
            (user_id, suggestion_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Sugestão não encontrada.")
    return {"ok": True}


class SandboxSummary(BaseModel):
    empresa_id: int
    total_atendimentos: int
    by_setor: dict[str, int]
    by_outcome: dict[str, int]


class CleanResult(BaseModel):
    total: int
    greetings: int
    low_value: int
    duplicates: int
    will_disable: int
    applied: bool


@router.post("/sandbox/clean", response_model=CleanResult)
async def sandbox_clean(
    empresa_id: int = Query(default=999),
    dry_run: bool = Query(default=True),
) -> CleanResult:
    """Sprint S.5 — limpa dataset (greetings/low_value/dupes) marcando
    status='disabled'. dry_run=true só conta, não modifica.
    """
    from whatsapp_langchain.shared.dataset_cleaner import (
        analyze_dataset,
        clean_dataset,
    )

    pool = await get_pool()
    if dry_run:
        stats = await analyze_dataset(pool, empresa_id)
        return CleanResult(
            total=stats.total,
            greetings=stats.greetings,
            low_value=stats.low_value,
            duplicates=stats.duplicates,
            will_disable=stats.will_disable,
            applied=False,
        )
    stats = await clean_dataset(pool, empresa_id)
    return CleanResult(
        total=stats.total,
        greetings=stats.greetings,
        low_value=stats.low_value,
        duplicates=stats.duplicates,
        will_disable=stats.will_disable,
        applied=True,
    )


@router.get("/sandbox/summary", response_model=SandboxSummary)
async def sandbox_summary(
    empresa_id: int = Query(default=999),
) -> SandboxSummary:
    """Sprint R.6 — KPIs da sandbox (3 meses ZigChat)."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT COUNT(*),
                   COALESCE(jsonb_object_agg(setor_classificado, n) FILTER (
                       WHERE setor_classificado IS NOT NULL
                   ), '{}'::jsonb) as by_setor
              FROM (
                SELECT setor_classificado, COUNT(*) as n
                  FROM fewshot_example
                 WHERE empresa_id = %s
                 GROUP BY setor_classificado
              ) s
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
        total = int(row[0] or 0) if row else 0
        by_setor = dict(row[1] or {}) if row else {}

        cur = await conn.execute(
            """
            SELECT outcome, COUNT(*) FROM fewshot_example
             WHERE empresa_id = %s GROUP BY outcome
            """,
            (empresa_id,),
        )
        by_outcome = {r[0]: int(r[1]) for r in await cur.fetchall()}
        # total real (não dependente de classificação)
        cur = await conn.execute(
            "SELECT COUNT(*) FROM fewshot_example WHERE empresa_id = %s",
            (empresa_id,),
        )
        r2 = await cur.fetchone()
        total = int(r2[0] or 0) if r2 else total
    return SandboxSummary(
        empresa_id=empresa_id,
        total_atendimentos=total,
        by_setor=by_setor,
        by_outcome=by_outcome,
    )


class TopProblem(BaseModel):
    setor: str
    titulo: str
    cluster_size: int
    sample_query: str


@router.get("/sandbox/top-problems", response_model=list[TopProblem])
async def sandbox_top_problems(
    empresa_id: int = Query(default=999),
    setor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[TopProblem]:
    """Top clusters criados por R.4 (documento_sugerido pendentes)."""
    pool = await get_pool()
    where_setor = ""
    params: list = [empresa_id]
    if setor:
        where_setor = " AND p.nome ILIKE 'KB Rádio ' || %s || '%%'"
        params.append(setor.capitalize())
    params.append(limit)

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT p.nome AS setor, ds.titulo, ds.cluster_size,
                   COALESCE(ds.queries_amostra[1], '') AS sample_query
              FROM documento_sugerido ds
              LEFT JOIN pasta p ON p.id = ds.pasta_id
             WHERE ds.empresa_id = %s
               AND ds.status = 'pending'
               {where_setor}
             ORDER BY ds.cluster_size DESC
             LIMIT %s
            """,
            tuple(params),
        )
        rows = await cur.fetchall()
    return [
        TopProblem(
            setor=(r[0] or "—").replace("KB Rádio ", "").lower(),
            titulo=r[1],
            cluster_size=int(r[2]),
            sample_query=r[3] or "",
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
