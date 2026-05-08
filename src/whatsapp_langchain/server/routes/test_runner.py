"""Endpoints admin pra rodar/monitorar bateria E2E pelo painel (Sprint L).

Acesso restrito a `auth.user.is_superadmin = TRUE`. Em prod, gated por
`enable_test_runner=True` (env). Quando false, todos endpoints retornam 404.

Endpoints:
    POST /api/admin/tests/run                      — dispara run
    GET  /api/admin/tests/runs                     — historico
    GET  /api/admin/tests/runs/{id}                — detalhe
    GET  /api/admin/tests/runs/{id}/events         — SSE log + progresso
    POST /api/admin/tests/runs/{id}/kill           — SIGTERM
    GET  /api/admin/tests/runs/{id}/report         — Allure HTML
    GET  /api/admin/tests/runs/{id}/report/{path:path} — assets do Allure
"""

from __future__ import annotations

import asyncio
import json
import mimetypes

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_superadmin
from whatsapp_langchain.shared.test_runner import (
    get_report_path,
    get_run,
    list_runs,
    start_run,
    tail_log,
)
from whatsapp_langchain.shared.test_runner import (
    kill_run as _kill_run,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/admin/tests",
    tags=["test-runner"],
    dependencies=[Depends(verify_service_token)],
)


class RunRequest(BaseModel):
    filtro: str | None = Field(default=None, max_length=200)


async def _require_admin_and_enabled(user_id: str) -> None:
    """Gate: feature flag + admin check. 404 quando desabilitado."""
    if not getattr(settings, "enable_test_runner", False):
        raise HTTPException(status_code=404, detail="Test runner desabilitado.")
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        raise HTTPException(status_code=403, detail="Apenas superadmins.")


@router.post("/run", status_code=201)
async def run_endpoint(
    body: RunRequest,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    await _require_admin_and_enabled(user_id)
    pool = await get_pool()
    try:
        run = await start_run(pool, user_id=user_id, filtro=body.filtro)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return run.to_dict()


@router.get("/runs")
async def list_runs_endpoint(
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    await _require_admin_and_enabled(user_id)
    pool = await get_pool()
    runs = await list_runs(pool, limit=50)
    return {"items": [r.to_dict() for r in runs]}


@router.get("/runs/{run_id}")
async def get_run_endpoint(
    run_id: int,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    await _require_admin_and_enabled(user_id)
    pool = await get_pool()
    run = await get_run(pool, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run nao encontrado.")
    return run.to_dict()


@router.post("/runs/{run_id}/kill", status_code=204)
async def kill_run_endpoint(
    run_id: int,
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    await _require_admin_and_enabled(user_id)
    pool = await get_pool()
    ok = await _kill_run(pool, run_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Run nao esta rodando ou ja terminou.",
        )


@router.get("/runs/{run_id}/events")
async def events_endpoint(
    run_id: int,
    user_id: str = Depends(get_user_id_from_request),
):
    """SSE — emite log_chunk + progress + done. Heartbeat 25s."""
    await _require_admin_and_enabled(user_id)
    pool = await get_pool()
    run = await get_run(pool, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run nao encontrado.")

    async def event_gen():
        offset = 0
        last_status = run.status
        # Estado inicial
        yield f"event: snapshot\ndata: {json.dumps(run.to_dict())}\n\n"
        try:
            while True:
                # Tail log
                chunk, offset = tail_log(run_id, offset)
                if chunk:
                    payload = json.dumps({"chunk": chunk})
                    yield f"event: log_chunk\ndata: {payload}\n\n"

                # Progresso (status atual)
                cur = await get_run(pool, run_id)
                if cur is None:
                    yield "event: error\ndata: {}\n\n"
                    return
                if cur.status != last_status:
                    yield (
                        f"event: progress\n"
                        f"data: {json.dumps(cur.to_dict())}\n\n"
                    )
                    last_status = cur.status

                if cur.status not in ("queued", "running"):
                    yield (
                        f"event: done\n"
                        f"data: {json.dumps(cur.to_dict())}\n\n"
                    )
                    return

                # Heartbeat + sleep
                yield ": heartbeat\n\n"
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("test_runner_sse_failed", run_id=run_id, error=str(exc))
            yield f"event: error\ndata: {json.dumps({'error': str(exc)[:200]})}\n\n"

    return StreamingResponse(
        event_gen(),
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
    return await _serve_report_file(run_id, "index.html")


@router.get("/runs/{run_id}/report/{file_path:path}")
async def report_asset(
    run_id: int,
    file_path: str,
    user_id: str = Depends(get_user_id_from_request),
):
    await _require_admin_and_enabled(user_id)
    return await _serve_report_file(run_id, file_path)


async def _serve_report_file(run_id: int, sub: str) -> FileResponse:
    path = get_report_path(run_id, sub)
    if not path:
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado.")
    mime, _ = mimetypes.guess_type(str(path))
    return FileResponse(
        str(path),
        media_type=mime or "application/octet-stream",
        headers={"Cache-Control": "no-cache"},
    )
