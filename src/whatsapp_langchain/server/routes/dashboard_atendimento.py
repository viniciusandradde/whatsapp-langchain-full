"""Endpoint do Dashboard de Atendimento operacional.

GET /api/dashboard/atendimento?periodo=hoje|7d|30d — payload agregado
com KPIs + tabelas + charts + sidebar de atendentes.

Perm: `atendimento.read` (todo atendente vê).
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.dashboard_atendimento import (
    PERIODOS,
    get_dashboard_payload,
)
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/dashboard/atendimento",
    tags=["dashboard-atendimento"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("")
async def get_dashboard(
    periodo: str = Query(default="hoje", description="hoje | 7d | 30d"),
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("atendimento.read")),
) -> dict[str, Any]:
    """Payload único agregado pra renderizar todo o dashboard."""
    if periodo not in PERIODOS:
        periodo = "hoje"

    pool = await get_pool()
    return await get_dashboard_payload(pool, empresa_id, periodo)
