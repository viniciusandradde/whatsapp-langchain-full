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


# Prefixo do `source_trace_id` sintético da fonte CSAT. Reusa o índice único
# `ux_fewshot_source_trace (empresa_id, source_trace_id)` da mig 137 — a
# idempotência sai de graça e sem migration nova.
_CSAT_PREFIX = "csat:"

# Mesmo truque para a fonte LangSmith: o run não tem coluna própria no banco
# (a mig 107 só criou `langfuse_trace_id`), então o vínculo vive no
# `source_trace_id` prefixado — e a correlação run→mensagem é feita na hora.
_LANGSMITH_PREFIX = "langsmith:"


async def ingest_from_langsmith(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    score_name: str = "nps",
    min_score: float = 8.0,
    days: int = 30,
    dry_run: bool = False,
) -> dict:
    """Ingesta runs do LangSmith com feedback bom como few-shots.

    O equivalente do caminho Langfuse, com uma diferença estrutural: não há
    coluna `langsmith_run_id` no banco (a mig 107 é só Langfuse). O vínculo
    run→diálogo local é feito por **correlação**: o run raiz carrega
    `metadata.thread_id = "{phone}:{agent_slug}"` (contrato do worker) e o
    `start_time`; a mensagem local é a linha de `message_queue` do mesmo
    telefone/agente na janela de ±5 minutos mais próxima do run.

    A nota vem do **feedback** do LangSmith (`score_name`, default "nps") —
    anotações feitas na UI de revisão ou via API. Sem feedback lá, esta fonte
    devolve zero com o motivo explícito no contador, não um zero mudo.
    """
    resultado = {
        "feedbacks_lidos": 0,
        "cruzados": 0,
        "novos": 0,
        "skipped": 0,
        "dry_run": dry_run,
    }
    from datetime import datetime, timedelta

    from langsmith import Client

    from whatsapp_langchain.shared.config import settings

    api_key = (
        settings.langchain_api_key.get_secret_value()
        if settings.langchain_api_key
        else None
    )
    if not api_key or not settings.langchain_project:
        return resultado

    client = Client(api_key=api_key)
    projeto = client.read_project(project_name=settings.langchain_project)
    corte = datetime.now(UTC) - timedelta(days=days)

    # feedback → melhor score por trace raiz (só do projeto de produção;
    # experiments de eval têm session própria e ficam de fora)
    from typing import Any

    bons: dict[str, tuple[float, Any]] = {}
    for fb in client.list_feedback(feedback_key=[score_name], limit=500):
        resultado["feedbacks_lidos"] += 1
        if fb.score is None or float(fb.score) < min_score:
            continue
        if fb.created_at and fb.created_at.replace(tzinfo=UTC) < corte:
            continue
        if fb.run_id is None:
            continue
        try:
            run = client.read_run(fb.run_id)
        except Exception:  # noqa: BLE001 — run apagado/sem acesso: pula
            continue
        if str(run.session_id) != str(projeto.id):
            continue
        raiz = run if not run.trace_id or run.trace_id == run.id else None
        if raiz is None:
            try:
                raiz = client.read_run(run.trace_id)
            except Exception:  # noqa: BLE001
                continue
        atual = bons.get(str(raiz.id))
        if atual is None or float(fb.score) > atual[0]:
            bons[str(raiz.id)] = (float(fb.score), raiz)

    if not bons:
        return resultado

    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            for trace_id, (score, raiz) in bons.items():
                meta = (raiz.extra or {}).get("metadata", {})
                thread = str(meta.get("thread_id", ""))
                if ":" not in thread:
                    continue
                phone, agent_slug = thread.rsplit(":", 1)
                cur = await conn.execute(
                    """
                    SELECT incoming_message, response, atendimento_id
                      FROM message_queue
                     WHERE empresa_id = %s
                       AND phone_number = %s
                       AND agent_id = %s
                       AND response IS NOT NULL
                       AND incoming_message IS NOT NULL
                       AND created_at BETWEEN %s - interval '5 minutes'
                                          AND %s + interval '1 minute'
                     ORDER BY abs(extract(epoch from (created_at - %s)))
                     LIMIT 1
                    """,
                    (
                        empresa_id,
                        phone,
                        agent_slug,
                        raiz.start_time,
                        raiz.start_time,
                        raiz.start_time,
                    ),
                )
                linha = await cur.fetchone()
                if not linha:
                    continue
                resultado["cruzados"] += 1
                cliente_msg, resposta, atendimento_id = linha
                cliente_norm = redact_pii(cliente_msg or "", mode="mask").text.strip()
                resp_norm = redact_pii(resposta or "", mode="mask").text.strip()
                if not cliente_norm or not resp_norm:
                    continue
                if dry_run:
                    resultado["novos"] += 1
                    continue
                ins = await conn.execute(
                    """
                    INSERT INTO fewshot_example
                        (empresa_id, agente_slug, cliente_msg, agente_resposta,
                         outcome, csat_nota, atendimento_id, status,
                         source_trace_id, fonte)
                    VALUES (%s, %s, %s, %s, 'success', %s, %s, 'pending',
                            %s, 'langsmith')
                    ON CONFLICT (empresa_id, source_trace_id)
                        WHERE source_trace_id IS NOT NULL
                    DO NOTHING
                    """,
                    (
                        empresa_id,
                        agent_slug or "atendimento",
                        cliente_norm,
                        resp_norm,
                        int(round(score)),
                        atendimento_id,
                        f"{_LANGSMITH_PREFIX}{trace_id}",
                    ),
                )
                if ins.rowcount and ins.rowcount > 0:
                    resultado["novos"] += 1
                else:
                    resultado["skipped"] += 1
            if not dry_run:
                await conn.commit()

    logger.info("langsmith_dataset_ingest", empresa_id=empresa_id, **resultado)
    return resultado


