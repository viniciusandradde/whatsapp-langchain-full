"""Auto-dataset via Langfuse (Fase 1) — golden examples do feedback real.

Fecha o loop de qualidade: o Langfuse guarda o score de satisfação (NPS 0-10
que o CSAT grava via `post_score` name="nps"); o conteúdo do diálogo está no
banco local (`message_queue`, ligado por `langfuse_trace_id`, mig 107). Este
módulo cruza os dois: traces bem avaliadas viram few-shots (golden) de forma
IDEMPOTENTE — re-rodar só insere traces novas (índice único source_trace_id,
mig 137).

Padrão de idempotência espelhado de `langsmith_sync.py` (dedup por chave;
re-run só insere novos). Normalização de PII espelhada de dataset_import.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared import langfuse_client
from whatsapp_langchain.shared.guardrails import redact_pii
from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()


async def ingest_from_langfuse(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    score_name: str = "nps",
    min_score: float = 8.0,
    days: int = 30,
    dry_run: bool = False,
) -> dict:
    """Ingesta traces bem avaliadas (score >= min_score) como few-shots.

    Retorna contadores: scores_lidos, cruzados (com conteúdo no banco), novos
    (inseridos), skipped (já existiam / re-run). status='pending' → o
    backfill de embeddings (endpoint existente) promove a 'ready'.
    """
    from_ts = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    scores = langfuse_client.list_scores(name=score_name, from_timestamp=from_ts)

    # trace_id → melhor score (bom o bastante)
    bons: dict[str, float] = {}
    for s in scores:
        tid = s.get("traceId") or s.get("trace_id")
        val = s.get("value")
        if not tid or val is None:
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v >= min_score and v > bons.get(tid, -1.0):
            bons[tid] = v

    resultado = {
        "scores_lidos": len(scores),
        "cruzados": 0,
        "novos": 0,
        "skipped": 0,
        "dry_run": dry_run,
    }
    if not bons:
        return resultado

    trace_ids = list(bons.keys())
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            # Conteúdo do diálogo vem do banco local (não do Langfuse).
            cur = await conn.execute(
                """
                SELECT langfuse_trace_id, incoming_message, response,
                       agent_id, atendimento_id
                  FROM message_queue
                 WHERE empresa_id = %s
                   AND langfuse_trace_id = ANY(%s)
                   AND response IS NOT NULL
                   AND incoming_message IS NOT NULL
                """,
                (empresa_id, trace_ids),
            )
            linhas = await cur.fetchall()
            resultado["cruzados"] = len(linhas)

            for trace_id, cliente_msg, resposta, agent_id, atendimento_id in linhas:
                cliente_norm = redact_pii(cliente_msg or "", mode="mask").text.strip()
                resp_norm = redact_pii(resposta or "", mode="mask").text.strip()
                if not cliente_norm or not resp_norm:
                    continue
                if dry_run:
                    resultado["novos"] += 1
                    continue
                # Idempotente: ON CONFLICT no índice único (empresa, trace).
                ins = await conn.execute(
                    """
                    INSERT INTO fewshot_example
                        (empresa_id, agente_slug, cliente_msg, agente_resposta,
                         outcome, csat_nota, atendimento_id, status,
                         source_trace_id, fonte)
                    VALUES (%s, %s, %s, %s, 'success', %s, %s, 'pending',
                            %s, 'langfuse')
                    ON CONFLICT (empresa_id, source_trace_id)
                        WHERE source_trace_id IS NOT NULL
                    DO NOTHING
                    """,
                    (
                        empresa_id,
                        agent_id or "vsa_tech",
                        cliente_norm,
                        resp_norm,
                        int(round(bons[trace_id])),
                        atendimento_id,
                        trace_id,
                    ),
                )
                if ins.rowcount and ins.rowcount > 0:
                    resultado["novos"] += 1
                else:
                    resultado["skipped"] += 1
            if not dry_run:
                await conn.commit()

    logger.info("langfuse_dataset_ingest", empresa_id=empresa_id, **resultado)
    return resultado
