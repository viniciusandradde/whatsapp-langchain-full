"""Audit log centralizado (Fase 0.1).

Substitui logs pontuais por sistema único e queryable. Toda mutation
sensível chama `record_audit()` ou usa `@audited(...)` decorator.

Padrão de uso:

    from whatsapp_langchain.shared.audit import record_audit

    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="cliente.update",
        entity_type="cliente",
        entity_id=str(cliente.id),
        payload_diff={"before": old_data, "after": new_data},
        request=request,  # opcional — extrai IP/UA/request_id
    )

Decorator pra endpoints CRUD repetitivos:

    from whatsapp_langchain.shared.audit import audited

    @router.put("/{id}")
    @audited("cliente.update", entity_type="cliente")
    async def update_cliente(id: int, body: ..., ...):
        ...

O decorator extrai `entity_id` do path param (heurística: 1º argumento
inteiro) e calcula diff via comparação de retornos antes/depois.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import Request
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


async def record_audit(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    payload_diff: dict[str, Any] | None = None,
    request: Request | None = None,
) -> int:
    """Registra audit row. Retorna id da row gravada.

    Falha NÃO bloqueia operação principal — log warn + continua. Audit
    perdido é melhor que feature quebrada.
    """
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    if request is not None:
        ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        request_id = request.headers.get("x-request-id")

    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO audit_log
                    (empresa_id, user_id, action, entity_type, entity_id,
                     payload_diff, ip, user_agent, request_id)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                RETURNING id
                """,
                (
                    empresa_id,
                    user_id,
                    action,
                    entity_type,
                    entity_id,
                    json.dumps(payload_diff or {}),
                    ip,
                    user_agent,
                    request_id,
                ),
            )
            row = await cur.fetchone()
            await conn.commit()
            assert row is not None
            return row[0]
    except Exception as e:  # noqa: BLE001 — audit nunca quebra fluxo principal
        logger.warning(
            "audit_record_failed",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            error=str(e),
        )
        return -1


async def list_audit(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    user_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Lista audit rows com filtros opcionais — usado pelo painel admin."""
    where = ["empresa_id = %s"]
    params: list[Any] = [empresa_id]
    if entity_type:
        where.append("entity_type = %s")
        params.append(entity_type)
    if entity_id:
        where.append("entity_id = %s")
        params.append(entity_id)
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)
    if action:
        where.append("action = %s")
        params.append(action)
    params.extend([limit, offset])

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT id, empresa_id, user_id, action, entity_type, entity_id,
                   payload_diff, ip, user_agent, request_id, at
              FROM audit_log
             WHERE {' AND '.join(where)}
             ORDER BY at DESC
             LIMIT %s OFFSET %s
            """,
            tuple(params),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "empresa_id": r[1],
            "user_id": r[2],
            "action": r[3],
            "entity_type": r[4],
            "entity_id": r[5],
            "payload_diff": r[6],
            "ip": r[7],
            "user_agent": r[8],
            "request_id": r[9],
            "at": r[10].isoformat() if r[10] else None,
        }
        for r in rows
    ]


def diff_dicts(before: dict | None, after: dict | None) -> dict:
    """Calcula diff útil pra audit — só campos que mudaram.

    Retorna { "before": {field: oldval}, "after": {field: newval} } só
    com chaves alteradas. Reduz volume na DB e facilita revisão.
    """
    before = before or {}
    after = after or {}
    changed_before: dict = {}
    changed_after: dict = {}
    all_keys = set(before.keys()) | set(after.keys())
    for k in all_keys:
        b = before.get(k)
        a = after.get(k)
        if b != a:
            changed_before[k] = b
            changed_after[k] = a
    return {"before": changed_before, "after": changed_after}
