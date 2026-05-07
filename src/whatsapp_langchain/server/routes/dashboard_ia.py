"""Dashboard IA — agregações de ia_execucao + ia_budget (mig 057+058).

Endpoints:
- GET /api/v1/dashboard/ia — agregações pra UI dashboard (consumo, top, série)
- GET /api/v1/ia-budget — config budget do mês atual
- PUT /api/v1/ia-budget — UPSERT limite + acao_estouro + alerta_pct
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.audit import record_audit
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.governanca_ia import get_budget_atual

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("/ia")
async def dashboard_ia_endpoint(
    days: int = 30,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    """Visão consolidada IA da empresa nos últimos N dias.

    Retorna:
    - resumo: total_calls, total_tokens_in/out, custo_total, custo_mes_atual
    - serie_diaria: [{dia, calls, custo}, ...]
    - top_modelos: [{provedor, nome, calls, custo}, ...]
    - top_agentes: [{agente_ia_id, slug, nome, calls, custo}, ...]
    - budget_atual: {limite, consumo, pct, acao_estouro} ou null
    """
    days = max(1, min(days, 365))
    desde = datetime.now() - timedelta(days=days)
    pool = await get_pool()

    async with pool.connection() as conn:
        # Resumo geral
        cur = await conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(tokens_input), 0),
                   COALESCE(SUM(tokens_output), 0), COALESCE(SUM(custo_total), 0)
              FROM ia_execucao
             WHERE empresa_id = %s AND created_at >= %s AND status = 'success'
            """,
            (empresa_id, desde),
        )
        r = await cur.fetchone()
        total_calls = int(r[0]) if r else 0
        total_input = int(r[1]) if r else 0
        total_output = int(r[2]) if r else 0
        custo_periodo = float(r[3]) if r else 0.0

        # Custo do mês atual (sempre o mês corrente, independente de days)
        ano_mes = datetime.now().strftime("%Y-%m")
        cur = await conn.execute(
            """
            SELECT COALESCE(SUM(custo_total), 0) FROM ia_execucao
             WHERE empresa_id = %s
               AND TO_CHAR(created_at, 'YYYY-MM') = %s
               AND status = 'success'
            """,
            (empresa_id, ano_mes),
        )
        r = await cur.fetchone()
        custo_mes = float(r[0]) if r else 0.0

        # Série diária
        cur = await conn.execute(
            """
            SELECT DATE(created_at) AS dia,
                   COUNT(*) AS calls,
                   COALESCE(SUM(custo_total), 0) AS custo
              FROM ia_execucao
             WHERE empresa_id = %s AND created_at >= %s
             GROUP BY DATE(created_at)
             ORDER BY dia
            """,
            (empresa_id, desde),
        )
        serie_diaria = [
            {
                "dia": row[0].isoformat(),
                "calls": int(row[1]),
                "custo": float(row[2]),
            }
            for row in await cur.fetchall()
        ]

        # Top modelos
        cur = await conn.execute(
            """
            SELECT modelo_provedor, modelo_nome,
                   COUNT(*) AS calls,
                   COALESCE(SUM(custo_total), 0) AS custo,
                   COALESCE(SUM(tokens_input), 0) AS tin,
                   COALESCE(SUM(tokens_output), 0) AS tout
              FROM ia_execucao
             WHERE empresa_id = %s AND created_at >= %s AND status = 'success'
             GROUP BY modelo_provedor, modelo_nome
             ORDER BY calls DESC LIMIT 10
            """,
            (empresa_id, desde),
        )
        top_modelos = [
            {
                "provedor": row[0],
                "nome": row[1],
                "calls": int(row[2]),
                "custo": float(row[3]),
                "tokens_input": int(row[4]),
                "tokens_output": int(row[5]),
            }
            for row in await cur.fetchall()
        ]

        # Top agentes (precisa JOIN com agente_ia pra nome)
        cur = await conn.execute(
            """
            SELECT a.id, a.slug, a.nome,
                   COUNT(e.*) AS calls,
                   COALESCE(SUM(e.custo_total), 0) AS custo
              FROM ia_execucao e
              JOIN agente_ia a ON a.id = e.agente_ia_id
             WHERE e.empresa_id = %s AND e.created_at >= %s AND e.status = 'success'
             GROUP BY a.id, a.slug, a.nome
             ORDER BY calls DESC LIMIT 10
            """,
            (empresa_id, desde),
        )
        top_agentes = [
            {
                "id": int(row[0]),
                "slug": row[1],
                "nome": row[2],
                "calls": int(row[3]),
                "custo": float(row[4]),
            }
            for row in await cur.fetchall()
        ]

    budget_atual = await get_budget_atual(pool, empresa_id)

    return {
        "periodo_dias": days,
        "resumo": {
            "total_calls": total_calls,
            "total_tokens_input": total_input,
            "total_tokens_output": total_output,
            "custo_periodo_usd": custo_periodo,
            "custo_mes_atual_usd": custo_mes,
        },
        "serie_diaria": serie_diaria,
        "top_modelos": top_modelos,
        "top_agentes": top_agentes,
        "budget_atual": budget_atual,
    }


