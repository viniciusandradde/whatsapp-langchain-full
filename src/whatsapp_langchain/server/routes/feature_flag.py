"""Endpoints de feature flags (Fase 0.2).

CRUD admin pra ativar/desativar features por empresa sem redeploy.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.audit import record_audit
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_superadmin
from whatsapp_langchain.shared.feature_flag import (
    delete_flag,
    list_flags,
    upsert_flag,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/feature-flags",
    tags=["feature-flag"],
    dependencies=[Depends(verify_service_token)],
)


class FeatureFlagInput(BaseModel):
    # `.` liberado: as exceções de plano são `plano.<chave>` (ADR-005 D3).
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9_.-]+$")
    value: Any = True
    descricao: str | None = Field(default=None, max_length=300)
    ativo: bool = True


async def _exigir_superadmin(user_id: str) -> None:
    """ADR-005 leva C1: feature flags viraram ferramenta de PLATAFORMA.

    Desde a leva A, uma flag `plano.<chave>` sobrepõe o plano da empresa
    (grandfathering, D3). Deixar o admin da empresa editar as próprias flags
    seria deixá-lo liberar qualquer recurso pago — por isso as três rotas
    passam a ser superadmin-only (mesmo padrão das rotas `/api/openrouter/*`).
    """
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        raise HTTPException(status_code=403, detail="Apenas superadmins.")


@router.get("")
async def list_endpoint(
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("perfil.read")),
) -> dict:
    """Lista flags da empresa (superadmin)."""
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    return {"items": await list_flags(pool, empresa_id)}


@router.put("/{key}")
async def upsert_endpoint(
    key: str,
    body: FeatureFlagInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("perfil.write")),
) -> dict:
    """Cria ou atualiza flag (superadmin). Audit registra quem ativou o quê."""
    await _exigir_superadmin(user_id)
    if body.key != key:
        raise HTTPException(
            status_code=422, detail="key no body deve bater com path param"
        )
    pool = await get_pool()
    out = await upsert_flag(
        pool,
        empresa_id=empresa_id,
        key=key,
        value=body.value,
        descricao=body.descricao,
        ativo=body.ativo,
        user_id=user_id,
    )
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="feature_flag.upsert",
        entity_type="feature_flag",
        entity_id=key,
        payload_diff={"after": {"value": body.value, "ativo": body.ativo}},
    )
    return out


@router.delete("/{key}", status_code=204)
async def delete_endpoint(
    key: str,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("perfil.write")),
) -> None:
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    ok = await delete_flag(pool, empresa_id, key)
    if not ok:
        raise HTTPException(status_code=404, detail="Flag não encontrada.")
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="feature_flag.delete",
        entity_type="feature_flag",
        entity_id=key,
    )
