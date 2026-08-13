"""Registro de dispositivos para push (app Android, mig 168).

Perm `atendimento.read` — a mesma base de quem enxerga a fila: todo operador
que vê atendimento precisa poder registrar o próprio aparelho.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.dispositivo_push import (
    registrar_dispositivo,
    remover_dispositivo,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/push",
    tags=["push"],
    dependencies=[Depends(verify_service_token)],
)


class RegistrarInput(BaseModel):
    token: str = Field(min_length=16, max_length=4096)
    plataforma: str = Field(default="android", max_length=20)


class RemoverInput(BaseModel):
    token: str = Field(min_length=16, max_length=4096)


@router.post("/registrar", status_code=204)
async def registrar(
    body: RegistrarInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("atendimento.read")),
) -> None:
    pool = await get_pool()
    await registrar_dispositivo(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        fcm_token=body.token,
        plataforma=body.plataforma,
    )
    logger.info("push_dispositivo_registrado", empresa_id=empresa_id, user_id=user_id)


@router.post("/remover", status_code=204)
async def remover(
    body: RemoverInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("atendimento.read")),
) -> None:
    """Chamado no Sair do app. Idempotente."""
    pool = await get_pool()
    await remover_dispositivo(pool, empresa_id=empresa_id, fcm_token=body.token)
