"""Endpoints catálogo: modelo_llm + mcp_server (Sprint 1+ padrão profissional)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.audit import diff_dicts, record_audit
from whatsapp_langchain.shared.catalogo import (
    create_mcp_server,
    create_modelo_llm,
    delete_mcp_server,
    delete_modelo_llm,
    get_mcp_server,
    get_modelo_llm,
    list_mcp_servers,
    list_modelos_llm,
    update_mcp_server,
    update_modelo_llm,
)
from whatsapp_langchain.shared.db import get_pool


# =====================================================================
# modelo_llm
# =====================================================================

router_modelo_llm = APIRouter(
    prefix="/api/v1/modelos-llm",
    tags=["catalogo"],
    dependencies=[Depends(verify_service_token)],
)

TIPOS_MODELO = {"chat", "embedding", "midia", "audio", "imagem"}


class CreateModeloLLMInput(BaseModel):
    provedor: str = Field(min_length=1, max_length=60)
    nome: str = Field(min_length=1, max_length=120)
    tipo: str
    descricao: str | None = Field(default=None, max_length=500)
    custo_input_mtok: float | None = Field(default=None, ge=0)
    custo_output_mtok: float | None = Field(default=None, ge=0)
    janela_contexto: int | None = Field(default=None, ge=1)

    @field_validator("tipo")
    @classmethod
    def _validate_tipo(cls, v: str) -> str:
        if v not in TIPOS_MODELO:
            raise ValueError(f"tipo deve ser um de {sorted(TIPOS_MODELO)}")
        return v


class UpdateModeloLLMInput(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    descricao: str | None = Field(default=None, max_length=500)
    custo_input_mtok: float | None = Field(default=None, ge=0)
    custo_output_mtok: float | None = Field(default=None, ge=0)
    janela_contexto: int | None = Field(default=None, ge=1)
    ativo: bool | None = None


@router_modelo_llm.get("")
async def list_modelos_endpoint(
    tipo: str | None = None,
    only_active: bool = True,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    items = await list_modelos_llm(
        pool, empresa_id, tipo=tipo, only_active=only_active
    )
    return {"items": [m.to_dict() for m in items]}


@router_modelo_llm.get("/{modelo_id}")
async def get_modelo_endpoint(
    modelo_id: int,
    _empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    m = await get_modelo_llm(pool, modelo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")
    return m.to_dict()


@router_modelo_llm.post("", status_code=201)
async def create_modelo_endpoint(
    body: CreateModeloLLMInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    out = await create_modelo_llm(
        pool,
        empresa_id=empresa_id,
        provedor=body.provedor,
        nome=body.nome,
        tipo=body.tipo,
        descricao=body.descricao,
        custo_input_mtok=body.custo_input_mtok,
        custo_output_mtok=body.custo_output_mtok,
        janela_contexto=body.janela_contexto,
    )
    await record_audit(
        pool, empresa_id=empresa_id, user_id=user_id,
        action="modelo_llm.create", entity_type="modelo_llm",
        entity_id=str(out.id), payload_diff={"after": out.to_dict()},
        request=request,
    )
    return out.to_dict()


@router_modelo_llm.put("/{modelo_id}")
async def update_modelo_endpoint(
    modelo_id: int,
    body: UpdateModeloLLMInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    before = await get_modelo_llm(pool, modelo_id)
    if before is None or (before.empresa_id is not None and before.empresa_id != empresa_id):
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")
    if before.empresa_id is None:
        raise HTTPException(
            status_code=403, detail="Modelos globais não podem ser editados."
        )
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    out = await update_modelo_llm(pool, modelo_id, **fields)
    if out is None:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")
    await record_audit(
        pool, empresa_id=empresa_id, user_id=user_id,
        action="modelo_llm.update", entity_type="modelo_llm",
        entity_id=str(modelo_id),
        payload_diff=diff_dicts(before.to_dict(), out.to_dict()),
        request=request,
    )
    return out.to_dict()


@router_modelo_llm.delete("/{modelo_id}", status_code=204)
async def delete_modelo_endpoint(
    modelo_id: int,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> None:
    pool = await get_pool()
    before = await get_modelo_llm(pool, modelo_id)
    if before is None or (before.empresa_id is not None and before.empresa_id != empresa_id):
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")
    if before.empresa_id is None:
        raise HTTPException(
            status_code=403, detail="Modelos globais não podem ser deletados."
        )
    ok = await delete_modelo_llm(pool, modelo_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")
    await record_audit(
        pool, empresa_id=empresa_id, user_id=user_id,
        action="modelo_llm.delete", entity_type="modelo_llm",
        entity_id=str(modelo_id),
        payload_diff={"before": before.to_dict()}, request=request,
    )


# =====================================================================
# mcp_server
# =====================================================================

router_mcp = APIRouter(
    prefix="/api/v1/mcp-servers",
    tags=["catalogo"],
    dependencies=[Depends(verify_service_token)],
)

TIPOS_MCP = {"stdio", "sse", "http", "websocket"}


class CreateMcpInput(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    tipo_conexao: str
    descricao: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    comando: str | None = Field(default=None, max_length=500)
    args: str | None = Field(default=None, max_length=2000)
    headers: dict[str, Any] | None = None

    @field_validator("tipo_conexao")
    @classmethod
    def _validate_tipo(cls, v: str) -> str:
        if v not in TIPOS_MCP:
            raise ValueError(f"tipo_conexao deve ser um de {sorted(TIPOS_MCP)}")
        return v


class UpdateMcpInput(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    descricao: str | None = Field(default=None, max_length=500)
    tipo_conexao: str | None = None
    url: str | None = Field(default=None, max_length=2000)
    comando: str | None = Field(default=None, max_length=500)
    args: str | None = Field(default=None, max_length=2000)
    headers: dict[str, Any] | None = None
    ativo: bool | None = None


@router_mcp.get("")
async def list_mcp_endpoint(
    only_active: bool = False,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    items = await list_mcp_servers(pool, empresa_id, only_active=only_active)
    return {"items": [m.to_dict() for m in items]}


@router_mcp.get("/{mcp_id}")
async def get_mcp_endpoint(
    mcp_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    m = await get_mcp_server(pool, empresa_id, mcp_id)
    if m is None:
        raise HTTPException(status_code=404, detail="MCP server não encontrado.")
    return m.to_dict()


@router_mcp.post("", status_code=201)
async def create_mcp_endpoint(
    body: CreateMcpInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    out = await create_mcp_server(
        pool, empresa_id,
        nome=body.nome, tipo_conexao=body.tipo_conexao, descricao=body.descricao,
        url=body.url, comando=body.comando, args=body.args, headers=body.headers,
        user_id=user_id,
    )
    await record_audit(
        pool, empresa_id=empresa_id, user_id=user_id,
        action="mcp_server.create", entity_type="mcp_server",
        entity_id=str(out.id), payload_diff={"after": out.to_dict()},
        request=request,
    )
    return out.to_dict()


@router_mcp.put("/{mcp_id}")
async def update_mcp_endpoint(
    mcp_id: int,
    body: UpdateMcpInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    pool = await get_pool()
    before = await get_mcp_server(pool, empresa_id, mcp_id)
    if before is None:
        raise HTTPException(status_code=404, detail="MCP server não encontrado.")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    out = await update_mcp_server(pool, empresa_id, mcp_id, **fields)
    if out is None:
        raise HTTPException(status_code=404, detail="MCP server não encontrado.")
    await record_audit(
        pool, empresa_id=empresa_id, user_id=user_id,
        action="mcp_server.update", entity_type="mcp_server",
        entity_id=str(mcp_id),
        payload_diff=diff_dicts(before.to_dict(), out.to_dict()),
        request=request,
    )
    return out.to_dict()


@router_mcp.delete("/{mcp_id}", status_code=204)
async def delete_mcp_endpoint(
    mcp_id: int,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> None:
    pool = await get_pool()
    before = await get_mcp_server(pool, empresa_id, mcp_id)
    if before is None:
        raise HTTPException(status_code=404, detail="MCP server não encontrado.")
    ok = await delete_mcp_server(pool, empresa_id, mcp_id)
    if not ok:
        raise HTTPException(status_code=404, detail="MCP server não encontrado.")
    await record_audit(
        pool, empresa_id=empresa_id, user_id=user_id,
        action="mcp_server.delete", entity_type="mcp_server",
        entity_id=str(mcp_id),
        payload_diff={"before": before.to_dict()}, request=request,
    )


@router_mcp.post("/{mcp_id}/test")
async def test_mcp_endpoint(
    mcp_id: int,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    """Health check do MCP server (paridade `testarMcpServer` do padrão de mercado).

    Pra http/sse/websocket: GET no URL com timeout 5s, espera 2xx.
    Pra stdio: NÃO testa (spawn arbitrário no container é risco — admin
    valida manualmente no shell). Marca como inactive + mensagem.
    Atualiza status + ultimo_teste_at + ultimo_erro no DB.
    """
    from datetime import datetime, timezone

    import httpx

    pool = await get_pool()
    mcp = await get_mcp_server(pool, empresa_id, mcp_id)
    if mcp is None:
        raise HTTPException(status_code=404, detail="MCP server não encontrado.")

    novo_status = "active"
    erro_msg: str | None = None

    if mcp.tipo_conexao in ("http", "sse", "websocket"):
        if not mcp.url:
            novo_status = "error"
            erro_msg = "URL não configurada."
        else:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(mcp.url)
                    if resp.status_code >= 400:
                        novo_status = "error"
                        erro_msg = f"HTTP {resp.status_code}"
            except Exception as exc:
                novo_status = "error"
                erro_msg = str(exc)[:500]
    else:
        # stdio: não testa por segurança
        novo_status = "inactive"
        erro_msg = "Test stdio não suportado — valide manualmente no shell."

    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE mcp_server SET status = %s, ultimo_teste_at = NOW(), "
            "ultimo_erro = %s, updated_at = NOW() "
            "WHERE empresa_id = %s AND id = %s",
            (novo_status, erro_msg, empresa_id, mcp_id),
        )
        await conn.commit()

    await record_audit(
        pool, empresa_id=empresa_id, user_id=user_id,
        action="mcp_server.test", entity_type="mcp_server",
        entity_id=str(mcp_id),
        payload_diff={"resultado": novo_status, "erro": erro_msg},
        request=request,
    )

    return {
        "ok": novo_status == "active",
        "status": novo_status,
        "erro": erro_msg,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }
