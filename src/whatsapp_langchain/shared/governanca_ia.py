"""Governança IA — registro de execução LLM + budget mensal.

Versão mínima focada no callback handler do worker:
- registrar_execucao: INSERT ia_execucao
- acrescentar_consumo: UPSERT ia_budget (incrementa consumo_usd do mês)
- get_custo_modelo: lookup custos pra cálculo
- get_budget_atual: leitura pra check pré-call
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


# Proveniência do custo gravado em `ia_execucao.custo_fonte`. Existe pra que
# relatório nunca mais misture medido com estimado sem avisar — foi assim que
# um erro de +91% passou despercebido até alguém questionar o número.
CUSTO_FONTE_OPENROUTER = "openrouter"  # veio do `usage.cost` da resposta
CUSTO_FONTE_TABELA = "tabela"  # estimado por `modelo_llm` (fallback)


async def get_custo_modelo(
    pool: AsyncConnectionPool,
    empresa_id: int,
    provedor: str,
    nome: str,
) -> tuple[float | None, float | None, float | None]:
    """Retorna (custo_input_mtok, custo_output_mtok, custo_cache_mtok).

    Só usado como FALLBACK: o caminho normal grava o `usage.cost` que a
    OpenRouter devolve, que é o valor realmente cobrado. Esta tabela não
    consegue acompanhar o preço real — a OpenRouter roteia entre provedores
    upstream com preços distintos (medido: 0.2072 USD/Mtok de prompt no
    deepseek-v3.2 contra 0.269 listados no catálogo).

    Prioriza override empresa-scoped; cai pra global. (None, None, None) se
    modelo não cadastrado.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT custo_input_mtok, custo_output_mtok, custo_cache_mtok
              FROM modelo_llm
             WHERE provedor = %s AND nome = %s AND ativo
               AND (empresa_id = %s OR empresa_id IS NULL)
             ORDER BY empresa_id DESC NULLS LAST  -- empresa-scoped vence global
             LIMIT 1
            """,
            (provedor, nome, empresa_id),
        )
        row = await cur.fetchone()
    if not row:
        return (None, None, None)
    return (
        float(row[0]) if row[0] is not None else None,
        float(row[1]) if row[1] is not None else None,
        float(row[2]) if row[2] is not None else None,
    )


def calc_custo(
    tokens_input: int,
    tokens_output: int,
    custo_input_mtok: float | None,
    custo_output_mtok: float | None,
    tokens_cached: int = 0,
    custo_cache_mtok: float | None = None,
) -> float | None:
    """Estima custo USD por USD/M tokens. None se preço ausente.

    FALLBACK apenas — preferir o `usage.cost` da OpenRouter, que é o valor
    cobrado de fato.

    `tokens_cached` é SUBCONJUNTO de `tokens_input` (padrão OpenAI-compatible:
    `prompt_tokens_details.cached_tokens` conta tokens já dentro de
    `prompt_tokens`). Ignorar isso foi o bug original: com 96,5% de cache hit,
    cobrar tudo a preço cheio superestimou o custo em 91% (13,32 contra 6,96
    USD reais).

    Sem `custo_cache_mtok` cadastrado, o cache é cobrado a preço de input —
    conservador (superestima) em vez de silenciosamente zerar o custo.
    """
    if custo_input_mtok is None and custo_output_mtok is None:
        return None

    custo = 0.0
    if custo_input_mtok is not None:
        # clamp: cached > input só acontece com dado inconsistente do provider;
        # sem isso `nao_cacheado` fica negativo e o custo sai abaixo do real.
        cacheado = max(0, min(tokens_cached, tokens_input))
        nao_cacheado = tokens_input - cacheado
        preco_cache = (
            custo_cache_mtok if custo_cache_mtok is not None else custo_input_mtok
        )
        custo += (nao_cacheado / 1_000_000) * custo_input_mtok
        custo += (cacheado / 1_000_000) * preco_cache
    if custo_output_mtok is not None:
        custo += (tokens_output / 1_000_000) * custo_output_mtok
    return round(custo, 8)


async def registrar_execucao(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    modelo_provedor: str,
    modelo_nome: str,
    tokens_input: int = 0,
    tokens_output: int = 0,
    tokens_cached: int = 0,
    custo_total: float | None = None,
    duracao_ms: int | None = None,
    tools_chamadas: list[str] | None = None,
    status: str = "success",
    erro_msg: str | None = None,
    atendimento_id: int | None = None,
    agente_ia_id: int | None = None,
    metadata: dict | None = None,
    langfuse_trace_id: str | None = None,
    custo_fonte: str | None = None,
    openrouter_generation_id: str | None = None,
) -> int:
    """Grava ia_execucao. Best-effort — falhas só logam, retorna 0.

    `custo_fonte` diz se `custo_total` foi MEDIDO (`openrouter`) ou ESTIMADO
    (`tabela`). `openrouter_generation_id` permite auditar a linha depois
    contra `GET /api/v1/generation?id=`.
    """
    import json

    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO ia_execucao
                    (empresa_id, atendimento_id, agente_ia_id,
                     modelo_provedor, modelo_nome,
                     tokens_input, tokens_output, tokens_cached,
                     custo_total, duracao_ms, tools_chamadas,
                     status, erro_msg, metadata, langfuse_trace_id,
                     custo_fonte, openrouter_generation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::text[], %s, %s, %s::jsonb, %s, %s, %s)
                RETURNING id
                """,
                (
                    empresa_id,
                    atendimento_id,
                    agente_ia_id,
                    modelo_provedor,
                    modelo_nome,
                    tokens_input,
                    tokens_output,
                    tokens_cached,
                    Decimal(str(custo_total)) if custo_total is not None else None,
                    duracao_ms,
                    list(tools_chamadas or []),
                    status,
                    erro_msg,
                    json.dumps(metadata or {}),
                    langfuse_trace_id,
                    custo_fonte,
                    openrouter_generation_id,
                ),
            )
            row = await cur.fetchone()
            await conn.commit()
        return int(row[0]) if row else 0
    except Exception as exc:
        logger.warning("ia_execucao_register_failed", error=str(exc))
        return 0


