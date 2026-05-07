"""Endpoints de gestão do atendente humano (Sprint G).

Status real-time + heartbeat + listagem com capacidade.

URLs:
- POST /api/atendentes/me/status        — atendente muda próprio status
- POST /api/atendentes/me/heartbeat     — prova-de-vida (60s client-side)
- GET  /api/atendentes/empresa-status   — admin lista todos da empresa
- PUT  /api/atendentes/{user_id}/max-paralelos — admin edita capacidade
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.atendente import (
    get_ranking_empresa,
    get_user_dashboard,
    heartbeat,
    list_atendentes_empresa,
    set_max_paralelos,
    set_status,
)
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/atendentes",
    tags=["atendentes"],
    dependencies=[Depends(verify_service_token)],
)


class SetStatusInput(BaseModel):
    status: str = Field(..., pattern=r"^(online|ausente|pausa|offline)$")


class SetMaxParalelosInput(BaseModel):
    max_paralelos: int = Field(..., ge=1, le=50)


@router.get("/me/status")
async def get_my_status(
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Retorna status atual + capacidade do user logado."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            'SELECT atendente_status, atendente_status_at, atendente_max_paralelos '
            'FROM auth."user" WHERE id = %s',
            (user_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return {
            "atendente_status": None,
            "atendente_status_at": None,
            "atendente_max_paralelos": 5,
        }
    return {
        "atendente_status": row[0],
        "atendente_status_at": row[1].isoformat() if row[1] else None,
        "atendente_max_paralelos": row[2] or 5,
    }


@router.post("/me/status", status_code=204)
async def set_my_status(
    body: SetStatusInput,
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    """Atendente muda próprio status (online/ausente/pausa/offline)."""
    pool = await get_pool()
    try:
        await set_status(pool, user_id, status=body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/me/heartbeat", status_code=204)
async def my_heartbeat(
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    """Prova-de-vida — client-side envia a cada 60s.

    NÃO muda status (só atualiza `atendente_status_at`). Worker job marca
    offline quando 5min sem heartbeat.
    """
    pool = await get_pool()
    await heartbeat(pool, user_id)


@router.get("/empresa-status")
async def get_empresa_atendentes(
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("atendimento.read")),
) -> dict:
    """Lista atendentes da empresa com status + count atendimentos abertos.

    Usado pela página `/atendentes` (Sprint H) e pelo header pra ver
    colegas online em tempo real.
    """
    pool = await get_pool()
    items = await list_atendentes_empresa(pool, empresa_id)
    return {"atendentes": [a.to_dict() for a in items]}


@router.get("/me/dashboard")
async def my_dashboard(
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Dashboard do próprio atendente — KPIs + counts."""
    pool = await get_pool()
    return await get_user_dashboard(pool, empresa_id=empresa_id, user_id=user_id)


@router.get("/{user_id}/dashboard")
async def user_dashboard(
    user_id: str,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("atendimento.read")),
) -> dict:
    """Dashboard de outro atendente — admin/supervisor."""
    pool = await get_pool()
    return await get_user_dashboard(pool, empresa_id=empresa_id, user_id=user_id)


@router.get("/ranking")
async def ranking(
    dias: int = 30,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("atendimento.read")),
) -> dict:
    """Ranking de atendentes nos últimos N dias (default 30)."""
    if not 1 <= dias <= 365:
        raise HTTPException(status_code=400, detail="dias deve estar entre 1 e 365")
    pool = await get_pool()
    items = await get_ranking_empresa(pool, empresa_id, dias=dias)
    return {"items": items, "dias": dias}


@router.put("/{user_id}/max-paralelos", status_code=204)
async def update_max_paralelos(
    user_id: str,
    body: SetMaxParalelosInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("atendimento.write")),
) -> None:
    """Admin edita capacidade de atendimentos paralelos do user.

    Validação cross-empresa: user precisa ser membro da empresa ativa.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM empresa_membro WHERE user_id = %s AND empresa_id = %s",
            (user_id, empresa_id),
        )
        if (await cur.fetchone()) is None:
            raise HTTPException(
                status_code=404,
                detail="Usuário não é membro desta empresa.",
            )
    try:
        await set_max_paralelos(pool, user_id, body.max_paralelos)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
