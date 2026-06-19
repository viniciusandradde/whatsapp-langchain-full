"""Histórico de Atendimentos — consulta sobre TODOS os status (módulo Conversas).

Diferente de `atendimento.list_atendimentos` (painel ao vivo: só abertos via
`tipo`), aqui a query cobre `resolvido`/`abandonado` também, com período +
filtros + paginação + ordenação + busca full-text no conteúdo das mensagens.
Reusa as tabelas já existentes (atendimento, cliente, conexao, departamento,
atendimento_avaliacao, atendimento_tag, atendimento_transferencia, message_queue)
e os helpers `get_atendimento_by_id`, `list_atendimento_mensagens`,
`list_tags_de_atendimento`, `list_anotacoes`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()

# Cap de linhas pra export (evita varrer empresas enormes — ~9.8k/3m no dump real).
EXPORT_ROW_CAP = 50_000

# Colunas ordenáveis (allowlist — nunca interpolar input direto no ORDER BY).
_SORT_COLS: dict[str, str] = {
    "created_at": "a.created_at",
    "closed_at": "a.closed_at",
    "last_message_at": "a.last_message_at",
    "duracao": "duracao_seg",
    "nota": "av.nota",
    "status": "a.status",
    "protocolo": "a.protocolo",
}

# SELECT compartilhado por lista + export (sem COUNT/paginação).
_SELECT = """
    a.id, a.protocolo, a.status, a.created_at, a.closed_at, a.last_message_at,
    a.prioridade, a.sentimento, a.classificacao, a.resumo_ia, a.iniciado_cliente,
    a.departamento_id, a.assigned_to_user_id, a.conexao_id,
    c.nome AS cliente_nome, c.telefone AS cliente_telefone,
    COALESCE(cx.display_name, a.conexao_nome) AS conexao_nome,
    COALESCE(cx.from_number, a.conexao_numero) AS conexao_numero,
    COALESCE(cx.provider, a.conexao_provider) AS conexao_provider,
    d.nome AS departamento_nome,
    u.name AS atendente_nome,
    av.nota AS nota_csat, av.categoria AS csat_categoria,
    EXTRACT(EPOCH FROM (COALESCE(a.closed_at, a.last_message_at) - a.created_at))
        AS duracao_seg
"""

_FROM = """
    FROM atendimento a
    LEFT JOIN cliente c ON c.id = a.cliente_id
    LEFT JOIN conexao cx ON cx.id = a.conexao_id
    LEFT JOIN departamento d ON d.id = a.departamento_id
    LEFT JOIN auth."user" u ON u.id = a.assigned_to_user_id
    LEFT JOIN atendimento_avaliacao av ON av.atendimento_id = a.id
