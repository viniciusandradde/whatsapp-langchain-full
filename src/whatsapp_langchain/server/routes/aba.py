"""Rotas CRUD de abas customizáveis no painel de atendimento.

Cada user gerencia suas próprias abas. Permissão exigida:
`atendimento.aba.manage` pra tudo (Operador+ tem por default).

Endpoints:
- GET    /api/abas/me                       — abas do user logado
- POST   /api/abas                          — cria pra mim
- PATCH  /api/abas/{id}                     — atualiza minha aba
- DELETE /api/abas/{id}                     — soft-delete minha aba
- POST   /api/abas/reorder                  — reordena por lista de ids
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
from whatsapp_langchain.shared.aba import (
    create_aba,
    delete_aba,
    list_abas,
    reorder_abas,
    update_aba,
)
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api",
    tags=["aba"],
    dependencies=[Depends(verify_service_token)],
)


class CreateAbaInput(BaseModel):
    descricao: str = Field(min_length=1, max_length=80)
    cor: str | None = Field(default=None, max_length=32)
    icone: str | None = Field(default=None, max_length=32)


class UpdateAbaInput(BaseModel):
    descricao: str | None = Field(default=None, min_length=1, max_length=80)
    cor: str | None = Field(default=None, max_length=32)
    icone: str | None = Field(default=None, max_length=32)


class ReorderAbasInput(BaseModel):
    ordered_ids: list[int] = Field(min_length=0)


@router.get("/abas/me")
async def list_my_abas(
    user_id: str = Depends(get_user_id_from_request),
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("atendimento.aba.manage")),
) -> dict:
    pool = await get_pool()
    items = await list_abas(pool, user_id=user_id, empresa_id=empresa_id)
    return {"items": items}


@router.post("/abas")
async def create_my_aba(
    payload: CreateAbaInput,
    user_id: str = Depends(get_user_id_from_request),
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("atendimento.aba.manage")),
) -> dict:
    pool = await get_pool()
    try:
        return await create_aba(
            pool,
            user_id=user_id,
            empresa_id=empresa_id,
            descricao=payload.descricao.strip(),
            cor=payload.cor,
            icone=payload.icone,
        )
    except Exception as exc:
        # UNIQUE (usuario_id, descricao) viola → 409
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise HTTPException(
                status_code=409, detail="Já existe uma aba com esse nome."
            ) from exc
        raise


@router.patch("/abas/{aba_id}")
async def update_my_aba(
    aba_id: int,
    payload: UpdateAbaInput,
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.aba.manage")),
) -> dict:
    pool = await get_pool()
    result = await update_aba(
        pool,
        aba_id=aba_id,
        user_id=user_id,
        descricao=payload.descricao.strip() if payload.descricao else None,
        cor=payload.cor,
        icone=payload.icone,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Aba não encontrada.")
    return result


@router.delete("/abas/{aba_id}")
async def delete_my_aba(
    aba_id: int,
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.aba.manage")),
) -> dict:
    pool = await get_pool()
    ok = await delete_aba(pool, aba_id=aba_id, user_id=user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Aba não encontrada.")
    return {"ok": True}


@router.post("/abas/reorder")
async def reorder_my_abas(
    payload: ReorderAbasInput,
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.aba.manage")),
) -> dict:
    pool = await get_pool()
    count = await reorder_abas(
        pool, user_id=user_id, ordered_ids=payload.ordered_ids
    )
    return {"updated": count}
