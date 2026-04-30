"""Endpoints de gestão de empresas e membros (M1.x).

Mutações exigem que o user seja admin da empresa-alvo ou superadmin
global. Cada endpoint valida explicitamente — não usamos role-guard
genérico pra manter as regras (ex: "remover último admin" → 409) no
lugar onde a operação acontece.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import (
    add_member,
    create_empresa,
    get_empresa_by_id,
    is_admin_of,
    is_superadmin,
    list_members,
    remove_member,
    update_empresa,
    update_member_role,
)
from whatsapp_langchain.shared.models import Empresa, EmpresaMembro

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/empresas",
    tags=["empresa_admin"],
    dependencies=[Depends(verify_service_token)],
)


class CreateEmpresaInput(BaseModel):
    nome: str = Field(min_length=1)
    slug: str = Field(min_length=2)
    plano: str = "free"
    doc: str | None = None


class UpdateEmpresaInput(BaseModel):
    nome: str | None = None
    slug: str | None = None
    plano: str | None = None
    doc: str | None = None
    status: str | None = None


class AddMemberInput(BaseModel):
    user_id: str = Field(min_length=1)
    role: str = "operator"


class UpdateRoleInput(BaseModel):
    role: str


VALID_ROLES = {"admin", "operator", "viewer"}


def _check_role(role: str) -> None:
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role inválido. Valores aceitos: {sorted(VALID_ROLES)}.",
        )


@router.post("", response_model=Empresa)
async def create_empresa_endpoint(
    body: CreateEmpresaInput,
    user_id: str = Depends(get_user_id_from_request),
):
    """Cria empresa. Quem cria vira admin. Slug único globalmente."""
    pool = await get_pool()
    try:
        empresa = await create_empresa(
            pool, body.nome, body.slug, body.plano, body.doc, user_id
        )
    except Exception as e:
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Slug já em uso.") from e
        raise
    logger.info("empresa_created", empresa_id=empresa.id, criador=user_id)
    return empresa


@router.put("/{empresa_id}", response_model=Empresa)
async def update_empresa_endpoint(
    empresa_id: int,
    body: UpdateEmpresaInput,
    user_id: str = Depends(get_user_id_from_request),
):
    """Atualiza campos da empresa. Só admin local ou superadmin."""
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode atualizar.")

    out = await update_empresa(
        pool,
        empresa_id,
        nome=body.nome,
        slug=body.slug,
        plano=body.plano,
        doc=body.doc,
        status=body.status,
    )
    if out is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return out


@router.get("/{empresa_id}/membros", response_model=list[EmpresaMembro])
async def list_members_endpoint(
    empresa_id: int,
    user_id: str = Depends(get_user_id_from_request),
):
    """Lista membros — qualquer membro da empresa (ou superadmin) pode ver."""
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        from whatsapp_langchain.shared.empresa import get_empresa_membership

        m = await get_empresa_membership(pool, empresa_id, user_id)
        if m is None:
            raise HTTPException(status_code=403, detail="Sem acesso à empresa.")
    if await get_empresa_by_id(pool, empresa_id) is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return await list_members(pool, empresa_id)


@router.post("/{empresa_id}/membros", response_model=EmpresaMembro)
async def add_member_endpoint(
    empresa_id: int,
    body: AddMemberInput,
    user_id: str = Depends(get_user_id_from_request),
):
    """Adiciona membro. Só admin local ou superadmin."""
    _check_role(body.role)
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode adicionar membros.")
    if await get_empresa_by_id(pool, empresa_id) is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return await add_member(pool, empresa_id, body.user_id, body.role)


@router.put("/{empresa_id}/membros/{member_user_id}", response_model=EmpresaMembro)
async def update_member_role_endpoint(
    empresa_id: int,
    member_user_id: str,
    body: UpdateRoleInput,
    user_id: str = Depends(get_user_id_from_request),
):
    """Atualiza role. Bloqueia demote do último admin (409)."""
    _check_role(body.role)
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode mudar roles.")
    out = await update_member_role(pool, empresa_id, member_user_id, body.role)
    if out is None:
        raise HTTPException(
            status_code=409,
            detail="Não é possível demote do último admin da empresa.",
        )
    return out


@router.delete("/{empresa_id}/membros/{member_user_id}", status_code=204)
async def remove_member_endpoint(
    empresa_id: int,
    member_user_id: str,
    user_id: str = Depends(get_user_id_from_request),
):
    """Remove membro. Bloqueia remoção do último admin (409)."""
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode remover membros.")
    ok = await remove_member(pool, empresa_id, member_user_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Membro não existe ou seria o último admin (não removível).",
        )
