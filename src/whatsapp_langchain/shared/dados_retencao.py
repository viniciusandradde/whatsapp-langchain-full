"""Retenção de dados por tempo — Fase E do plano de 2026-09-15.

Apaga as mensagens (`message_queue`) e a mídia (objeto no bucket + registro em
`arquivo`) de atendimentos **encerrados** cujo fechamento passou do prazo de
retenção, e as threads do LangGraph que ficaram totalmente dormentes. **Mantém**
o registro do `atendimento` (metadados, CSAT, tags, ranking).

Prazo efetivo por atendimento = `max(empresa, agente)`:

- `empresa.retencao_dias` NULL ou 0  → ilimitado: a empresa inteira nunca é
  podada (o agente só ESTENDE, não pode encurtar o infinito).
- `agente.retencao_dias`  NULL       → herda a empresa.
- `agente.retencao_dias`  0          → ilimitado: aquele agente nunca é podado.
- `agente.retencao_dias`  N > 0      → `max(empresa, N)` — o agente só mantém
  MAIS tempo, nunca menos.

`agente_ia.slug` casa com `message_queue.agent_id` (o thread é
`{telefone}:{agent_id}`), então a extensão por agente é resolvida no próprio
SQL por linha da fila. Agente do catálogo (sem linha em `agente_ia`) herda a
empresa.

Relógio: conta a partir de `atendimento.closed_at`. Atendimento aberto nunca é
podado — mesmo critério do `checkpoint_retencao` (Fase 2).

RLS: `message_queue`/`atendimento`/`arquivo` têm FORCE RLS. A poda roda por
empresa dentro de `empresa_scope(empresa_id=eid)`, então todo SELECT/DELETE já
filtra pela empresa. O SELECT inicial de empresas usa bypass (a tabela
`empresa` é a raiz tenant, sem RLS). As tabelas do LangGraph não têm RLS — a
thread é apagada pelo `checkpointer.adelete_thread` (pool próprio, autocommit).

Dois workers em produção: um `pg_try_advisory_lock` (chave 8_642_011, distinta
de 8_642_010 do checkpoint) serializa a poda; o outro pula. É idempotente —
rodar de novo só apaga o que acumulou desde a última vez.
"""

from __future__ import annotations

from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()

# Chave da trava de sessão. Não colide com 8_642_000 (migrations),
# 8_642_001 (bootstrap LangGraph) nem 8_642_010 (retenção de checkpoints).
_ADVISORY_LOCK_KEY = 8_642_011

# Fragmento de WHERE que seleciona as linhas de `message_queue` (alias `mq`) de
# atendimentos (alias `a`) encerrados além do prazo efetivo. Recebe, nesta
# ordem, `empresa_id`, `empresa_id`, `empresa_dias`, `empresa_dias`.
#
# O filtro explícito por `empresa_id` é LOAD-BEARING, não redundante com o RLS:
# no dev o pool conecta como superuser (`postgres`), que BYPASSA o FORCE RLS —
# sem este filtro, a poda de uma empresa apagaria dados de TODAS. Em produção o
# app roda como `chat_nexus_app` (NOBYPASSRLS) e o RLS reforça, mas o filtro
# explícito é a mesma defesa-em-profundidade do `cleanup_zumbis`.
_ALVO_WHERE = """
    mq.empresa_id = %s
    AND a.empresa_id = %s
    AND a.closed_at IS NOT NULL
    AND a.closed_at < NOW() - make_interval(days => GREATEST(
          %s,
          COALESCE(
            (SELECT ag.retencao_dias FROM agente_ia ag
              WHERE ag.empresa_id = mq.empresa_id
                AND ag.slug = mq.agent_id
                AND ag.retencao_dias > 0),
            %s
          )
        ))
    AND NOT EXISTS (
          SELECT 1 FROM agente_ia ag2
           WHERE ag2.empresa_id = mq.empresa_id
             AND ag2.slug = mq.agent_id
             AND ag2.retencao_dias = 0
        )
"""


def retencao_efetiva_dias(
    empresa_dias: int | None, agente_dias: int | None
) -> int | None:
    """Prazo efetivo em dias, ou `None` para ilimitado (nunca apaga).

    Espelha exatamente a regra do SQL — é a fonte única da política, usada nos
    testes e no portão por-empresa. O agente só ESTENDE.
    """
    # Empresa: NULL ou 0 = ilimitado (piso infinito).
    emp = empresa_dias if (empresa_dias and empresa_dias > 0) else None

    if agente_dias is None:
        return emp  # herda a empresa
    if agente_dias == 0:
        return None  # agente ilimitado
    # agente N > 0: só estende. Se a empresa é ilimitada, o agente não encurta.
    if emp is None:
        return None
    return max(emp, agente_dias)


