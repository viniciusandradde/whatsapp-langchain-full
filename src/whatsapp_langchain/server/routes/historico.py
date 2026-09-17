"""Histórico de Atendimentos — `/api/historico` (módulo Conversas).

Consulta de atendimentos sobre TODOS os status (resolvido/abandonado inclusos)
com período + filtros + paginação + ordenação + busca full-text, detalhe
agregado e exportação CSV/XLSX. Substitui a aba legada "Conversas".

RBAC: reusa `atendimento.read` (.own/.all). Escopo `.own` filtra por
departamento do operador (mesmo padrão de `routes/atendimento.py`).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared import historico_relatorios as rel
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_conexao_scope_ativo
from whatsapp_langchain.shared.historico import (
    HistoricoFiltros,
    get_historico_detalhe,
    iter_historico_rows_para_export,
    list_atendimentos_historico,
)
from whatsapp_langchain.shared.perfil import get_user_permissions
from whatsapp_langchain.shared.permissoes import (
    effective_scope,
    get_user_conexao_ids,
    get_user_departamento_ids,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/historico",
    tags=["historico"],
    dependencies=[Depends(verify_service_token)],
)

_PRIORIDADES = {"baixa", "media", "alta", "urgente"}
_SENTIMENTOS = {"positivo", "neutro", "negativo", "frustrado"}
_STATUS = {"aguardando", "em_andamento", "resolvido", "abandonado"}
_SORT_FIELDS = {
    "created_at",
    "closed_at",
    "last_message_at",
    "duracao",
    "nota",
    "status",
    "protocolo",
}

# Colunas do CSV/XLSX (ordem + cabeçalho legível).
_EXPORT_COLS: list[tuple[str, str]] = [
    ("protocolo", "Protocolo"),
    ("status", "Status"),
    ("cliente_nome", "Cliente"),
    ("cliente_telefone", "Telefone"),
    ("conexao_nome", "Canal"),
    ("conexao_numero", "Número"),
    ("departamento_nome", "Departamento"),
    ("atendente_nome", "Atendente"),
    ("prioridade", "Prioridade"),
    ("sentimento", "Sentimento"),
    ("iniciado_cliente", "Iniciado pelo cliente"),
    ("created_at", "Início"),
    ("closed_at", "Fim"),
    ("duracao_seg", "Duração (s)"),
    ("nota_csat", "Nota CSAT"),
    ("csat_categoria", "Categoria CSAT"),
    ("resumo_ia", "Resumo IA"),
]


async def _resolve_scope(
    request: Request, user_id: str, empresa_id: int
) -> tuple[set[int] | None, set[int] | None]:
    """Retorna `(deptos, conexoes)` do operador quando escopo `.own`; ambos
    None quando `.all` (sem restrição). Levanta 403 se sem `atendimento.read`.

    Conexão (ADR-002 Etapa 4) só entra em jogo se a EMPRESA optou
    (`conexao_scope_ativo`, default OFF) — contexto `'historico'`, que pode
    divergir do `'fila'` de `routes/atendimento.py` (mesma conexão pode
    estar visível num e não no outro, mig 188).
    """
    pool = await get_pool()
    perms = await get_user_permissions(pool, user_id, empresa_id)
    scope = effective_scope(perms, "atendimento.read")
    if scope is None:
        raise HTTPException(
            status_code=403,
            detail="Permissão necessária: atendimento.read[.own|.all]",
        )
    if scope != "own":
        return None, None
    dept_ids = set(await get_user_departamento_ids(pool, user_id, empresa_id))
    conexao_ids: set[int] | None = None
    if await is_conexao_scope_ativo(pool, empresa_id):
        conexao_ids = set(
            await get_user_conexao_ids(pool, user_id, empresa_id, contexto="historico")
        )
    return dept_ids, conexao_ids


def _parse_filtros(
    *,
    created_de: datetime | None,
    created_ate: datetime | None,
    closed_de: datetime | None,
    closed_ate: datetime | None,
    status: list[str] | None,
    conexao_id: int | None,
    departamento_id: int | None,
    atendente_id: str | None,
    tag_id: int | None,
    prioridade: str | None,
    sentimento: str | None,
    iniciado_cliente: bool | None,
    q: str | None,
) -> HistoricoFiltros:
    if status:
        invalidos = [s for s in status if s not in _STATUS]
        if invalidos:
            raise HTTPException(status_code=400, detail=f"status inválido: {invalidos}")
    if prioridade is not None and prioridade not in _PRIORIDADES:
        raise HTTPException(status_code=400, detail="prioridade inválida")
    if sentimento is not None and sentimento not in _SENTIMENTOS:
        raise HTTPException(status_code=400, detail="sentimento inválido")
    return HistoricoFiltros(
        created_de=created_de,
        created_ate=created_ate,
        closed_de=closed_de,
        closed_ate=closed_ate,
        status=status,
        conexao_id=conexao_id,
        departamento_id=departamento_id,
        assigned_to_user_id=atendente_id,
        tag_id=tag_id,
        prioridade=prioridade,
        sentimento=sentimento,
        iniciado_cliente=iniciado_cliente,
        q=q,
    )


@router.get("")
async def listar_historico(
    request: Request,
    created_de: datetime | None = Query(default=None),
    created_ate: datetime | None = Query(default=None),
    closed_de: datetime | None = Query(default=None),
    closed_ate: datetime | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    conexao_id: int | None = Query(default=None, ge=1),
    departamento_id: int | None = Query(default=None, ge=1),
    atendente_id: str | None = Query(default=None),
    tag_id: int | None = Query(default=None, ge=1),
    prioridade: str | None = Query(default=None),
    sentimento: str | None = Query(default=None),
    iniciado_cliente: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=160),
    sort_field: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, Any]:
    """Lista paginada do histórico com filtros + ordenação."""
    if sort_field not in _SORT_FIELDS:
        raise HTTPException(status_code=400, detail="sort_field inválido")
    scope_dept_ids, scope_conexao_ids = await _resolve_scope(
        request, user_id, empresa_id
    )
    filtros = _parse_filtros(
        created_de=created_de,
        created_ate=created_ate,
        closed_de=closed_de,
        closed_ate=closed_ate,
        status=status,
        conexao_id=conexao_id,
        departamento_id=departamento_id,
        atendente_id=atendente_id,
        tag_id=tag_id,
        prioridade=prioridade,
        sentimento=sentimento,
        iniciado_cliente=iniciado_cliente,
        q=q,
    )
    pool = await get_pool()
    rows, total = await list_atendimentos_historico(
        pool,
        empresa_id,
        filtros=filtros,
        sort_field=sort_field,
        sort_order=sort_order,
        limit=limit,
        offset=(page - 1) * limit,
        scope_departamento_ids=scope_dept_ids,
        scope_conexao_ids=scope_conexao_ids,
    )
    return {"rows": rows, "total": total, "page": page, "limit": limit}


@router.get("/export")
async def exportar_historico(
    request: Request,
    formato: str = Query(default="csv"),
    created_de: datetime | None = Query(default=None),
    created_ate: datetime | None = Query(default=None),
    closed_de: datetime | None = Query(default=None),
    closed_ate: datetime | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    conexao_id: int | None = Query(default=None, ge=1),
    departamento_id: int | None = Query(default=None, ge=1),
    atendente_id: str | None = Query(default=None),
    tag_id: int | None = Query(default=None, ge=1),
    prioridade: str | None = Query(default=None),
    sentimento: str | None = Query(default=None),
    iniciado_cliente: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=160),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> StreamingResponse:
    """Exporta o histórico filtrado em CSV ou XLSX (download)."""
    if formato not in ("csv", "xlsx"):
        raise HTTPException(status_code=400, detail="formato deve ser csv ou xlsx")
    scope_dept_ids, scope_conexao_ids = await _resolve_scope(
        request, user_id, empresa_id
    )
    filtros = _parse_filtros(
        created_de=created_de,
        created_ate=created_ate,
        closed_de=closed_de,
        closed_ate=closed_ate,
        status=status,
        conexao_id=conexao_id,
        departamento_id=departamento_id,
        atendente_id=atendente_id,
        tag_id=tag_id,
        prioridade=prioridade,
        sentimento=sentimento,
        iniciado_cliente=iniciado_cliente,
        q=q,
    )
    pool = await get_pool()
    rows, truncado = await iter_historico_rows_para_export(
        pool,
        empresa_id,
        filtros=filtros,
        scope_departamento_ids=scope_dept_ids,
        scope_conexao_ids=scope_conexao_ids,
    )
    logger.info(
        "historico_export",
        empresa_id=empresa_id,
        formato=formato,
        linhas=len(rows),
        truncado=truncado,
    )
    fname = f"historico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{formato}"
    if formato == "csv":
        content = _to_csv(rows)
        media = "text/csv; charset=utf-8"
    else:
        content = _to_xlsx(rows)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/relatorios/resumo")
async def relatorio_resumo(
    request: Request,
    dias: int = Query(default=30, ge=1, le=365),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, Any]:
    scope_dept, scope_conexao = await _resolve_scope(request, user_id, empresa_id)
    pool = await get_pool()
    return await rel.resumo(
        pool,
        empresa_id,
        dias=dias,
        scope_departamento_ids=scope_dept,
        scope_conexao_ids=scope_conexao,
    )


@router.get("/relatorios/por-operador")
async def relatorio_por_operador(
    request: Request,
    dias: int = Query(default=30, ge=1, le=365),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, Any]:
    scope_dept, scope_conexao = await _resolve_scope(request, user_id, empresa_id)
    pool = await get_pool()
    return {
        "items": await rel.por_operador(
            pool,
            empresa_id,
            dias=dias,
            scope_departamento_ids=scope_dept,
            scope_conexao_ids=scope_conexao,
        )
    }


@router.get("/relatorios/por-departamento")
async def relatorio_por_departamento(
    request: Request,
    dias: int = Query(default=30, ge=1, le=365),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, Any]:
    scope_dept, scope_conexao = await _resolve_scope(request, user_id, empresa_id)
    pool = await get_pool()
    return {
        "items": await rel.por_departamento(
            pool,
            empresa_id,
            dias=dias,
            scope_departamento_ids=scope_dept,
            scope_conexao_ids=scope_conexao,
        )
    }


@router.get("/relatorios/por-canal")
async def relatorio_por_canal(
    request: Request,
    dias: int = Query(default=30, ge=1, le=365),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, Any]:
    scope_dept, scope_conexao = await _resolve_scope(request, user_id, empresa_id)
    pool = await get_pool()
    return {
        "items": await rel.por_canal(
            pool,
            empresa_id,
            dias=dias,
            scope_departamento_ids=scope_dept,
            scope_conexao_ids=scope_conexao,
        )
    }


@router.get("/{atendimento_id}")
async def detalhe_historico(
    request: Request,
    atendimento_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, Any]:
    """Detalhe agregado de um atendimento (timeline + transferências +
    avaliação + tags + anotações + eventos)."""
    scope_dept_ids, scope_conexao_ids = await _resolve_scope(
        request, user_id, empresa_id
    )
    pool = await get_pool()
    detalhe = await get_historico_detalhe(pool, atendimento_id, empresa_id)
    if detalhe is None:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado")
    # RBAC record-level: escopo .own só vê deptos/conexões vinculados. 404
    # (não 403) pelo mesmo motivo do resto do arquivo — não vaza que o
    # atendimento existe fora do escopo do user.
    if scope_dept_ids is not None:
        dep = detalhe["atendimento"].get("departamento_id")
        if dep not in scope_dept_ids:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado")
    if scope_conexao_ids is not None:
        cx = detalhe["atendimento"].get("conexao_id")
        if cx not in scope_conexao_ids:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado")
    return detalhe


def _fmt_cell(key: str, val: Any) -> Any:
    if val is None:
        return ""
    if key in ("created_at", "closed_at") and isinstance(val, datetime):
        return val.strftime("%d/%m/%Y %H:%M:%S")
    if key == "iniciado_cliente":
        return "Sim" if val else "Não"
    return val


def _to_csv(rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([label for _, label in _EXPORT_COLS])
    for r in rows:
        writer.writerow([_fmt_cell(k, r.get(k)) for k, _ in _EXPORT_COLS])
    # BOM pra Excel abrir UTF-8 com acentos corretos.
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def _to_xlsx(rows: list[dict[str, Any]]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Histórico"
    ws.append([label for _, label in _EXPORT_COLS])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append([_fmt_cell(k, r.get(k)) for k, _ in _EXPORT_COLS])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
