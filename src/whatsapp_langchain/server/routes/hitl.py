"""HITL — Human-in-the-loop (Sprint O.3).

Endpoints admin pra:
- Listar ações pendentes
- Aprovar/rejeitar ação (resume/cancel agente)
- SSE stream pra UI realtime

Tools que disparam HITL: transfer_to_human, cancelar_agendamento,
criar_agendamento (lista configurável via env).
"""

from __future__ import annotations

import asyncio
import json
import os

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/admin/hitl",
    tags=["hitl"],
    dependencies=[Depends(verify_service_token)],
)


HITL_TOOLS_DEFAULT = "transfer_to_human,cancelar_agendamento"


def hitl_tools() -> set[str]:
    """Tools que requerem aprovação humana (configurável via env)."""
    raw = os.environ.get("HITL_TOOLS", HITL_TOOLS_DEFAULT)
    return {t.strip() for t in raw.split(",") if t.strip()}


class AcaoPendente(BaseModel):
    id: int
    atendimento_id: int
    agente_slug: str
    tool_name: str
    tool_args: dict
    motivo: str | None
    status: str
    expires_at: str
    created_at: str


class ReviewBody(BaseModel):
    note: str | None = None


@router.get("/pendentes", response_model=list[AcaoPendente])
async def list_pendentes(
    empresa_id: int = Depends(get_empresa_context),
    status: str = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AcaoPendente]:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, atendimento_id, agente_slug, tool_name, tool_args,
                   motivo, status, expires_at, created_at
              FROM acao_pendente
             WHERE empresa_id = %s AND status = %s
             ORDER BY created_at ASC
             LIMIT %s
            """,
            (empresa_id, status, limit),
        )
        rows = await cur.fetchall()
    return [
        AcaoPendente(
            id=r[0], atendimento_id=r[1], agente_slug=r[2],
            tool_name=r[3], tool_args=r[4] or {}, motivo=r[5],
            status=r[6],
            expires_at=r[7].isoformat() if r[7] else "",
            created_at=r[8].isoformat() if r[8] else "",
        )
        for r in rows
    ]


@router.post("/{acao_id}/approve")
async def approve(
    acao_id: int,
    body: ReviewBody,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE acao_pendente
               SET status='approved', reviewed_by_user_id=%s,
                   reviewed_at=NOW(), review_note=%s
             WHERE id=%s AND empresa_id=%s AND status='pending'
             RETURNING tool_name, atendimento_id
            """,
            (user_id, body.note, acao_id, empresa_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Ação não pendente.")
    logger.info(
        "hitl_approved",
        acao_id=acao_id, tool=row[0], atendimento_id=row[1], user_id=user_id,
    )
    return {"ok": True, "tool_name": row[0]}


@router.post("/{acao_id}/reject")
async def reject(
    acao_id: int,
    body: ReviewBody,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE acao_pendente
               SET status='rejected', reviewed_by_user_id=%s,
                   reviewed_at=NOW(), review_note=%s
             WHERE id=%s AND empresa_id=%s AND status='pending'
             RETURNING tool_name, atendimento_id
            """,
            (user_id, body.note, acao_id, empresa_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Ação não pendente.")
    logger.info(
        "hitl_rejected",
        acao_id=acao_id, tool=row[0], atendimento_id=row[1], user_id=user_id,
    )
    return {"ok": True}


@router.get("/events")
async def events_stream(
    empresa_id: int = Depends(get_empresa_context),
):
    """SSE — emite eventos quando acao_pendente é INSERT/UPDATE.

    UI assina pra atualizar lista em real-time.
    """
    async def gen():
        # Snapshot inicial
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT COUNT(*) FROM acao_pendente
                 WHERE empresa_id=%s AND status='pending'
                """,
                (empresa_id,),
            )
            row = await cur.fetchone()
        snapshot = {"pending_count": int(row[0] or 0)}
        yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

        # LISTEN
        try:
            async with pool.connection() as conn:
                await conn.set_autocommit(True)
                await conn.execute("LISTEN acao_pendente_change")
                while True:
                    notif = await conn.notifies(timeout=25.0)
                    if not notif:
                        yield ": heartbeat\n\n"
                        continue
                    for n in notif:
                        try:
                            payload = json.loads(n.payload)
                        except json.JSONDecodeError:
                            continue
                        if payload.get("empresa_id") != empresa_id:
                            continue
                        yield f"event: change\ndata: {json.dumps(payload)}\n\n"
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning("hitl_sse_failed", error=str(e))
            yield f"event: error\ndata: {json.dumps({'error': str(e)[:200]})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
