"""Entry point do Worker — loop de processamento de mensagens.

Inicia o Worker que consome mensagens da fila PostgreSQL em loop.
Cada mensagem é processada pelo agente configurado.

Uso:
    python -m whatsapp_langchain.worker.main
"""

import asyncio

import structlog

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import (
    bootstrap_langgraph_schema,
    close_pool,
    get_pool,
    open_checkpointer,
    open_store,
    run_migrations,
)
from whatsapp_langchain.shared.observability import setup_logging
from whatsapp_langchain.worker.consumer import claim_next_message
from whatsapp_langchain.worker.evolution_client import EvolutionClient
from whatsapp_langchain.worker.outbound_client import OutboundClient
from whatsapp_langchain.worker.processor import process_message
from whatsapp_langchain.worker.twilio_client import TwilioClient

logger = structlog.get_logger()


async def main() -> None:
    """Loop principal do Worker.

    1. Configura logging e banco de dados
    2. Aplica migrações pendentes
    3. Entra em loop infinito buscando mensagens na fila
    4. Processa cada mensagem com o agente apropriado
    """
    setup_logging(log_level=settings.log_level, json_output=settings.log_json)
    logger.info("worker_starting")

    pool = await get_pool()
    await run_migrations(pool)
    await bootstrap_langgraph_schema()

    checkpointer_stack, checkpointer = await open_checkpointer()

    store_stack, store = await open_store()

    outbound_mode = settings.resolved_twilio_outbound_mode
    if outbound_mode == "real":
        missing = []
        if not settings.twilio_account_sid:
            missing.append("TWILIO_ACCOUNT_SID")
        if not settings.twilio_api_key_sid:
            missing.append("TWILIO_API_KEY_SID")
        if not settings.twilio_api_key_secret:
            missing.append("TWILIO_API_KEY_SECRET")
        if not settings.twilio_from_number:
            missing.append("TWILIO_FROM_NUMBER")

        if missing:
            logger.error(
                "twilio_credentials_missing",
                missing=missing,
                outbound_mode=outbound_mode,
            )
            msg = f"Twilio outbound em modo real requer variáveis: {', '.join(missing)}"
            raise SystemExit(msg)

    twilio = TwilioClient(
        account_sid=settings.twilio_account_sid,
        api_key_sid=settings.twilio_api_key_sid,
        api_key_secret=settings.twilio_api_key_secret,
        from_number=settings.twilio_from_number,
        delivery_mode=outbound_mode,
    )

    # M2.b — Evolution client paralelo. Sem credenciais → mock automático
    # (rows com provider=evolution caem em log-only sem derrubar o worker).
    evolution_api_key = (
        settings.evolution_api_key.get_secret_value()
        if settings.evolution_api_key is not None
        else ""
    )
    evolution_mode = settings.evolution_outbound_mode.strip().lower() or "mock"
    if evolution_mode == "real" and not (
        settings.evolution_api_url
        and evolution_api_key
        and settings.evolution_instance_name
    ):
        logger.warning(
            "evolution_credentials_missing_falling_back_to_mock",
            api_url=bool(settings.evolution_api_url),
            api_key=bool(evolution_api_key),
            instance_name=bool(settings.evolution_instance_name),
        )
        evolution_mode = "mock"

    evolution = EvolutionClient(
        api_url=settings.evolution_api_url,
        api_key=evolution_api_key,
        instance_name=settings.evolution_instance_name,
        delivery_mode=evolution_mode,
    )

    clients_by_provider: dict[str, OutboundClient] = {
        "twilio_sandbox": twilio,
        "twilio_prod": twilio,
        "waba": twilio,
        "evolution": evolution,
    }

    logger.info(
        "clients_ready",
        twilio_mode=outbound_mode,
        twilio_from_number=settings.twilio_from_number or None,
        evolution_mode=evolution_mode,
        evolution_instance=settings.evolution_instance_name or None,
    )

    logger.info(
        "worker_ready",
        poll_interval=settings.poll_interval_seconds,
        memory_enabled=store is not None,
        providers=sorted(clients_by_provider.keys()),
    )

    # S5 Calendar v2: cron sync periódico Google → DB pra detectar drift
    # (evento criado/cancelado fora do sistema). Roda em paralelo ao loop
    # principal de message_queue.
    sync_task = asyncio.create_task(_calendar_sync_loop(pool))

    # Sprint G.4: marca atendente offline quando heartbeat > 5min sem ping.
    # Evita user esquecer painel aberto e ficar "online" indefinidamente.
    idle_task = asyncio.create_task(_atendente_idle_loop(pool))

    try:
        while True:
            message = await claim_next_message(pool, settings.lease_seconds)

            if message is None:
                await asyncio.sleep(settings.poll_interval_seconds)
                continue

            await process_message(
                message,
                pool,
                checkpointer=checkpointer,
                store=store,
                clients=clients_by_provider,
            )

    except KeyboardInterrupt:
        logger.info("worker_interrupted")
    finally:
        sync_task.cancel()
        idle_task.cancel()
        for t in (sync_task, idle_task):
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

    while True:
        try:
            empresas = await list_active_calendar_empresas(pool)
            for empresa_id in empresas:
                try:
                    await sync_calendar_for_empresa(pool, empresa_id)
                except Exception as e:  # noqa: BLE001
                    err_str = str(e)
                    # `invalid_grant` é PERMANENTE — token revogado/expirado
                    # nunca volta sozinho. Auto-desabilita pra parar spam de
                    # logs a cada 5min. Admin re-conecta no painel.
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


if __name__ == "__main__":
    asyncio.run(main())
