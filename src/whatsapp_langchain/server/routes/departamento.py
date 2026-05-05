"""CRUD de Departamento (M6.a)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from pydantic import BaseModel, Field

from whatsapp_langchain.shared.departamento import (
    DuplicateDepartamentoError,
    assign_user_to_departamento,
    create_departamento,
    delete_departamento,
    get_departamento_by_id,
    list_departamentos,
    list_users_in_departamento,
    unassign_user_from_departamento,
    update_departamento,
)
from whatsapp_langchain.shared.models import Departamento, DepartamentoInput

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/departamentos",
    tags=["departamentos"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("")
async def list_my_departamentos(
    empresa_id: int = Depends(get_empresa_context),
    com_users: bool = False,
) -> dict[str, list[Departamento]]:
    pool = await get_pool()
    rows = await list_departamentos(
        pool, empresa_id, com_users_count=com_users
    )
    return {"departamentos": rows}


@router.get("/{dep_id}")
async def get_my_departamento(
    dep_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> Departamento:
    pool = await get_pool()
    row = await get_departamento_by_id(pool, empresa_id, dep_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Departamento não encontrado.")
    return row


@router.post("", status_code=201)
async def create(
    body: DepartamentoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Departamento:
    pool = await get_pool()
    try:
        out = await create_departamento(pool, empresa_id, body, user_id=user_id)
    except DuplicateDepartamentoError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    logger.info(
        "departamento_created",
        empresa_id=empresa_id,
        dep_id=out.id,
        nome=out.nome,
        user_id=user_id,
    )
    return out


@router.put("/{dep_id}")
async def update(
    dep_id: int,
    body: DepartamentoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Departamento:
    pool = await get_pool()
    existing = await get_departamento_by_id(pool, empresa_id, dep_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Departamento não encontrado.")
    try:
        out = await update_departamento(pool, empresa_id, dep_id, body)
    except DuplicateDepartamentoError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if out is None:
        raise HTTPException(status_code=404, detail="Departamento não encontrado.")
    logger.info(
        "departamento_updated",
        empresa_id=empresa_id,
        dep_id=dep_id,
        nome=out.nome,
        user_id=user_id,
    )
    return out


@router.delete("/{dep_id}", status_code=204)
async def delete(
    dep_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    pool = await get_pool()
    deleted = await delete_departamento(pool, empresa_id, dep_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Departamento não encontrado.")
    logger.info(
        "departamento_deleted",
        empresa_id=empresa_id,
        dep_id=dep_id,
        user_id=user_id,
    )


# ---- E2.B: usuario_departamento ----


class AssignUserInput(BaseModel):
    user_id: str = Field(min_length=1)


@router.get("/{dep_id}/users")
async def list_dep_users(
    dep_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Lista users atribuídos ao departamento (com nome/email)."""
    pool = await get_pool()
    existing = await get_departamento_by_id(pool, empresa_id, dep_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Departamento não encontrado.")
    items = await list_users_in_departamento(pool, dep_id, empresa_id)
    return {"items": items}


@router.post("/{dep_id}/users", status_code=201)
async def assign_dep_user(
    dep_id: int,
    body: AssignUserInput,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    pool = await get_pool()
    existing = await get_departamento_by_id(pool, empresa_id, dep_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Departamento não encontrado.")
    inserted = await assign_user_to_departamento(
        pool,
        user_id=body.user_id,
        departamento_id=dep_id,
        empresa_id=empresa_id,
    )
    return {"ok": True, "inserted": inserted}


@router.delete("/{dep_id}/users/{target_user_id}", status_code=204)
async def unassign_dep_user(
    dep_id: int,
    target_user_id: str,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    pool = await get_pool()
    ok = await unassign_user_from_departamento(
        pool,
        user_id=target_user_id,
        departamento_id=dep_id,
        empresa_id=empresa_id,
    )
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="User não estava atribuído a esse departamento.",
        )
