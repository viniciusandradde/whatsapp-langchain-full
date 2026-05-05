"""Endpoints de auditoria (Fase 0.1).

Read-only: registro de auditoria nunca é alterado/deletado via API.
Cleanup vem por retention policy (Fase 6).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Query

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.audit import list_audit
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/audit",
    tags=["audit"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("")
async def list_audit_endpoint(
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("security.audit.read")),
) -> dict:
    """Lista audit logs com filtros. Permite paginação."""
    pool = await get_pool()
    items = await list_audit(
        pool,
        empresa_id,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}
