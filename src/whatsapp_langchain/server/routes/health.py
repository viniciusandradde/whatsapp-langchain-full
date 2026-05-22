"""Rotas de health check + métricas Prometheus (Fase 0 enterprise).

Endpoints:
  /health                 — geral (HTTP 200 ok / 503 degraded)
  /api/health/db          — só DB (latency em ms)
  /api/health/queue       — message_queue (size por status, oldest queued)
  /api/health/agent       — última invocação OK ou erro
  /api/health/workers     — workers ativos (heartbeat)
  /metrics                — Prometheus text format

Filosofia: cada subsystem tem health independente — status pages tipo
BetterStack/Statuspage podem mapear granular ao invés de "tudo ou nada".
"""

from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from whatsapp_langchain import __version__
from whatsapp_langchain.shared.db import check_db_health, get_pool
from whatsapp_langchain.shared.metrics import (
    CONTENT_TYPE_PROMETHEUS,
    queue_size,
    render_prometheus_text,
)

router = APIRouter(tags=["health"])


# ---- Geral (compat retroativa) ----


@router.get("/health")
async def health() -> JSONResponse:
    """Health geral — agrega DB. Mantido pra compat com checks existentes."""
    is_healthy = await check_db_health()
    if not is_healthy:
        return JSONResponse(
            content={
                "status": "degraded",
                "database": "disconnected",
                "version": __version__,
            },
            status_code=503,
        )
    return JSONResponse(
        content={
            "status": "ok",
            "database": "connected",
            "version": __version__,
        }
    )


# ---- Granulares (Fase 0) ----


@router.get("/api/health/db")
async def health_db() -> JSONResponse:
    """DB-specific health: latency em ms + ok/degraded."""
    start = time.perf_counter()
    is_healthy = await check_db_health()
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    status_code = 200 if is_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if is_healthy else "degraded",
            "subsystem": "database",
            "latency_ms": latency_ms,
        },
    )


@router.get("/api/health/queue")
async def health_queue() -> JSONResponse:
    """Queue health: counts por status + oldest queued (idade em segundos).

    Sprint A.2.3: cross-tenant deliberado (health/ops visa todos os
    tenants). Bypass RLS via set_config inline antes das queries.
    """
    pool = await get_pool()
    try:
        async with pool.connection() as conn:
            await conn.execute(
                "SELECT set_config('app.bypass_rls', 'true', false)"
            )
            cur = await conn.execute(
                """
                SELECT status, COUNT(*)
                  FROM message_queue
                 GROUP BY status
                """
            )
            by_status = {row[0]: row[1] for row in await cur.fetchall()}

            cur = await conn.execute(
                """
                SELECT EXTRACT(EPOCH FROM NOW() - MIN(created_at))
                  FROM message_queue
                 WHERE status = 'queued'
                """
            )
            row = await cur.fetchone()
            oldest_queued_age_s = float(row[0]) if row and row[0] else 0.0
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "subsystem": "queue",
                "error": str(exc)[:200],
            },
        )

    # Atualiza gauge Prometheus
    for st, count in by_status.items():
        queue_size.labels(status=st).set(count)

    # Degraded se backlog grande OU mensagem velha
    backlog = by_status.get("queued", 0) + by_status.get("processing", 0)
    is_degraded = backlog > 500 or oldest_queued_age_s > 600
    return JSONResponse(
        status_code=200 if not is_degraded else 503,
        content={
            "status": "ok" if not is_degraded else "degraded",
            "subsystem": "queue",
            "by_status": by_status,
            "oldest_queued_age_seconds": round(oldest_queued_age_s, 1),
        },
    )


@router.get("/api/health/agent")
async def health_agent() -> JSONResponse:
    """Agent health: última msg processada com sucesso (recência).

    Sprint A.2.3: bypass RLS (cross-tenant ops).
    """
    pool = await get_pool()
    try:
        async with pool.connection() as conn:
            await conn.execute(
                "SELECT set_config('app.bypass_rls', 'true', false)"
            )
            cur = await conn.execute(
                """
                SELECT EXTRACT(EPOCH FROM NOW() - MAX(processed_at))
                  FROM message_queue
                 WHERE status = 'done'
                """
            )
            row = await cur.fetchone()
            last_done_age_s = float(row[0]) if row and row[0] else None

            cur = await conn.execute(
                """
                SELECT COUNT(*)
                  FROM message_queue
                 WHERE status = 'failed' AND updated_at > NOW() - INTERVAL '10 minutes'
                """
            )
            failed_recent = (await cur.fetchone())[0]
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "subsystem": "agent",
                "error": str(exc)[:200],
            },
        )

    # Sem msg processada nunca → ok (sistema novo); processada >5min atrás
    # com queue >0 → suspeito; >10 falhas/10min → degraded
    is_degraded = failed_recent > 10
    return JSONResponse(
        status_code=200 if not is_degraded else 503,
        content={
            "status": "ok" if not is_degraded else "degraded",
            "subsystem": "agent",
            "last_done_age_seconds": (
                round(last_done_age_s, 1) if last_done_age_s is not None else None
            ),
            "failed_in_last_10min": failed_recent,
        },
    )


@router.get("/api/health/workers")
async def health_workers() -> JSONResponse:
    """Workers heartbeat — proxy: lookup de processing rows recentes (<2min).

    Sem tabela `worker_heartbeat` ainda — heurística: se há rows em
    `processing` com `lease_until` futuro, há worker vivo. Workers em
    crash/idle aparecem como zero.

    Sprint A.2.3: bypass RLS (cross-tenant ops).
    """
    pool = await get_pool()
    try:
        async with pool.connection() as conn:
            await conn.execute(
                "SELECT set_config('app.bypass_rls', 'true', false)"
            )
            cur = await conn.execute(
                """
                SELECT COUNT(DISTINCT id)
                  FROM message_queue
                 WHERE status = 'processing' AND lease_until > NOW()
                """
            )
            active_leases = (await cur.fetchone())[0]
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "subsystem": "workers",
                "error": str(exc)[:200],
            },
        )

    # Indeterminado: queue vazia → ok (sem trabalho); queue >0 + sem
    # leases ativas → suspeito mas não certeza (worker pode ter acabado
    # de claim e não commitou ainda). Reportamos info; status 200 sempre
    # exceto erro DB.
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "subsystem": "workers",
            "active_leases": active_leases,
            "note": (
                "Heurística baseada em lease_until ativo; sem heartbeat dedicado ainda."
            ),
        },
    )


# ---- Prometheus metrics ----


@router.get("/metrics")
async def metrics() -> Response:
    """Endpoint Prometheus — text/plain format. Sem auth (padrão Prometheus)."""
    return Response(
        content=render_prometheus_text(),
        media_type=CONTENT_TYPE_PROMETHEUS,
    )
