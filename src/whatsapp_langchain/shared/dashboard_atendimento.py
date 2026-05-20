"""Helpers de agregação pro Dashboard de Atendimento (operacional).

Endpoint `/api/dashboard/atendimento` chama essas funções em paralelo
e retorna payload único com KPIs + tabelas + charts.

Queries são otimizadas pra rodar em 1 round-trip cada (índices
existentes em atendimento.empresa_id + status + created_at).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


PERIODOS = {"hoje", "7d", "30d"}


def _periodo_to_range(periodo: str) -> tuple[datetime, datetime]:
    """Retorna (start, end) em UTC pro filtro."""
    now = datetime.now(UTC)
    if periodo == "hoje":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif periodo == "7d":
        start = now - timedelta(days=7)
    elif periodo == "30d":
        start = now - timedelta(days=30)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


async def get_kpis(
    pool: AsyncConnectionPool, empresa_id: int, periodo: str
) -> dict[str, Any]:
    """6 KPIs principais:

    - aguardando (snapshot atual, sem filtro de período)
    - em_andamento (snapshot atual)
    - resolvidos_no_periodo
    - abandonados_no_periodo
    - tempo_medio_espera_min (atendimentos aguardando agora — pior caso)
    - taxa_via_ia (% atendimentos resolvidos sem assigned_to_user_id no período)
    """
    start, end = _periodo_to_range(periodo)

    async with pool.connection() as conn:
        # Snapshot atual (sem filtro de tempo)
        cur = await conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'aguardando') AS aguardando,
                COUNT(*) FILTER (WHERE status = 'em_andamento') AS em_andamento
              FROM atendimento
             WHERE empresa_id = %s AND status IN ('aguardando', 'em_andamento')
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
        aguardando = int(row[0] or 0) if row else 0
        em_andamento = int(row[1] or 0) if row else 0

        # Métricas do período (resolvidos, abandonados, taxa IA)
        cur = await conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'resolvido') AS resolvidos,
                COUNT(*) FILTER (WHERE status = 'abandonado') AS abandonados,
                COUNT(*) FILTER (
                    WHERE status = 'resolvido' AND assigned_to_user_id IS NULL
                ) AS resolvidos_ia,
                COUNT(*) FILTER (WHERE status = 'resolvido') AS resolvidos_total
              FROM atendimento
             WHERE empresa_id = %s
               AND closed_at >= %s AND closed_at < %s
               AND status IN ('resolvido', 'abandonado')
            """,
            (empresa_id, start, end),
        )
        row = await cur.fetchone()
        resolvidos = int(row[0] or 0) if row else 0
        abandonados = int(row[1] or 0) if row else 0
        resolvidos_ia = int(row[2] or 0) if row else 0
        resolvidos_total = int(row[3] or 0) if row else 0
        taxa_ia = (resolvidos_ia / resolvidos_total * 100) if resolvidos_total else 0.0

        # Tempo médio de espera dos atendimentos AGUARDANDO no momento
        cur = await conn.execute(
            """
            SELECT
                COALESCE(
                    AVG(EXTRACT(EPOCH FROM (NOW() - created_at)) / 60.0),
                    0
                ) AS tempo_medio_min
              FROM atendimento
             WHERE empresa_id = %s AND status = 'aguardando'
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
        tempo_medio_espera_min = round(float(row[0] or 0), 1) if row else 0.0

    return {
        "aguardando": aguardando,
        "em_andamento": em_andamento,
        "resolvidos": resolvidos,
        "abandonados": abandonados,
        "tempo_medio_espera_min": tempo_medio_espera_min,
        "taxa_via_ia_pct": round(taxa_ia, 1),
    }


async def get_tabela_aguardando(
    pool: AsyncConnectionPool, empresa_id: int, limit: int = 20
) -> list[dict[str, Any]]:
    """Atendimentos status=aguardando ordenados por tempo de espera DESC."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
                a.id, a.protocolo, a.created_at,
                a.departamento_id, d.nome AS departamento_nome,
                c.nome AS cliente_nome, c.telefone AS cliente_telefone,
                EXTRACT(EPOCH FROM (NOW() - a.created_at)) / 60 AS espera_min
              FROM atendimento a
              JOIN cliente c ON c.id = a.cliente_id
              LEFT JOIN departamento d ON d.id = a.departamento_id
             WHERE a.empresa_id = %s AND a.status = 'aguardando'
             ORDER BY a.created_at ASC
             LIMIT %s
            """,
            (empresa_id, limit),
        )
        rows = await cur.fetchall()

    return [
        {
            "id": r[0],
            "protocolo": r[1],
            "created_at": r[2].isoformat() if r[2] else None,
            "departamento_id": r[3],
            "departamento_nome": r[4],
            "cliente_nome": r[5] or r[6] or "—",
            "cliente_telefone": r[6],
            "espera_min": round(float(r[7] or 0), 1),
        }
        for r in rows
    ]


async def get_tabela_em_andamento_sem_resposta(
    pool: AsyncConnectionPool, empresa_id: int, limit: int = 20,
    minutos_threshold: int = 5,
) -> list[dict[str, Any]]:
    """Atendimentos em_andamento sem resposta há > N min.

    Heurística: last_message_at < NOW() - threshold AND mensagens recentes
    do cliente (não do agente/atendente).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
                a.id, a.protocolo, a.last_message_at,
                a.assigned_to_user_id, a.departamento_id, d.nome AS dep_nome,
                c.nome AS cliente_nome, c.telefone AS cliente_telefone,
                EXTRACT(EPOCH FROM (NOW() - a.last_message_at)) / 60 AS desde_ultima_min
              FROM atendimento a
              JOIN cliente c ON c.id = a.cliente_id
              LEFT JOIN departamento d ON d.id = a.departamento_id
             WHERE a.empresa_id = %s
               AND a.status = 'em_andamento'
               AND a.last_message_at < NOW() - (%s || ' minutes')::INTERVAL
             ORDER BY a.last_message_at ASC
             LIMIT %s
            """,
            (empresa_id, str(minutos_threshold), limit),
        )
        rows = await cur.fetchall()

    return [
        {
            "id": r[0],
            "protocolo": r[1],
            "last_message_at": r[2].isoformat() if r[2] else None,
            "assigned_to_user_id": r[3],
            "departamento_id": r[4],
            "departamento_nome": r[5],
            "cliente_nome": r[6] or r[7] or "—",
            "cliente_telefone": r[7],
            "desde_ultima_min": round(float(r[8] or 0), 1),
        }
        for r in rows
    ]


async def get_chart_criados_finalizados(
    pool: AsyncConnectionPool, empresa_id: int, periodo: str
) -> list[dict[str, Any]]:
    """Bar chart: criados vs finalizados por dia no período."""
    start, end = _periodo_to_range(periodo)
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            WITH days AS (
                SELECT generate_series(
                    %s::date, %s::date, '1 day'::interval
                )::date AS dia
            )
            SELECT
                d.dia,
                COUNT(c.id) AS criados,
                COUNT(f.id) AS finalizados
              FROM days d
              LEFT JOIN atendimento c ON c.empresa_id = %s
                  AND DATE(c.created_at) = d.dia
              LEFT JOIN atendimento f ON f.empresa_id = %s
                  AND DATE(f.closed_at) = d.dia
                  AND f.status IN ('resolvido', 'abandonado')
             GROUP BY d.dia
             ORDER BY d.dia ASC
            """,
            (start.date(), end.date(), empresa_id, empresa_id),
        )
        rows = await cur.fetchall()

    return [
        {
            "dia": r[0].isoformat() if r[0] else None,
            "criados": int(r[1] or 0),
            "finalizados": int(r[2] or 0),
        }
        for r in rows
    ]


