"""Endpoints de listagem de agendamentos (S2 Calendar v2).

Lê da tabela local `agendamento` (espelho do Google Calendar com
governança). Pra UI de dashboard de agendamentos, histórico por
cliente, filtro por período.

Permissão: empresa_id resolvido via session (`get_empresa_context`).
Não há mutation aqui — agendamentos são criados/cancelados via tools
do agente (`calendar_create_event`, `calendar_cancel_event`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.shared.agendamento import VALID_STATUS, list_by_period
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import Agendamento

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/agendamentos",
    tags=["agendamento"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("")
async def list_agendamentos(
    inicio: datetime | None = Query(
        default=None,
        description="ISO 8601. Default: agora - 7 dias.",
    ),
    fim: datetime | None = Query(
        default=None,
        description="ISO 8601. Default: agora + 30 dias.",
    ),
    status: str | None = Query(
        default=None,
        description=f"Filtra por status. Valores: {sorted(VALID_STATUS)}",
    ),
    cliente_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[Agendamento]]:
    """Lista agendamentos da empresa cuja `data_inicio ∈ [inicio, fim]`."""
    now = datetime.now(timezone.utc)
    inicio_use = inicio or (now - timedelta(days=7))
    fim_use = fim or (now + timedelta(days=30))

    if inicio_use > fim_use:
        raise HTTPException(
            status_code=422, detail="`inicio` deve ser <= `fim`."
        )

    try:
        items = await list_by_period(
            await get_pool(),
            empresa_id,
            inicio=inicio_use,
            fim=fim_use,
            status=status,
            cliente_id=cliente_id,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return {"items": items}
