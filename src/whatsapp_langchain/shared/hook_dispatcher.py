"""Dispatcher async de webhooks (M4.d + E1.4).

Fire-and-forget no caller: `dispatch_event` retorna imediatamente após
agendar uma `asyncio.Task` por hook elegível.

Cada task tenta entregar HTTP POST até `HOOK_MAX_ATTEMPTS` vezes com
backoff exponencial (1s, 5s, 25s). Cada tentativa é persistida em
`hook_log` (sucesso ou falha individual). Se TODAS as tentativas
falharem, o evento entra em `hook_dead_letter` pra retry manual via
endpoint admin / UI `/hooks/dead-letter`.

HMAC-SHA256 do body com o `secret` do hook (se houver) vai no header
`X-Webhook-Signature`. Erros de rede/timeout/4xx/5xx nunca levantam pro
caller — só ficam em log + DLQ se aplicável.

Eventos suportados (conjunto fechado pra manter contrato estável):

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
HOOK_MAX_ATTEMPTS = 3
HOOK_BACKOFF_SECONDS = (1.0, 5.0, 25.0)


def _is_success(status_code: int | None, error: str | None) -> bool:
    """Tentativa é sucesso quando não tem error e status_code < 400."""
    if error is not None:
        return False
    if status_code is None:
        return False
    return status_code < 400


def _sign(secret: str, body: bytes) -> str:
    """Assina o body em HMAC-SHA256 hex. Header `X-Webhook-Signature`."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _attempt_post(
    hook: Hook, body: bytes, headers: dict[str, str]
) -> tuple[int | None, str | None, str | None, int]:
    """Faz UMA tentativa HTTP POST. Retorna (status_code, response_body, error, duration_ms).

    `error` é None em sucesso transport-level (mesmo se status >= 400);
    só preenche em timeout/network error/exceção.
    """
    started = time.perf_counter()
    status_code: int | None = None
    response_body: str | None = None
    error: str | None = None

    try:
        async with httpx.AsyncClient(timeout=HOOK_TIMEOUT_SECONDS) as client:
            resp = await client.post(hook.url, content=body, headers=headers)
            status_code = resp.status_code
            # Trunca pra evitar payloads gigantes na auditoria
            response_body = resp.text[:1000] if resp.text else None
    except httpx.TimeoutException:
        error = f"timeout após {HOOK_TIMEOUT_SECONDS}s"
    except httpx.RequestError as e:
        error = f"request error: {type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001 — fire-and-forget defensivo
        error = f"unexpected: {type(e).__name__}: {e}"

    duration_ms = int((time.perf_counter() - started) * 1000)
    return status_code, response_body, error, duration_ms


async def _persist_dead_letter(
    pool: AsyncConnectionPool,
    hook: Hook,
    evento: str,
    payload: dict,
    *,
    attempts: int,
    last_status_code: int | None,
    last_response_body: str | None,
    last_error: str | None,
) -> None:
    """Insere row em hook_dead_letter pra retry manual via endpoint admin."""
    try:
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO hook_dead_letter
                    (empresa_id, hook_id, evento, payload, attempts,
                     last_status_code, last_response_body, last_error)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                """,
                (
                    hook.empresa_id,
                    hook.id,
                    evento,
                    json.dumps(payload),
                    attempts,
                    last_status_code,
                    last_response_body,
                    last_error,
                ),
            )
            await conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.error(
            "hook_dead_letter_persist_failed",
            hook_id=hook.id,
            evento=evento,
            error=str(e),
        )


async def _deliver(
    pool: AsyncConnectionPool, hook: Hook, evento: str, payload: dict
) -> None:
    """Entrega um único hook com retry + DLQ. Nunca propaga exceção.

    Tenta até `HOOK_MAX_ATTEMPTS` vezes com backoff exponencial; cada
    tentativa vira uma row em `hook_log`. Se nenhuma tentativa der
    sucesso (status_code<400 e sem error), insere em `hook_dead_letter`
    pra retry manual.
    """
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": HOOK_USER_AGENT,
        "X-Webhook-Event": evento,
        "X-Webhook-Hook-Id": str(hook.id),
    }
    if hook.secret:
        headers["X-Webhook-Signature"] = _sign(hook.secret, body)

    last_status_code: int | None = None
    last_response_body: str | None = None
    last_error: str | None = None
    attempts_made = 0

    for attempt_idx in range(HOOK_MAX_ATTEMPTS):
        attempts_made = attempt_idx + 1
        status_code, response_body, error, duration_ms = await _attempt_post(
            hook, body, headers
        )
        last_status_code = status_code
        last_response_body = response_body
        last_error = error

        # Persiste cada tentativa em hook_log (audit detalhado).
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
                attempt=attempts_made,
                error=str(e),
            )

        if _is_success(status_code, error):
            logger.info(
                "hook_dispatched",
                hook_id=hook.id,
                evento=evento,
                url=hook.url,
                status_code=status_code,
                attempts=attempts_made,
                duration_ms=duration_ms,
            )
            return

        # Falha nessa tentativa; aguardar backoff antes da próxima (se houver)
        if attempt_idx < HOOK_MAX_ATTEMPTS - 1:
            backoff = HOOK_BACKOFF_SECONDS[attempt_idx]
            logger.info(
                "hook_retry_scheduled",
                hook_id=hook.id,
                evento=evento,
                attempt=attempts_made,
                next_backoff_seconds=backoff,
                status_code=status_code,
                error=error,
            )
            await asyncio.sleep(backoff)

    # Todas as tentativas falharam → DLQ.
    logger.warning(
        "hook_dead_lettered",
        hook_id=hook.id,
        evento=evento,
        url=hook.url,
        attempts=attempts_made,
        last_status_code=last_status_code,
        last_error=last_error,
    )
    await _persist_dead_letter(
        pool,
        hook,
        evento,
        payload,
        attempts=attempts_made,
        last_status_code=last_status_code,
        last_response_body=last_response_body,
        last_error=last_error,
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
