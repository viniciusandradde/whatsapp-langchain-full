"""Endpoints de disparo do painel (Task 7) — preview/validação.

Painel-facing (`verify_service_token` + `get_empresa_context`). O preview
("Preparar") resolve a origem, conta válidos/inválidos/duplicados e devolve
uma amostra; a UI só habilita "ENVIAR" depois disso. O envio em si reusa o
fluxo de campanha existente (create + dispatch).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.shared import disparo as disp
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/disparador",
    tags=["disparador"],
    dependencies=[Depends(verify_service_token)],
)


@router.post("/preview")
async def preview(
    body: disp.PreviewRequest,
    empresa_id: int = Depends(get_empresa_context),
) -> disp.PreviewResultado:
    """Resolve a origem e devolve contagens + amostra (estágio 'Preparar')."""
    pool = await get_pool()
    return await disp.preview_disparo(
        pool,
        empresa_id,
        body.origem,
        conexao_id=body.conexao_id,
        validar_numeros=body.validar_numeros,
    )
