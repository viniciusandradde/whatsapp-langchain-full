"""Endpoints CRUD de Agentes IA cadastráveis (Sub-fase A).

Substitui pontualmente o /api/agente_ia (mig 014). Mantém compat:
worker continua resolvendo via slug; loader pega config rica daqui.
"""

from __future__ import annotations

import re
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.agente import (
    DuplicateAgenteError,
    create_agente,
    get_agente_by_slug,
    list_agentes,
    set_default_agente,
    soft_delete_agente,
    update_agente,
)
from whatsapp_langchain.shared.audit import diff_dicts, record_audit
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/agentes",
    tags=["agente-ia"],
    dependencies=[Depends(verify_service_token)],
)


SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,60}$")
ESTILOS = {"preciso", "equilibrado", "criativo", "muito_criativo"}
LIMITE_ACOES = {"solicitar_humano", "encerrar", "continuar", "bloquear"}


class CreateAgenteInput(BaseModel):
    slug: str = Field(min_length=2, max_length=60)
    nome: str = Field(min_length=1, max_length=120)
    descricao: str | None = Field(default=None, max_length=500)
    template_catalog: str = Field(default="vsa_tech", max_length=60)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError(
                "slug deve começar com letra e usar só [a-z0-9_-] (2-60 chars)"
            )
        return v


class UpdateAgenteInput(BaseModel):
    """Patch parcial — só campos não-None são tocados."""

    nome: str | None = Field(default=None, min_length=1, max_length=120)
    descricao: str | None = Field(default=None, max_length=500)
    template_catalog: str | None = Field(default=None, max_length=60)
    prompt_override: str | None = Field(default=None, max_length=20_000)
    modelo: str | None = Field(default=None, max_length=120)
    estilo_resposta: str | None = None
    temperatura_override: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=200_000)
    top_p_override: float | None = Field(default=None, ge=0, le=1)
    tools_enabled: list[str] | None = None
    tools_config: dict | None = None
    aceita_imagem: bool | None = None
    aceita_audio: bool | None = None
    aceita_documento: bool | None = None
    base_conhecimento_ids: list[int] | None = None
    variavel_ids: list[int] | None = None
    mcp_server_ids: list[int] | None = None
    limite_custo_acao: str | None = None
    ativo: bool | None = None
    # Sprint 2 paridade ZigChat (mig 043)
    modelo_provedor: str | None = Field(default=None, max_length=60)
    modelo_nome: str | None = Field(default=None, max_length=120)
    tipo_memoria: str | None = None
    janela_memoria: int | None = Field(default=None, ge=1, le=200)
    timeout_minutos: int | None = Field(default=None, ge=1, le=1440)
    acao_limite_menu_id: int | None = None

    @field_validator("estilo_resposta")
    @classmethod
    def _validate_estilo(cls, v: str | None) -> str | None:
        if v is not None and v not in ESTILOS:
            raise ValueError(f"estilo_resposta deve ser um de {sorted(ESTILOS)}")
        return v

    @field_validator("limite_custo_acao")
    @classmethod
    def _validate_limite(cls, v: str | None) -> str | None:
        if v is not None and v not in LIMITE_ACOES:
            raise ValueError(f"limite_custo_acao deve ser um de {sorted(LIMITE_ACOES)}")
        return v

    @field_validator("tipo_memoria")
    @classmethod
    def _validate_memoria(cls, v: str | None) -> str | None:
        valid = {"buffer", "window", "summary", "none"}
        if v is not None and v not in valid:
            raise ValueError(f"tipo_memoria deve ser um de {sorted(valid)}")
        return v


# ---- Endpoints ----


@router.get("/templates")
async def list_templates_endpoint(
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    """Lista templates de agente disponíveis no catálogo Python (com metadata).

    Resposta: `{"items": [{slug, label, descricao}, ...]}`

    Usado pelos forms de criar/editar agente DB pra dropdown de
    `template_catalog`. Metadata curada em `agents/loader.py::_TEMPLATE_METADATA`.
    """
    from whatsapp_langchain.agents.loader import list_agente_templates

    return {"items": list_agente_templates()}


@router.get("")
async def list_endpoint(
    only_active: bool = False,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    items = await list_agentes(pool, empresa_id, only_active=only_active)
    return {"items": [a.to_dict() for a in items]}


@router.get("/{slug}")
async def get_endpoint(
    slug: str,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    out = await get_agente_by_slug(pool, empresa_id, slug)
    if out is None:
        raise HTTPException(status_code=404, detail="Agente não encontrado.")
    return out.to_dict()


@router.post("", status_code=201)
async def create_endpoint(
    body: CreateAgenteInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    try:
        out = await create_agente(
            pool,
            empresa_id,
            slug=body.slug,
            nome=body.nome,
            descricao=body.descricao,
            template_catalog=body.template_catalog,
            user_id=user_id,
        )
    except DuplicateAgenteError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="agente.create",
        entity_type="agente_ia",
        entity_id=out.slug,
        payload_diff={"after": out.to_dict()},
        request=request,
    )
    return out.to_dict()


@router.put("/{slug}")
async def update_endpoint(
    slug: str,
    body: UpdateAgenteInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    before = await get_agente_by_slug(pool, empresa_id, slug)
    if before is None:
        raise HTTPException(status_code=404, detail="Agente não encontrado.")

    # Filtra campos não-None do body
    fields: dict[str, Any] = {
        k: v for k, v in body.model_dump().items() if v is not None
    }
    updated = await update_agente(pool, empresa_id, slug, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Agente não encontrado após update.")

    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="agente.update",
        entity_type="agente_ia",
        entity_id=slug,
        payload_diff=diff_dicts(before.to_dict(), updated.to_dict()),
        request=request,
    )
    return updated.to_dict()


@router.delete("/{slug}", status_code=204)
async def delete_endpoint(
    slug: str,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> None:
    """Soft delete (ativo=false). Preserva FKs em atendimentos antigos."""
    pool = await get_pool()
    ok = await soft_delete_agente(pool, empresa_id, slug)
    if not ok:
        raise HTTPException(status_code=404, detail="Agente não encontrado.")
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="agente.delete",
        entity_type="agente_ia",
        entity_id=slug,
        request=request,
    )


@router.post("/{slug}/set-default")
async def set_default_endpoint(
    slug: str,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    """Promove agente a default da empresa (limpa default anterior)."""
    pool = await get_pool()
    ok = await set_default_agente(pool, empresa_id, slug)
    if not ok:
        raise HTTPException(
            status_code=404, detail="Agente não encontrado ou inativo."
        )
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="agente.set_default",
        entity_type="agente_ia",
        entity_id=slug,
        request=request,
    )
    return {"ok": True, "slug": slug}
