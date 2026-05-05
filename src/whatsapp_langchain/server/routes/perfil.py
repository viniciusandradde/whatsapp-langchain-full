"""CRUD de perfis de acesso + atribuição (E2.A RBAC).

Endpoints:
- GET  /api/perfis              — lista perfis da empresa
- GET  /api/perfis/{id}         — detalhe + permissões
- POST /api/perfis              — cria perfil custom
- PUT  /api/perfis/{id}         — atualiza permissões + descrição
- DELETE /api/perfis/{id}       — remove perfil custom (cascade)
- GET  /api/permissoes          — catálogo global de permissões
- POST /api/perfis/{id}/users   — atribui perfil a user
- DELETE /api/perfis/{id}/users/{user_id}  — desatribui
- GET  /api/perfis/me           — set de permissões do user atual
- POST /api/empresas/{id}/migrate-rbac     — one-shot legacy migration

Permissão exigida: `perfil.write` pra mutations, `perfil.read` pra GETs.
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
from whatsapp_langchain.shared.empresa import is_admin_of
from whatsapp_langchain.shared.perfil import (
    assign_perfil,
    create_perfil,
    delete_perfil,
    get_perfil,
    get_user_permissions,
    list_perfis,
    list_user_perfis,
    migrate_empresa_legacy_to_perfis,
    unassign_perfil,
    update_perfil_permissoes,
)
from whatsapp_langchain.shared.permissoes import CATALOGO

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api",
    tags=["rbac"],
    dependencies=[Depends(verify_service_token)],
)


class CreatePerfilInput(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    descricao: str | None = None
    permissoes: list[str] = Field(default_factory=list)


class UpdatePerfilInput(BaseModel):
    permissoes: list[str]
    descricao: str | None = None


class AssignPerfilInput(BaseModel):
    user_id: str = Field(min_length=1)


# ---- Catálogo global ----


@router.get("/permissoes")
async def list_permissoes() -> dict:
    """Catálogo canônico de permissões (read-only, do código)."""
    return {
        "items": [
            {"codigo": c, "descricao": d, "modulo": m}
            for c, d, m in CATALOGO
        ]
    }


# ---- Perfis ----


@router.get("/perfis")
async def list_perfis_endpoint(
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("perfil.read")),
) -> dict:
    pool = await get_pool()
    return {"items": await list_perfis(pool, empresa_id)}


@router.get("/perfis/me")
async def my_permissions(
    user_id: str = Depends(get_user_id_from_request),
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Permissões efetivas do user atual — usado pelo hook usePermission."""
    pool = await get_pool()
    perms = await get_user_permissions(pool, user_id, empresa_id)
    perfis = await list_user_perfis(pool, user_id, empresa_id)
    return {
        "permissoes": sorted(perms),
        "perfis": perfis,
    }


@router.get("/perfis/{perfil_id}")
async def get_perfil_endpoint(
    perfil_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("perfil.read")),
) -> dict:
    pool = await get_pool()
    out = await get_perfil(pool, perfil_id, empresa_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    return out


@router.post("/perfis", status_code=201)
async def create_perfil_endpoint(
    body: CreatePerfilInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("perfil.write")),
) -> dict:
    pool = await get_pool()
    # Valida que todas as permissões existem no catálogo
    catalogo_codes = {c[0] for c in CATALOGO}
    invalidas = [p for p in body.permissoes if p not in catalogo_codes]
    if invalidas:
        raise HTTPException(
            status_code=422,
            detail=f"Permissões inválidas: {invalidas}",
        )
    perfil_id = await create_perfil(
        pool,
        empresa_id=empresa_id,
        nome=body.nome,
        descricao=body.descricao,
        permissoes=body.permissoes,
    )
    return await get_perfil(pool, perfil_id, empresa_id) or {"id": perfil_id}


@router.put("/perfis/{perfil_id}")
async def update_perfil_endpoint(
    perfil_id: int,
    body: UpdatePerfilInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("perfil.write")),
) -> dict:
    pool = await get_pool()
    catalogo_codes = {c[0] for c in CATALOGO}
    invalidas = [p for p in body.permissoes if p not in catalogo_codes]
    if invalidas:
        raise HTTPException(
            status_code=422, detail=f"Permissões inválidas: {invalidas}"
        )
    try:
        ok = await update_perfil_permissoes(
            pool,
            perfil_id,
            empresa_id,
            permissoes=body.permissoes,
            descricao=body.descricao,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    return await get_perfil(pool, perfil_id, empresa_id) or {}


@router.delete("/perfis/{perfil_id}", status_code=204)
async def delete_perfil_endpoint(
    perfil_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("perfil.write")),
) -> None:
    pool = await get_pool()
    try:
        ok = await delete_perfil(pool, perfil_id, empresa_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")


# ---- Atribuição ----


@router.post("/perfis/{perfil_id}/users", status_code=201)
async def assign_perfil_endpoint(
    perfil_id: int,
    body: AssignPerfilInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("perfil.write")),
) -> dict:
    pool = await get_pool()
    # Garante que perfil existe nessa empresa
    p = await get_perfil(pool, perfil_id, empresa_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    await assign_perfil(
        pool,
        empresa_id=empresa_id,
        user_id=body.user_id,
        perfil_id=perfil_id,
        assigned_by_user_id=user_id,
    )
    return {"ok": True}


@router.delete("/perfis/{perfil_id}/users/{target_user_id}", status_code=204)
async def unassign_perfil_endpoint(
    perfil_id: int,
    target_user_id: str,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("perfil.write")),
) -> None:
    pool = await get_pool()
    ok = await unassign_perfil(
        pool, empresa_id=empresa_id, user_id=target_user_id, perfil_id=perfil_id
    )
    if not ok:
        raise HTTPException(
            status_code=404, detail="User não tinha esse perfil."
        )


# ---- Migração legacy (one-shot) ----


@router.post("/empresas/{target_empresa_id}/migrate-rbac")
async def migrate_rbac_endpoint(
    target_empresa_id: int,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Converte empresa_membro.role → usuario_perfil em massa.

    Idempotente. Só admin da empresa OU superadmin pode executar.
    """
    pool = await get_pool()
    if not await is_admin_of(pool, target_empresa_id, user_id):
        raise HTTPException(
            status_code=403,
            detail="Só admin da empresa pode migrar RBAC.",
        )
    return await migrate_empresa_legacy_to_perfis(pool, target_empresa_id)
