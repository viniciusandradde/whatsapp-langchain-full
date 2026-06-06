"""Entry point do Worker — loop de processamento de mensagens.

Inicia o Worker que consome mensagens da fila PostgreSQL em loop.
Cada mensagem é processada pelo agente configurado.

Uso:
    python -m whatsapp_langchain.worker.main
"""

import asyncio
import contextlib

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
from whatsapp_langchain.worker.processor import process_message

logger = structlog.get_logger()


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
    # Não há mais cliente/instance default "via código" no boot. Aqui só
    # validamos as credenciais APP-LEVEL do Twilio (a CONTA, compartilhada por
    # todas as conexões twilio_*) — o número (from_number) vem da conexão.
    outbound_mode = settings.resolved_twilio_outbound_mode
    if outbound_mode == "real":
        missing = [
            name
            for name, val in (
                ("TWILIO_ACCOUNT_SID", settings.twilio_account_sid),
                ("TWILIO_API_KEY_SID", settings.twilio_api_key_sid),
                ("TWILIO_API_KEY_SECRET", settings.twilio_api_key_secret),
            )
            if not val
        ]
        if missing:
            logger.error(
                "twilio_credentials_missing",
                missing=missing,
                outbound_mode=outbound_mode,
            )
            msg = (
                "Twilio outbound em modo real requer credenciais de CONTA: "
                f"{', '.join(missing)}"
            )
            raise SystemExit(msg)

    logger.info(
        "worker_ready",
        poll_interval=settings.poll_interval_seconds,
        memory_enabled=store is not None,
        twilio_mode=outbound_mode,
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

    # Sprint A.2.5 — importa context manager pra RLS
    from whatsapp_langchain.shared.rls_context import empresa_scope

    try:
        while True:
            try:
                # Claim roda SEM context (precisa ver toda a fila, multi-tenant).
                # Quando A.2.6 trocar DATABASE_URL pra chat_nexus_app
                # (NOBYPASSRLS), claim vai precisar de bypass: ver A.2.6.
                message = await claim_next_message(pool, settings.lease_seconds)

                if message is None:
                    await asyncio.sleep(settings.poll_interval_seconds)
                    continue

                # Sprint A.2.5: seta RLS context da empresa da msg antes
                # de processar. Qualquer pool.connection() dentro de
                # process_message (helpers shared/*.py, agente IA tools,
                # checkpointer, store) herda app.empresa_id automaticamente
                # via _RlsAwarePool wrapper. Garante isolamento entre
                # mensagens de empresas diferentes processadas pelo mesmo
                # worker.
                with empresa_scope(empresa_id=message.empresa_id):
                    # R7: heartbeat renova o lease em background enquanto a IA
                    # processa, pra IA lenta (>lease) não disparar reclaim +
                    # resposta duplicada. Criado DENTRO do empresa_scope pra
                    # herdar o contextvar de RLS (renova com app.empresa_id set).
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
            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception:
                # Falha transitória (DB caiu, claim/mark_failed lançou, etc.)
                # NÃO pode derrubar o consumo da fila inteira. Loga e segue com
                # backoff; a msg em 'processing' é reclaimável após a lease.
                logger.exception("worker_loop_iteration_error")
                await asyncio.sleep(settings.poll_interval_seconds)

    except KeyboardInterrupt:
        logger.info("worker_interrupted")
    finally:
        sync_task.cancel()
        idle_task.cancel()
        cleanup_task.cancel()
        for t in (sync_task, idle_task, cleanup_task):
            try:
                await t
            except asyncio.CancelledError:
                pass
        if store_stack is not None:
            await store_stack.aclose()
        await checkpointer_stack.aclose()
        await close_pool()
        logger.info("worker_stopped")


# S5: cron interno do worker — sync Google → DB a cada N minutos
CALENDAR_SYNC_INTERVAL_SECONDS = 300  # 5 min


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


if __name__ == "__main__":
    asyncio.run(main())
