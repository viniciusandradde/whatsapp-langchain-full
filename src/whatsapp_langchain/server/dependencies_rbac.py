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
