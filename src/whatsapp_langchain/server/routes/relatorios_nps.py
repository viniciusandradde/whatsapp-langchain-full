"""Sprint X — Relatórios NPS de atendimento.

4 endpoints agregados sobre `atendimento_avaliacao` (mig 073):

- GET /api/relatorios/nps                     — score geral + série diária
- GET /api/relatorios/nps/por-departamento   — breakdown por depto
- GET /api/relatorios/nps/ranking-operadores — ranking com NPS/CSAT
- GET /api/relatorios/nps/avaliacoes         — lista paginada com comentários

Cálculo NPS clássico: (%promotores 9-10) − (%detratores 0-6).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool

router = APIRouter(
    prefix="/api/relatorios/nps",
    tags=["relatorios-nps"],
    dependencies=[Depends(verify_service_token)],
)


class NPSSerieDia(BaseModel):
    data: date
    score: float | None
    total: int


class NPSResumo(BaseModel):
    score: float | None
    total: int
    promotores: int
    neutros: int
    detratores: int
    pct_promotores: float | None
    pct_detratores: float | None
    csat_medio: float | None
    serie_diaria: list[NPSSerieDia]


class NPSPorDepartamento(BaseModel):
    departamento_id: int | None
    departamento_nome: str | None
    total: int
    promotores: int
    neutros: int
    detratores: int
    score: float | None
    csat_medio: float | None


class RankingOperadorNPS(BaseModel):
    user_id: str | None
    nome: str | None
    image: str | None
    avaliacoes_total: int
    promotores: int
    detratores: int
    score: float | None
    csat_medio: float | None


class NPSAvaliacaoItem(BaseModel):
    id: int
    atendimento_id: int
    nota: int
    categoria: str
    comentario: str | None
    created_at: str
    cliente_nome: str | None
    departamento_nome: str | None
    atendente_nome: str | None
    protocolo: str | None


class NPSAvaliacoesPage(BaseModel):
    items: list[NPSAvaliacaoItem]
    total: int
    pagina: int
    limit: int


# Cláusula SQL reusada — calcula NPS score a partir das contagens.
# Usa NULLIF pra evitar divisão por zero (retorna NULL se total=0).
_NPS_SCORE_EXPR = """
    ROUND((
        100.0 * COUNT(*) FILTER (WHERE categoria='promotor')
              / NULLIF(COUNT(*), 0)
      - 100.0 * COUNT(*) FILTER (WHERE categoria='detrator')
              / NULLIF(COUNT(*), 0)
    )::numeric, 1)
