"""Endpoint admin pra audit log LGPD (mig 094).

GET /api/lgpd/eventos — lista eventos da empresa ativa com filtros.
Perm: `lgpd.audit.read` (Admin + Gestor por default).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.lgpd import (
    EVENT_TYPES,
    count_events,
    list_events,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/lgpd",
    tags=["lgpd"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("/eventos")
async def list_eventos(
    event_type: str | None = Query(default=None),
    atendimento_id: int | None = Query(default=None),
    cliente_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, Any]:
    """Lista eventos LGPD da empresa com filtros + paginação.

    Filtros aceitos: event_type, atendimento_id, cliente_id, date_from, date_to.
    Default ordem: created_at DESC. Max 500 por página.
    """
    if event_type and event_type not in EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"event_type inválido. Use um de: {sorted(EVENT_TYPES)}",
        )

    pool = await get_pool()
    eventos = await list_events(
        pool,
        empresa_id,
        event_type=event_type,
        atendimento_id=atendimento_id,
        cliente_id=cliente_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    total = await count_events(
        pool,
        empresa_id,
        event_type=event_type,
        atendimento_id=atendimento_id,
    )
    return {
        "eventos": eventos,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/eventos/tipos")
async def list_event_types(
    _empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[str]]:
    """Retorna lista de event_types válidos pra dropdowns no painel."""
    return {"event_types": sorted(EVENT_TYPES)}
