"""CRUD da whitelist de números — bypass total da IA por número (mig 133).

Números cadastrados aqui não recebem nenhuma resposta automática do worker
(gate em `worker/processor.py`); as mensagens seguem registradas na fila
humana. Leitura liberada (contexto de empresa); mutação exige
`whitelist.manage` (Admin/Gestor).

Endpoints:
- GET    /api/whitelist          — lista números da empresa
- POST   /api/whitelist          — cadastra número
- PATCH  /api/whitelist/{id}     — atualiza apelido
- DELETE /api/whitelist/{id}     — remove (IA volta a responder)
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
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.whitelist import (
    atualizar_whitelist,
    listar_whitelist,
    registrar_whitelist,
    remover_whitelist,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api",
    tags=["whitelist"],
    dependencies=[Depends(verify_service_token)],
)


class CreateWhitelistInput(BaseModel):
    telefone: str = Field(min_length=8, max_length=32)
    nome: str | None = Field(default=None, max_length=80)


class UpdateWhitelistInput(BaseModel):
    nome: str | None = Field(default=None, max_length=80)


@router.get("/whitelist")
async def list_whitelist_endpoint(
    empresa_id: int = Depends(get_empresa_context),
    # Leitura liberada — mutação exige `whitelist.manage`.
) -> dict:
    pool = await get_pool()
    items = await listar_whitelist(pool, empresa_id)
    return {"items": items}


@router.post("/whitelist")
async def create_whitelist_endpoint(
    payload: CreateWhitelistInput,
    user_id: str = Depends(get_user_id_from_request),
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("whitelist.manage")),
) -> dict:
    pool = await get_pool()
    try:
        return await registrar_whitelist(
            pool,
            empresa_id,
            telefone=payload.telefone.strip(),
            nome=payload.nome.strip() if payload.nome else None,
            created_by_user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Telefone inválido.") from exc
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise HTTPException(
                status_code=409, detail="Esse número já está na whitelist."
            ) from exc
        raise


@router.patch("/whitelist/{whitelist_id}")
async def update_whitelist_endpoint(
    whitelist_id: int,
    payload: UpdateWhitelistInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("whitelist.manage")),
) -> dict:
    pool = await get_pool()
    result = await atualizar_whitelist(
        pool,
        empresa_id,
        whitelist_id,
        nome=payload.nome.strip() if payload.nome else None,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Número não encontrado.")
    return result


@router.delete("/whitelist/{whitelist_id}")
async def delete_whitelist_endpoint(
    whitelist_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("whitelist.manage")),
) -> dict:
    pool = await get_pool()
    ok = await remover_whitelist(pool, empresa_id, whitelist_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Número não encontrado.")
    return {"ok": True}
