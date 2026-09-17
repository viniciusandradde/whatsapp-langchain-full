"""Relatórios/analytics do Histórico de Atendimentos (Fase 2).

Métricas operacionais sobre o conjunto completo de atendimentos num período:
volume, tempos (resolução + 1ª resposta), CSAT/NPS, e quebras por operador /
departamento / canal. Reusa os padrões de agregação de `dashboard_atendimento`
e `relatorios_nps`. Tempo de 1ª resposta é DERIVADO de `message_queue` (sem
coluna nova / sem tocar o hot-path do worker).

RBAC: `scope_departamento_ids` (escopo `.own`) filtra por departamento.
`scope_conexao_ids` (ADR-002 Etapa 4, opt-in por empresa) filtra por conexão
— mesmo default-deny: só a UNIÃO das duas condições passa (AND, não OR).
"""

from __future__ import annotations

from typing import Any

from psycopg_pool import AsyncConnectionPool


def _scope(
    scope_departamento_ids: set[int] | None,
    scope_conexao_ids: set[int] | None = None,
) -> tuple[str, list[Any]]:
    sql = ""
    params: list[Any] = []
    if scope_departamento_ids is not None:
        sql += " AND a.departamento_id = ANY(%s)"
        params.append(list(scope_departamento_ids))
    if scope_conexao_ids is not None:
        sql += " AND a.conexao_id = ANY(%s)"
        params.append(list(scope_conexao_ids))
    return sql, params


async def _one(
    pool: AsyncConnectionPool, sql: str, params: list[Any]
) -> dict[str, Any]:
    async with pool.connection() as conn:
        cur = await conn.execute(sql, tuple(params))  # type: ignore[arg-type]
        row = await cur.fetchone()
        cols = [c.name for c in cur.description] if cur.description else []
    return {cols[i]: row[i] for i in range(len(cols))} if row else {}


async def _all(
    pool: AsyncConnectionPool, sql: str, params: list[Any]
) -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        cur = await conn.execute(sql, tuple(params))  # type: ignore[arg-type]
        rows = await cur.fetchall()
        cols = [c.name for c in cur.description] if cur.description else []
    return [{cols[i]: r[i] for i in range(len(cols))} for r in rows]


async def resumo(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    dias: int,
    scope_departamento_ids: set[int] | None = None,
    scope_conexao_ids: set[int] | None = None,
) -> dict[str, Any]:
    """KPIs do período + série diária + tempos + CSAT/NPS."""
    sc, sp = _scope(scope_departamento_ids, scope_conexao_ids)

    kpis = await _one(
        pool,
        f"""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE status='resolvido') AS resolvidos,
          COUNT(*) FILTER (WHERE status='abandonado') AS abandonados,
          COUNT(*) FILTER (WHERE status IN ('aguardando','em_andamento')) AS abertos,
          COUNT(*) FILTER (
            WHERE status='resolvido' AND assigned_to_user_id IS NULL
          ) AS resolvidos_via_ia,
          ROUND(AVG(EXTRACT(EPOCH FROM (closed_at - created_at)))
                FILTER (WHERE closed_at IS NOT NULL))::int AS tempo_medio_resolucao_seg
        FROM atendimento a
        WHERE a.empresa_id=%s AND a.created_at >= NOW() - (%s||' days')::INTERVAL{sc}
        """,
        [empresa_id, dias, *sp],
    )

    pr = await _one(
        pool,
        f"""
        SELECT ROUND(AVG(EXTRACT(EPOCH FROM (fr.first_at - a.created_at))))::int
                 AS tempo_medio_primeira_resposta_seg
        FROM atendimento a
        JOIN LATERAL (
            SELECT MIN(mq.processed_at) AS first_at
              FROM message_queue mq
             WHERE mq.atendimento_id = a.id
               AND mq.response IS NOT NULL AND mq.processed_at IS NOT NULL
        ) fr ON TRUE
        WHERE a.empresa_id=%s AND a.created_at >= NOW() - (%s||' days')::INTERVAL
          AND fr.first_at IS NOT NULL{sc}
        """,
        [empresa_id, dias, *sp],
    )

    csat = await _one(
        pool,
        f"""
        SELECT COUNT(*) AS avaliacoes,
               ROUND(AVG(av.nota)::numeric, 2) AS csat_medio,
               ROUND(
                 100.0 * COUNT(*) FILTER (WHERE av.categoria='promotor')
                       / NULLIF(COUNT(*), 0)
               - 100.0 * COUNT(*) FILTER (WHERE av.categoria='detrator')
                       / NULLIF(COUNT(*), 0), 1) AS nps
        FROM atendimento_avaliacao av
        JOIN atendimento a ON a.id = av.atendimento_id
        WHERE av.empresa_id=%s AND av.created_at >= NOW() - (%s||' days')::INTERVAL{sc}
        """,
        [empresa_id, dias, *sp],
    )

    serie = await _all(
        pool,
        f"""
        SELECT to_char(date_trunc('day', a.created_at), 'YYYY-MM-DD') AS dia,
               COUNT(*) AS criados,
               COUNT(*) FILTER (WHERE a.closed_at IS NOT NULL) AS finalizados
        FROM atendimento a
        WHERE a.empresa_id=%s AND a.created_at >= NOW() - (%s||' days')::INTERVAL{sc}
        GROUP BY 1 ORDER BY 1
        """,
        [empresa_id, dias, *sp],
    )

    return {"kpis": {**kpis, **pr, **csat}, "serie_diaria": serie, "periodo_dias": dias}


