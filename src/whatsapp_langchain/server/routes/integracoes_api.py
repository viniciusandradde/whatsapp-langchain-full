"""Routes do módulo Integrações (conexões de API genéricas).

Endpoints (perm `integracao.manage`):
- GET    /api/integracoes/providers         — catálogo Python (read-only)
- GET    /api/integracoes                    — lista conexões da empresa
- GET    /api/integracoes/{id}              — detalhe (creds mascarados)
- POST   /api/integracoes                    — cria nova conexão
- PATCH  /api/integracoes/{id}              — UPDATE parcial
- POST   /api/integracoes/{id}/testar       — handler de teste do provider
- DELETE /api/integracoes/{id}              — remove
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from whatsapp_langchain.integrations.api_connection import (
    create_conexao,
    delete_conexao,
    get_conexao_safe,
    list_conexoes,
    record_test_result,
    update_conexao,
)
from whatsapp_langchain.integrations.crypto import IntegracaoConfigError
from whatsapp_langchain.integrations.providers import (
    PROVIDERS,
    list_providers,
)
from whatsapp_langchain.integrations.test_handlers import run_test
from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/integracoes",
    tags=["integracoes"],
    dependencies=[Depends(verify_service_token)],
)


def _check_encryption_key() -> None:
    if settings.wareline_encryption_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Módulo Integrações desabilitado — "
                "WARELINE_ENCRYPTION_KEY não configurada no servidor."
            ),
        )


# --- Modelos input ---


class CreateConexaoInput(BaseModel):
    provider_slug: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=80)
    credentials: dict = Field(default_factory=dict)
    base_url: str | None = Field(default=None, max_length=300)
    extra_config: dict | None = None
    ativo: bool = True


class UpdateConexaoInput(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    base_url: str | None = Field(default=None, max_length=300)
    credentials_patch: dict | None = None
    extra_config: dict | None = None
    ativo: bool | None = None


# --- Endpoints ---


@router.get("/providers")
async def list_providers_endpoint(
    include_legacy: bool = True,
    _: None = Depends(require_permission("integracao.manage")),
) -> dict:
    """Catálogo de providers conhecidos. Read-only — definido em código."""
    providers = list_providers(include_legacy=include_legacy)
    return {
        "items": [p.model_dump() for p in providers],
    }


@router.get("")
async def list_conexoes_endpoint(
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("integracao.manage")),
) -> dict:
    """Lista conexões cadastradas da empresa (sem credenciais)."""
    _check_encryption_key()
    pool = await get_pool()
    items = await list_conexoes(pool, empresa_id=empresa_id)
    return {"items": items}


@router.get("/{connection_id}")
async def get_conexao_endpoint(
    connection_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("integracao.manage")),
) -> dict:
    """Detalhe (credenciais sensíveis mascaradas com ••••••••)."""
    _check_encryption_key()
    pool = await get_pool()
    config = await get_conexao_safe(
        pool, connection_id=connection_id, empresa_id=empresa_id
    )
    if config is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    return config


@router.post("", status_code=201)
async def create_conexao_endpoint(
    payload: CreateConexaoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("integracao.manage")),
) -> dict:
    """Cria conexão. Valida schema do provider antes de salvar."""
    _check_encryption_key()
    if payload.provider_slug not in PROVIDERS:
        raise HTTPException(
            status_code=404, detail=f"Provider '{payload.provider_slug}' desconhecido."
        )
    pool = await get_pool()
    try:
        return await create_conexao(
            pool,
            empresa_id=empresa_id,
            provider_slug=payload.provider_slug,
            label=payload.label.strip(),
            credentials=payload.credentials,
            base_url=payload.base_url,
            extra_config=payload.extra_config,
            ativo=payload.ativo,
            created_by_user_id=user_id,
        )
    except IntegracaoConfigError as exc:
        msg = str(exc)
        if "já existe" in msg.lower():
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc


@router.patch("/{connection_id}")
async def update_conexao_endpoint(
    connection_id: int,
    payload: UpdateConexaoInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("integracao.manage")),
) -> dict:
    """UPDATE parcial. credentials_patch é mesclado (campos vazios mantêm)."""
    _check_encryption_key()
    pool = await get_pool()
    try:
        result = await update_conexao(
            pool,
            connection_id=connection_id,
            empresa_id=empresa_id,
            label=payload.label.strip() if payload.label else None,
            base_url=payload.base_url,
            credentials_patch=payload.credentials_patch,
            extra_config=payload.extra_config,
            ativo=payload.ativo,
        )
    except IntegracaoConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    return result


@router.post("/{connection_id}/testar")
async def testar_conexao_endpoint(
    connection_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("integracao.manage")),
) -> dict:
    """Roteia pro handler do provider e atualiza ultimo_teste_*."""
    _check_encryption_key()
    pool = await get_pool()
    conf = await get_conexao_safe(
        pool, connection_id=connection_id, empresa_id=empresa_id
    )
    if conf is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    ok, mensagem = await run_test(
        pool, connection_id=connection_id, empresa_id=empresa_id
    )
    await record_test_result(
        pool, connection_id=connection_id, ok=ok, mensagem=mensagem if not ok else None
    )
    return {"ok": ok, "mensagem": mensagem}


@router.delete("/{connection_id}")
async def delete_conexao_endpoint(
    connection_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("integracao.manage")),
) -> dict:
    """Hard delete + CASCADE no token cache."""
    _check_encryption_key()
    pool = await get_pool()
    ok = await delete_conexao(
        pool, connection_id=connection_id, empresa_id=empresa_id
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    return {"ok": True}
