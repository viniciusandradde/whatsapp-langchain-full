"""CRUD de conexões WhatsApp do painel admin.

Endpoints escopados pela empresa ativa (`get_empresa_context`). Mutações
ficam abertas a qualquer membro no MVP — diferenciar por role é tarefa
futura (M1.x).
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.shared.conexao import (
    get_conexao_by_id,
    list_conexoes,
    set_conexao_status,
    upsert_conexao,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import Conexao, ConexaoInput

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/conexoes",
    tags=["conexoes"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("")
async def list_my_conexoes(
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[Conexao]]:
    """Lista conexões da empresa ativa, default primeiro."""
    pool = await get_pool()
    return {"conexoes": await list_conexoes(pool, empresa_id)}


@router.get("/{conexao_id}")
async def read_conexao(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> Conexao:
    """Detalhe de uma conexão. 404 quando inexistente, 403 cross-tenant."""
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="Conexão fora da empresa ativa.")
    return conexao


@router.post("")
async def create_conexao(
    body: ConexaoInput,
    empresa_id: int = Depends(get_empresa_context),
) -> Conexao:
    """Cria conexão na empresa ativa. UPSERT — se from_number existir, atualiza."""
    pool = await get_pool()
    out = await upsert_conexao(pool, empresa_id, body)
    logger.info(
        "conexao_created",
        empresa_id=empresa_id,
        conexao_id=out.id,
        provider=out.provider,
        from_number=out.from_number,
    )
    return out


@router.put("/{conexao_id}")
async def update_conexao(
    conexao_id: int,
    body: ConexaoInput,
    empresa_id: int = Depends(get_empresa_context),
) -> Conexao:
    """Atualiza uma conexão existente. 404 quando inexistente, 403 cross-tenant."""
    pool = await get_pool()
    existing = await get_conexao_by_id(pool, conexao_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if existing.empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="Conexão fora da empresa ativa.")

    # Mantém o from_number do payload — UPSERT vai casar pelo UNIQUE.
    out = await upsert_conexao(pool, empresa_id, body)
    logger.info(
        "conexao_updated",
        empresa_id=empresa_id,
        conexao_id=out.id,
        from_number=out.from_number,
    )
    return out


@router.delete("/{conexao_id}", status_code=204)
async def disable_conexao(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    """Soft-delete: status='disabled'. Preserva histórico em message_queue."""
    pool = await get_pool()
    existing = await get_conexao_by_id(pool, conexao_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if existing.empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="Conexão fora da empresa ativa.")
    await set_conexao_status(pool, conexao_id, "disabled")
    logger.info("conexao_disabled", empresa_id=empresa_id, conexao_id=conexao_id)
