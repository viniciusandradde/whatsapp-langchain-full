"""Dispatcher async de webhooks (M4.d).

Fire-and-forget: chamadas de `dispatch_event` retornam imediatamente.
Cada hook elegível é entregue em uma `asyncio.Task` separada que faz
HTTP POST com timeout de 10s, calcula HMAC-SHA256 do body com o `secret`
do hook (se houver), e persiste o resultado em `hook_log` (sucesso ou
erro). Erros de rede/timeout não levantam — só ficam logados.

Os eventos são intencionalmente um conjunto pequeno e fechado pra
manter o contrato estável:

    mensagem.recebida       — payload: {atendimento_id, cliente_id, body, ...}
    atendimento.aberto      — payload: {atendimento_id, cliente_id, conexao_id, ...}
    atendimento.atendido    — payload: {atendimento_id, assigned_to_user_id}
    atendimento.fechado     — payload: {atendimento_id, status, closed_at}
    atendimento.transferido — payload: {atendimento_id, from_user, to_user}
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time

import httpx
import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.hook import insert_log, list_hooks_for_dispatch
from whatsapp_langchain.shared.models import Hook

logger = structlog.get_logger()


HOOK_TIMEOUT_SECONDS = 10.0
HOOK_USER_AGENT = "NexusChatAI-Webhook/1.0"


def _sign(secret: str, body: bytes) -> str:
    """Assina o body em HMAC-SHA256 hex. Header `X-Webhook-Signature`."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _deliver(
    pool: AsyncConnectionPool, hook: Hook, evento: str, payload: dict
) -> None:
    """Entrega um único hook + grava hook_log. Nunca propaga exceção."""
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": HOOK_USER_AGENT,
        "X-Webhook-Event": evento,
        "X-Webhook-Hook-Id": str(hook.id),
    }
    if hook.secret:
        headers["X-Webhook-Signature"] = _sign(hook.secret, body)

    started = time.perf_counter()
    status_code: int | None = None
    response_body: str | None = None
    error: str | None = None

    try:
        async with httpx.AsyncClient(timeout=HOOK_TIMEOUT_SECONDS) as client:
            resp = await client.post(hook.url, content=body, headers=headers)
            status_code = resp.status_code
            # Limita o que persistimos pra evitar payloads gigantes na auditoria.
            response_body = resp.text[:1000] if resp.text else None
    except httpx.TimeoutException:
        error = f"timeout após {HOOK_TIMEOUT_SECONDS}s"
    except httpx.RequestError as e:
        error = f"request error: {type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001 — fire-and-forget defensivo
        error = f"unexpected: {type(e).__name__}: {e}"

    duration_ms = int((time.perf_counter() - started) * 1000)
    try:
        await insert_log(
            pool,
            hook.id,
            evento,
            payload,
            status_code=status_code,
            response_body=response_body,
            error=error,
            duration_ms=duration_ms,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(
            "hook_log_persist_failed",
            hook_id=hook.id,
            evento=evento,
            error=str(e),
        )

    log_fn = (
        logger.info if error is None and (status_code or 0) < 400 else logger.warning
    )
    log_fn(
        "hook_dispatched",
        hook_id=hook.id,
        evento=evento,
        url=hook.url,
        status_code=status_code,
        error=error,
        duration_ms=duration_ms,
    )


async def dispatch_event(
    pool: AsyncConnectionPool, empresa_id: int, evento: str, payload: dict
) -> None:
    """Resolve hooks ativos da empresa pro evento e dispara em paralelo.

    Fire-and-forget: cria as tasks com `asyncio.create_task` e retorna —
    o caller não bloqueia esperando a entrega. Falhas individuais não
    interrompem outros hooks; tudo fica em `hook_log`.
    """
    try:
        hooks = await list_hooks_for_dispatch(pool, empresa_id, evento)
    except Exception as e:  # noqa: BLE001 — robusto contra DB transitório
        logger.error(
            "hook_lookup_failed",
            empresa_id=empresa_id,
            evento=evento,
            error=str(e),
        )
        return

    if not hooks:
        return

    for h in hooks:
        # create_task evita bloquear o caller. As tarefas vivem dentro do
        # event loop até terminarem; se o processo cair antes, a entrega
        # é perdida — esperado num MVP fire-and-forget.
        asyncio.create_task(_deliver(pool, h, evento, payload))
