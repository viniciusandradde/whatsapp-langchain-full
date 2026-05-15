"""Audit trail especializado de governança (RBAC, members, departamentos).

Esta módulo é separado do `audit.py` genérico porque governança tem
campos extras (actor + target) e uma view própria no painel
(`/settings/security/governanca`).

Uso típico:

    from whatsapp_langchain.shared.audit_governanca import record_audit_governanca

    await record_audit_governanca(
        pool,
        empresa_id=empresa_id,
        actor_user_id=current_user_id,
        target_user_id=member_user_id,
        action="perfil.sync",
        entity_type="usuario_perfil",
        entity_id=str(member_user_id),
        payload_before={"perfil_ids": [1, 2]},
        payload_after={"perfil_ids": [1, 3, 5]},
        request=request,  # FastAPI Request — opcional, pra IP/UA/request_id
    )

Best-effort: erros aqui NÃO devem bloquear a operação principal.
Caller deve envelopar com try/except quando o audit falhar (ex: tabela
ainda não migrada em ambiente novo).
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import Request
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


# Whitelist de actions válidas — evita typos virarem rows aleatórias.
VALID_ACTIONS = frozenset(
    {
        "perfil.sync",  # PUT /members/{id}/perfis (substitui set inteiro)
        "depto.sync",  # PUT /members/{id}/departamentos
        "role.change",  # PUT /members/{id}/role (legacy)
        "superadmin.grant",
        "superadmin.revoke",
        "member.add",
        "member.remove",
        "member.disable",
        "member.enable",
    }
)


async def record_audit_governanca(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    actor_user_id: str,
    action: str,
    target_user_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload_before: dict | list | None = None,
    payload_after: dict | list | None = None,
    request: Request | None = None,
) -> int | None:
    """Insere row em audit_governanca. Best-effort: nunca raise.

    Returns:
        id do row inserido, ou None se falhou.
    """
    if action not in VALID_ACTIONS:
        logger.warning("audit_governanca_invalid_action", action=action)
        # ainda grava (com warning), pra não perder evento por typo

    request_id = None
    ip = None
    ua = None
    if request is not None:
        # request_id middleware adiciona em state.request_id (correlation_id.py)
        request_id = getattr(request.state, "request_id", None) or request.headers.get(
            "x-request-id"
        )
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")

    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO audit_governanca
                    (empresa_id, actor_user_id, target_user_id, action,
                     entity_type, entity_id,
                     payload_before, payload_after,
                     request_id, ip_address, user_agent)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                RETURNING id
                """,
                (
                    empresa_id,
                    actor_user_id,
                    target_user_id,
                    action,
                    entity_type,
                    entity_id,
                    json.dumps(payload_before, ensure_ascii=False)
                    if payload_before is not None
                    else None,
                    json.dumps(payload_after, ensure_ascii=False)
                    if payload_after is not None
                    else None,
                    request_id,
                    ip,
                    ua,
                ),
            )
            row = await cur.fetchone()
            await conn.commit()
        return int(row[0]) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "audit_governanca_insert_failed",
            empresa_id=empresa_id,
            action=action,
            target=target_user_id,
            error=str(exc),
        )
        return None


async def list_audit_governanca(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    actor_user_id: str | None = None,
    target_user_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Lista eventos com filtros opcionais. Mais recentes primeiro."""
    conds = ["empresa_id = %s"]
    params: list[Any] = [empresa_id]
    if actor_user_id:
        conds.append("actor_user_id = %s")
        params.append(actor_user_id)
    if target_user_id:
        conds.append("target_user_id = %s")
        params.append(target_user_id)
    if action:
        conds.append("action = %s")
        params.append(action)
    where = " AND ".join(conds)
    params.extend([limit, offset])

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT id, empresa_id, actor_user_id, target_user_id, action,
                   entity_type, entity_id, payload_before, payload_after,
                   request_id, ip_address, user_agent, created_at
              FROM audit_governanca
             WHERE {where}
             ORDER BY created_at DESC, id DESC
             LIMIT %s OFFSET %s
            """,
            tuple(params),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "empresa_id": r[1],
            "actor_user_id": r[2],
            "target_user_id": r[3],
            "action": r[4],
            "entity_type": r[5],
            "entity_id": r[6],
            "payload_before": r[7],
            "payload_after": r[8],
            "request_id": r[9],
            "ip_address": r[10],
            "user_agent": r[11],
            "created_at": r[12].isoformat() if r[12] else None,
        }
        for r in rows
    ]
