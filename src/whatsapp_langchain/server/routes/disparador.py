"""Endpoints do Disparador consumidos pela extensão Chrome (Task 2).

Diferente dos demais routers admin (autenticados por `verify_service_token` +
header de empresa), estes endpoints autenticam pela **API key por empresa**
(`verify_api_key`), que descobre a empresa pela própria chave e ativa o
contexto RLS. A extensão usa SOMENTE este caminho — nunca o token de serviço.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import require_scope, verify_api_key
from whatsapp_langchain.shared import campanha as camp_lib
from whatsapp_langchain.shared.api_key import ApiKeyContext
from whatsapp_langchain.shared.db import get_pool

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


# ---- Disparo in-browser (extensão ZDG-clone, híbrido) ----
# A extensão envia via WPPConnect no navegador e reporta os acks aqui pra que o
# /campanhas mostre histórico/progresso. Campanhas origem_envio='extensao' NÃO
# são pegas pelo dispatcher/poller do backend.


class ExtCampanhaInput(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    mensagem: str | None = Field(default=None, max_length=4000)
    telefones: list[str] = Field(min_length=1, max_length=10_000)


class ExtReportItem(BaseModel):
    telefone: str
    status: str  # 'enviado' | 'falhou'
    erro: str | None = None
    wamid: str | None = None


class ExtReportInput(BaseModel):
    items: list[ExtReportItem] = Field(min_length=1, max_length=2000)


@router.post("/ext/campanha", status_code=201)
async def ext_criar_campanha(
    body: ExtCampanhaInput,
    ctx: ApiKeyContext = Depends(require_scope("dispatch")),
) -> dict:
    """Cria uma campanha origem_envio='extensao' (status 'running') pro disparo
    in-browser. Retorna o id + os destinatários normalizados pra enviar."""
    pool = await get_pool()
    try:
        camp = await camp_lib.create_campanha(
            pool,
            ctx.empresa_id,
            nome=body.nome,
            descricao=None,
            mensagem=body.mensagem,
            conexao_id=None,
            intervalo_ms=500,
            max_destinatarios=10_000,
            telefones_brutos=body.telefones,
            user_id=None,
            origem_envio="extensao",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    destinatarios = await camp_lib.list_destinatarios(pool, camp["id"], limit=10_000)
    return {
        "campanha_id": camp["id"],
        "total": camp["total_destinatarios"],
        "telefones": [d["telefone"] for d in destinatarios],
    }


@router.post("/ext/campanha/{camp_id}/report")
async def ext_report(
    camp_id: int,
    body: ExtReportInput,
    ctx: ApiKeyContext = Depends(require_scope("dispatch")),
) -> dict:
    """Aplica o reporte de envio in-browser (acks por destinatário)."""
    pool = await get_pool()
    try:
        return await camp_lib.aplicar_report_ext(
            pool, ctx.empresa_id, camp_id, [i.model_dump() for i in body.items]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
