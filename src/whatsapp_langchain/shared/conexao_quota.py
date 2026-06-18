"""Teto diário de envios por conexão + aquecimento (warm-up) — anti-ban.

Contexto: número novo + volume alto = sinal de spam pro WhatsApp (foi o que
restringiu o número da campanha 9). Duas defesas, ambas por conexão:

- **Teto diário** (`conexao.daily_send_cap`): limite manual de mensagens/dia.
- **Aquecimento** (`conexao.warmup_started_at`): curva crescente nos primeiros
  dias de um número novo — dia 0 ≈ 20 msgs, ~1.8x/dia, graduando em ~8 dias.

O teto EFETIVO do dia é o menor entre o teto manual e a curva de aquecimento.
O contador `conexao_envio_diario` (mig 126) registra quanto já saiu hoje; o
dispatcher consulta antes de cada envio e reagenda a campanha pro dia seguinte
ao bater o teto (o disparo "pinga" ao longo dos dias = aquecimento na prática).
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Conexao

# Curva de aquecimento: dia0=20, *1.8/dia, graduando no dia WARMUP_DIAS.
WARMUP_BASE = 20
WARMUP_FACTOR = 1.8
WARMUP_DIAS = 8  # a partir daqui, sem teto de aquecimento (só o manual vale)


def warmup_cap_for_day(dias: int) -> int | None:
    """Teto da curva de aquecimento para o N-ésimo dia (0-indexado).

    Retorna None quando o número já "graduou" (>= WARMUP_DIAS) — aí só o
    teto manual (se houver) limita.
    """
    if dias < 0:
        dias = 0
    if dias >= WARMUP_DIAS:
        return None
    return int(round(WARMUP_BASE * (WARMUP_FACTOR**dias)))


def effective_cap(
    daily_send_cap: int | None, dias_aquecimento: int | None
) -> tuple[int | None, str | None]:
    """Combina teto manual + curva de aquecimento → (teto_efetivo, motivo).

    `dias_aquecimento` None = aquecimento desligado. Retorna o menor teto e um
    rótulo do que está limitando ('aquecimento (dia N)' | 'teto manual' | None).
    """
    warm = (
        warmup_cap_for_day(dias_aquecimento) if dias_aquecimento is not None else None
    )
    candidatos: list[tuple[int, str]] = []
    if daily_send_cap is not None:
        candidatos.append((daily_send_cap, "teto manual"))
    if warm is not None:
        candidatos.append((warm, f"aquecimento (dia {dias_aquecimento})"))
    if not candidatos:
        return None, None
    cap, motivo = min(candidatos, key=lambda c: c[0])
    return cap, motivo


@dataclass
class QuotaStatus:
    cap: int | None  # teto efetivo do dia (None = ilimitado)
    usados: int  # envios já feitos hoje por esta conexão
    restante: int | None  # cap - usados (None = ilimitado); nunca negativo
    motivo: str | None  # rótulo do teto ativo


async def quota_status(pool: AsyncConnectionPool, conexao: Conexao) -> QuotaStatus:
    """Calcula o teto efetivo do dia e quanto resta para esta conexão."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
                COALESCE((SELECT enviados FROM conexao_envio_diario
                          WHERE conexao_id = %s AND dia = CURRENT_DATE), 0),
                CASE WHEN %s::timestamptz IS NULL THEN NULL
                     ELSE (CURRENT_DATE - (%s::timestamptz)::date) END
            """,
            (conexao.id, conexao.warmup_started_at, conexao.warmup_started_at),
        )
        row = await cur.fetchone()
    usados = int(row[0]) if row else 0
    dias = row[1] if row else None
    cap, motivo = effective_cap(conexao.daily_send_cap, dias)
    restante = None if cap is None else max(0, cap - usados)
    return QuotaStatus(cap=cap, usados=usados, restante=restante, motivo=motivo)


async def incr_uso_hoje(
    conn: AsyncConnection, empresa_id: int, conexao_id: int, n: int = 1
) -> None:
    """Incrementa o contador de envios de hoje (UPSERT idempotente por dia).

    Recebe uma conexão já aberta para participar da mesma transação do
    `UPDATE campanha SET enviados = enviados + 1` do dispatcher.
    """
    await conn.execute(
        """
        INSERT INTO conexao_envio_diario (empresa_id, conexao_id, dia, enviados)
        VALUES (%s, %s, CURRENT_DATE, %s)
        ON CONFLICT (conexao_id, dia)
        DO UPDATE SET enviados = conexao_envio_diario.enviados + EXCLUDED.enviados,
                      updated_at = NOW()
        """,
        (empresa_id, conexao_id, n),
    )