"""


@dataclass
class HistoricoFiltros:
    """Filtros da consulta de histórico (todos opcionais)."""

    created_de: datetime | None = None
    created_ate: datetime | None = None
    closed_de: datetime | None = None
    closed_ate: datetime | None = None
    status: list[str] | None = None
    conexao_id: int | None = None
    departamento_id: int | None = None
    assigned_to_user_id: str | None = None
    tag_id: int | None = None
    prioridade: str | None = None
    sentimento: str | None = None
    iniciado_cliente: bool | None = None
    q: str | None = None


def _build_where(
    empresa_id: int,
    f: HistoricoFiltros,
    scope_departamento_ids: set[int] | None,
) -> tuple[str, list[Any]]:
    """Monta o WHERE dinâmico + lista de params (ordem importa)."""
    conds: list[str] = ["a.empresa_id = %s"]
    params: list[Any] = [empresa_id]

    if f.created_de is not None:
        conds.append("a.created_at >= %s")
        params.append(f.created_de)
    if f.created_ate is not None:
        conds.append("a.created_at <= %s")
        params.append(f.created_ate)
    if f.closed_de is not None:
        conds.append("a.closed_at >= %s")
        params.append(f.closed_de)
    if f.closed_ate is not None:
        conds.append("a.closed_at <= %s")
        params.append(f.closed_ate)
    if f.status:
        conds.append("a.status = ANY(%s)")
        params.append(list(f.status))
    if f.conexao_id is not None:
        conds.append("a.conexao_id = %s")
        params.append(f.conexao_id)
    if f.departamento_id is not None:
        conds.append("a.departamento_id = %s")
        params.append(f.departamento_id)
    if f.assigned_to_user_id is not None:
        conds.append("a.assigned_to_user_id = %s")
        params.append(f.assigned_to_user_id)
    if f.prioridade is not None:
        conds.append("a.prioridade = %s")
        params.append(f.prioridade)
    if f.sentimento is not None:
        conds.append("a.sentimento = %s")
        params.append(f.sentimento)
    if f.iniciado_cliente is not None:
        conds.append("a.iniciado_cliente = %s")
        params.append(f.iniciado_cliente)
    if f.tag_id is not None:
        conds.append(
            "EXISTS (SELECT 1 FROM atendimento_tag at "
            "WHERE at.atendimento_id = a.id AND at.tag_id = %s)"
        )
        params.append(f.tag_id)
    if f.q:
        like = f"%{f.q.strip()}%"
        conds.append(
            "("
            "a.protocolo ILIKE %s OR c.nome ILIKE %s OR c.telefone ILIKE %s "
            "OR a.resumo_ia ILIKE %s "
            "OR EXISTS (SELECT 1 FROM message_queue mq "
            "  WHERE mq.atendimento_id = a.id "
            "    AND (mq.incoming_message ILIKE %s OR mq.response ILIKE %s))"
            ")"
        )
        params.extend([like, like, like, like, like, like])

    # RBAC record-level: escopo `.own` → só deptos do operador.
    if scope_departamento_ids is not None:
        conds.append("a.departamento_id = ANY(%s)")
        params.append(list(scope_departamento_ids))

    return " AND ".join(conds), params


async def list_atendimentos_historico(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    filtros: HistoricoFiltros,
    sort_field: str = "created_at",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    scope_departamento_ids: set[int] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Lista paginada do histórico. Retorna (rows, total)."""
    where, params = _build_where(empresa_id, filtros, scope_departamento_ids)
    order_col = _SORT_COLS.get(sort_field, "a.created_at")
    direction = "ASC" if sort_order.lower() == "asc" else "DESC"

    sql = f"""
        SELECT {_SELECT}, COUNT(*) OVER() AS _total
        {_FROM}
        WHERE {where}
        ORDER BY {order_col} {direction} NULLS LAST, a.id DESC
        LIMIT %s OFFSET %s
    """
    async with pool.connection() as conn:
        cur = await conn.execute(sql, (*params, limit, offset))  # type: ignore[arg-type]
        rows = await cur.fetchall()
        cols = [c.name for c in cur.description] if cur.description else []

    total = int(rows[0][cols.index("_total")]) if rows else 0
    out = [_row_to_dict(r, cols, drop={"_total"}) for r in rows]
    return out, total


async def iter_historico_rows_para_export(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    filtros: HistoricoFiltros,
    scope_departamento_ids: set[int] | None = None,
    cap: int = EXPORT_ROW_CAP,
) -> tuple[list[dict[str, Any]], bool]:
    """Carrega linhas pro export (sem paginação, até `cap`). Retorna
    (rows, truncado) — `truncado=True` se bateu no cap."""
    where, params = _build_where(empresa_id, filtros, scope_departamento_ids)
    sql = f"""
        SELECT {_SELECT}
        {_FROM}
        WHERE {where}
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT %s
    """
    async with pool.connection() as conn:
        cur = await conn.execute(sql, (*params, cap + 1))  # type: ignore[arg-type]
        rows = await cur.fetchall()
        cols = [c.name for c in cur.description] if cur.description else []

    truncado = len(rows) > cap
    if truncado:
        rows = rows[:cap]
        logger.warning("historico_export_truncado", empresa_id=empresa_id, cap=cap)
    return [_row_to_dict(r, cols) for r in rows], truncado


def _row_to_dict(
    row: Any, cols: list[str], drop: set[str] | None = None
) -> dict[str, Any]:
    drop = drop or set()
    d = {cols[i]: row[i] for i in range(len(cols)) if cols[i] not in drop}
    # duração arredondada em segundos (int) pra consumo na UI/export.
    dur = d.get("duracao_seg")
    d["duracao_seg"] = int(dur) if dur is not None else None
    return d


async def get_historico_detalhe(
    pool: AsyncConnectionPool, atendimento_id: int, empresa_id: int
) -> dict[str, Any] | None:
    """Detalhe agregado de um atendimento pro drawer do histórico:
    base + timeline + tags + transferências + avaliação + anotações + eventos.
    Reusa os helpers existentes. Retorna None se não existe na empresa."""
    from whatsapp_langchain.shared.atendimento import (
        get_atendimento_by_id,
        list_atendimento_mensagens,
    )
    from whatsapp_langchain.shared.atendimento_tag import list_tags_de_atendimento
    from whatsapp_langchain.shared.cliente import list_anotacoes

    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return None

    mensagens = await list_atendimento_mensagens(pool, atendimento_id, empresa_id)
    tags = await list_tags_de_atendimento(
        pool, atendimento_id=atendimento_id, empresa_id=empresa_id
    )
    try:
        anotacoes_raw = await list_anotacoes(pool, atd.cliente_id)
        anotacoes = [
            a.model_dump() if hasattr(a, "model_dump") else vars(a)
            for a in anotacoes_raw
        ]
    except Exception:  # noqa: BLE001 — anotações é best-effort no detalhe
        anotacoes = []

    transferencias = await _list_transferencias(pool, atendimento_id)
    avaliacao = await _get_avaliacao(pool, atendimento_id)
    menu_historico = await _list_menu_historico(pool, atendimento_id)
    eventos = _build_eventos(atd, transferencias, avaliacao)

    return {
        "atendimento": atd.model_dump() if hasattr(atd, "model_dump") else vars(atd),
        "mensagens": mensagens,
        "tags": tags,
        "transferencias": transferencias,
        "avaliacao": avaliacao,
        "anotacoes": anotacoes,
        "menu_historico": menu_historico,
        "eventos": eventos,
    }


