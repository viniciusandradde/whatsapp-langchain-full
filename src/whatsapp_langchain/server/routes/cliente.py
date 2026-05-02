"""CRUD de Clientes do painel admin (M3 CRM Light).

Endpoints escopados pela empresa ativa via `get_empresa_context`.
Mutações ficam abertas a qualquer membro no MVP — diferenciar por role
fica pra um milestone futuro.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.cliente import (
    add_anotacao,
    add_tag,
    get_cliente_by_id,
    list_anotacoes,
    list_clientes,
    remove_tag,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import Cliente, ClienteAnotacao

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/clientes",
    tags=["clientes"],
    dependencies=[Depends(verify_service_token)],
)


class AnotacaoInput(BaseModel):
    conteudo: str = Field(min_length=1, max_length=4000)


class TagInput(BaseModel):
    tag: str = Field(min_length=1, max_length=64)


class ClienteDetail(BaseModel):
    """Resposta do GET /{id} — cliente + anotações cronológicas."""

    cliente: Cliente
    anotacoes: list[ClienteAnotacao]


@router.get("")
async def list_my_clientes(
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[Cliente]]:
    """Lista clientes da empresa ativa (mais recente primeiro)."""
    pool = await get_pool()
    rows = await list_clientes(
        pool, empresa_id, search=search, limit=limit, offset=offset
    )
    return {"clientes": rows}


async def _load_cliente_in_empresa(cliente_id: int, empresa_id: int) -> Cliente:
    """Helper: carrega + valida que o cliente pertence à empresa ativa."""
    pool = await get_pool()
    cliente = await get_cliente_by_id(pool, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    if cliente.empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="Cliente fora da empresa ativa.")
    return cliente


@router.get("/{cliente_id}")
async def read_cliente(
    cliente_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> ClienteDetail:
    """Detalhe de um cliente — inclui tags (no objeto) e anotações."""
    cliente = await _load_cliente_in_empresa(cliente_id, empresa_id)
    pool = await get_pool()
    anotacoes = await list_anotacoes(pool, cliente_id)
    return ClienteDetail(cliente=cliente, anotacoes=anotacoes)


@router.post("/{cliente_id}/anotacoes", status_code=201)
async def create_anotacao(
    cliente_id: int,
    body: AnotacaoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> ClienteAnotacao:
    """Adiciona anotação livre vinculada ao operador autenticado."""
    await _load_cliente_in_empresa(cliente_id, empresa_id)
    pool = await get_pool()
    out = await add_anotacao(pool, cliente_id, user_id, body.conteudo)
    logger.info(
        "cliente_anotacao_created",
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        anotacao_id=out.id,
        user_id=user_id,
    )
    return out


@router.post("/{cliente_id}/tags", status_code=204)
async def create_tag(
    cliente_id: int,
    body: TagInput,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    """Adiciona tag ao cliente (idempotente — duplicata é silenciosa)."""
    await _load_cliente_in_empresa(cliente_id, empresa_id)
    pool = await get_pool()
    await add_tag(pool, cliente_id, body.tag)
    logger.info(
        "cliente_tag_added",
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        tag=body.tag,
    )


@router.delete("/{cliente_id}/tags/{tag}", status_code=204)
async def delete_tag(
    cliente_id: int,
    tag: str,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    """Remove tag (idempotente — sem 404 quando não existe)."""
    await _load_cliente_in_empresa(cliente_id, empresa_id)
    pool = await get_pool()
    await remove_tag(pool, cliente_id, tag)
    logger.info(
        "cliente_tag_removed",
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        tag=tag,
    )
