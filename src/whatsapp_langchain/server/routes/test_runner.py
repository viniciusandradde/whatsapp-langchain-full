"""Pure proxy pros endpoints do test runner standalone (Sprint L).

API valida superadmin + feature flag, depois forwarda pra
`http://tests:8001/...` (container dedicado).

Quando `enable_test_runner=False` ou `TESTS_RUNNER_URL` não está setado,
todos endpoints retornam 404 — UI mostra "feature desabilitada".

Endpoints:
    POST /api/admin/tests/run                          → POST /run
    GET  /api/admin/tests/runs                         → GET  /runs
    GET  /api/admin/tests/runs/{id}                    → GET  /runs/{id}
    POST /api/admin/tests/runs/{id}/kill               → POST /runs/{id}/kill
    GET  /api/admin/tests/runs/{id}/events             → GET  /runs/{id}/events (SSE)
    GET  /api/admin/tests/runs/{id}/report             → GET  /runs/{id}/report
    GET  /api/admin/tests/runs/{id}/report/{path:path} → GET  /runs/{id}/report/...
"""

from __future__ import annotations

import os

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_superadmin

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/admin/tests",
    tags=["test-runner"],
    dependencies=[Depends(verify_service_token)],
)


def _runner_url() -> str:
    return os.environ.get("TESTS_RUNNER_URL", "http://tests:8001").rstrip("/")


def _runner_enabled() -> bool:
    if not getattr(settings, "enable_test_runner", False):
        return False
    return bool(_runner_url())


async def _require_admin_and_enabled(user_id: str) -> None:
    if not _runner_enabled():
        raise HTTPException(status_code=404, detail="Test runner desabilitado.")
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        raise HTTPException(status_code=403, detail="Apenas superadmins.")


class RunRequest(BaseModel):
    filtro: str | None = Field(default=None, max_length=200)


@router.post("/run", status_code=201)
async def run_endpoint(
    body: RunRequest,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    await _require_admin_and_enabled(user_id)
    payload = {"user_id": user_id, "filtro": body.filtro}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(f"{_runner_url()}/run", json=payload)
        except httpx.HTTPError as exc:
            logger.warning("tests_runner_unreachable", error=str(exc))
            raise HTTPException(
                status_code=503,
                detail="Container tests não está rodando. Suba com `docker compose --profile tests up -d tests`.",
            ) from exc
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise HTTPException(status_code=r.status_code, detail=detail)
    return r.json()


@router.get("/runs")
async def list_runs_endpoint(
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    await _require_admin_and_enabled(user_id)
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{_runner_url()}/runs")
        except httpx.HTTPError as exc:
            logger.warning("tests_runner_unreachable", error=str(exc))
            return {"items": []}
    if r.status_code >= 400:
        return {"items": []}
    return r.json()


@router.get("/runs/{run_id}")
async def get_run_endpoint(
    run_id: int,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    await _require_admin_and_enabled(user_id)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_runner_url()}/runs/{run_id}")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Run nao encontrado.")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.post("/runs/{run_id}/kill", status_code=204)
async def kill_run_endpoint(
    run_id: int,
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    await _require_admin_and_enabled(user_id)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{_runner_url()}/runs/{run_id}/kill")
    if r.status_code == 409:
        raise HTTPException(status_code=409, detail="Run nao esta rodando.")
    if r.status_code >= 400 and r.status_code != 204:
        raise HTTPException(status_code=r.status_code, detail=r.text)


@router.get("/runs/{run_id}/events")
async def events_endpoint(
    run_id: int,
    request: Request,
    user_id: str = Depends(get_user_id_from_request),
):
    """SSE proxy — abre stream upstream e pipe pro client."""
    await _require_admin_and_enabled(user_id)

    async def stream():
        client = httpx.AsyncClient(timeout=None)
        try:
            async with client.stream(
                "GET",
                f"{_runner_url()}/runs/{run_id}/events",
                headers={"Accept": "text/event-stream"},
            ) as r:
                if r.status_code >= 400:
                    yield (
                        f"event: error\ndata: {{\"status\":{r.status_code}}}\n\n".encode()
                    )
                    return
                async for chunk in r.aiter_bytes():
                    if await request.is_disconnected():
                        return
                    yield chunk
        finally:
            await client.aclose()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs/{run_id}/report")
async def report_index(
    run_id: int,
    user_id: str = Depends(get_user_id_from_request),
):
    await _require_admin_and_enabled(user_id)
    return await _proxy_report_file(run_id, "")


@router.get("/runs/{run_id}/report/{file_path:path}")
async def report_asset(
    run_id: int,
    file_path: str,
    user_id: str = Depends(get_user_id_from_request),
):
    await _require_admin_and_enabled(user_id)
    return await _proxy_report_file(run_id, file_path)


async def _proxy_report_file(run_id: int, sub: str) -> Response:
    suffix = f"/{sub}" if sub else ""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{_runner_url()}/runs/{run_id}/report{suffix}")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado.")
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/octet-stream"),
        headers={"Cache-Control": "no-cache"},
    )
