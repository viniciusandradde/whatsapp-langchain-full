"""CRUD de pasta + move documento (E2.C M7)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared import pasta as pasta_lib
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/pastas",
    tags=["pasta"],
    dependencies=[Depends(verify_service_token)],
)


class PastaInput(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None
    descricao: str | None = Field(default=None, max_length=300)


class MoveDocInput(BaseModel):
    pasta_id: int | None = None


@router.get("")
async def list_pastas_endpoint(
    empresa_id: int = Depends(get_empresa_context),
    com_docs: bool = False,
) -> dict:
    pool = await get_pool()
    items = await pasta_lib.list_pastas(
        pool, empresa_id, com_docs_count=com_docs
    )
    return {"items": items}


@router.get("/{pasta_id}")
async def get_pasta_endpoint(
    pasta_id: int, empresa_id: int = Depends(get_empresa_context)
) -> dict:
    pool = await get_pool()
    out = await pasta_lib.get_pasta(pool, empresa_id, pasta_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")
    return out


@router.post("", status_code=201)
async def create_pasta_endpoint(
    body: PastaInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    pool = await get_pool()
    try:
        out = await pasta_lib.create_pasta(
            pool,
            empresa_id,
            nome=body.nome,
            parent_id=body.parent_id,
            descricao=body.descricao,
            user_id=user_id,
        )
    except pasta_lib.DuplicatePastaError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    logger.info(
        "pasta_created", empresa_id=empresa_id, pasta_id=out["id"], nome=body.nome
    )
    return out


@router.put("/{pasta_id}")
async def update_pasta_endpoint(
    pasta_id: int,
    body: PastaInput,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    pool = await get_pool()
    try:
        out = await pasta_lib.update_pasta(
            pool,
            empresa_id,
            pasta_id,
            nome=body.nome,
            parent_id=body.parent_id,
            descricao=body.descricao,
        )
    except pasta_lib.DuplicatePastaError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if out is None:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")
    return out


@router.delete("/{pasta_id}", status_code=204)
async def delete_pasta_endpoint(
    pasta_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    pool = await get_pool()
    ok = await pasta_lib.delete_pasta(pool, empresa_id, pasta_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")


@router.post("/{pasta_id}/documentos/{doc_id}")
async def move_doc_to_pasta(
    pasta_id: int,
    doc_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Move documento pra esta pasta. pasta_id=0 → raiz (NULL)."""
    pool = await get_pool()
    target = None if pasta_id == 0 else pasta_id
    try:
        ok = await pasta_lib.move_documento(
            pool, empresa_id, doc_id, pasta_id=target
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Documento não encontrado nessa empresa.",
        )
    return {"ok": True, "doc_id": doc_id, "pasta_id": target}