async def por_operador(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    dias: int,
    scope_departamento_ids: set[int] | None = None,
    scope_conexao_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    sc, sp = _scope(scope_departamento_ids, scope_conexao_ids)
    return await _all(
        pool,
        f"""
        SELECT a.assigned_to_user_id AS user_id, u.name AS nome,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE a.status='resolvido') AS resolvidos,
               ROUND(AVG(EXTRACT(EPOCH FROM (a.closed_at - a.created_at)))
                     FILTER (WHERE a.closed_at IS NOT NULL))::int AS tempo_medio_seg,
               ROUND(AVG(av.nota)::numeric, 2) AS csat_medio
        FROM atendimento a
        LEFT JOIN auth."user" u ON u.id = a.assigned_to_user_id
        LEFT JOIN atendimento_avaliacao av ON av.atendimento_id = a.id
        WHERE a.empresa_id=%s AND a.created_at >= NOW() - (%s||' days')::INTERVAL
          AND a.assigned_to_user_id IS NOT NULL{sc}
        GROUP BY a.assigned_to_user_id, u.name
        ORDER BY total DESC
        """,
        [empresa_id, dias, *sp],
    )


async def por_departamento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    dias: int,
    scope_departamento_ids: set[int] | None = None,
    scope_conexao_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    sc, sp = _scope(scope_departamento_ids, scope_conexao_ids)
    return await _all(
        pool,
        f"""
        SELECT a.departamento_id, d.nome AS departamento_nome,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE a.status='resolvido') AS resolvidos,
               ROUND(AVG(EXTRACT(EPOCH FROM (a.closed_at - a.created_at)))
                     FILTER (WHERE a.closed_at IS NOT NULL))::int AS tempo_medio_seg,
               ROUND(AVG(av.nota)::numeric, 2) AS csat_medio
        FROM atendimento a
        LEFT JOIN departamento d ON d.id = a.departamento_id
        LEFT JOIN atendimento_avaliacao av ON av.atendimento_id = a.id
        WHERE a.empresa_id=%s AND a.created_at >= NOW() - (%s||' days')::INTERVAL
          AND a.departamento_id IS NOT NULL{sc}
        GROUP BY a.departamento_id, d.nome
        ORDER BY total DESC
        """,
        [empresa_id, dias, *sp],
    )


async def por_canal(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    dias: int,
    scope_departamento_ids: set[int] | None = None,
    scope_conexao_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    sc, sp = _scope(scope_departamento_ids, scope_conexao_ids)
    return await _all(
        pool,
        f"""
        SELECT a.conexao_id,
               COALESCE(cx.display_name, a.conexao_nome,
                        cx.from_number, a.conexao_numero) AS canal,
               COALESCE(cx.provider, a.conexao_provider) AS provider,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE a.status='resolvido') AS resolvidos
        FROM atendimento a
        LEFT JOIN conexao cx ON cx.id = a.conexao_id
        WHERE a.empresa_id=%s AND a.created_at >= NOW() - (%s||' days')::INTERVAL{sc}
        GROUP BY a.conexao_id,
                 COALESCE(cx.display_name, a.conexao_nome,
                          cx.from_number, a.conexao_numero),
                 COALESCE(cx.provider, a.conexao_provider)
        ORDER BY total DESC
        """,
        [empresa_id, dias, *sp],
    )
