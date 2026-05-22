"""Sprint B.4 — endpoints /api/billing/* (admin painel).

Endpoints:
- POST /api/billing/checkout {plano} → cria subscription Asaas + URL pagamento
- GET  /api/billing/historico        → lista últimas N transações da empresa
- POST /api/billing/cancel           → cancela subscription ativa (downgrade free)
- GET  /api/billing/status           → resumo (plano + customer + última tx)

Auth: service_token + X-User-Id + X-Empresa-Id. Só admin pode.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.integrations.asaas import AsaasError
from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.asaas import (
    cancel_active_subscription,
    create_subscription_for_plano,
    list_transacoes,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_admin_of

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/billing",
    tags=["billing"],
    dependencies=[Depends(verify_service_token)],
)


def _ensure_asaas_enabled() -> None:
    if not settings.asaas_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "Integração ASAAS não configurada (ASAAS_API_KEY ausente). "
                "Contate o admin."
            ),
        )


async def _require_admin(empresa_id: int, user_id: str) -> None:
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(
            status_code=403,
            detail="Apenas admin da empresa pode gerenciar billing.",
        )


class CheckoutInput(BaseModel):
    plano: str = Field(..., pattern=r"^(pro|enterprise)$")


@router.post("/checkout")
async def checkout(
    body: CheckoutInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
):
    """Cria/atualiza subscription Asaas pro plano escolhido.

    Retorna URL de pagamento Asaas (invoiceUrl). UI redireciona user.
    Plano só ativa após webhook PAYMENT_CONFIRMED.
    """
    _ensure_asaas_enabled()
    await _require_admin(empresa_id, user_id)

    pool = await get_pool()
    try:
        result = await create_subscription_for_plano(
            pool, empresa_id, body.plano
        )
    except AsaasError as e:
        status = e.status_code if e.status_code and 400 <= e.status_code < 600 else 502
        raise HTTPException(status_code=status, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "billing_checkout_created",
        empresa_id=empresa_id, user_id=user_id, plano=body.plano,
        subscription_id=result["subscription_id"],
    )
    return result


@router.get("/historico")
async def historico(
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    limit: int = 50,
):
    """Lista transações da empresa (qualquer membro vê)."""
    pool = await get_pool()
    from whatsapp_langchain.shared.empresa import get_empresa_membership

    if not await get_empresa_membership(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Sem acesso à empresa.")

    items = await list_transacoes(pool, empresa_id, limit=min(max(limit, 1), 200))
    return {"items": items}


@router.post("/cancel")
async def cancel(
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
):
    """Cancela subscription ativa. Plano vira free imediatamente."""
    _ensure_asaas_enabled()
    await _require_admin(empresa_id, user_id)

    pool = await get_pool()
    result = await cancel_active_subscription(pool, empresa_id)
    logger.info(
        "billing_cancel",
        empresa_id=empresa_id, user_id=user_id, result=result,
    )
    return result


@router.get("/status")
async def status_billing(
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
):
    """Resumo billing pra UI (plano, customer, última transação)."""
    pool = await get_pool()
    from whatsapp_langchain.shared.empresa import get_empresa_membership
    from whatsapp_langchain.shared.rls_context import empresa_scope

    if not await get_empresa_membership(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Sem acesso à empresa.")

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM empresa_billing_status WHERE empresa_id = %s",
                (empresa_id,),
            )
            row = await cur.fetchone()
            cols = [d.name for d in cur.description] if cur.description else []
    if row is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return dict(zip(cols, row))
