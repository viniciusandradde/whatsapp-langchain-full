"""Saúde das conexões dos clientes (mig 196) — leitura para o painel.

`GET /api/monitor/conexoes` é recurso de PLATAFORMA (superadmin, bypass de
RLS): todas as conexões de todos os clientes com estado, última mensagem
recebida, recebidas × esperadas nas últimas 24 h e os episódios ativos.
`GET /api/monitor/banner` é por empresa: as conexões que o cliente precisa
reconectar, para o banner do AppShell. Quem escreve é o tick do worker
(`shared/saude_conexoes.py`); aqui não se chama a Evolution.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_superadmin
from whatsapp_langchain.shared.rls_context import empresa_scope
from whatsapp_langchain.shared.saude_conexoes import banner_da_empresa, montar_painel

router = APIRouter(
    prefix="/api/monitor",
    tags=["monitor"],
    dependencies=[Depends(verify_service_token)],
)


async def _exigir_superadmin(user_id: str) -> None:
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        raise HTTPException(status_code=403, detail="Apenas superadmins.")


@router.get("/conexoes")
async def listar_conexoes_endpoint(
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Todas as conexões monitoradas + estado do tick + resolvidos das últimas 48 h."""
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    with empresa_scope(None, bypass=True):
        return await montar_painel(pool)


@router.get("/banner")
async def banner_endpoint(
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Conexões da empresa ativa que estão caídas (para o banner do painel)."""
    pool = await get_pool()
    return await banner_da_empresa(pool, empresa_id)
