"""Endpoints do Disparador consumidos pela extensão Chrome (Task 2).

Diferente dos demais routers admin (autenticados por `verify_service_token` +
header de empresa), estes endpoints autenticam pela **API key por empresa**
(`verify_api_key`), que descobre a empresa pela própria chave e ativa o
contexto RLS. A extensão usa SOMENTE este caminho — nunca o token de serviço.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from whatsapp_langchain.server.dependencies import verify_api_key
from whatsapp_langchain.shared.api_key import ApiKeyContext

logger = structlog.get_logger()

router = APIRouter(prefix="/api/disparador", tags=["disparador"])


@router.get("/status")
async def get_status(ctx: ApiKeyContext = Depends(verify_api_key)) -> dict:
    """Health-check autenticado: a extensão usa pra validar a API key + URL.

    Retorna a empresa resolvida e os escopos da chave (sem expor segredo).
    """
    return {
        "ok": True,
        "empresa_id": ctx.empresa_id,
        "scopes": ctx.scopes,
        "rate_limit_per_minute": ctx.rate_limit_per_minute,
    }
