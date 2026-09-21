"""Entry point do Worker — loop de processamento de mensagens.

Inicia o Worker que consome mensagens da fila PostgreSQL em loop.
Cada mensagem é processada pelo agente configurado.

Uso:
    python -m whatsapp_langchain.worker.main
"""

import asyncio
import contextlib
import signal

import structlog

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import (
    bootstrap_langgraph_schema,
    close_pool,
    get_migrator_pool,
    get_pool,
    open_checkpointer,
    open_store,
    run_migrations,
)
from whatsapp_langchain.shared.observability import setup_logging
from whatsapp_langchain.shared.queue import renew_lease
from whatsapp_langchain.worker.consumer import claim_next_message
from whatsapp_langchain.worker.processor import WORKER_HEALTH, process_message

logger = structlog.get_logger()

# Teto de falhas consecutivas antes do worker se matar pra ser reiniciado.
# Alto o bastante pra não reagir a erro transitório (LLM instável, Evolution
# fora do ar), baixo o bastante pra não passar horas sem responder cliente.
MAX_CONSECUTIVE_FAILURES = 10

# Quanto o shutdown espera pelas mensagens em voo antes de cancelar. Abaixo dos
# 10 s que o Docker dá entre SIGTERM e SIGKILL: o que não terminar aqui volta
# pra fila pelo lease, mas terminar é sempre melhor que reprocessar.
SHUTDOWN_GRACE_SECONDS = 8


