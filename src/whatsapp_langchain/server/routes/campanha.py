"""Endpoints de Campanha (E2.D M6.b).

CRUD + dispatch + abort. Dispatch é fire-and-forget — handler retorna
202 e o background task atualiza progresso no DB.
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
from whatsapp_langchain.shared import campanha as camp_lib
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/campanhas",
    tags=["campanha"],
    dependencies=[Depends(verify_service_token)],
)


class CampanhaCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    descricao: str | None = Field(default=None, max_length=500)
    mensagem: str = Field(min_length=1, max_length=4000)
    conexao_id: int | None = None
    intervalo_ms: int = Field(default=500, ge=0, le=60_000)
    max_destinatarios: int = Field(default=1000, ge=1, le=10_000)
    # Lista crua (será normalizada em E.164 no helper)
    telefones: list[str] = Field(min_length=1, max_length=10_000)
    # Sub-fase B+ (padrão profissional) (mig 051)
    modelo_mensagem_id: int | None = None
    scheduled_at: str | None = None  # ISO datetime
    tipo: str = "broadcast"  # broadcast|transactional|reativacao
    filtro_segmento: str | None = Field(default=None, max_length=120)
    filtro_tags: list[str] | None = None


@router.get("")
async def list_campanhas_endpoint(
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    pool = await get_pool()
    items = await camp_lib.list_campanhas(pool, empresa_id)
    return {"items": items}


@router.get("/{camp_id}")
async def get_campanha_endpoint(
    camp_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    pool = await get_pool()
    out = await camp_lib.get_campanha(pool, empresa_id, camp_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    return out


@router.get("/{camp_id}/destinatarios")
async def list_dest_endpoint(
    camp_id: int,
    empresa_id: int = Depends(get_empresa_context),
    limit: int = 200,
) -> dict:
    pool = await get_pool()
    out = await camp_lib.get_campanha(pool, empresa_id, camp_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    items = await camp_lib.list_destinatarios(pool, camp_id, limit=limit)
    return {"items": items}


@router.post("", status_code=201)
async def create_endpoint(
    body: CampanhaCreate,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    pool = await get_pool()
    try:
        out = await camp_lib.create_campanha(
            pool,
            empresa_id,
            nome=body.nome,
            descricao=body.descricao,
            mensagem=body.mensagem,
            conexao_id=body.conexao_id,
            intervalo_ms=body.intervalo_ms,
            max_destinatarios=body.max_destinatarios,
            telefones_brutos=body.telefones,
            user_id=user_id,
            # Sub-fase B+ (padrão profissional) (mig 051)
            modelo_mensagem_id=body.modelo_mensagem_id,
            scheduled_at=body.scheduled_at,
            tipo=body.tipo,
            filtro_segmento=body.filtro_segmento,
            filtro_tags=body.filtro_tags,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return out


@router.post("/{camp_id}/dispatch", status_code=202)
async def dispatch_endpoint(
    camp_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Inicia envio em background. Retorna 202 imediatamente.

    Idempotência: dispatch só atua em campanha 'draft'. Chamadas
    repetidas em campanha 'running' são no-op (mas retornam 200 no
    background task helper). Pra reenviar pendentes/falhos, use
    endpoint dedicado (TODO).
    """
    pool = await get_pool()
    out = await camp_lib.get_campanha(pool, empresa_id, camp_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    if out["status"] != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Campanha em status {out['status']!r} — só draft pode ser despachado.",
        )
    camp_lib.schedule_dispatch(pool, empresa_id, camp_id)
    logger.info("campanha_dispatch_scheduled", camp_id=camp_id, empresa_id=empresa_id)
    return {"ok": True, "campanha_id": camp_id, "status": "queued"}


@router.post("/{camp_id}/abort", status_code=200)
async def abort_endpoint(
    camp_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    pool = await get_pool()
    ok = await camp_lib.abort_campanha(pool, empresa_id, camp_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Campanha não está em draft/running.",
        )
    return {"ok": True}
