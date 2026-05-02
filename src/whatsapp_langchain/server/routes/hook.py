"""CRUD de Webhooks (M4.d).

Endpoints escopados pela empresa ativa. Eventos válidos são checados em
`EVENTOS_VALIDOS` (mesma lista do CHECK constraint da tabela). Logs por
hook em `GET /{id}/logs` retornam as últimas tentativas (max 200).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.hook import (
    EVENTOS_VALIDOS,
    create_hook,
    delete_hook,
    get_hook_by_id,
    list_hooks,
    list_logs,
    update_hook,
)
from whatsapp_langchain.shared.models import Hook, HookInput, HookLog

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/hooks",
    tags=["hooks"],
    dependencies=[Depends(verify_service_token)],
)


def _validate_evento(evento: str) -> None:
    if evento not in EVENTOS_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Evento inválido: '{evento}'. Aceitos: "
                + ", ".join(sorted(EVENTOS_VALIDOS))
            ),
        )


@router.get("")
async def list_my_hooks(
    evento: str | None = Query(default=None),
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[Hook]]:
    if evento:
        _validate_evento(evento)
    pool = await get_pool()
    rows = await list_hooks(pool, empresa_id, evento=evento)
    return {"hooks": rows}


@router.get("/eventos")
async def list_eventos() -> dict[str, list[str]]:
    """Eventos válidos — útil pro dropdown da UI."""
    return {"eventos": sorted(EVENTOS_VALIDOS)}


async def _load_hook_in_empresa(hook_id: int, empresa_id: int) -> Hook:
    pool = await get_pool()
    h = await get_hook_by_id(pool, hook_id)
    if h is None:
        raise HTTPException(status_code=404, detail="Hook não encontrado.")
    if h.empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="Hook fora da empresa ativa.")
    return h


@router.post("", status_code=201)
async def create(
    body: HookInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Hook:
    _validate_evento(body.evento)
    pool = await get_pool()
    out = await create_hook(pool, empresa_id, body, user_id=user_id)
    logger.info(
        "hook_created",
        empresa_id=empresa_id,
        hook_id=out.id,
        evento=out.evento,
        url=out.url,
        user_id=user_id,
    )
    return out


@router.put("/{hook_id}")
async def update(
    hook_id: int,
    body: HookInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Hook:
    await _load_hook_in_empresa(hook_id, empresa_id)
    _validate_evento(body.evento)
    pool = await get_pool()
    out = await update_hook(pool, hook_id, body)
    if out is None:
        raise HTTPException(status_code=404, detail="Hook não encontrado.")
    logger.info(
        "hook_updated",
        empresa_id=empresa_id,
        hook_id=hook_id,
        evento=out.evento,
        user_id=user_id,
    )
    return out


@router.delete("/{hook_id}", status_code=204)
async def delete(
    hook_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    await _load_hook_in_empresa(hook_id, empresa_id)
    pool = await get_pool()
    await delete_hook(pool, hook_id)
    logger.info(
        "hook_deleted",
        empresa_id=empresa_id,
        hook_id=hook_id,
        user_id=user_id,
    )


@router.get("/{hook_id}/logs")
async def read_logs(
    hook_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[HookLog]]:
    """Últimas N tentativas de entrega do hook (200=ok, 4xx/5xx=erro)."""
    await _load_hook_in_empresa(hook_id, empresa_id)
    pool = await get_pool()
    logs = await list_logs(pool, hook_id, limit=limit)
    return {"logs": logs}
