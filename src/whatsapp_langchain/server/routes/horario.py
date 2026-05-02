"""CRUD de Horário de funcionamento + Feriado + status de expediente (M6.a).

Dois conjuntos de endpoints sob `/api/horarios` e `/api/feriados`,
mais `/api/horarios/status` que devolve `{is_open, agora}` pra UI.
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
from whatsapp_langchain.shared.horario import (
    DuplicateFeriadoError,
    create_feriado,
    create_horario,
    delete_feriado,
    delete_horario,
    is_business_hours,
    list_all_horarios,
    list_feriados,
)
from whatsapp_langchain.shared.models import (
    Feriado,
    FeriadoInput,
    HorarioFuncionamento,
    HorarioFuncionamentoInput,
)

logger = structlog.get_logger()

router_horario = APIRouter(
    prefix="/api/horarios",
    tags=["horarios"],
    dependencies=[Depends(verify_service_token)],
)

router_feriado = APIRouter(
    prefix="/api/feriados",
    tags=["feriados"],
    dependencies=[Depends(verify_service_token)],
)


# --- Horarios ---


@router_horario.get("")
async def list_horarios(
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[HorarioFuncionamento]]:
    pool = await get_pool()
    rows = await list_all_horarios(pool, empresa_id)
    return {"horarios": rows}


@router_horario.post("", status_code=201)
async def create(
    body: HorarioFuncionamentoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> HorarioFuncionamento:
    if body.hora_fim <= body.hora_inicio:
        raise HTTPException(
            status_code=422, detail="hora_fim deve ser maior que hora_inicio."
        )
    pool = await get_pool()
    out = await create_horario(pool, empresa_id, body)
    logger.info(
        "horario_funcionamento_created",
        empresa_id=empresa_id,
        horario_id=out.id,
        dia_semana=out.dia_semana,
        user_id=user_id,
    )
    return out


@router_horario.delete("/{horario_id}", status_code=204)
async def delete_horario_route(
    horario_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    pool = await get_pool()
    deleted = await delete_horario(pool, empresa_id, horario_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Horário não encontrado.")
    logger.info(
        "horario_funcionamento_deleted",
        empresa_id=empresa_id,
        horario_id=horario_id,
        user_id=user_id,
    )


@router_horario.get("/status")
async def status(
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, bool]:
    """Retorna `{is_open: bool}` consultando is_business_hours na hora atual."""
    pool = await get_pool()
    is_open = await is_business_hours(pool, empresa_id)
    return {"is_open": is_open}


# --- Feriados ---


@router_feriado.get("")
async def list_feriados_route(
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[Feriado]]:
    pool = await get_pool()
    rows = await list_feriados(pool, empresa_id)
    return {"feriados": rows}


@router_feriado.post("", status_code=201)
async def create_feriado_route(
    body: FeriadoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Feriado:
    pool = await get_pool()
    try:
        out = await create_feriado(pool, empresa_id, body, user_id=user_id)
    except DuplicateFeriadoError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    logger.info(
        "feriado_created",
        empresa_id=empresa_id,
        feriado_id=out.id,
        data=out.data,
        user_id=user_id,
    )
    return out


@router_feriado.delete("/{feriado_id}", status_code=204)
async def delete_feriado_route(
    feriado_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    pool = await get_pool()
    deleted = await delete_feriado(pool, empresa_id, feriado_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Feriado não encontrado.")
    logger.info(
        "feriado_deleted",
        empresa_id=empresa_id,
        feriado_id=feriado_id,
        user_id=user_id,
    )