async def ingest_from_csat(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    min_score: float = 8.0,
    days: int = 30,
    dry_run: bool = False,
) -> dict:
    """Golden examples a partir da avaliação que o próprio cliente deu.

    A nota do CSAT/NPS já é nossa (`atendimento_avaliacao`, mig 073) e liga ao
    diálogo por `atendimento_id` — não depende de provedor de trace nenhum. Em
    produção rende ~120 candidatos, contra 6 que o caminho Langfuse rendeu antes
    de ser desligado.

    Idempotente pelo mesmo índice único do caminho Langfuse, com
    `source_trace_id = 'csat:<message_queue.id>'`.
    """
    resultado = {
        "candidatos": 0,
        "novos": 0,
        "skipped": 0,
        "dry_run": dry_run,
    }
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT mq.id, mq.incoming_message, mq.response,
                       mq.agent_id, mq.atendimento_id, av.nota
                  FROM atendimento_avaliacao av
                  JOIN message_queue mq ON mq.atendimento_id = av.atendimento_id
                 WHERE av.empresa_id = %s
                   AND av.nota >= %s
                   AND av.created_at > NOW() - make_interval(days => %s)
                   AND mq.response IS NOT NULL
                   AND mq.incoming_message IS NOT NULL
                """,
                (empresa_id, min_score, days),
            )
            linhas = await cur.fetchall()
            resultado["candidatos"] = len(linhas)

            for mq_id, cliente_msg, resposta, agent_id, atendimento_id, nota in linhas:
                cliente_norm = redact_pii(cliente_msg or "", mode="mask").text.strip()
                resp_norm = redact_pii(resposta or "", mode="mask").text.strip()
                if not cliente_norm or not resp_norm:
                    continue
                if dry_run:
                    resultado["novos"] += 1
                    continue
                ins = await conn.execute(
                    """
                    INSERT INTO fewshot_example
                        (empresa_id, agente_slug, cliente_msg, agente_resposta,
                         outcome, csat_nota, atendimento_id, status,
                         source_trace_id, fonte)
                    VALUES (%s, %s, %s, %s, 'success', %s, %s, 'pending',
                            %s, 'csat')
                    ON CONFLICT (empresa_id, source_trace_id)
                        WHERE source_trace_id IS NOT NULL
                    DO NOTHING
                    """,
                    (
                        empresa_id,
                        agent_id or "atendimento",
                        cliente_norm,
                        resp_norm,
                        int(round(float(nota))),
                        atendimento_id,
                        f"{_CSAT_PREFIX}{mq_id}",
                    ),
                )
                if ins.rowcount and ins.rowcount > 0:
                    resultado["novos"] += 1
                else:
                    resultado["skipped"] += 1
            if not dry_run:
                await conn.commit()

    logger.info("csat_dataset_ingest", empresa_id=empresa_id, **resultado)
    return resultado


async def ingest_gold(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    min_score: float = 8.0,
    days: int = 30,
    dry_run: bool = False,
) -> dict:
    """Gera golden examples somando as fontes disponíveis.

    **Fonte sempre presente:** o CSAT local. **Fonte adicional:** o provedor de
    observabilidade ativo, o mesmo que a tela `/traces` mostra — antes daqui o
    auto-dataset falava com o Langfuse hardcoded, então continuava batendo num
    host desligado mesmo depois de o admin escolher LangSmith.

    Devolve `avisos` com o que **não** pôde ser feito. Isso é o ponto: até aqui,
    "provedor fora do ar" e "nenhuma conversa qualificou" produziam o mesmo `0`,
    e a tela mostrava esse zero como se fosse resposta.
    """
    from whatsapp_langchain.shared import langfuse_client
    from whatsapp_langchain.shared.obs_provider import (
        langfuse_configurado,
        provider_efetivo,
    )

    avisos: list[str] = []
    por_fonte: dict[str, dict] = {}

    por_fonte["csat"] = await ingest_from_csat(
        pool, empresa_id, min_score=min_score, days=days, dry_run=dry_run
    )

    provider = await provider_efetivo()
    if provider == "langfuse":
        if langfuse_client.ping():
            por_fonte["langfuse"] = await ingest_from_langfuse(
                pool, empresa_id, min_score=min_score, days=days, dry_run=dry_run
            )
        else:
            avisos.append(
                "Langfuse está configurado mas não respondeu — nenhuma conversa "
                "veio dele nesta rodada. As chaves seguem no ambiente mesmo com "
                "os containers desligados, por isso ele aparece como ativo."
            )
    elif provider == "langsmith":
        try:
            por_fonte["langsmith"] = await ingest_from_langsmith(
                pool, empresa_id, min_score=min_score, days=days, dry_run=dry_run
            )
            if por_fonte["langsmith"].get("feedbacks_lidos", 0) == 0:
                avisos.append(
                    "LangSmith é o provedor ativo, mas nenhum trace tem "
                    "feedback ('nps') no período — anote conversas boas na "
                    "revisão do LangSmith para que elas somem ao dataset. "
                    "Esta rodada usou a avaliação dos clientes."
                )
        except Exception as e:  # noqa: BLE001 — provedor fora não derruba a rodada
            logger.warning("langsmith_dataset_ingest_falhou", erro=str(e)[:200])
            avisos.append(
                "LangSmith é o provedor ativo mas a consulta falhou "
                "nesta rodada — usada apenas a avaliação dos clientes."
            )
    else:
        avisos.append(
            "Nenhum provedor de observabilidade ativo. Esta rodada usou apenas "
            "a avaliação dos clientes."
        )
    if langfuse_configurado() and provider != "langfuse":
        avisos.append(
            "Dica: o Langfuse tem credencial configurada. Ao religá-lo, "
            "selecione-o em Observabilidade → Traces pra somar os traces "
            "avaliados ao dataset."
        )

    novos = sum(f.get("novos", 0) for f in por_fonte.values())
    skipped = sum(f.get("skipped", 0) for f in por_fonte.values())
    resultado = {
        "novos": novos,
        "skipped": skipped,
        "dry_run": dry_run,
        "provider": provider,
        "por_fonte": por_fonte,
        "avisos": avisos,
    }
    logger.info(
        "dataset_gold_ingest",
        empresa_id=empresa_id,
        novos=novos,
        skipped=skipped,
        provider=provider,
        avisos=len(avisos),
    )
    return resultado
