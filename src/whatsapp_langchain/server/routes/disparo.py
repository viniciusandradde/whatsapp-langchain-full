"""Endpoints de disparo do painel (Task 7) — preview/validação.

Painel-facing (`verify_service_token` + `get_empresa_context`). O preview
("Preparar") resolve a origem, conta válidos/inválidos/duplicados e devolve
uma amostra; a UI só habilita "ENVIAR" depois disso. O envio em si reusa o
fluxo de campanha existente (create + dispatch).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.shared import disparo as disp
from whatsapp_langchain.shared import opt_out as oo
from whatsapp_langchain.shared.campanha import normalize_phone
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


class OptOutInput(BaseModel):
    telefone: str = Field(min_length=5, max_length=20)


@router.get("/opt-out")
async def listar_opt_out(empresa_id: int = Depends(get_empresa_context)) -> dict:
    """Lista a supressão (opt-out) da empresa."""
    pool = await get_pool()
    return {"items": await oo.listar_opt_out(pool, empresa_id)}


@router.post("/opt-out", status_code=201)
async def adicionar_opt_out(
    body: OptOutInput, empresa_id: int = Depends(get_empresa_context)
) -> dict:
    """Adiciona manualmente um telefone à supressão."""
    pool = await get_pool()
    telefone = normalize_phone(body.telefone)
    if not telefone:
        raise HTTPException(400, "Telefone inválido")
    wa_jid = f"{telefone.lstrip('+')}@s.whatsapp.net"
    await oo.registrar_opt_out(
        pool,
        empresa_id,
        wa_jid=wa_jid,
        telefone=telefone,
        motivo="manual",
        origem="painel",
    )
    return {"ok": True, "telefone": telefone}


@router.delete("/opt-out/{opt_out_id}")
async def remover_opt_out(
    opt_out_id: int, empresa_id: int = Depends(get_empresa_context)
) -> dict:
    """Remove um telefone da supressão (re-permite contato)."""
    pool = await get_pool()
    removido = await oo.remover_opt_out(pool, empresa_id, opt_out_id)
    if not removido:
        raise HTTPException(404, "Entrada não encontrada")
    return {"ok": True}
