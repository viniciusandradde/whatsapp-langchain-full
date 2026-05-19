"""Routes admin pra configurar integração Wareline ConecteHub.

Endpoints (perm `integracao.wareline.manage` — Admin/Gestor):
- GET    /api/integracoes/wareline           — config atual (sem senha/secret)
- PUT    /api/integracoes/wareline           — UPSERT credenciais (cripto antes)
- POST   /api/integracoes/wareline/testar    — faz OAuth + busca CPF dummy
- DELETE /api/integracoes/wareline           — remove credenciais + token cache
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from whatsapp_langchain.integrations.wareline import WarelineError
from whatsapp_langchain.integrations.wareline.client import WarelineClient
from whatsapp_langchain.integrations.wareline.credentials import (
    delete_credentials,
    get_credentials_safe_view,
    record_test_result,
    save_credentials,
    update_credentials_partial,
)
from whatsapp_langchain.integrations.wareline.errors import (
    WarelineConfigError,
)
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
    prefix="/api/integracoes/wareline",
    tags=["integracoes"],
    dependencies=[Depends(verify_service_token)],
)


def _check_encryption_key_configured() -> None:
    """Falha cedo (503) se WARELINE_ENCRYPTION_KEY ausente."""
    if settings.wareline_encryption_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Integração Wareline desabilitada — "
                "WARELINE_ENCRYPTION_KEY não configurada no servidor."
            ),
        )


class CredentialsPutInput(BaseModel):
    """Body pro PUT. Senha/secret em branco = mantém valor anterior."""

    username: str | None = Field(default=None, min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=1, max_length=500)
    client_id: str | None = Field(default=None, min_length=1, max_length=200)
    client_secret: str | None = Field(default=None, min_length=1, max_length=500)
    base_url: str | None = Field(default=None, max_length=300)
    pacientes_base_url: str | None = Field(default=None, max_length=300)
    ativo: bool | None = None


@router.get("")
async def get_wareline_config(
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("integracao.wareline.manage")),
) -> dict:
    """Retorna config (sem campos sensíveis). 404 se não cadastrada."""
    _check_encryption_key_configured()
    pool = await get_pool()
    config = await get_credentials_safe_view(pool, empresa_id)
    if config is None:
        raise HTTPException(
            status_code=404, detail="Integração Wareline ainda não configurada."
        )
    return config


@router.put("")
async def put_wareline_config(
    payload: CredentialsPutInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("integracao.wareline.manage")),
) -> dict:
    """UPSERT credenciais. Primeira chamada exige todos os campos;
    chamadas posteriores podem omitir password/client_secret pra preservar."""
    _check_encryption_key_configured()
    pool = await get_pool()
    existing = await get_credentials_safe_view(pool, empresa_id)

    if existing is None:
        # Primeira config — todos os campos obrigatórios
        missing = [
            f
            for f, v in [
                ("username", payload.username),
                ("password", payload.password),
                ("client_id", payload.client_id),
                ("client_secret", payload.client_secret),
            ]
            if not v
        ]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Primeira configuração exige todos os campos. "
                    f"Faltando: {', '.join(missing)}"
                ),
            )
        return await save_credentials(
            pool,
            empresa_id=empresa_id,
            username=payload.username,  # type: ignore[arg-type]
            password=payload.password,  # type: ignore[arg-type]
            client_id=payload.client_id,  # type: ignore[arg-type]
            client_secret=payload.client_secret,  # type: ignore[arg-type]
            base_url=payload.base_url,
            pacientes_base_url=payload.pacientes_base_url,
            ativo=payload.ativo if payload.ativo is not None else True,
            created_by_user_id=user_id,
        )

    # Update parcial — só campos não-None entram
    updated = await update_credentials_partial(
        pool,
        empresa_id=empresa_id,
        username=payload.username,
        password=payload.password,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        base_url=payload.base_url,
        pacientes_base_url=payload.pacientes_base_url,
        ativo=payload.ativo,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Config sumiu durante o UPDATE")
    logger.info(
        "wareline_config_updated",
        empresa_id=empresa_id,
        actor_user_id=user_id,
    )
    return updated


@router.post("/testar")
async def testar_wareline(
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("integracao.wareline.manage")),
) -> dict:
    """Faz OAuth + busca paciente de teste (CPF dummy do staging).

    Atualiza `ultimo_teste_*` no DB. Retorna `{ok, mensagem}`.
    """
    _check_encryption_key_configured()
    pool = await get_pool()
    client = WarelineClient(pool, empresa_id=empresa_id)
    try:
        # Busca CPF dummy da doc Wareline. Em staging retorna paciente
        # fictício; em prod, se for CPF inválido vira NotFound mas o OAuth
        # já valida que credenciais estão certas.
        try:
            pacientes = await client.buscar_paciente("11111111111")
            mensagem = (
                f"Conectado. Paciente teste retornado: "
                f"{pacientes[0].nome if pacientes else '(vazio)'}"
            )
        except WarelineError as exc:
            # NotFound em prod pra esse CPF é esperado — significa que
            # OAuth funcionou mas paciente não existe
            from whatsapp_langchain.integrations.wareline.errors import (
                WarelineNotFoundError,
            )

            if isinstance(exc, WarelineNotFoundError):
                mensagem = (
                    "Conectado. (OAuth OK — CPF de teste não cadastrado, "
                    "o que é esperado em prod.)"
                )
            else:
                raise
        await record_test_result(
            pool, empresa_id=empresa_id, ok=True, mensagem=None
        )
        return {"ok": True, "mensagem": mensagem}
    except WarelineConfigError as exc:
        msg = str(exc)
        await record_test_result(
            pool, empresa_id=empresa_id, ok=False, mensagem=msg
        )
        return {"ok": False, "mensagem": msg}
    except WarelineError as exc:
        msg = str(exc)
        logger.warning(
            "wareline_test_failed", empresa_id=empresa_id, error=msg
        )
        await record_test_result(
            pool, empresa_id=empresa_id, ok=False, mensagem=msg
        )
        return {"ok": False, "mensagem": msg}


@router.delete("")
async def delete_wareline_config(
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("integracao.wareline.manage")),
) -> dict:
    """Remove credenciais + cache token (cascade)."""
    _check_encryption_key_configured()
    pool = await get_pool()
    deleted = await delete_credentials(pool, empresa_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail="Integração Wareline não configurada."
        )
    logger.info(
        "wareline_config_deleted",
        empresa_id=empresa_id,
        actor_user_id=user_id,
    )
    return {"ok": True}