async def get_chart_por_hora(
    pool: AsyncConnectionPool, empresa_id: int, periodo: str
) -> list[dict[str, Any]]:
    """Heatmap: contagem de atendimentos criados por hora do dia (0-23)."""
    start, end = _periodo_to_range(periodo)
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
                EXTRACT(HOUR FROM created_at)::int AS hora,
                COUNT(*) AS total
              FROM atendimento
             WHERE empresa_id = %s
               AND created_at >= %s AND created_at < %s
             GROUP BY hora
             ORDER BY hora
            """,
            (empresa_id, start, end),
        )
        rows = await cur.fetchall()

    # Preenche todas as 24 horas com 0 se vazias
    by_hour = {int(r[0]): int(r[1]) for r in rows}
    return [{"hora": h, "total": by_hour.get(h, 0)} for h in range(24)]


async def get_chart_por_departamento(
    pool: AsyncConnectionPool, empresa_id: int, periodo: str
) -> list[dict[str, Any]]:
    """Pizza: contagem por departamento no período."""
    start, end = _periodo_to_range(periodo)
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
                COALESCE(d.nome, '— Sem departamento') AS dep_nome,
                COUNT(a.id) AS total
              FROM atendimento a
              LEFT JOIN departamento d ON d.id = a.departamento_id
             WHERE a.empresa_id = %s
               AND a.created_at >= %s AND a.created_at < %s
             GROUP BY dep_nome
             ORDER BY total DESC
             LIMIT 8
            """,
            (empresa_id, start, end),
        )
        rows = await cur.fetchall()

    return [
        {"departamento": r[0], "total": int(r[1] or 0)} for r in rows
    ]


