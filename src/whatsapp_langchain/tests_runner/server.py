"""FastAPI standalone do test runner — roda no container `tests` (Sprint L).

Sem autenticação. Bind no port 8001 dentro da rede Docker — não exposto
ao host. A API valida superadmin e proxia. Esta é a fonte de verdade
de execução.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from whatsapp_langchain.shared.db import close_pool, get_pool
from whatsapp_langchain.tests_runner.runner import (
    get_report_path,
    get_run,
    list_runs,
    start_run,
    tail_log,
)
from whatsapp_langchain.tests_runner.runner import kill_run as _kill_run

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await get_pool()
    logger.info("tests_runner_started", pool_min=pool.min_size, pool_max=pool.max_size)
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(title="Tests Runner (Sprint L)", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": "tests_runner"}


class RunRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    filtro: str | None = Field(default=None, max_length=200)
    # Sprint Eval-UI (mig 075): roteia entre tests/e2e/ e tests/eval/.
    modo: str = Field(default="e2e", max_length=20)


@app.post("/run", status_code=201)
async def run_endpoint(body: RunRequest) -> dict:
    pool = await get_pool()
    try:
        run = await start_run(
            pool, user_id=body.user_id, filtro=body.filtro, modo=body.modo
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return run.to_dict()


@app.get("/runs")
async def list_runs_endpoint() -> dict:
    pool = await get_pool()
    runs = await list_runs(pool, limit=50)
    return {"items": [r.to_dict() for r in runs]}


@app.get("/runs/{run_id}")
async def get_run_endpoint(run_id: int) -> dict:
    pool = await get_pool()
    run = await get_run(pool, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run nao encontrado.")
    return run.to_dict()


@app.post("/runs/{run_id}/kill", status_code=204)
async def kill_run_endpoint(run_id: int) -> None:
    pool = await get_pool()
    ok = await _kill_run(pool, run_id)
    if not ok:
        raise HTTPException(
            status_code=409, detail="Run nao esta rodando ou ja terminou."
        )


@app.get("/runs/{run_id}/events")
async def events_endpoint(run_id: int):
    pool = await get_pool()
    run = await get_run(pool, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run nao encontrado.")

    async def event_gen():
        offset = 0
        last_status = run.status
        yield f"event: snapshot\ndata: {json.dumps(run.to_dict())}\n\n"
        try:
            while True:
                chunk, offset = tail_log(run_id, offset)
                if chunk:
                    payload = json.dumps({"chunk": chunk})
                    yield f"event: log_chunk\ndata: {payload}\n\n"

                cur = await get_run(pool, run_id)
                if cur is None:
                    yield "event: error\ndata: {}\n\n"
                    return
                if cur.status != last_status:
                    yield f"event: progress\ndata: {json.dumps(cur.to_dict())}\n\n"
                    last_status = cur.status

                if cur.status not in ("queued", "running"):
                    yield f"event: done\ndata: {json.dumps(cur.to_dict())}\n\n"
                    return

                yield ": heartbeat\n\n"
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("tests_runner_sse_failed", run_id=run_id, error=str(exc))
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


@app.get("/runs/{run_id}/report")
async def report_index(run_id: int):
    return await _serve_report_file(run_id, "index.html")


@app.get("/runs/{run_id}/report/{file_path:path}")
async def report_asset(run_id: int, file_path: str):
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
