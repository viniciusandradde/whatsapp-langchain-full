"""Regras de negócio configuráveis pra agendamento (S3 Calendar v2).

Single row por empresa em `agendamento_regras`. CRUD via UPSERT.
Consumido por `shared/agendamento.validate_request` e
`shared/calendar_integration.find_free_slots`.

Quando empresa não tem row, retorna defaults sensatos (08-18, seg-sex,
60min antecedência) sem precisar criar row vazia.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timezone
from typing import Final

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import AgendamentoRegras

logger = structlog.get_logger()


# Defaults retornados quando empresa não tem row em agendamento_regras
# (em vez de exigir UPSERT inicial — UX simples).
DEFAULTS: Final[dict] = {
    "hora_inicio": "08:00",
    "hora_fim": "18:00",
    "antecedencia_minima_minutos": 60,
    "intervalo_entre_minutos": 0,
    "dias_semana_permitidos": [1, 2, 3, 4, 5],
    "dias_bloqueados": [],
    "requer_aprovacao": False,
}


def _format_time(value) -> str:
    """psycopg retorna time como datetime.time; converter pra 'HH:MM'."""
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)


def _row_to_regras(row, empresa_id: int) -> AgendamentoRegras:
    return AgendamentoRegras(
        empresa_id=empresa_id,
        hora_inicio=_format_time(row[0]),
        hora_fim=_format_time(row[1]),
        antecedencia_minima_minutos=row[2],
        intervalo_entre_minutos=row[3],
        dias_semana_permitidos=row[4] or [],
        dias_bloqueados=row[5] or [],
        requer_aprovacao=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


async def get(pool: AsyncConnectionPool, empresa_id: int) -> AgendamentoRegras:
    """Lê regras da empresa. Se não existe row, retorna defaults virtuais.

    Sem efeito colateral — não cria row implicitamente. UPSERT explícito
    via `upsert()` quando admin chama PUT.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT hora_inicio, hora_fim, antecedencia_minima_minutos,
                   intervalo_entre_minutos, dias_semana_permitidos,
                   dias_bloqueados, requer_aprovacao,
                   created_at, updated_at
              FROM agendamento_regras
             WHERE empresa_id = %s
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()

    if row is None:
        # Defaults virtuais sem persistir
        now = datetime.now(timezone.utc)
        return AgendamentoRegras(
            empresa_id=empresa_id,
            hora_inicio=DEFAULTS["hora_inicio"],
            hora_fim=DEFAULTS["hora_fim"],
            antecedencia_minima_minutos=DEFAULTS["antecedencia_minima_minutos"],
            intervalo_entre_minutos=DEFAULTS["intervalo_entre_minutos"],
            dias_semana_permitidos=list(DEFAULTS["dias_semana_permitidos"]),
            dias_bloqueados=list(DEFAULTS["dias_bloqueados"]),
            requer_aprovacao=DEFAULTS["requer_aprovacao"],
            created_at=now,
            updated_at=now,
        )

    return _row_to_regras(row, empresa_id)


async def upsert(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    hora_inicio: str | None = None,
    hora_fim: str | None = None,
    antecedencia_minima_minutos: int | None = None,
    intervalo_entre_minutos: int | None = None,
    dias_semana_permitidos: list[int] | None = None,
    dias_bloqueados: list[str] | None = None,
    requer_aprovacao: bool | None = None,
) -> AgendamentoRegras:
    """UPSERT por empresa_id. Campos None mantêm valor existente (ou default no INSERT).

    Validações de hora (formato HH:MM) e dias_semana (1-7) ficam no caller.
    """
    # Resolve valores: None → existing/default. Como o INSERT usa COALESCE
    # do que já está na row, simplificamos chamando UPDATE primeiro pra
    # preservar campos não-passados, depois fallback INSERT.
    current = await get(pool, empresa_id)

    novo = {
        "hora_inicio": hora_inicio if hora_inicio is not None else current.hora_inicio,
        "hora_fim": hora_fim if hora_fim is not None else current.hora_fim,
        "antecedencia_minima_minutos": (
            antecedencia_minima_minutos
            if antecedencia_minima_minutos is not None
            else current.antecedencia_minima_minutos
        ),
        "intervalo_entre_minutos": (
            intervalo_entre_minutos
            if intervalo_entre_minutos is not None
            else current.intervalo_entre_minutos
        ),
        "dias_semana_permitidos": (
            dias_semana_permitidos
            if dias_semana_permitidos is not None
            else current.dias_semana_permitidos
        ),
        "dias_bloqueados": (
            dias_bloqueados
            if dias_bloqueados is not None
            else current.dias_bloqueados
        ),
        "requer_aprovacao": (
            requer_aprovacao
            if requer_aprovacao is not None
            else current.requer_aprovacao
        ),
    }

    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO agendamento_regras
                (empresa_id, hora_inicio, hora_fim,
                 antecedencia_minima_minutos, intervalo_entre_minutos,
                 dias_semana_permitidos, dias_bloqueados, requer_aprovacao)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (empresa_id) DO UPDATE SET
                hora_inicio = EXCLUDED.hora_inicio,
                hora_fim = EXCLUDED.hora_fim,
                antecedencia_minima_minutos = EXCLUDED.antecedencia_minima_minutos,
                intervalo_entre_minutos = EXCLUDED.intervalo_entre_minutos,
                dias_semana_permitidos = EXCLUDED.dias_semana_permitidos,
                dias_bloqueados = EXCLUDED.dias_bloqueados,
                requer_aprovacao = EXCLUDED.requer_aprovacao,
                updated_at = NOW()
            """,
            (
                empresa_id,
                novo["hora_inicio"],
                novo["hora_fim"],
                novo["antecedencia_minima_minutos"],
                novo["intervalo_entre_minutos"],
                json.dumps(novo["dias_semana_permitidos"]),
                json.dumps(novo["dias_bloqueados"]),
                novo["requer_aprovacao"],
            ),
        )
        await conn.commit()

    logger.info(
        "agendamento_regras_upserted",
        empresa_id=empresa_id,
        hora_inicio=novo["hora_inicio"],
        hora_fim=novo["hora_fim"],
        antecedencia=novo["antecedencia_minima_minutos"],
    )

    return await get(pool, empresa_id)