async def _lease_heartbeat(pool, message) -> None:
    """Renova o lease enquanto a mensagem é processada (R7).

    IA + mídia + guardrails podem ultrapassar LEASE_SECONDS; sem renovar, o
    lease expira e outro worker reivindica a MESMA mensagem (claim reclama rows
    `processing` com lease vencido) → o agente roda 2x e o cliente recebe a
    resposta DUPLICADA em deploy multi-worker. Renova a cada ~lease/3
    (best-effort: falha de DB tenta de novo no próximo tick). Se perder a
    propriedade do lease (outro worker já assumiu — fence por attempts), para de
    renovar.
    """
    interval = max(5, settings.lease_seconds // 3)
    while True:
        await asyncio.sleep(interval)
        try:
            still_owner = await renew_lease(
                pool, message.id, message.attempts, settings.lease_seconds
            )
        except Exception:
            logger.exception("lease_renew_failed", message_id=message.id)
            continue
        if not still_owner:
            logger.warning(
                "lease_lost_during_processing",
                message_id=message.id,
                attempts=message.attempts,
            )
            return


async def main() -> None:
    """Loop principal do Worker.

    1. Configura logging e banco de dados
    2. Aplica migrações pendentes
    3. Entra em loop infinito buscando mensagens na fila
    4. Processa cada mensagem com o agente apropriado
    """
    setup_logging(log_level=settings.log_level, json_output=settings.log_json)
    logger.info("worker_starting")

    # Sprint A.2.6: migrations rodam como migrator (superuser).
    # Pool de runtime (chat_nexus_app) é aberto depois.
    migrator_pool = await get_migrator_pool()
    await run_migrations(migrator_pool)
    await bootstrap_langgraph_schema()
    pool = await get_pool()

    checkpointer_stack, checkpointer = await open_checkpointer()

    store_stack, store = await open_store()

    # Outbound é montado POR-CONEXÃO dentro do processor
    # (`build_outbound_client` lê credenciais da conexão cadastrada na UI).
    # Não há cliente/instance default "via código" no boot: WABA usa o
    # access_token cifrado da conexão e Evolution a instância dela.
    logger.info(
        "worker_ready",
        poll_interval=settings.poll_interval_seconds,
        concurrency=settings.worker_concurrency,
        memory_enabled=store is not None,
        evolution_mode=settings.evolution_outbound_mode.strip().lower() or "mock",
    )

    # S5 Calendar v2: cron sync periódico Google → DB pra detectar drift
    # (evento criado/cancelado fora do sistema). Roda em paralelo ao loop
    # principal de message_queue.
    sync_task = asyncio.create_task(_calendar_sync_loop(pool))

    # Sprint G.4: marca atendente offline quando heartbeat > 5min sem ping.
    # Evita user esquecer painel aberto e ficar "online" indefinidamente.
    idle_task = asyncio.create_task(_atendente_idle_loop(pool))

    # Sprint cleanup: fecha atendimentos zumbis (>48h aguardando / >24h
    # sem resposta) a cada 6h. Override por empresa via empresa.config.
    cleanup_task = asyncio.create_task(_cleanup_zumbis_loop(pool))

    # Resumo diário por WhatsApp (mig 135) — envia no horário configurado
    resumo_task = asyncio.create_task(_resumo_diario_loop(pool))

    # Vigência do plano (ADR-005 leva E, mig 193): avisos D-7/D-3/D0 e
    # rebaixamento após a carência
    vigencia_task = asyncio.create_task(_plano_vigencia_loop(pool))

    # Relatório mensal de uso (mig 165) — PDF para o cliente, no dia marcado
    relatorio_task = asyncio.create_task(_relatorio_uso_loop(pool))

    # Saúde de IA (mig 178): catálogo OpenRouter + métricas de endpoint
    openrouter_task = asyncio.create_task(_openrouter_sync_loop(pool))

    # Saúde das conexões dos clientes (mig 196): sonda + silêncio contra
    # baseline, avisa o canal da plataforma
    saude_task = asyncio.create_task(_saude_conexoes_loop(pool))

    # Push FCM (mig 168): LISTEN no mesmo canal do SSE → notifica os
    # dispositivos da empresa em mensagem nova de cliente. No-op sem a
    # credencial no env.
    from whatsapp_langchain.shared.push_loop import push_loop

    push_task = asyncio.create_task(push_loop(pool))

    # Fase 2 dos checkpoints (plano 2026-09-15): poda o que o checkpointer
    # acumula. Precisa do `checkpointer` (pool do LangGraph + adelete_thread)
    # e do `pool` da app (mapeamento thread→atendimento).
    retencao_task = asyncio.create_task(_checkpoint_retencao_loop(pool, checkpointer))

    parar = asyncio.Event()
    em_voo: set[asyncio.Task[None]] = set()
    # SIGTERM é o que o Docker manda no deploy. Sem handler o processo morre
    # no ato e as N mensagens em voo ficam presas em `processing` até o lease
    # vencer — N conversas mudas por até LEASE_SECONDS. Com o handler, o loop
    # para de reivindicar e espera o que já começou.
    with contextlib.suppress(NotImplementedError):
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, parar.set)

    try:
        await _loop_consumo(pool, checkpointer, store, parar=parar, em_voo=em_voo)
    except KeyboardInterrupt:
        logger.info("worker_interrupted")
    finally:
        await _esperar_em_voo(em_voo)
        sync_task.cancel()
        idle_task.cancel()
        cleanup_task.cancel()
        resumo_task.cancel()
        vigencia_task.cancel()
        relatorio_task.cancel()
        openrouter_task.cancel()
        saude_task.cancel()
        push_task.cancel()
        retencao_task.cancel()
        for t in (
            sync_task,
            idle_task,
            cleanup_task,
            resumo_task,
            vigencia_task,
            relatorio_task,
            openrouter_task,
            saude_task,
            push_task,
            retencao_task,
        ):
            try:
                await t
            except asyncio.CancelledError:
                pass
        if store_stack is not None:
            await store_stack.aclose()
        await checkpointer_stack.aclose()
        await close_pool()
        logger.info("worker_stopped")


