"""CRUD de Quick Replies / ModeloMensagem do painel admin (M4.b).

Endpoints escopados pela empresa ativa. UNIQUE (empresa_id, titulo) gera
HTTP 409 quando o usuário tenta criar/renomear pra um título já usado.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.modelo_mensagem import (
    DuplicateTituloError,
    create_modelo,
    delete_modelo,
    get_modelo_by_id,
    list_modelos,
    update_modelo,
)
from whatsapp_langchain.shared.models import ModeloMensagem, ModeloMensagemInput

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/modelos",
    tags=["modelos"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("")
async def list_my_modelos(
    search: str | None = Query(default=None, max_length=200),
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[ModeloMensagem]]:
    """Lista modelos da empresa ativa em ordem alfabética."""
    pool = await get_pool()
    rows = await list_modelos(pool, empresa_id, search=search)
    return {"modelos": rows}


async def _load_modelo_in_empresa(modelo_id: int, empresa_id: int) -> ModeloMensagem:
    pool = await get_pool()
    m = await get_modelo_by_id(pool, modelo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")
    if m.empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="Modelo fora da empresa ativa.")
    return m


@router.post("", status_code=201)
async def create(
    body: ModeloMensagemInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> ModeloMensagem:
    pool = await get_pool()
    try:
        out = await create_modelo(pool, empresa_id, body, user_id=user_id)
    except DuplicateTituloError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    logger.info(
        "modelo_mensagem_created",
        empresa_id=empresa_id,
        modelo_id=out.id,
        titulo=out.titulo,
        user_id=user_id,
    )
    return out


@router.put("/{modelo_id}")
async def update(
    modelo_id: int,
    body: ModeloMensagemInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> ModeloMensagem:
    await _load_modelo_in_empresa(modelo_id, empresa_id)
    pool = await get_pool()
    try:
        out = await update_modelo(pool, modelo_id, body)
    except DuplicateTituloError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if out is None:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")
    logger.info(
        "modelo_mensagem_updated",
        empresa_id=empresa_id,
        modelo_id=modelo_id,
        titulo=out.titulo,
        user_id=user_id,
    )
    return out


@router.delete("/{modelo_id}", status_code=204)
async def delete(
    modelo_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    await _load_modelo_in_empresa(modelo_id, empresa_id)
    pool = await get_pool()
    await delete_modelo(pool, modelo_id)
    logger.info(
        "modelo_mensagem_deleted",
        empresa_id=empresa_id,
        modelo_id=modelo_id,
        user_id=user_id,
    )
