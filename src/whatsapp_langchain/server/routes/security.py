"""Endpoints de segurança / audit (E1.8).

Hoje contém:
- GET /api/security/login-events — histórico de tentativas de login
  (success, failed, blocked, logout, password_*) com IP e user-agent.

Acesso restrito: superadmin OU admin da empresa do user-alvo.
Sem filtro de empresa (auth_login_event não tem empresa_id — login
acontece antes da seleção de empresa), então o filtro é por user_id ou
email; admin global vê tudo.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from whatsapp_langchain.server.dependencies import (
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_superadmin

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/security",
    tags=["security"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("/login-events")
async def list_login_events(
    user_id: str | None = Query(default=None, description="Filtra por user_id"),
    email: str | None = Query(default=None, description="Filtra por email"),
    event_type: str | None = Query(
        default=None, description="login_success|login_failed|..."
    ),
    limit: int = Query(default=100, ge=1, le=500),
    requester_user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Lista eventos de auth ordenados por data desc.

    Sem filtro: superadmin vê tudo. Não-superadmin precisa filtrar por
    user_id próprio (ver own history em `/profile/sessions`).
    """
    pool = await get_pool()
    is_super = await is_superadmin(pool, requester_user_id)

    if not is_super:
        # Non-superadmin só pode ver próprio histórico
        if user_id and user_id != requester_user_id:
            raise HTTPException(
                status_code=403,
                detail="Você só pode ver o próprio histórico de login.",
            )
        if email is not None:
            raise HTTPException(
                status_code=403,
                detail="Filtro por email é restrito a superadmin.",
            )
        # Força filtro pra próprio user
        user_id = requester_user_id

    where: list[str] = []
    params: list = []
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)
    if email:
        where.append("email = %s")
        params.append(email)
    if event_type:
        where.append("event_type = %s")
        params.append(event_type)
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    params.append(limit)

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT id, user_id, email, event_type, ip_address,
                   user_agent, reason, metadata, created_at
              FROM auth_login_event
              {where_clause}
             ORDER BY created_at DESC, id DESC
             LIMIT %s
            """,
            params,
        )
        rows = await cur.fetchall()

    return {
        "events": [
            {
                "id": r[0],
                "user_id": r[1],
                "email": r[2],
                "event_type": r[3],
                "ip_address": r[4],
                "user_agent": r[5],
                "reason": r[6],
                "metadata": r[7],
                "created_at": r[8].isoformat() if r[8] else None,
            }
            for r in rows
        ]
    }
