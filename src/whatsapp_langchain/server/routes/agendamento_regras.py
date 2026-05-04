"""Endpoints de regras de agendamento (S3 Calendar v2).

GET /api/calendar/regras — qualquer membro vê as regras vigentes.
PUT /api/calendar/regras — admin only (is_admin_of); UPSERT parcial.

Validação de input:
- hora_inicio/hora_fim formato HH:MM
- dias_semana_permitidos: lista de int 1-7
- dias_bloqueados: lista de strings YYYY-MM-DD
"""

from __future__ import annotations

import re
from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.agendamento_regras import get, upsert
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_admin_of
from whatsapp_langchain.shared.models import (
    AgendamentoRegras,
    AgendamentoRegrasInput,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/calendar/regras",
    tags=["agendamento_regras"],
    dependencies=[Depends(verify_service_token)],
)


_HORA_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _validate_hora(label: str, value: str) -> None:
    if not _HORA_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail=f"{label!r} deve estar no formato HH:MM (ex: 09:30).",
        )


def _validate_dias_semana(values: list[int]) -> None:
    if not all(isinstance(d, int) and 1 <= d <= 7 for d in values):
        raise HTTPException(
            status_code=422,
            detail="dias_semana_permitidos deve ser lista de int 1-7 (ISO weekday).",
        )


def _validate_dias_bloqueados(values: list[str]) -> None:
    for d in values:
        try:
            date.fromisoformat(d)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail=f"dias_bloqueados[{d!r}] não é YYYY-MM-DD válido.",
            ) from None


@router.get("")
async def get_regras(
    empresa_id: int = Depends(get_empresa_context),
) -> AgendamentoRegras:
    """Lê regras vigentes (defaults virtuais se nunca configurou)."""
    pool = await get_pool()
    return await get(pool, empresa_id)


@router.put("")
async def put_regras(
    body: AgendamentoRegrasInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> AgendamentoRegras:
    """UPSERT parcial. Só admin pode editar regras."""
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(
            status_code=403, detail="Só admin pode editar regras de agendamento."
        )

    if body.hora_inicio is not None:
        _validate_hora("hora_inicio", body.hora_inicio)
    if body.hora_fim is not None:
        _validate_hora("hora_fim", body.hora_fim)
    if body.hora_inicio and body.hora_fim and body.hora_fim <= body.hora_inicio:
        raise HTTPException(
            status_code=422, detail="hora_fim deve ser maior que hora_inicio."
        )
    if body.dias_semana_permitidos is not None:
        _validate_dias_semana(body.dias_semana_permitidos)
    if body.dias_bloqueados is not None:
        _validate_dias_bloqueados(body.dias_bloqueados)

    out = await upsert(
        pool,
        empresa_id,
        hora_inicio=body.hora_inicio,
        hora_fim=body.hora_fim,
        antecedencia_minima_minutos=body.antecedencia_minima_minutos,
        intervalo_entre_minutos=body.intervalo_entre_minutos,
        dias_semana_permitidos=body.dias_semana_permitidos,
        dias_bloqueados=body.dias_bloqueados,
        requer_aprovacao=body.requer_aprovacao,
    )

    logger.info(
        "agendamento_regras_changed",
        empresa_id=empresa_id,
        actor_user_id=user_id,
    )
    return out