async def _threads_dormentes(
    pool: AsyncConnectionPool, empresa_id: int, empresa_dias: int
) -> list[str]:
    """Threads cujos atendimentos estão TODOS fechados além do prazo efetivo.

    Uma thread `{telefone}:{agent_id}` atravessa vários atendimentos (suporte
    contínuo) e tem um único agente. Só sai da base quando não há atendimento em
    aberto e o fechamento mais recente já passou do prazo efetivo do agente dela.
    Agente ilimitado (`retencao_dias = 0`) preserva a thread. Filtra por
    `empresa_id` explícito (o RLS é inerte no dev — ver `_ALVO_WHERE`).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT mq.thread_id
              FROM message_queue mq
              JOIN atendimento a ON a.id = mq.atendimento_id
              LEFT JOIN agente_ia ag
                ON ag.empresa_id = mq.empresa_id AND ag.slug = mq.agent_id
             WHERE mq.empresa_id = %s
               AND mq.thread_id IS NOT NULL
             GROUP BY mq.thread_id
            HAVING count(*) FILTER (WHERE a.closed_at IS NULL) = 0
               AND bool_or(ag.retencao_dias = 0) IS NOT TRUE
               AND max(a.closed_at) < NOW() - make_interval(days => GREATEST(
                     %s,
                     COALESCE(
                       max(ag.retencao_dias) FILTER (WHERE ag.retencao_dias > 0),
                       %s
                     )
                   ))
            """,
            (empresa_id, empresa_dias, empresa_dias),
        )
        rows = await cur.fetchall()
    return [r[0] for r in rows if r and isinstance(r[0], str)]


async def podar_empresa(
    pool: AsyncConnectionPool,
    empresa_id: int,
    empresa_dias: int,
    *,
    checkpointer: Any | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Poda uma empresa (piso `empresa_dias`, que já deve ser > 0).

    Roda DENTRO de `empresa_scope(empresa_id=eid)` (o chamador seta). Ordem:
    coletar threads dormentes e as mídias-alvo ANTES de apagar as linhas (senão
    perde a referência), apagar mídia (bucket + registro), apagar as linhas da
    fila, apagar as threads dormentes do checkpointer.
    """
    from whatsapp_langchain.shared import arquivo as arquivo_lib
    from whatsapp_langchain.shared import storage

    # 1. Threads que vão sair inteiras (lido antes de apagar a fila).
    threads = await _threads_dormentes(pool, empresa_id, empresa_dias)

    # 2. UUIDs de mídia das linhas-alvo (pra apagar objeto + registro).
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT DISTINCT mq.media_arquivo_uuid
              FROM message_queue mq
              JOIN atendimento a ON a.id = mq.atendimento_id
             WHERE {_ALVO_WHERE}
               AND mq.media_arquivo_uuid IS NOT NULL
            """,
            (empresa_id, empresa_id, empresa_dias, empresa_dias),
        )
        rows = await cur.fetchall()
    uuids = [str(r[0]) for r in rows if r and r[0] is not None]

    # Conta as linhas-alvo (pro dry_run e pro log).
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT count(*)
              FROM message_queue mq
              JOIN atendimento a ON a.id = mq.atendimento_id
             WHERE {_ALVO_WHERE}
            """,
            (empresa_id, empresa_id, empresa_dias, empresa_dias),
        )
        row = await cur.fetchone()
    mensagens_alvo = int(row[0]) if row else 0

    resultado: dict[str, Any] = {
        "empresa_id": empresa_id,
        "empresa_dias": empresa_dias,
        "mensagens_alvo": mensagens_alvo,
        "midias_alvo": len(uuids),
        "threads_alvo": len(threads),
        "dry_run": dry_run,
    }

    if dry_run:
        return resultado

    # 3. Apaga a mídia (objeto no bucket + registro em `arquivo`). Uma falha
    # isolada não trava o resto — a próxima rodada reprocessa (idempotente).
    midias_apagadas = 0
    for uuid in uuids:
        try:
            arq = await arquivo_lib.get_arquivo(pool, uuid)
            if arq is not None:
                await storage.apagar_midia(pool, arq)
                midias_apagadas += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "dados_retencao_midia_falhou",
                empresa_id=empresa_id,
                arquivo_uuid=uuid,
                error=str(exc),
            )

    # 4. Apaga as linhas da fila (o texto e o base64 legado da conversa).
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            DELETE FROM message_queue mq
             USING atendimento a
             WHERE mq.atendimento_id = a.id
               AND {_ALVO_WHERE}
            """,
            (empresa_id, empresa_id, empresa_dias, empresa_dias),
        )
        mensagens_apagadas = cur.rowcount
        await conn.commit()

    # 5. Apaga as threads dormentes do checkpointer (pool próprio, sem RLS).
    threads_apagadas = 0
    if checkpointer is not None:
        for thread_id in threads:
            try:
                await checkpointer.adelete_thread(thread_id)
                threads_apagadas += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "dados_retencao_thread_falhou",
                    empresa_id=empresa_id,
                    thread_id=thread_id,
                    error=str(exc),
                )

    resultado.update(
        {
            "midias_apagadas": midias_apagadas,
            "mensagens_apagadas": mensagens_apagadas,
            "threads_apagadas": threads_apagadas,
        }
    )
    logger.info("dados_retencao_empresa_ok", **resultado)
    return resultado