"""


@router.get("", response_model=NPSResumo)
async def nps_geral(
    periodo: int = Query(default=30, ge=1, le=365),
    empresa_id: int = Depends(get_empresa_context),
) -> NPSResumo:
    """Score NPS geral + breakdown + série diária no período."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE categoria='promotor') AS promotores,
              COUNT(*) FILTER (WHERE categoria='neutro') AS neutros,
              COUNT(*) FILTER (WHERE categoria='detrator') AS detratores,
              ROUND(AVG(nota)::numeric, 2) AS csat_medio,
              {_NPS_SCORE_EXPR} AS score
              FROM atendimento_avaliacao
             WHERE empresa_id = %s
               AND created_at >= NOW() - (%s || ' days')::INTERVAL
            """,
            (empresa_id, periodo),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=500, detail="Query NPS falhou")
        total = int(row[0] or 0)
        promotores = int(row[1] or 0)
        neutros = int(row[2] or 0)
        detratores = int(row[3] or 0)
        csat_medio = float(row[4]) if row[4] is not None else None
        score = float(row[5]) if row[5] is not None else None

        # Série diária
        cur = await conn.execute(
            f"""
            SELECT DATE(created_at) AS dia,
                   {_NPS_SCORE_EXPR} AS score,
                   COUNT(*) AS total
              FROM atendimento_avaliacao
             WHERE empresa_id = %s
               AND created_at >= NOW() - (%s || ' days')::INTERVAL
             GROUP BY DATE(created_at)
             ORDER BY dia ASC
            """,
            (empresa_id, periodo),
        )
        serie = [
            NPSSerieDia(
                data=r[0],
                score=float(r[1]) if r[1] is not None else None,
                total=int(r[2]),
            )
            for r in await cur.fetchall()
        ]

    pct_promotores = (
        round(100.0 * promotores / total, 1) if total > 0 else None
    )
    pct_detratores = (
        round(100.0 * detratores / total, 1) if total > 0 else None
    )

    return NPSResumo(
        score=score,
        total=total,
        promotores=promotores,
        neutros=neutros,
        detratores=detratores,
        pct_promotores=pct_promotores,
        pct_detratores=pct_detratores,
        csat_medio=csat_medio,
        serie_diaria=serie,
    )


@router.get("/por-departamento", response_model=list[NPSPorDepartamento])
async def nps_por_departamento(
    periodo: int = Query(default=30, ge=1, le=365),
    empresa_id: int = Depends(get_empresa_context),
) -> list[NPSPorDepartamento]:
    """Agrega NPS por departamento. ORDER BY score DESC."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT
              av.departamento_id,
              d.nome,
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE av.categoria='promotor') AS promotores,
              COUNT(*) FILTER (WHERE av.categoria='neutro') AS neutros,
              COUNT(*) FILTER (WHERE av.categoria='detrator') AS detratores,
              ROUND(AVG(av.nota)::numeric, 2) AS csat_medio,
              {_NPS_SCORE_EXPR.replace("categoria", "av.categoria")} AS score
              FROM atendimento_avaliacao av
              LEFT JOIN departamento d ON d.id = av.departamento_id
             WHERE av.empresa_id = %s
               AND av.created_at >= NOW() - (%s || ' days')::INTERVAL
             GROUP BY av.departamento_id, d.nome
             ORDER BY score DESC NULLS LAST, total DESC
            """,
            (empresa_id, periodo),
        )
        rows = await cur.fetchall()
    return [
        NPSPorDepartamento(
            departamento_id=r[0],
            departamento_nome=r[1],
            total=int(r[2]),
            promotores=int(r[3]),
            neutros=int(r[4]),
            detratores=int(r[5]),
            csat_medio=float(r[6]) if r[6] is not None else None,
            score=float(r[7]) if r[7] is not None else None,
        )
        for r in rows
    ]


@router.get("/ranking-operadores", response_model=list[RankingOperadorNPS])
async def nps_ranking_operadores(
    periodo: int = Query(default=30, ge=1, le=365),
    empresa_id: int = Depends(get_empresa_context),
) -> list[RankingOperadorNPS]:
    """Ranking de operadores por NPS no período. JOIN com auth.user pra nome."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT
              av.assigned_to_user_id,
              u.name,
              u.image,
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE av.categoria='promotor') AS promotores,
              COUNT(*) FILTER (WHERE av.categoria='detrator') AS detratores,
              ROUND(AVG(av.nota)::numeric, 2) AS csat_medio,
              {_NPS_SCORE_EXPR.replace("categoria", "av.categoria")} AS score
              FROM atendimento_avaliacao av
              LEFT JOIN auth."user" u ON u.id = av.assigned_to_user_id
             WHERE av.empresa_id = %s
               AND av.created_at >= NOW() - (%s || ' days')::INTERVAL
               AND av.assigned_to_user_id IS NOT NULL
             GROUP BY av.assigned_to_user_id, u.name, u.image
             ORDER BY score DESC NULLS LAST, total DESC
            """,
            (empresa_id, periodo),
        )
        rows = await cur.fetchall()
    return [
        RankingOperadorNPS(
            user_id=r[0],
            nome=r[1],
            image=r[2],
            avaliacoes_total=int(r[3]),
            promotores=int(r[4]),
            detratores=int(r[5]),
            csat_medio=float(r[6]) if r[6] is not None else None,
            score=float(r[7]) if r[7] is not None else None,
        )
        for r in rows
    ]


@router.get("/avaliacoes", response_model=NPSAvaliacoesPage)
async def nps_avaliacoes(
    periodo: int = Query(default=30, ge=1, le=365),
    categoria: str | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    empresa_id: int = Depends(get_empresa_context),
) -> NPSAvaliacoesPage:
    """Lista paginada de avaliações com comentários. Filtro opcional por
    categoria (`promotor`/`neutro`/`detrator`).
    """
    if categoria is not None and categoria not in (
        "promotor",
        "neutro",
        "detrator",
    ):
        raise HTTPException(status_code=400, detail="categoria inválida")
    offset = (pagina - 1) * limit
    where_cat = "AND av.categoria = %s" if categoria else ""
    params: tuple = (
        (empresa_id, periodo, categoria, limit, offset)
        if categoria
        else (empresa_id, periodo, limit, offset)
    )
    count_params: tuple = (
        (empresa_id, periodo, categoria)
        if categoria
        else (empresa_id, periodo)
    )

    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT
              av.id, av.atendimento_id, av.nota, av.categoria,
              av.comentario, av.created_at,
              c.nome, d.nome, u.name, a.protocolo
              FROM atendimento_avaliacao av
              LEFT JOIN cliente c ON c.id = av.cliente_id
              LEFT JOIN departamento d ON d.id = av.departamento_id
              LEFT JOIN auth."user" u ON u.id = av.assigned_to_user_id
              LEFT JOIN atendimento a ON a.id = av.atendimento_id
             WHERE av.empresa_id = %s
               AND av.created_at >= NOW() - (%s || ' days')::INTERVAL
               {where_cat}
             ORDER BY av.created_at DESC
             LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = await cur.fetchall()
        items = [
            NPSAvaliacaoItem(
                id=int(r[0]),
                atendimento_id=int(r[1]),
                nota=int(r[2]),
                categoria=r[3],
                comentario=r[4],
                created_at=r[5].isoformat() if r[5] else "",
                cliente_nome=r[6],
                departamento_nome=r[7],
                atendente_nome=r[8],
                protocolo=r[9],
            )
            for r in rows
        ]

        cur = await conn.execute(
            f"""
            SELECT COUNT(*) FROM atendimento_avaliacao av
             WHERE av.empresa_id = %s
               AND av.created_at >= NOW() - (%s || ' days')::INTERVAL
               {where_cat}
            """,
            count_params,
        )
        row = await cur.fetchone()
        total = int(row[0]) if row else 0

    return NPSAvaliacoesPage(items=items, total=total, pagina=pagina, limit=limit)
