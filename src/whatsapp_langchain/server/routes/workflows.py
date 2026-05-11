"""Endpoints admin de Workflows ZigChat (proposta/menu-langgraph-workflows).

CRUD de `workflow_chatbot` + leitura de state ativo pra debug.

- GET  /api/admin/workflows                        → lista por empresa
- GET  /api/admin/workflows/{id}                   → detalhe + versão ativa
- PUT  /api/admin/workflows/{id}                   → atualiza + publica versão
- POST /api/admin/workflows/{id}/toggle-active     → liga/desliga
- GET  /api/admin/atendimentos/{id}/workflow-state → debug L2 do state runtime

Auth:
- Lista/detail: qualquer membro da empresa.
- PUT/toggle: admin local da empresa OU superadmin.
- Workflow-state: qualquer membro da empresa do atendimento.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import (
    get_empresa_membership,
    is_admin_of,
    is_superadmin,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/admin",
    tags=["workflows"],
    dependencies=[Depends(verify_service_token)],
)


# ---- Schemas ----


class WorkflowListItem(BaseModel):
    id: int
    slug: str
    nome: str
    descricao: str | None
    versao: int
    versao_ativa_id: int | None
    ativo: bool
    updated_at: str | None


class WorkflowDetail(BaseModel):
    id: int
    empresa_id: int
    slug: str
    nome: str
    descricao: str | None
    definicao: dict[str, Any]
    versao: int
    versao_ativa_id: int | None
    ativo: bool
    created_at: str | None
    updated_at: str | None


class WorkflowUpdate(BaseModel):
    nome: str | None = None
    descricao: str | None = None
    definicao: dict[str, Any] | None = None


class WorkflowStateOut(BaseModel):
    atendimento_id: int
    current_nodes: list[str]
    vars: dict[str, Any]
    history: list[str]
    interrupt_pending: Any
    workflow_version_id: int
    is_terminal: bool
    events: list[dict[str, Any]]


# ---- Helpers de auth ----


async def _require_member(pool, empresa_id: int, user_id: str) -> None:
    if await is_superadmin(pool, user_id):
        return
    member = await get_empresa_membership(pool, empresa_id, user_id)
    if not member:
        raise HTTPException(status_code=403, detail="Sem acesso à empresa.")


async def _require_admin(pool, empresa_id: int, user_id: str) -> None:
    if await is_superadmin(pool, user_id):
        return
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(
            status_code=403, detail="Apenas admins da empresa podem editar."
        )


# ---- Endpoints CRUD ----


@router.get("/workflows", response_model=list[WorkflowListItem])
async def list_workflows(
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
):
    """Lista workflows da empresa ativa."""
    pool = await get_pool()
    await _require_member(pool, empresa_id, user_id)
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, slug, nome, descricao, versao, versao_ativa_id,
                   ativo, updated_at
              FROM workflow_chatbot
             WHERE empresa_id = %s
             ORDER BY slug
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [
        WorkflowListItem(
            id=r[0],
            slug=r[1],
            nome=r[2],
            descricao=r[3],
            versao=r[4],
            versao_ativa_id=r[5],
            ativo=r[6],
            updated_at=r[7].isoformat() if r[7] else None,
        )
        for r in rows
    ]


@router.get("/workflows/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow(
    workflow_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
):
    pool = await get_pool()
    await _require_member(pool, empresa_id, user_id)
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, empresa_id, slug, nome, descricao, definicao,
                   versao, versao_ativa_id, ativo, created_at, updated_at
              FROM workflow_chatbot
             WHERE id = %s AND empresa_id = %s
            """,
            (workflow_id, empresa_id),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Workflow não encontrado.")
    definicao = row[5]
    if isinstance(definicao, str):
        definicao = json.loads(definicao)
    return WorkflowDetail(
        id=row[0],
        empresa_id=row[1],
        slug=row[2],
        nome=row[3],
        descricao=row[4],
        definicao=definicao,
        versao=row[6],
        versao_ativa_id=row[7],
        ativo=row[8],
        created_at=row[9].isoformat() if row[9] else None,
        updated_at=row[10].isoformat() if row[10] else None,
    )


