"""CRUD de API keys do Disparador (Task 10) — painel admin.

Painel-facing (`verify_service_token` + `get_empresa_context`). A chave em
claro é retornada SÓ na criação (o banco guarda apenas o hash); a UI mostra
uma vez com aviso de copiar. Listagem/revogação nunca expõem o segredo.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared import api_key as ak
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/disparador/api-keys",
    tags=["disparador"],
    dependencies=[Depends(verify_service_token)],
)


class ApiKeyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    scopes: list[str] | None = None


@router.get("")
async def listar(empresa_id: int = Depends(get_empresa_context)) -> dict:
    """Lista as chaves da empresa (sem segredo)."""
    pool = await get_pool()
    return {"items": await ak.list_api_keys(pool, empresa_id)}


@router.post("", status_code=201)
async def criar(
    body: ApiKeyCreate,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("disparador.api_key.manage")),
) -> dict:
    """Cria uma chave e retorna o segredo UMA única vez (`key`)."""
    pool = await get_pool()
    plain, meta = await ak.create_api_key(
        pool, empresa_id, label=body.label, scopes=body.scopes, user_id=user_id
    )
    return {"key": plain, **meta}


@router.post("/{key_id}/revoke")
async def revogar(
    key_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("disparador.api_key.manage")),
) -> dict:
    """Revoga (soft) uma chave."""
    pool = await get_pool()
    if not await ak.revoke_api_key(pool, empresa_id, key_id):
        raise HTTPException(404, "Chave não encontrada ou já revogada")
    return {"ok": True}