async def _loop_consumo(
    pool,
    checkpointer,
    store,
    *,
    parar: asyncio.Event,
    em_voo: set[asyncio.Task[None]],
) -> None:
    """Loop de consumo: até `WORKER_CONCURRENCY` mensagens em voo por réplica.

    Cada slot do semáforo é uma mensagem sendo processada numa task própria.
    Enquanto houver slot livre o loop reivindica sem dormir (enche os slots);
    só dorme `poll_interval_seconds` quando a fila devolve None. Com N=1 é
    exatamente o loop serial de antes: claim → processa → claim.

    Só é seguro porque `claim_next` é serializado POR CONVERSA — N slots
    nunca rodam dois turnos no mesmo thread do LangGraph. Ordem dentro da
    conversa vem daí; paralelismo é só entre conversas.

    `parar` encerra o loop sem cancelar o que está em voo (quem espera é
    `_esperar_em_voo`, no shutdown). `em_voo` é do chamador pra que o
    shutdown enxergue as tasks mesmo se este loop morrer por exceção.
    """
    slots = asyncio.Semaphore(settings.worker_concurrency)

    while not parar.is_set():
        await slots.acquire()
        # SIGTERM pode ter chegado enquanto todos os slots estavam ocupados:
        # aí o slot que acabou de liberar NÃO pode virar uma mensagem nova.
        if parar.is_set():
            slots.release()
            break
        try:
            # Circuit breaker anti-zumbi. `process_message` engole a
            # exception e chama mark_failed, então o loop seguiria rodando
            # feliz enquanto nenhum cliente é respondido — foi assim que
            # o incidente 2026-07-26 passou 40h despercebido (container
            # `Up`, restarts=0, checkpointer com conexão morta). Falhar
            # ruidosamente devolve o processo pro `restart:
            # unless-stopped`, que reabre as conexões de boot. Checado
            # ANTES do claim: com N=1 é "depois de processar, antes do
            # próximo", a semântica de sempre.
            if WORKER_HEALTH.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error(
                    "worker_unhealthy_exiting",
                    consecutive_failures=WORKER_HEALTH.consecutive_failures,
                    threshold=MAX_CONSECUTIVE_FAILURES,
                    reason="falhas consecutivas; reiniciando pra recriar conexões",
                )
                raise SystemExit(1)

            # Claim roda SEM context de empresa (precisa ver toda a fila,
            # multi-tenant) — `claim_next_message` faz o bypass de RLS.
            message = await claim_next_message(pool, settings.lease_seconds)
        except (KeyboardInterrupt, asyncio.CancelledError, SystemExit):
            slots.release()
            raise
        except Exception:
            # Falha transitória (DB caiu, claim lançou, etc.) NÃO pode
            # derrubar o consumo da fila inteira. Loga e segue com backoff.
            slots.release()
            logger.exception("worker_loop_iteration_error")
            await asyncio.sleep(settings.poll_interval_seconds)
            continue

        if message is None:
            slots.release()
            await asyncio.sleep(settings.poll_interval_seconds)
            continue

        task = asyncio.create_task(
            _processar_mensagem(message, pool, checkpointer, store, slots),
            name=f"msg:{message.id}",
        )
        em_voo.add(task)
        task.add_done_callback(em_voo.discard)