async def get_atendentes_online(
    pool: AsyncConnectionPool, empresa_id: int
) -> dict[str, Any]:
    """Atendentes da empresa: status + count de atendimentos abertos."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
                em.user_id,
                u.name AS nome,
                u.email,
                em.atendente_status,
                em.atendente_status_at,
                em.is_active,
                (
                    SELECT COUNT(*) FROM atendimento a
                     WHERE a.empresa_id = %s
                       AND a.assigned_to_user_id = em.user_id
                       AND a.status IN ('aguardando', 'em_andamento')
                ) AS abertos
              FROM empresa_membro em
              JOIN auth."user" u ON u.id = em.user_id
             WHERE em.empresa_id = %s
               AND em.is_active = TRUE
             ORDER BY
                CASE em.atendente_status WHEN 'online' THEN 0 ELSE 1 END,
                u.name ASC
            """,
            (empresa_id, empresa_id),
        )
        rows = await cur.fetchall()

    atendentes = [
        {
            "user_id": r[0],
            "nome": r[1] or r[2] or "—",
            "email": r[2],
            "status": r[3] or "offline",
            "status_at": r[4].isoformat() if r[4] else None,
            "is_active": r[5],
            "atendimentos_abertos": int(r[6] or 0),
        }
        for r in rows
    ]
    online_count = sum(1 for a in atendentes if a["status"] == "online")
    return {
        "total": len(atendentes),
        "online_count": online_count,
        "offline_count": len(atendentes) - online_count,
        "items": atendentes,
    }


async def get_dashboard_payload(
    pool: AsyncConnectionPool, empresa_id: int, periodo: str
) -> dict[str, Any]:
    """Roda todas as queries em paralelo via asyncio.gather."""
    import asyncio

    if periodo not in PERIODOS:
        periodo = "hoje"

    (
        kpis,
        aguardando_tab,
        sem_resposta_tab,
        chart_criados_finalizados,
        chart_por_hora,
        chart_por_departamento,
        atendentes,
    ) = await asyncio.gather(
        get_kpis(pool, empresa_id, periodo),
        get_tabela_aguardando(pool, empresa_id),
        get_tabela_em_andamento_sem_resposta(pool, empresa_id),
        get_chart_criados_finalizados(pool, empresa_id, periodo),
        get_chart_por_hora(pool, empresa_id, periodo),
        get_chart_por_departamento(pool, empresa_id, periodo),
        get_atendentes_online(pool, empresa_id),
    )

    return {
        "periodo": periodo,
        "kpis": kpis,
        "tabelas": {
            "aguardando": aguardando_tab,
            "em_andamento_sem_resposta": sem_resposta_tab,
        },
        "charts": {
            "criados_finalizados": chart_criados_finalizados,
            "por_hora": chart_por_hora,
            "por_departamento": chart_por_departamento,
        },
        "atendentes": atendentes,
        "updated_at": datetime.now(UTC).isoformat(),
    }
