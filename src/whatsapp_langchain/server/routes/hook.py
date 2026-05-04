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
    get_dead_letter,
    get_hook_by_id,
    list_dead_letter,
    list_hooks,
    list_logs,
    update_dead_letter_status,
    update_hook,
)
from whatsapp_langchain.shared.hook_dispatcher import dispatch_event
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


# ---------------------------------------------------------------------------
# Dead Letter Queue (E1.4)
# ---------------------------------------------------------------------------


@router.get("/dead-letter")
async def list_dlq(
    status: str | None = Query(default="pending"),
    limit: int = Query(default=100, ge=1, le=500),
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[dict]]:
    """Lista entradas DLQ da empresa.

    `status` aceita pending|retrying|done|archived. None retorna todos.
    """
    pool = await get_pool()
    try:
        items = await list_dead_letter(
            pool, empresa_id, status=status, limit=limit
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"items": items}


@router.post("/dead-letter/{dlq_id}/retry", status_code=202)
async def retry_dlq(
    dlq_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Reagenda entrega do hook da DLQ entry.

    Marca a row como `retrying` e dispara `dispatch_event` de novo.
    Se a nova tentativa falhar, vira nova entry DLQ separada (a antiga
    permanece com status retrying pra evidência). Operador deve `archive`
    pra limpar quando ok.
    """
    pool = await get_pool()
    item = await get_dead_letter(pool, dlq_id, empresa_id)
    if item is None:
        raise HTTPException(status_code=404, detail="DLQ entry não encontrada.")
    if item["status"] not in ("pending", "retrying"):
        raise HTTPException(
            status_code=409,
            detail=f"DLQ entry com status {item['status']!r} não pode ser retentada.",
        )

    await update_dead_letter_status(
        pool, dlq_id, empresa_id, status="retrying", bump_retry_at=True
    )

    # Dispatch fire-and-forget — usa o pipeline normal (com retry+DLQ),
    # então se a nova tentativa esgotar de novo, vira NOVA row DLQ.
    await dispatch_event(pool, empresa_id, item["evento"], item["payload"])

    logger.info(
        "hook_dlq_retry_triggered",
        empresa_id=empresa_id,
        dlq_id=dlq_id,
        hook_id=item["hook_id"],
        evento=item["evento"],
        user_id=user_id,
    )
    return {"status": "retrying"}


@router.post("/dead-letter/{dlq_id}/archive", status_code=200)
async def archive_dlq(
    dlq_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Marca DLQ entry como `archived` (operador decidiu ignorar)."""
    pool = await get_pool()
    item = await get_dead_letter(pool, dlq_id, empresa_id)
    if item is None:
        raise HTTPException(status_code=404, detail="DLQ entry não encontrada.")

    affected = await update_dead_letter_status(
        pool, dlq_id, empresa_id, status="archived"
    )
    if not affected:
        raise HTTPException(status_code=404, detail="DLQ entry não encontrada.")

    logger.info(
        "hook_dlq_archived",
        empresa_id=empresa_id,
        dlq_id=dlq_id,
        user_id=user_id,
    )
    return {"status": "archived"}
