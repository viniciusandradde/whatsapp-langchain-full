"""CRUD da Base de Conhecimento (M5.c).

Endpoints escopados pela empresa ativa via cookie. O empresa_id sai do
`get_empresa_context` (mesmo padrão de modelo_mensagem/hook).
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
from whatsapp_langchain.shared import base_conhecimento
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import (
    DocumentoConhecimento,
    DocumentoConhecimentoInput,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/base-conhecimento",
    tags=["base-conhecimento"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("")
async def list_documentos(
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[DocumentoConhecimento]]:
    """Lista todos os docs da empresa, ativos e inativos."""
    pool = await get_pool()
    docs = await base_conhecimento.list_documentos(pool, empresa_id)
    return {"documentos": docs}


@router.get("/{doc_id}")
async def get_documento(
    doc_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> DocumentoConhecimento:
    pool = await get_pool()
    doc = await base_conhecimento.get_documento(pool, empresa_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return doc


@router.post("", status_code=201)
async def create_documento(
    body: DocumentoConhecimentoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> DocumentoConhecimento:
    pool = await get_pool()
    out = await base_conhecimento.upsert_documento(
        pool, empresa_id, body, user_id=user_id
    )
    logger.info(
        "base_conhecimento_created",
        empresa_id=empresa_id,
        doc_id=out.id,
        titulo=out.titulo,
        user_id=user_id,
    )
    return out


@router.put("/{doc_id}")
async def update_documento(
    doc_id: int,
    body: DocumentoConhecimentoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> DocumentoConhecimento:
    pool = await get_pool()
    existing = await base_conhecimento.get_documento(pool, empresa_id, doc_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    out = await base_conhecimento.upsert_documento(
        pool, empresa_id, body, doc_id=doc_id, user_id=user_id
    )
    logger.info(
        "base_conhecimento_updated",
        empresa_id=empresa_id,
        doc_id=doc_id,
        titulo=out.titulo,
        user_id=user_id,
    )
    return out


@router.delete("/{doc_id}", status_code=204)
async def delete_documento(
    doc_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    pool = await get_pool()
    deleted = await base_conhecimento.delete_documento(pool, empresa_id, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    logger.info(
        "base_conhecimento_deleted",
        empresa_id=empresa_id,
        doc_id=doc_id,
        user_id=user_id,
    )


class _BuscarBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=3, ge=1, le=10)


class _BuscarResultado(BaseModel):
    documento: DocumentoConhecimento
    score: float


@router.post("/buscar")
async def buscar_documentos(
    body: _BuscarBody,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[_BuscarResultado]]:
    """Endpoint de teste — espelha o que a tool do agente vê."""
    pool = await get_pool()
    results = await base_conhecimento.search_relevant(
        pool, empresa_id, body.query, k=body.k
    )
    return {
        "resultados": [
            _BuscarResultado(documento=d, score=s) for d, s in results
        ]
    }