async def acrescentar_consumo(
    pool: AsyncConnectionPool, empresa_id: int, valor_usd: float
) -> None:
    """Soma valor ao consumo_usd do mês atual (UPSERT). Best-effort.

    Este INSERT é quem cria a linha do mês — o débito chega antes de qualquer
    tela. Por isso ele herda `limite_usd`/`acao_estouro`/`alerta_pct` do mês
    configurado mais recente: sem isso o teto voltava a zero todo dia primeiro
    e só reaparecia se alguém abrisse a tela de novo. E como `get_budget_atual`
    lê limite zero como "sem teto", o mês órfão ficava indistinguível de uma
    empresa que nunca configurou nada — nenhum alerta, nenhum bloqueio.

    `ano_mes` é CHAR(7) no formato YYYY-MM, então ordem alfabética é ordem
    cronológica e `ORDER BY ano_mes DESC` acha mesmo o mês anterior (pode ser
    mais de um mês atrás, se a empresa ficou parada).

    O consumo NÃO é herdado: começa do zero no mês novo.
    """
    if valor_usd <= 0:
        return
    ano_mes = datetime.now().strftime("%Y-%m")
    try:
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO ia_budget
                    (empresa_id, ano_mes, limite_usd, consumo_usd,
                     acao_estouro, alerta_pct)
                SELECT %s, %s,
                       COALESCE(p.limite_usd, 0), %s,
                       COALESCE(p.acao_estouro, 'alertar'),
                       COALESCE(p.alerta_pct, 80)
                  FROM (SELECT 1) AS _
                  LEFT JOIN LATERAL (
                      SELECT limite_usd, acao_estouro, alerta_pct
                        FROM ia_budget
                       WHERE empresa_id = %s AND ano_mes < %s
                       ORDER BY ano_mes DESC
                       LIMIT 1
                  ) p ON TRUE
                ON CONFLICT (empresa_id, ano_mes) DO UPDATE SET
                    consumo_usd = ia_budget.consumo_usd + EXCLUDED.consumo_usd,
                    updated_at = NOW()
                """,
                (
                    empresa_id,
                    ano_mes,
                    Decimal(str(valor_usd)),
                    empresa_id,
                    ano_mes,
                ),
            )
            await conn.commit()
    except Exception as exc:
        logger.warning("ia_budget_update_failed", error=str(exc))


async def get_budget_atual(pool: AsyncConnectionPool, empresa_id: int) -> dict | None:
    """Retorna budget do mês atual ou None se não configurado.

    Estrutura: {limite_usd, consumo_usd, acao_estouro, alerta_pct,
                pct_consumo, estourado}
    """
    ano_mes = datetime.now().strftime("%Y-%m")
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT limite_usd, consumo_usd, acao_estouro, alerta_pct,
                   acao_limite_menu_id
              FROM ia_budget b
              LEFT JOIN agente_ia a ON FALSE  -- placeholder; menu_id vem do agente
             WHERE b.empresa_id = %s AND b.ano_mes = %s
             LIMIT 1
            """,
            (empresa_id, ano_mes),
        )
        row = await cur.fetchone()
    if not row:
        return None
    limite = float(row[0])
    consumo = float(row[1])
    pct = round((consumo / limite * 100), 2) if limite > 0 else 0
    return {
        "limite_usd": limite,
        "consumo_usd": consumo,
        "acao_estouro": row[2],
        "alerta_pct": row[3],
        "pct_consumo": pct,
        "estourado": consumo >= limite if limite > 0 else False,
    }
