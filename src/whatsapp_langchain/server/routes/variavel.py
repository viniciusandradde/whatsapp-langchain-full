"""CRUD de Variáveis de Ambiente (M5.d).

Cada empresa cadastra KVs que podem ser referenciados em prompts/
modelos como `{{var.NOME}}`. UNIQUE (empresa_id, nome) gera HTTP 409
quando o usuário tenta criar/renomear pra um nome já usado.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import VariavelAmbiente, VariavelAmbienteInput
from whatsapp_langchain.shared.variavel import (
    DuplicateNomeError,
    create_variavel,
    delete_variavel,
    get_variavel_by_id,
    list_variaveis,
    update_variavel,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/variaveis",
    tags=["variaveis"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("")
async def list_my_variaveis(
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[VariavelAmbiente]]:
    pool = await get_pool()
    rows = await list_variaveis(pool, empresa_id)
    return {"variaveis": rows}


@router.get("/{var_id}")
async def get_my_variavel(
    var_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> VariavelAmbiente:
    pool = await get_pool()
    row = await get_variavel_by_id(pool, empresa_id, var_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Variável não encontrada.")
    return row


@router.post("", status_code=201)
async def create(
    body: VariavelAmbienteInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> VariavelAmbiente:
    pool = await get_pool()
    try:
        out = await create_variavel(pool, empresa_id, body, user_id=user_id)
    except DuplicateNomeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    logger.info(
        "variavel_ambiente_created",
        empresa_id=empresa_id,
        var_id=out.id,
        nome=out.nome,
        user_id=user_id,
    )
    return out


@router.put("/{var_id}")
async def update(
    var_id: int,
    body: VariavelAmbienteInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> VariavelAmbiente:
    pool = await get_pool()
    existing = await get_variavel_by_id(pool, empresa_id, var_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Variável não encontrada.")
    try:
        out = await update_variavel(pool, empresa_id, var_id, body)
    except DuplicateNomeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if out is None:
        raise HTTPException(status_code=404, detail="Variável não encontrada.")
    logger.info(
        "variavel_ambiente_updated",
        empresa_id=empresa_id,
        var_id=var_id,
        nome=out.nome,
        user_id=user_id,
    )
    return out


@router.delete("/{var_id}", status_code=204)
async def delete(
    var_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    pool = await get_pool()
    deleted = await delete_variavel(pool, empresa_id, var_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Variável não encontrada.")
    logger.info(
        "variavel_ambiente_deleted",
        empresa_id=empresa_id,
        var_id=var_id,
        user_id=user_id,
    )
