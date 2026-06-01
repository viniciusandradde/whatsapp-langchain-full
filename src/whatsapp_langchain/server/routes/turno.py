"""Sprint U (Fase 2) — endpoints de turnos / jornada de trabalho.

CRUD de turnos + atribuição de usuários. Paridade ZigChat `Turno`.

Auth: leitura `departamento.read`, escrita `horario.write`.

Endpoints:
- GET    /api/turnos                  — lista (com horários + users_count)
- POST   /api/turnos                  — criar
- GET    /api/turnos/{id}             — detalhe
- PUT    /api/turnos/{id}             — atualizar (nome/ativo/horários)
- DELETE /api/turnos/{id}             — remover
- GET    /api/turnos/{id}/users       — usuários do turno
- PUT    /api/turnos/{id}/users       — sync usuários do turno
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.turno import (
    create_turno,
    delete_turno,
    get_turno,
    list_turnos,
    list_users_in_turno,
    set_users_in_turno,
    update_turno,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/turnos",
    tags=["turnos"],
    dependencies=[Depends(verify_service_token)],
)


class HorarioInput(BaseModel):
    dia_semana: int = Field(ge=0, le=6)
    hora_inicio: str = Field(pattern=r"^\d{2}:\d{2}$")
    hora_fim: str = Field(pattern=r"^\d{2}:\d{2}$")


class CreateTurnoInput(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    ativo: bool = True
    horarios: list[HorarioInput] = Field(default_factory=list)


class UpdateTurnoInput(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    ativo: bool | None = None
    horarios: list[HorarioInput] | None = None


class SetUsersInput(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


@router.get("")
async def list_endpoint(
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("departamento.read")),
):
    pool = await get_pool()
    items = await list_turnos(pool, empresa_id)
    return {"items": [t.to_dict() for t in items]}


@router.post("", status_code=201)
async def create_endpoint(
    body: CreateTurnoInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("horario.write")),
):
    pool = await get_pool()
    try:
        t = await create_turno(
            pool,
            empresa_id,
            nome=body.nome,
            ativo=body.ativo,
            horarios=[h.model_dump() for h in body.horarios],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(
                status_code=409, detail=f"Já existe turno '{body.nome}'."
            ) from e
        raise
    return t.to_dict()


@router.get("/{turno_id}")
async def get_endpoint(
    turno_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("departamento.read")),
):
    pool = await get_pool()
    t = await get_turno(pool, empresa_id, turno_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Turno não encontrado.")
    return t.to_dict()


@router.put("/{turno_id}")
async def update_endpoint(
    turno_id: int,
    body: UpdateTurnoInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("horario.write")),
):
    pool = await get_pool()
    try:
        t = await update_turno(
            pool,
            empresa_id,
            turno_id,
            nome=body.nome,
            ativo=body.ativo,
            horarios=(
                [h.model_dump() for h in body.horarios]
                if body.horarios is not None
                else None
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if t is None:
        raise HTTPException(status_code=404, detail="Turno não encontrado.")
    return t.to_dict()


@router.delete("/{turno_id}", status_code=204)
async def delete_endpoint(
    turno_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("horario.write")),
):
    pool = await get_pool()
    ok = await delete_turno(pool, empresa_id, turno_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Turno não encontrado.")


@router.get("/{turno_id}/users")
async def list_users_endpoint(
    turno_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("departamento.read")),
):
    pool = await get_pool()
    return {"users": await list_users_in_turno(pool, empresa_id, turno_id)}


@router.put("/{turno_id}/users")
async def set_users_endpoint(
    turno_id: int,
    body: SetUsersInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("horario.write")),
):
    pool = await get_pool()
    ok = await set_users_in_turno(pool, empresa_id, turno_id, body.user_ids)
    if not ok:
        raise HTTPException(status_code=404, detail="Turno não encontrado.")
    return {"ok": True}