# =====================================================================
# IA Budget — governança custo mensal (mig 058)
# =====================================================================

router_budget = APIRouter(
    prefix="/api/v1/ia-budget",
    tags=["governanca-ia"],
    dependencies=[Depends(verify_service_token)],
)

ACAO_ESTOURO_VALIDA = {"alertar", "bloquear", "redirecionar_menu"}


class UpsertBudgetInput(BaseModel):
    limite_usd: float = Field(ge=0, description="Limite mensal em USD")
    acao_estouro: str = "alertar"
    alerta_pct: int = Field(default=80, ge=1, le=100)
    ano_mes: str | None = Field(
        default=None,
        description="Formato YYYY-MM. Default = mês atual.",
    )

    @field_validator("acao_estouro")
    @classmethod
    def _validate_acao(cls, v: str) -> str:
        if v not in ACAO_ESTOURO_VALIDA:
            raise ValueError(
                f"acao_estouro deve ser um de {sorted(ACAO_ESTOURO_VALIDA)}"
            )
        return v


@router_budget.get("")
async def get_budget_endpoint(
    ano_mes: str | None = None,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    """Retorna budget do mês especificado (default = atual). None se não há."""
    pool = await get_pool()
    target = ano_mes or datetime.now().strftime("%Y-%m")
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, ano_mes, limite_usd, consumo_usd, acao_estouro,
                   alerta_pct, estourado_em, alertado_em, created_at, updated_at
              FROM ia_budget
             WHERE empresa_id = %s AND ano_mes = %s
            """,
            (empresa_id, target),
        )
        row = await cur.fetchone()
    if not row:
        return {"empresa_id": empresa_id, "ano_mes": target, "exists": False}
    return {
        "exists": True,
        "id": int(row[0]),
        "empresa_id": empresa_id,
        "ano_mes": row[1],
        "limite_usd": float(row[2]),
        "consumo_usd": float(row[3]),
        "acao_estouro": row[4],
        "alerta_pct": row[5],
        "estourado_em": row[6].isoformat() if row[6] else None,
        "alertado_em": row[7].isoformat() if row[7] else None,
        "created_at": row[8].isoformat() if row[8] else None,
        "updated_at": row[9].isoformat() if row[9] else None,
        "pct_consumo": round(float(row[3]) / float(row[2]) * 100, 2)
        if float(row[2]) > 0
        else 0,
    }


@router_budget.put("")
async def upsert_budget_endpoint(
    body: UpsertBudgetInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("agente.config")),
) -> dict:
    """UPSERT do budget do mês. consumo_usd preservado se já existe."""
    pool = await get_pool()
    target = body.ano_mes or datetime.now().strftime("%Y-%m")
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO ia_budget
                (empresa_id, ano_mes, limite_usd, acao_estouro, alerta_pct)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (empresa_id, ano_mes) DO UPDATE SET
                limite_usd = EXCLUDED.limite_usd,
                acao_estouro = EXCLUDED.acao_estouro,
                alerta_pct = EXCLUDED.alerta_pct,
                updated_at = NOW()
            RETURNING id, limite_usd, consumo_usd, acao_estouro, alerta_pct
            """,
            (empresa_id, target, Decimal(str(body.limite_usd)),
             body.acao_estouro, body.alerta_pct),
        )
        row = await cur.fetchone()
        await conn.commit()
    await record_audit(
        pool, empresa_id=empresa_id, user_id=user_id,
        action="ia_budget.upsert", entity_type="ia_budget",
        entity_id=str(row[0]) if row else target,
        payload_diff={"after": dict(body.model_dump(), ano_mes=target)},
        request=request,
    )
    return {
        "id": int(row[0]),
        "ano_mes": target,
        "limite_usd": float(row[1]),
        "consumo_usd": float(row[2]),
        "acao_estouro": row[3],
        "alerta_pct": row[4],
    }