async def _processar_mensagem(message, pool, checkpointer, store, slots) -> None:
    """Uma mensagem, numa task própria, com escopo de RLS e heartbeat próprios.

    Sprint A.2.5: o `empresa_scope` é setado DENTRO da task. `create_task`
    copia o contexto no momento da criação, então cada task tem a sua cópia:
    `pool.connection()` em qualquer helper (shared/*.py, tools do agente)
    injeta o `app.empresa_id` desta mensagem, sem vazar pras tasks irmãs nem
    pro loop. Checkpointer e store ficam FORA disso: têm pool próprio
    (`_open_langgraph_pool`), sem o wrapper RLS — as tabelas do LangGraph não
    têm `empresa_id`, o escopo delas é o `thread_id` e o namespace do store.

    R7: o heartbeat renova o lease em background enquanto a IA processa, pra
    IA lenta (>lease) não disparar reclaim + resposta duplicada. Criado dentro
    do `empresa_scope` pra herdar o contextvar.
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope

    try:
        with empresa_scope(empresa_id=message.empresa_id):
            heartbeat = asyncio.create_task(_lease_heartbeat(pool, message))
            try:
                await process_message(
                    message,
                    pool,
                    checkpointer=checkpointer,
                    store=store,
                )
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
    except asyncio.CancelledError:
        raise
    except Exception:
        # `process_message` já engole e chama mark_failed; isto cobre falha
        # antes/depois dele (heartbeat, escopo). A row volta pelo lease.
        logger.exception("worker_task_error", message_id=message.id)
    finally:
        slots.release()


async def _esperar_em_voo(em_voo: set[asyncio.Task[None]]) -> None:
    """Dá `SHUTDOWN_GRACE_SECONDS` pras mensagens em voo terminarem; cancela o resto."""
    if not em_voo:
        return
    logger.info("worker_draining", em_voo=len(em_voo), grace_s=SHUTDOWN_GRACE_SECONDS)
    _, pendentes = await asyncio.wait(em_voo, timeout=SHUTDOWN_GRACE_SECONDS)
    for task in pendentes:
        task.cancel()
    if pendentes:
        await asyncio.gather(*pendentes, return_exceptions=True)
        logger.warning("worker_drain_timeout", canceladas=len(pendentes))


# S5: cron interno do worker — sync Google → DB a cada N minutos
CALENDAR_SYNC_INTERVAL_SECONDS = 300  # 5 min

# Fase 2 dos checkpoints: poda de retenção a cada 6h (idempotente; a trava
# de sessão no módulo garante que só um worker roda por ciclo).
CHECKPOINT_RETENCAO_INTERVAL_SECONDS = 6 * 60 * 60


async def _calendar_sync_loop(pool) -> None:
    """Loop periódico que reconcilia drift Google → tabela agendamento.

    Roda em paralelo ao loop principal. Pra cada empresa com Calendar
    ativo, chama `sync_calendar_for_empresa` que detecta eventos
    cancelados/criados fora do sistema. Conflito local-vs-Google é
    apenas logado (não sobrescreve).
    """
    from whatsapp_langchain.shared.agendamento import (
        list_active_calendar_empresas,
    )
    from whatsapp_langchain.shared.calendar_integration import (
        sync_calendar_for_empresa,
    )

    # Sprint A.2.5 — RLS context por empresa
    from whatsapp_langchain.shared.rls_context import empresa_scope

    while True:
        try:
            # list_active_calendar_empresas precisa ver TODAS as empresas
            # com calendar ativo. Hoje funciona sem context (modo permissive).
            # Após A.2.6 (DATABASE_URL chat_nexus_app + policy estrita),
            # essa lista precisará bypass_rls=True ou ser feita via tabela
            # `empresa` (sem RLS, pois é global).
            empresas = await list_active_calendar_empresas(pool)
            for empresa_id in empresas:
                # Cada sync roda no escopo RLS da própria empresa — qualquer
                # query interna (agendamento, empresa_calendar_config) filtra
                # automaticamente.
                with empresa_scope(empresa_id=empresa_id):
                    try:
                        await sync_calendar_for_empresa(pool, empresa_id)
                    except Exception as e:  # noqa: BLE001
                        err_str = str(e)
                        # `invalid_grant` é PERMANENTE — token revogado/
                        # expirado nunca volta sozinho. Auto-desabilita pra
                        # parar spam de logs a cada 5min. Admin re-conecta.
                        if "invalid_grant" in err_str:
                            try:
                                async with pool.connection() as conn:
                                    await conn.execute(
                                        "UPDATE empresa_calendar_config "
                                        "SET ativo = FALSE, updated_at = NOW() "
                                        "WHERE empresa_id = %s",
                                        (empresa_id,),
                                    )
                                    await conn.commit()
                                logger.error(
                                    "calendar_auto_disabled_token_revoked",
                                    empresa_id=empresa_id,
                                    reason="invalid_grant",
                                    action="admin_must_reconnect_oauth",
                                )
                            except Exception as inner:  # noqa: BLE001
                                logger.warning(
                                    "calendar_auto_disable_failed",
                                    empresa_id=empresa_id,
                                    error=str(inner),
                                )
                        else:
                            logger.warning(
                                "calendar_sync_empresa_failed",
                                empresa_id=empresa_id,
                                error=err_str,
                            )
        except Exception as e:  # noqa: BLE001
            logger.warning("calendar_sync_loop_error", error=str(e))
        await asyncio.sleep(CALENDAR_SYNC_INTERVAL_SECONDS)


# Sprint G.4: cron interno marca atendente offline quando idle > 5min.
ATENDENTE_IDLE_INTERVAL_SECONDS = 60
ATENDENTE_IDLE_THRESHOLD_SECONDS = 300


async def _atendente_idle_loop(pool) -> None:
    """Marca atendente como offline quando heartbeat > 5min sem ping.

    Cliente envia POST /api/atendentes/me/heartbeat a cada 60s. Se passa
    5min sem heartbeat E status='online', o worker considera que o user
    fechou o painel ou perdeu conexão e força status='offline'. Evita
    user "fantasma" que recebe atendimentos atribuídos sem estar de fato
    presente.
    """
    from whatsapp_langchain.shared.atendente import mark_idle_offline

    while True:
        try:
            await mark_idle_offline(pool, idle_seconds=ATENDENTE_IDLE_THRESHOLD_SECONDS)
        except Exception as e:  # noqa: BLE001
            logger.warning("atendente_idle_loop_error", error=str(e))
        await asyncio.sleep(ATENDENTE_IDLE_INTERVAL_SECONDS)


CLEANUP_INTERVAL_SECONDS = 6 * 3600  # 6h


async def _cleanup_zumbis_loop(pool) -> None:
    """Roda cleanup de atendimentos zumbis a cada 6h em todas as empresas.

    Thresholds defaults (override por empresa via empresa.config):
    - aguardando >48h → abandonado
    - em_andamento >24h sem msg do cliente → abandonado
    """
    from whatsapp_langchain.shared.atendimento_cleanup import (
        cleanup_zumbis_all_empresas,
    )

    # Aguarda 5min após startup pra não competir com migrations/bootstrap
    await asyncio.sleep(300)

    while True:
        try:
            await cleanup_zumbis_all_empresas(pool, motivo="cleanup_auto")
        except Exception as e:  # noqa: BLE001
            logger.warning("cleanup_zumbis_loop_error", error=str(e))
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


async def _resumo_diario_loop(pool) -> None:
    """Checa a cada 60s se alguma empresa está no horário do resumo diário.

    O check é barato (1 SELECT nas empresas com resumo ativo); o guard de
    idempotência (`resumo_diario_last_sent`, claim atômico) garante 1 envio
    por dia por empresa mesmo com múltiplos workers.
    """
    from whatsapp_langchain.shared.resumo_diario import run_resumo_diario_all

    # Aguarda o boot estabilizar (migrations/bootstrap)
    await asyncio.sleep(120)

    while True:
        try:
            await run_resumo_diario_all(pool)
        except Exception as e:  # noqa: BLE001
            logger.warning("resumo_diario_loop_error", error=str(e))
        await asyncio.sleep(60)


async def _plano_vigencia_loop(pool) -> None:
    """A cada 30 min avisa vencimentos (D-7/D-3/D0) e rebaixa quem passou da
    carência. Idempotente por claim de etapa e UPDATE condicional — as
    réplicas podem rodar ao mesmo tempo; o horário comercial local decide
    quando o aviso sai de verdade."""
    from whatsapp_langchain.shared.plano_vigencia import processar_vigencias

    await asyncio.sleep(180)
    while True:
        try:
            contagem = await processar_vigencias(pool)
            if contagem["avisos"] or contagem["rebaixadas"] or contagem["erros"]:
                logger.info("plano_vigencia_tick", **contagem)
        except Exception as e:  # noqa: BLE001
            logger.warning("plano_vigencia_loop_error", error=str(e))
        await asyncio.sleep(30 * 60)


# Saúde das conexões (mig 196): o claim em `saude_conexoes_estado` espaça os
# ticks de verdade (5 min) entre as réplicas; o loop só tenta a cada minuto
# para uma réplica morta não deixar o monitor parado por mais que isso.
SAUDE_CONEXOES_LOOP_SECONDS = 60


async def _saude_conexoes_loop(pool) -> None:
    """Sonda as conexões, compara a atividade com a baseline e abre/fecha
    episódios em `conexao_alerta`, avisando o canal da plataforma. Uma
    réplica por tick (claim atômico dentro de `avaliar_saude`)."""
    from whatsapp_langchain.shared.saude_conexoes import avaliar_saude

    await asyncio.sleep(240)
    while True:
        try:
            contagem = await avaliar_saude(pool)
            if contagem["abertos"] or contagem["resolvidos"] or contagem["erros"]:
                logger.info("saude_conexoes_tick", **contagem)
        except Exception as e:  # noqa: BLE001
            logger.warning("saude_conexoes_loop_error", error=str(e))
        await asyncio.sleep(SAUDE_CONEXOES_LOOP_SECONDS)


async def _relatorio_uso_loop(pool) -> None:
    """Checa a cada 5min se alguma empresa está no dia do relatório mensal.

    Tick mais folgado que o do resumo diário porque a granularidade é mensal:
    5 minutos de atraso num envio que acontece uma vez por mês não muda nada, e
    o SELECT roda 12x menos. O claim atômico (`relatorio_uso_last_sent`, que
    guarda a competência) garante um envio por mês por empresa mesmo com
    vários workers.
    """
    from whatsapp_langchain.shared.relatorio_uso import run_relatorio_uso_all

    # Aguarda o boot estabilizar (migrations/bootstrap)
    await asyncio.sleep(180)

    while True:
        try:
            await run_relatorio_uso_all(pool)
        except Exception as e:  # noqa: BLE001
            logger.warning("relatorio_uso_loop_error", error=str(e))
        await asyncio.sleep(300)


# Saúde de IA (mig 178): 10 min equilibra frescor do alerta de degradação
# (janelas do OpenRouter são de 30m — colher mais rápido não traz dado novo)
# com volume de chamadas (~25 modelos/tick, bem abaixo dos rate limits).
OPENROUTER_SYNC_INTERVAL_SECONDS = 600


async def _checkpoint_retencao_loop(pool, checkpointer) -> None:
    """Poda os checkpoints do LangGraph a cada 6h (Fase 2 do plano).

    Molde do `_cleanup_zumbis_loop`: delay inicial, `try` que nunca mata o
    loop, intervalo fixo. A trava de sessão em `rodar_retencao` cuida dos
    dois workers de produção — não precisa de claim 1x/dia porque a poda é
    idempotente (ao contrário do resumo diário).
    """
    from whatsapp_langchain.shared.checkpoint_retencao import rodar_retencao

    # Espera o boot estabilizar (migrations/bootstrap do schema LangGraph).
    await asyncio.sleep(300)

    while True:
        try:
            await rodar_retencao(checkpointer, pool, settings.checkpoint_retencao_dias)
        except Exception as e:  # noqa: BLE001
            logger.warning("checkpoint_retencao_loop_error", error=str(e))
        await asyncio.sleep(CHECKPOINT_RETENCAO_INTERVAL_SECONDS)


async def _openrouter_sync_loop(pool) -> None:
    """Coleta saúde dos modelos em uso + sincroniza o catálogo 1x/dia.

    Métricas por endpoint (uptime/latência/throughput) a cada tick; o catálogo
    completo (388 modelos, 103 provedores) roda uma vez por dia via claim
    atômico em `openrouter_sync_estado` — seguro com múltiplos workers.
    """
    from whatsapp_langchain.shared.openrouter_catalogo import run_openrouter_sync

    # Aguarda o boot estabilizar (migrations/bootstrap)
    await asyncio.sleep(180)

    while True:
        try:
            await run_openrouter_sync(pool)
        except Exception as e:  # noqa: BLE001
            logger.warning("openrouter_sync_loop_error", error=str(e))
        await asyncio.sleep(OPENROUTER_SYNC_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
