"""Proxy enxuto pro LangSmith — lista runs do project + link pra UI completa.

A UI de traces do painel não duplica o LangSmith: traz só uma lista resumida
(nome, status, latência, tokens, thread) e um link `Abrir →` que leva direto
pra smith.langchain.com.

Requer `LANGCHAIN_API_KEY` e `LANGCHAIN_PROJECT` configuradas. Sem elas o
endpoint retorna 503 — útil pra ambientes que não usam LangSmith.

Filtragem por `thread_id` é client-side: o LangSmith API foi consultado, e os
runs com `extra.metadata.thread_id` correspondente são selecionados antes do
truncamento por `limit`.
"""

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from langsmith import Client as LangSmithClient

from whatsapp_langchain.server.dependencies import verify_service_token
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.models import TraceInfo

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/traces",
    tags=["traces"],
    dependencies=[Depends(verify_service_token)],
)


def _smith_url(run_id: str) -> str:
    return (
        f"https://smith.langchain.com/o/_/projects/p/"
        f"{settings.langchain_project}/r/{run_id}"
    )


def _to_trace_info(run) -> TraceInfo:
    metadata = (run.extra or {}).get("metadata", {}) or {}
    latency_ms = None
    if run.end_time and run.start_time:
        latency_ms = int((run.end_time - run.start_time).total_seconds() * 1000)

    return TraceInfo(
        run_id=str(run.id),
        name=run.name,
        status=run.status,
        start_time=run.start_time.isoformat() if run.start_time else None,
        end_time=run.end_time.isoformat() if run.end_time else None,
        latency_ms=latency_ms,
        total_tokens=run.total_tokens,
        thread_id=metadata.get("thread_id"),
        smith_url=_smith_url(str(run.id)),
    )


def _fetch_runs(api_key: str, project: str, limit: int) -> list:
    """Bloqueia chamando a API LangSmith — chamado via asyncio.to_thread."""
    client = LangSmithClient(api_key=api_key)
    return list(
        client.list_runs(
            project_name=project,
            is_root=True,
            limit=limit,
        )
    )


@router.get("")
async def list_traces(
    limit: int = Query(default=20, ge=1, le=100),
    thread_id: str | None = Query(default=None),
) -> dict[str, list[TraceInfo]]:
    """Lista as runs mais recentes do project; opcionalmente filtra por thread_id.

    Filtro de thread é client-side: busca um múltiplo do `limit` na API
    LangSmith e filtra localmente por `extra.metadata.thread_id`.
    """
    if not settings.langchain_api_key or not settings.langchain_project:
        raise HTTPException(
            status_code=503,
            detail="LangSmith não configurado (LANGCHAIN_API_KEY/PROJECT ausentes).",
        )

    api_key = settings.langchain_api_key.get_secret_value()
    project = settings.langchain_project
    fetch = limit if not thread_id else min(limit * 5, 500)
    runs = await asyncio.to_thread(_fetch_runs, api_key, project, fetch)

    if thread_id:
        runs = [
            r
            for r in runs
            if (r.extra or {}).get("metadata", {}).get("thread_id") == thread_id
        ]

    runs = runs[:limit]
    traces = [_to_trace_info(r) for r in runs]
    logger.debug("traces_listed", count=len(traces), thread_id=thread_id)
    return {"traces": traces}
