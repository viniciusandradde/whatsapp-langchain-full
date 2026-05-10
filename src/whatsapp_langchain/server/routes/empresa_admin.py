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
    get_user_status,
    is_admin_of,
    is_superadmin,
    list_members,
    remove_member,
    set_user_status,
    update_empresa,
    update_empresa_csat,
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


# Sprint Y: configuração da pesquisa NPS por empresa
class CsatConfig(BaseModel):
    csat_ativo: bool
    csat_pergunta: str | None = None
    csat_msg_agradecimento: str | None = None
    csat_solicita_comentario: bool = True


@router.get("/{empresa_id}/csat", response_model=CsatConfig)
async def get_empresa_csat_endpoint(
    empresa_id: int,
    user_id: str = Depends(get_user_id_from_request),
):
    """Lê a config CSAT da empresa. Acesso pra qualquer membro (admin lê
    + pode editar; não-admin só vê)."""
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        from whatsapp_langchain.shared.empresa import get_empresa_membership

        if not await get_empresa_membership(pool, empresa_id, user_id):
            raise HTTPException(status_code=403, detail="Sem acesso à empresa.")
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT csat_ativo, csat_pergunta, csat_msg_agradecimento,
                      csat_solicita_comentario FROM empresa WHERE id = %s""",
            (empresa_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return CsatConfig(
        csat_ativo=bool(row[0]),
        csat_pergunta=row[1],
        csat_msg_agradecimento=row[2],
        csat_solicita_comentario=bool(row[3]),
    )


@router.put("/{empresa_id}/csat", response_model=CsatConfig)
async def update_empresa_csat_endpoint(
    empresa_id: int,
    body: CsatConfig,
    user_id: str = Depends(get_user_id_from_request),
):
    """Atualiza config CSAT da empresa. Só admin local ou superadmin."""
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode atualizar.")
    ok = await update_empresa_csat(
        pool,
        empresa_id,
        csat_ativo=body.csat_ativo,
        csat_pergunta=body.csat_pergunta,
        csat_msg_agradecimento=body.csat_msg_agradecimento,
        csat_solicita_comentario=body.csat_solicita_comentario,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    logger.info(
        "empresa_csat_updated",
        empresa_id=empresa_id,
        csat_ativo=body.csat_ativo,
        actor=user_id,
    )
    return body


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


# ---------------------------------------------------------------------------
# Status do user — ativar/desativar (E1.7)
# ---------------------------------------------------------------------------


class UpdateStatusInput(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


@router.put("/{empresa_id}/membros/{member_user_id}/status")
async def update_member_status(
    empresa_id: int,
    member_user_id: str,
    body: UpdateStatusInput,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Ativa/desativa user (auth.user.status).

    Desativar: remove sessões ativas + bloqueia novos logins até reativar.
    Ativar: libera login (sessões antigas continuam expiradas — user
    precisa logar de novo).

    Proteções:
    - Só admin da empresa OU superadmin pode mudar status
    - Não permite desativar a si mesmo (evita lockout acidental)
    - Não permite desativar o último admin da empresa (proteção paralela
      ao update_member_role)
    """
    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(status_code=403, detail="Só admin pode mudar status.")

    if member_user_id == user_id and body.status == "disabled":
        raise HTTPException(
            status_code=409,
            detail="Você não pode desativar a si mesmo. Peça para outro admin.",
        )

    # Quando desativando, validar que não é o último admin da empresa
    if body.status == "disabled":
        members = await list_members(pool, empresa_id)
        admins_ativos = [
            m
            for m in members
            if m.role == "admin" and m.user_id != member_user_id
        ]
        target_member = next((m for m in members if m.user_id == member_user_id), None)
        if target_member and target_member.role == "admin" and not admins_ativos:
            raise HTTPException(
                status_code=409,
                detail="Não pode desativar o último admin da empresa.",
            )

    affected = await set_user_status(pool, member_user_id, status=body.status)
    if not affected:
        raise HTTPException(status_code=404, detail="User não encontrado.")

    logger.info(
        "user_status_changed",
        target_user_id=member_user_id,
        new_status=body.status,
        actor_user_id=user_id,
        empresa_id=empresa_id,
    )
    return {"user_id": member_user_id, "status": body.status}


@router.get("/users/{member_user_id}/status")
async def get_status(
    member_user_id: str,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Lê status do user. Acessível por superadmin OU pelo próprio user."""
    pool = await get_pool()
    if member_user_id != user_id and not await is_superadmin(pool, user_id):
        raise HTTPException(
            status_code=403,
            detail="Só superadmin ou o próprio user pode ver status.",
        )
    status = await get_user_status(pool, member_user_id)
    if status is None:
        raise HTTPException(status_code=404, detail="User não encontrado.")
    return {"user_id": member_user_id, "status": status}