async def _list_menu_historico(
    pool: AsyncConnectionPool, atendimento_id: int
) -> list[dict[str, Any]]:
    """Jornada do cliente no chatbot/menu (equivalente ao
    AtendimentoMenuHistorico do ZigChat): qual menu/opção em cada passo."""
    sql = """
        SELECT mh.escolhido_at, mh.resposta,
               mc.nome AS menu_nome, mi.label AS item_label
          FROM atendimento_menu_historico mh
          LEFT JOIN menu_chatbot mc ON mc.id = mh.menu_id
          LEFT JOIN menu_item mi ON mi.id = mh.item_id
         WHERE mh.atendimento_id = %s
         ORDER BY mh.escolhido_at ASC, mh.id ASC
    """
    async with pool.connection() as conn:
        cur = await conn.execute(sql, (atendimento_id,))
        rows = await cur.fetchall()
        cols = [c.name for c in cur.description] if cur.description else []
    return [{cols[i]: r[i] for i in range(len(cols))} for r in rows]


async def _list_transferencias(
    pool: AsyncConnectionPool, atendimento_id: int
) -> list[dict[str, Any]]:
    sql = """
        SELECT t.id, t.created_at, t.motivo,
               t.de_user_id, t.de_departamento_id, t.de_agente_slug,
               t.para_user_id, t.para_departamento_id, t.para_agente_slug,
               t.iniciado_por_user_id,
               du.name AS de_user_nome, pu.name AS para_user_nome,
               dd.nome AS de_depto_nome, pd.nome AS para_depto_nome
          FROM atendimento_transferencia t
          LEFT JOIN auth."user" du ON du.id = t.de_user_id
          LEFT JOIN auth."user" pu ON pu.id = t.para_user_id
          LEFT JOIN departamento dd ON dd.id = t.de_departamento_id
          LEFT JOIN departamento pd ON pd.id = t.para_departamento_id
         WHERE t.atendimento_id = %s
         ORDER BY t.id ASC
    """
    async with pool.connection() as conn:
        cur = await conn.execute(sql, (atendimento_id,))
        rows = await cur.fetchall()
        cols = [c.name for c in cur.description] if cur.description else []
    return [{cols[i]: r[i] for i in range(len(cols))} for r in rows]


async def _get_avaliacao(
    pool: AsyncConnectionPool, atendimento_id: int
) -> dict[str, Any] | None:
    sql = """
        SELECT nota, categoria, comentario, created_at
          FROM atendimento_avaliacao
         WHERE atendimento_id = %s
    """
    async with pool.connection() as conn:
        cur = await conn.execute(sql, (atendimento_id,))
        row = await cur.fetchone()
        cols = [c.name for c in cur.description] if cur.description else []
    return {cols[i]: row[i] for i in range(len(cols))} if row else None


def _build_eventos(
    atd: Any,
    transferencias: list[dict[str, Any]],
    avaliacao: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Linha do tempo de eventos derivada de timestamps (sem tabela dedicada)."""
    eventos: list[dict[str, Any]] = []
    if getattr(atd, "created_at", None):
        eventos.append({"tipo": "aberto", "at": atd.created_at})
    if getattr(atd, "triagem_at", None):
        eventos.append({"tipo": "triagem", "at": atd.triagem_at})
    for t in transferencias:
        eventos.append(
            {
                "tipo": "transferencia",
                "at": t["created_at"],
                "para_depto": t.get("para_depto_nome"),
                "para_user": t.get("para_user_nome"),
                "motivo": t.get("motivo"),
            }
        )
    if getattr(atd, "closed_at", None):
        eventos.append({"tipo": "fechado", "at": atd.closed_at, "status": atd.status})
    if avaliacao:
        eventos.append(
            {
                "tipo": "avaliacao",
                "at": avaliacao["created_at"],
                "nota": avaliacao["nota"],
            }
        )
    eventos.sort(key=lambda e: e["at"] or atd.created_at)
    return eventos
