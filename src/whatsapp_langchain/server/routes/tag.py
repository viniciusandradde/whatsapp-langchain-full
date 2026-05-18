"""CRUD de tags da empresa (Sprint Atendimento UX 1.2).

Tags são da empresa (CRUD requer `tag.manage`). Aplicação em atendimento
fica em `/api/atendimentos/{id}/tags` (perm separada `atendimento.tag.aplicar`).

Endpoints:
- GET    /api/tags                 — lista tags ativas da empresa
- POST   /api/tags                 — cria tag
- PATCH  /api/tags/{id}            — atualiza
- DELETE /api/tags/{id}            — hard delete (cascateia em atendimento_tag)
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.tag import (
    create_tag,
    delete_tag,
    list_tags,
    update_tag,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api",
    tags=["tag"],
    dependencies=[Depends(verify_service_token)],
)


class CreateTagInput(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    cor: str | None = Field(default=None, max_length=32)
    descricao: str | None = Field(default=None, max_length=200)


class UpdateTagInput(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=80)
    cor: str | None = Field(default=None, max_length=32)
    descricao: str | None = Field(default=None, max_length=200)
    ativo: bool | None = None


@router.get("/tags")
async def list_tags_endpoint(
    only_ativos: bool = Query(default=True),
    empresa_id: int = Depends(get_empresa_context),
    # Leitura é liberada — qualquer um que vê atendimento precisa enxergar
    # as opções de tag pra UI. Mutação exige `tag.manage`.
) -> dict:
    pool = await get_pool()
    items = await list_tags(pool, empresa_id=empresa_id, only_ativos=only_ativos)
    return {"items": items}


@router.post("/tags")
async def create_tag_endpoint(
    payload: CreateTagInput,
    user_id: str = Depends(get_user_id_from_request),
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("tag.manage")),
) -> dict:
    pool = await get_pool()
    try:
        return await create_tag(
            pool,
            empresa_id=empresa_id,
            nome=payload.nome.strip(),
            cor=payload.cor,
            descricao=payload.descricao,
            created_by_user_id=user_id,
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise HTTPException(
                status_code=409, detail="Já existe uma tag com esse nome."
            ) from exc
        raise


@router.patch("/tags/{tag_id}")
async def update_tag_endpoint(
    tag_id: int,
    payload: UpdateTagInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("tag.manage")),
) -> dict:
    pool = await get_pool()
    try:
        result = await update_tag(
            pool,
            tag_id=tag_id,
            empresa_id=empresa_id,
            nome=payload.nome.strip() if payload.nome else None,
            cor=payload.cor,
            descricao=payload.descricao,
            ativo=payload.ativo,
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise HTTPException(
                status_code=409, detail="Já existe uma tag com esse nome."
            ) from exc
        raise
    if result is None:
        raise HTTPException(status_code=404, detail="Tag não encontrada.")
    return result


@router.delete("/tags/{tag_id}")
async def delete_tag_endpoint(
    tag_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("tag.manage")),
) -> dict:
    pool = await get_pool()
    ok = await delete_tag(pool, tag_id=tag_id, empresa_id=empresa_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Tag não encontrada.")
    return {"ok": True}