async def rodar_retencao_dados(
    pool: AsyncConnectionPool,
    *,
    checkpointer: Any | None = None,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Roda a retenção em todas as empresas ativas, sob a trava de sessão.

    Retorna `None` quando outro worker já está podando neste ciclo (não pegou a
    trava). Empresas com `retencao_dias` NULL/0 (ilimitado) são puladas — nada
    apaga sem o dono ter escolhido um prazo.
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope

    # Trava numa conexão dedicada mantida aberta por toda a operação (advisory
    # lock é por sessão; o trabalho abre outras conexões do pool livremente).
    with empresa_scope(None, bypass=True):
        async with pool.connection() as lock_conn:
            cur = await lock_conn.execute(
                "SELECT pg_try_advisory_lock(%s)", (_ADVISORY_LOCK_KEY,)
            )
            row = await cur.fetchone()
            got_lock = bool(row[0]) if row else False
            if not got_lock:
                logger.info("dados_retencao_pulou", motivo="outro_worker")
                return None

            try:
                async with pool.connection() as conn:
                    cur = await conn.execute(
                        "SELECT id, retencao_dias FROM empresa "
                        "WHERE status = 'active' ORDER BY id"
                    )
                    empresas = await cur.fetchall()

                resultados: list[dict[str, Any]] = []
                puladas = 0
                for eid, ret in empresas:
                    empresa_dias = retencao_efetiva_dias(ret, None)
                    if empresa_dias is None:
                        # Piso ilimitado: agente só estende → nada apaga.
                        puladas += 1
                        continue
                    try:
                        with empresa_scope(empresa_id=int(eid)):
                            r = await podar_empresa(
                                pool,
                                int(eid),
                                empresa_dias,
                                checkpointer=checkpointer,
                                dry_run=dry_run,
                            )
                        resultados.append(r)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "dados_retencao_empresa_falhou",
                            empresa_id=int(eid),
                            error=str(exc),
                        )
                        resultados.append({"empresa_id": int(eid), "error": str(exc)})
            finally:
                await lock_conn.execute(
                    "SELECT pg_advisory_unlock(%s)", (_ADVISORY_LOCK_KEY,)
                )

    total_msgs = sum(r.get("mensagens_apagadas", 0) for r in resultados)
    total_midias = sum(r.get("midias_apagadas", 0) for r in resultados)
    total_threads = sum(r.get("threads_apagadas", 0) for r in resultados)
    logger.info(
        "dados_retencao_ok",
        empresas_podadas=len(resultados),
        empresas_puladas=puladas,
        mensagens_apagadas=total_msgs,
        midias_apagadas=total_midias,
        threads_apagadas=total_threads,
        dry_run=dry_run,
    )
    return {
        "empresas_podadas": len(resultados),
        "empresas_puladas": puladas,
        "mensagens_apagadas": total_msgs,
        "midias_apagadas": total_midias,
        "threads_apagadas": total_threads,
        "dry_run": dry_run,
        "por_empresa": resultados,
    }