@router.put("/workflows/{workflow_id}", response_model=WorkflowDetail)
async def update_workflow(
    workflow_id: int,
    body: WorkflowUpdate,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
):
    """Atualiza workflow + cria nova versão imutável.

    Cliente envia `definicao` completa (workflow inteiro). Backend valida
    schema mínimo (entry + nodes), incrementa versao, insere row em
    workflow_chatbot_version, aponta versao_ativa_id pra ela.
    """
    pool = await get_pool()
    await _require_admin(pool, empresa_id, user_id)

    if body.definicao is not None:
        # Validação mínima
        if not isinstance(body.definicao.get("nodes"), dict):
            raise HTTPException(
                status_code=400, detail="definicao.nodes deve ser dict"
            )
        if not body.definicao.get("entry"):
            raise HTTPException(
                status_code=400, detail="definicao.entry obrigatório"
            )
        if body.definicao["entry"] not in body.definicao["nodes"]:
            raise HTTPException(
                status_code=400,
                detail=f"entry '{body.definicao['entry']}' não está em nodes",
            )

    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, versao, definicao FROM workflow_chatbot "
            "WHERE id = %s AND empresa_id = %s",
            (workflow_id, empresa_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workflow não encontrado.")

        update_fields: list[str] = []
        update_params: list[Any] = []
        if body.nome is not None:
            update_fields.append("nome = %s")
            update_params.append(body.nome)
        if body.descricao is not None:
            update_fields.append("descricao = %s")
            update_params.append(body.descricao)
        new_version_id = None
        if body.definicao is not None:
            new_versao = int(row[1]) + 1
            update_fields.append("definicao = %s::jsonb")
            update_params.append(json.dumps(body.definicao, ensure_ascii=False))
            update_fields.append("versao = %s")
            update_params.append(new_versao)
            # Insere version imutável
            cur = await conn.execute(
                """
                INSERT INTO workflow_chatbot_version
                    (workflow_id, versao, definicao, published_by_user_id)
                VALUES (%s, %s, %s::jsonb, %s)
                RETURNING id
                """,
                (
                    workflow_id,
                    new_versao,
                    json.dumps(body.definicao, ensure_ascii=False),
                    user_id,
                ),
            )
            ver_row = await cur.fetchone()
            if ver_row:
                new_version_id = int(ver_row[0])
                update_fields.append("versao_ativa_id = %s")
                update_params.append(new_version_id)

        if update_fields:
            update_fields.append("updated_at = NOW()")
            update_params.extend([workflow_id, empresa_id])
            await conn.execute(
                f"""UPDATE workflow_chatbot SET {', '.join(update_fields)}
                    WHERE id = %s AND empresa_id = %s""",
                tuple(update_params),
            )
            await conn.commit()

    logger.info(
        "workflow_updated",
        workflow_id=workflow_id,
        empresa_id=empresa_id,
        user_id=user_id,
        new_version_id=new_version_id,
    )
    return await get_workflow(workflow_id, empresa_id, user_id)


@router.post("/workflows/{workflow_id}/toggle-active")
async def toggle_workflow_active(
    workflow_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
):
    pool = await get_pool()
    await _require_admin(pool, empresa_id, user_id)
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE workflow_chatbot
               SET ativo = NOT ativo, updated_at = NOW()
             WHERE id = %s AND empresa_id = %s
            RETURNING ativo
            """,
            (workflow_id, empresa_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Workflow não encontrado.")
    return {"workflow_id": workflow_id, "ativo": bool(row[0])}


# ---- Endpoint de state (debug L2) ----


@router.get(
    "/atendimentos/{atendimento_id}/workflow-state",
    response_model=WorkflowStateOut | None,
)
async def get_atendimento_workflow_state(
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
):
    """Lê o state runtime do workflow pra um atendimento — pra debug L2.

    Importa LangGraph checkpointer dinamicamente pra evitar dependência
    no boot dos workers. Se empresa não tem workflow ativo OU atendimento
    nunca entrou em workflow, retorna 404.
    """
    from whatsapp_langchain.shared.db import open_checkpointer
    from whatsapp_langchain.workflows.loader import get_workflow_state_snapshot

    pool = await get_pool()
    await _require_member(pool, empresa_id, user_id)

    # Valida que atendimento é da empresa
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT empresa_id FROM atendimento WHERE id = %s",
            (atendimento_id,),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado.")
    if row[0] != empresa_id:
        raise HTTPException(
            status_code=403, detail="Atendimento fora da empresa ativa."
        )

    # Abre checkpointer sob demanda — em prod, worker já tem 1 aberto, mas o
    # API server roda separado e pode não ter. Pra simplicidade, abrimos
    # 1 ad-hoc (mais lento mas raríssimo).
    async with open_checkpointer() as checkpointer:
        snapshot = await get_workflow_state_snapshot(
            pool, checkpointer, atendimento_id, empresa_id
        )
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Atendimento sem state de workflow "
                "(workflow desativado ou não iniciado)."
            ),
        )
    return WorkflowStateOut(**snapshot)
