"""Dependency `require_permission` (E2.A RBAC).

Uso:
    from whatsapp_langchain.server.dependencies_rbac import require_permission

    @router.post("/clientes/{id}/anotacao")
    async def post_anotacao(
        id: int,
        _: None = Depends(require_permission("cliente.write")),
    ):
        ...

Resolve user_id via X-User-Id, empresa_id via session/header, lê
permissões efetivas com `shared/perfil.get_user_permissions`. Lança
HTTPException 403 sem o code da permissão exigida.

Decision: dependency factory retorna a função de check, então o caller
escreve `Depends(require_permission("X"))` sem boilerplate. Cache do set
de permissões por request via `request.state` (1 query por request,
mesmo com várias permissões checadas).
"""

from __future__ import annotations

import structlog
from fastapi import Depends, HTTPException, Request

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.perfil import get_user_permissions

logger = structlog.get_logger()


async def _resolve_user_perms(
    request: Request, user_id: str, empresa_id: int
) -> set[str]:
    """Cache por request — get_user_permissions roda uma vez só, mesmo
    com várias `require_permission` no mesmo handler."""
    cached = getattr(request.state, "_user_perms", None)
    if cached is not None:
        return cached
    pool = await get_pool()
    perms = await get_user_permissions(pool, user_id, empresa_id)
    request.state._user_perms = perms
    return perms


def require_permission(codigo: str):
    """Factory de dependency que checa se o user tem `codigo`."""

    async def _checker(
        request: Request,
        user_id: str = Depends(get_user_id_from_request),
        empresa_id: int = Depends(get_empresa_context),
    ) -> None:
        perms = await _resolve_user_perms(request, user_id, empresa_id)
        if codigo not in perms:
            logger.warning(
                "permission_denied",
                user_id=user_id,
                empresa_id=empresa_id,
                required=codigo,
                has_count=len(perms),
            )
            raise HTTPException(
                status_code=403,
                detail=f"Permissão necessária: {codigo}",
            )

    return _checker


def require_agente_access(mode: str = "read"):
    """Sprint C — dependency que aplica ACL granular por agente.

    Aplica APÓS `require_permission('agente.config')` — primeiro empresa
    valida que user tem a perm geral, depois esta checa se o agente
    específico está na whitelist do(s) perfil(is) do user.

    Uso:
        @router.put("/{slug}")
        async def update_agente(
            slug: str,
            _perm: None = Depends(require_permission("agente.config")),
            _acl:  None = Depends(require_agente_access("write")),
        ):
            ...

    Como funciona o slug → agente_id:
        O path param `{slug}` é extraído via `request.path_params`. Lookup
        no DB. Se slug não existe, 404 (não 403 — não vaza ACL).

    Modo compat: agentes sem rows em `agente_perfil` passam (back-compat).
    Quando admin adiciona a 1ª linha pra um agente, vira whitelist
    estrita pra esse agente específico.

    Args:
        mode: 'read' (GET) ou 'write' (POST/PUT/DELETE).
    """
    if mode not in ("read", "write"):
        raise ValueError(f"mode inválido: {mode}")

    async def _checker(
        request: Request,
        user_id: str = Depends(get_user_id_from_request),
        empresa_id: int = Depends(get_empresa_context),
    ) -> None:
        slug = request.path_params.get("slug")
        if not slug:
            # Endpoints sem {slug} (ex: GET /api/v1/agentes lista) não
            # devem usar essa dep — a list_agentes faz filtro próprio.
            raise HTTPException(
                status_code=500,
                detail="require_agente_access requer {slug} no path.",
            )

        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id FROM agente_ia WHERE empresa_id = %s AND slug = %s",
                (empresa_id, slug),
            )
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Agente não encontrado.")
        agente_id = int(row[0])

        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT user_can_access_agente(%s, %s, %s, %s)",
                (user_id, empresa_id, agente_id, mode),
            )
            row = await cur.fetchone()
        allowed = bool(row[0]) if row else False

        if not allowed:
            logger.warning(
                "agente_acl_denied",
                user_id=user_id,
                empresa_id=empresa_id,
                agente_id=agente_id,
                slug=slug,
                mode=mode,
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Sem acesso ao agente '{slug}' "
                    f"(modo {mode}). Solicite ao admin atribuir seu "
                    "perfil em /agents/{slug}/perfis."
                ),
            )

    return _checker
