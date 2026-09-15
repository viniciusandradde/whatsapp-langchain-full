"""Retenção de checkpoints do LangGraph — Fase 2 do plano de 2026-09-15.

Contexto em `.planning/reports/20260915-checkpoints-langgraph-plano.md` e na
regra do `CLAUDE.md`. A Fase 1 (PR #123) parou o vazamento de base64 no
`configurable`; esta fase poda o que se acumula.

Duas políticas, as duas seguras porque o app só usa `aget_state` (o checkpoint
MAIS RECENTE de cada thread), nunca `get_state_history` nem `checkpoint_id`
explícito — confirmado em `src/`:

1. `podar_para_ultimo_por_thread` — em cada `(thread_id, checkpoint_ns)` mantém
   só o `max(checkpoint_id)` (exatamente o que o `aget_tuple` devolve com
   `ORDER BY checkpoint_id DESC LIMIT 1`) e apaga o resto de `checkpoints` e
   `checkpoint_writes`. **Não toca `checkpoint_blobs`**: são ~22 MB, e podar
   exige cruzar `channel_versions` do sobrevivente — risco sem ganho. Todos os
   checkpoints são v4 (medido), então a migração de pending-sends (só v<4, que
   lê writes do checkpoint PAI) nunca dispara: apagar writes de checkpoint
   antigo é seguro.

2. `apagar_threads_encerradas` — threads cujos atendimentos estão todos fechados
   e o mais recente fechou há mais de `dias` dias → apaga a thread inteira via
   `checkpointer.adelete_thread` (existe em langgraph-checkpoint-postgres 3.0.4).
   O cliente que voltar depois começa conversa nova; a memória semântica
   (`store`, por telefone) é separada e sobrevive.

As tabelas do LangGraph não têm RLS (mig 101 as exclui de propósito) e o pool
do checkpointer roda em autocommit fora do wrapper RLS — por isso a poda usa
`checkpointer.conn`. O mapeamento thread→atendimento vem de `message_queue`/
`atendimento` (com RLS), lido com bypass porque é manutenção de sistema.

Produção roda dois workers. Um `pg_try_advisory_lock` serializa a poda: só um
worker roda por ciclo, o outro pula. Diferente do resumo diário (onde rodar 2×
mandaria a mensagem 2× ao cliente), a retenção é idempotente — rodar de novo só
apaga o que acumulou desde a última vez —, então não precisa de trava
"1×/dia", só da serialização pra dois DELETEs grandes não brigarem.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

# Chave da trava de sessão (não colide com 8_642_000 = migrations,
# 8_642_001 = bootstrap do LangGraph).
_ADVISORY_LOCK_KEY = 8_642_010


def _valor_unico(row):
    """Extrai o único valor de uma linha, seja ela dict (o pool do LangGraph
    usa `row_factory=dict_row`) ou tupla (pool da app)."""
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


async def podar_para_ultimo_por_thread(lg_pool) -> dict[str, int]:
    """Mantém só o checkpoint mais recente por `(thread_id, checkpoint_ns)`.

    Roda no pool do LangGraph (autocommit, sem RLS). `checkpoint_writes`
    primeiro, `checkpoints` depois — nunca deixa write órfão de checkpoint.
    """
    async with lg_pool.connection() as conn:
        cur = await conn.execute(
            """
            DELETE FROM checkpoint_writes cw
             USING (
               SELECT thread_id, checkpoint_ns, max(checkpoint_id) AS keep
                 FROM checkpoints
                GROUP BY thread_id, checkpoint_ns
             ) latest
             WHERE cw.thread_id = latest.thread_id
               AND cw.checkpoint_ns = latest.checkpoint_ns
               AND cw.checkpoint_id <> latest.keep
            """
        )
        writes_apagados = cur.rowcount
        cur = await conn.execute(
            """
            DELETE FROM checkpoints c
             USING (
               SELECT thread_id, checkpoint_ns, max(checkpoint_id) AS keep
                 FROM checkpoints
                GROUP BY thread_id, checkpoint_ns
             ) latest
             WHERE c.thread_id = latest.thread_id
               AND c.checkpoint_ns = latest.checkpoint_ns
               AND c.checkpoint_id <> latest.keep
            """
        )
        checkpoints_apagados = cur.rowcount
    return {
        "checkpoints_apagados": checkpoints_apagados,
        "writes_apagados": writes_apagados,
    }


async def _threads_encerradas(app_pool, dias: int) -> list[str]:
    """Threads cujos atendimentos estão TODOS fechados e o último fechou há
    mais de `dias` dias. Bypass de RLS: leitura de manutenção cross-empresa.

    Uma thread `{telefone}:{agente}` atravessa vários atendimentos (suporte
    contínuo). Só sai da base quando não há nenhum atendimento em aberto
    (`closed_at IS NULL`) e o fechamento mais recente já passou da janela.
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope

    with empresa_scope(None, bypass=True):
        async with app_pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT mq.thread_id
                  FROM message_queue mq
                  JOIN atendimento a ON a.id = mq.atendimento_id
                 WHERE mq.thread_id IS NOT NULL
                 GROUP BY mq.thread_id
                HAVING count(*) FILTER (WHERE a.closed_at IS NULL) = 0
                   AND max(a.closed_at) < NOW() - make_interval(days => %s)
                """,
                (dias,),
            )
            rows = await cur.fetchall()
    threads: list[str] = []
    for r in rows:
        thread_id = _valor_unico(r)
        if isinstance(thread_id, str):
            threads.append(thread_id)
    return threads


async def apagar_threads_encerradas(
    checkpointer, app_pool, dias: int
) -> dict[str, int]:
    """Apaga por inteiro as threads de atendimentos fechados há mais de `dias`."""
    threads = await _threads_encerradas(app_pool, dias)
    apagadas = 0
    for thread_id in threads:
        try:
            await checkpointer.adelete_thread(thread_id)
            apagadas += 1
        except Exception as exc:  # noqa: BLE001 — uma thread ruim não para o resto
            logger.warning(
                "checkpoint_adelete_thread_falhou",
                thread_id=thread_id,
                error=str(exc),
            )
    return {"threads_encerradas_apagadas": apagadas}


async def rodar_retencao(checkpointer, app_pool, dias: int) -> dict[str, int] | None:
    """Roda as duas políticas sob a trava de sessão. `None` = outro worker
    está podando neste ciclo (não conseguiu a trava)."""
    lg_pool = checkpointer.conn
    async with lg_pool.connection() as conn:
        cur = await conn.execute(
            "SELECT pg_try_advisory_lock(%s)", (_ADVISORY_LOCK_KEY,)
        )
        got_lock = bool(_valor_unico(await cur.fetchone()))
        if not got_lock:
            logger.info("checkpoint_retencao_pulou", motivo="outro_worker")
            return None
        try:
            resultado = await podar_para_ultimo_por_thread(lg_pool)
            resultado.update(
                await apagar_threads_encerradas(checkpointer, app_pool, dias)
            )
        finally:
            await conn.execute("SELECT pg_advisory_unlock(%s)", (_ADVISORY_LOCK_KEY,))
    logger.info("checkpoint_retencao_ok", **resultado)
    return resultado
