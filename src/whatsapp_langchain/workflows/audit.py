"""Audit log de eventos do workflow (mig 078).

API mínima:
    await log_event(pool, atend_id=..., empresa_id=..., node_id=...,
                    evento="entered", payload={...})

Best-effort: falha não bloqueia o workflow.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def log_event(
    pool: Any,
    *,
    atendimento_id: int,
    empresa_id: int,
    node_id: str,
    evento: str,
    workflow_version_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Persiste 1 row em `workflow_evento`. Silencioso em caso de erro."""
    try:
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO workflow_evento
                    (workflow_version_id, atendimento_id, empresa_id,
                     node_id, evento, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    workflow_version_id,
                    atendimento_id,
                    empresa_id,
                    node_id,
                    evento,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
            await conn.commit()
    except Exception as exc:  # noqa: BLE001 — audit é best-effort
        logger.warning(
            "workflow_event_log_failed atendimento_id=%s node=%s evento=%s error=%s",
            atendimento_id,
            node_id,
            evento,
            exc,
        )
