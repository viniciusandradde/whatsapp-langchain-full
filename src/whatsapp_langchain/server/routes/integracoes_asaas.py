"""Config GLOBAL da integração Asaas (billing da plataforma) — superadmin only.

Asaas é a conta ÚNICA da plataforma (Chat Nexus fatura as empresas-clientes),
NÃO é per-empresa. Esta tela deixa o SUPERADMIN editar a credencial pela UI
(Integrações → Asaas) em vez de só env var. Persiste cifrado em
`platform_integration_config` (mig 117); o billing lê DB primeiro, env fallback
(`shared.asaas.get_asaas_effective`).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.integrations.asaas import AsaasClient, AsaasError
from whatsapp_langchain.server.dependencies import (
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.asaas import ASAAS_SLUG, get_asaas_effective
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_superadmin
from whatsapp_langchain.shared.platform_config import (
    get_platform_config,
    set_platform_config,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/admin/integracoes/asaas",
    tags=["integracoes-asaas"],
    dependencies=[Depends(verify_service_token)],
)


async def _require_superadmin(user_id: str):
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        raise HTTPException(
            status_code=403,
            detail="Apenas superadmin configura a integração Asaas (global da plataforma).",
        )
    return pool


class AsaasConfigInput(BaseModel):
    environment: str = Field("sandbox", pattern=r"^(sandbox|production)$")
    # Campos sensíveis: branco/omitido = MANTÉM o valor anterior.
    api_key: str | None = None
    webhook_token: str | None = None
    success_url: str | None = None
    cancel_url: str | None = None


@router.get("")
async def get_config(user_id: str = Depends(get_user_id_from_request)):
    """Status da config (sem expor secrets) — flags + source (db|env|none)."""
    pool = await _require_superadmin(user_id)
    cfg = await get_asaas_effective(pool)
    return {
        "configurado": cfg["enabled"],
        "source": cfg["source"],
        "environment": cfg["environment"],
        "tem_api_key": bool(cfg["api_key"]),
        "tem_webhook_token": bool(cfg["webhook_token"]),
        "success_url": cfg["success_url"],
        "cancel_url": cfg["cancel_url"],
    }


@router.put("")
async def put_config(
    body: AsaasConfigInput, user_id: str = Depends(get_user_id_from_request)
):
    """Salva a config no DB (cifrada). Sensível em branco mantém o anterior."""
    pool = await _require_superadmin(user_id)
    existing = await get_platform_config(pool, ASAAS_SLUG) or {}
    api_key = (body.api_key or "").strip() or existing.get("api_key", "")
    webhook_token = (body.webhook_token or "").strip() or existing.get(
        "webhook_token", ""
    )
    if not api_key or not webhook_token:
        raise HTTPException(
            status_code=400,
            detail="api_key e webhook_token são obrigatórios na 1ª configuração.",
        )
    data = {
        "api_key": api_key,
        "webhook_token": webhook_token,
        "environment": body.environment,
        "success_url": (body.success_url or "").strip(),
        "cancel_url": (body.cancel_url or "").strip(),
    }
    await set_platform_config(pool, ASAAS_SLUG, data, updated_by=user_id)
    logger.info(
        "asaas_config_updated", updated_by=user_id, environment=body.environment
    )
    return {"status": "ok", "source": "db"}


@router.post("/testar")
async def testar(user_id: str = Depends(get_user_id_from_request)):
    """Valida a credencial efetiva chamando GET /myAccount no Asaas.

    Retorna SEMPRE 200 com `{ok, conta?, erro?}`. NÃO propaga o status HTTP do
    Asaas — um 401 do Asaas (key inválida/ausente) NÃO é 401 desta API; se
    propagasse, o apiFetch do front trataria como "Sessão expirada".
    """
    await _require_superadmin(user_id)
    pool = await get_pool()
    try:
        client = await AsaasClient.from_pool(pool)
        acc = await client.get_account()
    except AsaasError as e:
        return {"ok": False, "erro": str(e)}
    return {"ok": True, "conta": acc.get("name") or acc.get("email") or "Asaas"}
