"""Endpoints de captura server-side via Evolution (Task 5).

Disparados pelo PAINEL (autenticados por `verify_service_token` +
`get_empresa_context`), não pela extensão. A captura de contatos/grupos é
pesada (store da Evolution, fetch de membros por grupo) → roda em background
task e o painel acompanha via `GET /api/captura/lotes/{lote_id}`.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared import captura as cap
from whatsapp_langchain.shared.conexao import get_conexao_by_id
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api", tags=["captura"], dependencies=[Depends(verify_service_token)]
)


class CapturaResponse(BaseModel):
    lote_id: int
    status: str


class PromoverInput(BaseModel):
    contato_ids: list[int] = Field(min_length=1, max_length=5000)


async def _conexao_evolution_ou_404(conexao_id: int, empresa_id: int):
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise HTTPException(404, "Conexão não encontrada")
    if conexao.provider != "evolution":
        raise HTTPException(400, "Captura server-side só suporta conexões Evolution")
    return pool, conexao


@router.post("/conexoes/{conexao_id}/captura/contatos", status_code=202)
async def capturar_contatos(
    conexao_id: int,
    background_tasks: BackgroundTasks,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("disparador.capturar")),
    user_id: str = Depends(get_user_id_from_request),
) -> CapturaResponse:
    """Inicia captura de contatos da instância Evolution (background)."""
    pool, conexao = await _conexao_evolution_ou_404(conexao_id, empresa_id)
    lote_id = await cap.criar_lote(
        pool,
        empresa_id,
        origem="evolution_server",
        tipo="contatos",
        conexao_id=conexao_id,
        user_id=user_id,
    )
    background_tasks.add_task(
        cap.capturar_contatos_evolution, pool, empresa_id, conexao, lote_id
    )
    return CapturaResponse(lote_id=lote_id, status="processando")


@router.post("/conexoes/{conexao_id}/captura/grupos", status_code=202)
async def capturar_grupos(
    conexao_id: int,
    background_tasks: BackgroundTasks,
    com_membros: bool = True,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("disparador.capturar")),
    user_id: str = Depends(get_user_id_from_request),
) -> CapturaResponse:
    """Inicia captura de grupos (e membros) da instância Evolution (background)."""
    pool, conexao = await _conexao_evolution_ou_404(conexao_id, empresa_id)
    lote_id = await cap.criar_lote(
        pool,
        empresa_id,
        origem="evolution_server",
        tipo="grupo_membros" if com_membros else "grupos",
        conexao_id=conexao_id,
        user_id=user_id,
    )
    background_tasks.add_task(
        cap.capturar_grupos_evolution, pool, empresa_id, conexao, lote_id, com_membros
    )
    return CapturaResponse(lote_id=lote_id, status="processando")


@router.get("/captura/lotes/{lote_id}")
async def status_lote(
    lote_id: int, empresa_id: int = Depends(get_empresa_context)
) -> dict:
    """Status + contadores de um lote (polling do painel)."""
    pool = await get_pool()
    lote = await cap.get_lote(pool, empresa_id, lote_id)
    if lote is None:
        raise HTTPException(404, "Lote não encontrado")
    return lote


@router.get("/captura/contatos")
async def listar_contatos(
    limit: int = 1000,
    offset: int = 0,
    q: str | None = None,
    empresa_id: int = Depends(get_empresa_context),
) -> dict:
    """Lista contatos capturados (browser do painel) + totais.

    `total` permite a UI mostrar 'X de N' — antes a lista capava em 200 e dava a
    impressão de que só 200 foram capturados. Teto por página subiu pra 5000.

    `q` (opcional) filtra por nome ou telefone. Parâmetro ADITIVO: quem chama
    sem ele continua recebendo a lista inteira, como antes. Existe porque numa
    base de ~20 mil contatos a única forma de achar alguém era paginar até
    topar com ele — e busca client-side sobre a página carregada acharia 1 em
    cada 99.
    """
    pool = await get_pool()
    items = await cap.listar_contatos(
        pool, empresa_id, limit=min(limit, 5000), offset=offset, q=q
    )
    # O total acompanha o filtro: com busca ativa, "X de N" tem que falar do
    # resultado, senão a paginação oferece páginas vazias.
    totais = await cap.contar_contatos(pool, empresa_id, q=q)
    return {
        "items": items,
        "total": totais["total"],
        "promoviveis": totais["promoviveis"],
        "limit": min(limit, 5000),
        "offset": offset,
    }


@router.get("/captura/grupos")
async def listar_grupos(empresa_id: int = Depends(get_empresa_context)) -> dict:
    """Lista grupos capturados."""
    pool = await get_pool()
    return {"items": await cap.listar_grupos(pool, empresa_id)}


@router.post("/captura/promover")
async def promover(
    body: PromoverInput, empresa_id: int = Depends(get_empresa_context)
) -> dict:
    """Promove contatos do staging para o CRM `cliente` (só os com telefone)."""
    pool = await get_pool()
    promovidos = await cap.promover_contatos(pool, empresa_id, body.contato_ids)
    return {"promovidos": promovidos}


@router.post("/captura/promover-todos")
async def promover_todos(empresa_id: int = Depends(get_empresa_context)) -> dict:
    """Promove TODOS os contatos elegíveis (com telefone, não promovidos) ao CRM.

    Server-side — não depende da lista carregada na UI (que era capada). Resolve
    o caso 'só 200 viraram cliente'."""
    pool = await get_pool()
    promovidos = await cap.promover_todos_contatos(pool, empresa_id)
    return {"promovidos": promovidos}


@router.post("/captura/despromover")
async def despromover(
    body: PromoverInput,
    empresa_id: int = Depends(get_empresa_context),
    _perm: None = Depends(require_permission("cliente.delete")),
) -> dict:
    """Remove contatos do CRM (desfaz a promoção).

    Desvincula do staging e apaga o `cliente` quando não há atendimento
    (preserva histórico — clientes com conversa são só desvinculados).
    """
    pool = await get_pool()
    return await cap.despromover_contatos(pool, empresa_id, body.contato_ids)
