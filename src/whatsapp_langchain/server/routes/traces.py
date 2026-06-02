"""Observabilidade — lista traces do provider ativo + link pra UI completa.

**Langfuse é o primário; LangSmith é o fallback.** Quando `LANGFUSE_ENABLED`
(as duas keys setadas), a lista vem do Langfuse self-host; senão cai pro
LangSmith (`LANGCHAIN_API_KEY/PROJECT`). 503 só quando NENHUM está configurado.

A UI não duplica o painel do provider: traz uma lista resumida (nome, status,
latência, tokens, thread) + `Abrir →` que leva pro trace na UI do provider.
Filtro por `thread_id` mapeia pra `session_id` no Langfuse (o worker seta
`session_id = thread_id`) e pra `extra.metadata.thread_id` no LangSmith.
"""

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from langsmith import Client as LangSmithClient

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.shared import langfuse_client
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import TraceInfo

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/traces",
    tags=["traces"],
    dependencies=[Depends(verify_service_token)],
)


def _active_provider() -> str | None:
    """langfuse > langsmith > None (nenhum configurado)."""
    if settings.langfuse_enabled:
        return "langfuse"
    if settings.langchain_api_key and settings.langchain_project:
        return "langsmith"
    return None


# ----------------------------- Langfuse ------------------------------


def _lf_to_trace_info(t: dict[str, Any]) -> TraceInfo:
    tid = str(t.get("id"))
    latency = t.get("latency")  # segundos (float) no Langfuse
    latency_ms = int(latency * 1000) if isinstance(latency, int | float) else None
    usage = t.get("usage") or {}
    total_tokens = usage.get("total") if isinstance(usage, dict) else None
    url = langfuse_client.trace_url(tid)
    return TraceInfo(
        run_id=tid,
        name=t.get("name"),
        status=None,
        start_time=t.get("timestamp"),
        end_time=None,
        latency_ms=latency_ms,
        total_tokens=total_tokens,
        thread_id=t.get("sessionId"),
        source="langfuse",
        url=url,
        smith_url=url,
    )


# ----------------------------- LangSmith -----------------------------


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

    url = _smith_url(str(run.id))
    return TraceInfo(
        run_id=str(run.id),
        name=run.name,
        status=run.status,
        start_time=run.start_time.isoformat() if run.start_time else None,
        end_time=run.end_time.isoformat() if run.end_time else None,
        latency_ms=latency_ms,
        total_tokens=run.total_tokens,
        thread_id=metadata.get("thread_id"),
        source="langsmith",
        url=url,
        smith_url=url,
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


@router.get("/config")
async def traces_config() -> dict[str, Any]:
    """Fonte de observabilidade ativa — o frontend usa pra badge + deep-links."""
    provider = _active_provider()
    return {"provider": provider, "enabled": provider is not None}


@router.get("/atendimento/{atendimento_id}")
async def trace_link_for_atendimento(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, Any]:
    """Deep-link de observabilidade pra um atendimento.

    Resolve o `thread_id` EXATO (`phone_number:agent_id`) da última mensagem do
    atendimento na `message_queue` — garante match com o `session_id` no
    Langfuse. Retorna também a URL direta do trace quando há `langfuse_trace_id`.
    """
    provider = _active_provider()
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT phone_number, agent_id, langfuse_trace_id "
            "FROM message_queue "
            "WHERE empresa_id = %s AND atendimento_id = %s "
            "ORDER BY id DESC LIMIT 1",
            (empresa_id, atendimento_id),
        )
        row = await cur.fetchone()
    if row is None:
        return {"provider": provider, "thread_id": None, "trace_url": None}
    phone, agent, trace_id = row
    thread_id = f"{phone}:{agent}" if phone and agent else None
    trace_url = (
        langfuse_client.trace_url(trace_id)
        if trace_id and settings.langfuse_enabled
        else None
    )
    return {"provider": provider, "thread_id": thread_id, "trace_url": trace_url}


@router.get("")
async def list_traces(
    limit: int = Query(default=20, ge=1, le=100),
    thread_id: str | None = Query(default=None),
) -> dict[str, list[TraceInfo]]:
    """Lista os traces mais recentes do provider ativo (Langfuse > LangSmith)."""
    provider = _active_provider()
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Observabilidade não configurada (defina LANGFUSE_* ou "
                "LANGCHAIN_API_KEY/PROJECT)."
            ),
        )

    if provider == "langfuse":
        raw = await asyncio.to_thread(langfuse_client.list_traces, limit, thread_id)
        traces = [_lf_to_trace_info(t) for t in raw]
        logger.debug("traces_listed", provider=provider, count=len(traces))
        return {"traces": traces}

    # Fallback LangSmith — filtro de thread é client-side.
    api_key = settings.langchain_api_key.get_secret_value()  # type: ignore[union-attr]
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
    logger.debug("traces_listed", provider=provider, count=len(traces))
    return {"traces": traces}
