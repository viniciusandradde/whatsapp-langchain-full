"""FastAPI application factory com lifespan.

Entry point do servidor HTTP. Configura logging, banco de dados,
CORS e inclui todos os routers.

Uso:
    uvicorn whatsapp_langchain.server.main:app --reload --port 8000
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from whatsapp_langchain.agents.loader import AgentNotFoundError
from whatsapp_langchain.server.middlewares import (
    install_admin_rate_limit,
    install_correlation_id,
    install_security_headers,
)
from whatsapp_langchain.server.routes.admin import router as admin_router
from whatsapp_langchain.server.routes.audit import router as audit_router
from whatsapp_langchain.server.routes.agente import router as agente_router
from whatsapp_langchain.server.routes.atendente import router as atendente_router
from whatsapp_langchain.server.routes.dataset_import import (
    router as rag_dataset_router,
)
from whatsapp_langchain.server.routes.hitl import (
    router as hitl_router,
)
from whatsapp_langchain.server.routes.rag_stats import (
    router as rag_stats_router,
)
from whatsapp_langchain.server.routes.relatorios_nps import (
    router as relatorios_nps_router,
)
from whatsapp_langchain.server.routes.test_runner import (
    router as test_runner_router,
)
from whatsapp_langchain.server.routes.catalogo import (
    router_mcp as mcp_router,
    router_modelo_llm as modelo_llm_router,
)
from whatsapp_langchain.server.routes.dashboard_ia import (
    router as dashboard_ia_router,
    router_budget as ia_budget_router,
)
from whatsapp_langchain.server.routes.agendamento import (
    router as agendamento_router,
)
from whatsapp_langchain.server.routes.agendamento_regras import (
    router as agendamento_regras_router,
)
from whatsapp_langchain.server.routes.atendimento import (
    router as atendimento_router,
)
from whatsapp_langchain.server.routes.base_conhecimento import (
    router as base_conhecimento_router,
)
from whatsapp_langchain.server.routes.calendar_integration import (
    router as calendar_integration_router,
)
from whatsapp_langchain.server.routes.cliente import router as cliente_router
from whatsapp_langchain.server.routes.conexao import router as conexao_router
from whatsapp_langchain.server.routes.departamento import (
    router as departamento_router,
)
from whatsapp_langchain.server.routes.empresa_admin import (
    router as empresa_admin_router,
)
from whatsapp_langchain.server.routes.evolution_webhook import (
    router as evolution_webhook_router,
)
from whatsapp_langchain.server.routes.health import router as health_router
from whatsapp_langchain.server.routes.hook import router as hook_router
from whatsapp_langchain.server.routes.horario import (
    router_feriado as feriado_router,
)
from whatsapp_langchain.server.routes.horario import (
    router_horario as horario_router,
)
from whatsapp_langchain.server.routes.menu_chatbot import (
    router as menu_chatbot_router,
)
from whatsapp_langchain.server.routes.modelo_mensagem import (
    router as modelo_mensagem_router,
)
from whatsapp_langchain.server.routes.campanha import router as campanha_router
from whatsapp_langchain.server.routes.feature_flag import router as feature_flag_router
from whatsapp_langchain.server.routes.pasta import router as pasta_router
from whatsapp_langchain.server.routes.perfil import router as perfil_router
from whatsapp_langchain.server.routes.security import router as security_router
from whatsapp_langchain.server.routes.traces import router as traces_router
from whatsapp_langchain.server.routes.variavel import (
    router as variavel_router,
)
from whatsapp_langchain.server.routes.webhook import router as webhook_router
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import (
    bootstrap_langgraph_schema,
    close_pool,
    get_pool,
    run_migrations,
)
from whatsapp_langchain.shared.observability import setup_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Gerencia o ciclo de vida da aplicação.

    Startup: configura logging, cria pool do banco, aplica migrações.
    Shutdown: fecha pool do banco.
    """
    # Startup
    setup_logging(
        log_level=settings.log_level,
        json_output=settings.log_json,
    )
    settings.validate_runtime_settings()

    # Fase 0 enterprise — OpenTelemetry. Init ANTES de outros setups
    # pra que spans cubram bootstrap completo. No-op se OTLP não
    # configurado em prod (logs ficam só local).
    from whatsapp_langchain.shared.telemetry import init_telemetry

    init_telemetry(
        service_name="nexus-chat-ai-api",
        environment=settings.environment,
    )

    logger.info("server_starting", port=settings.port)

    pool = await get_pool()
    await run_migrations(pool)
    await bootstrap_langgraph_schema()
    # E2.A: sincroniza catálogo de permissões + seed perfis system
    # pra empresa default (id=1). Idempotente em ambos.
    from whatsapp_langchain.shared.permissoes import (
        seed_default_perfis,
        sync_catalogo,
    )

    await sync_catalogo(pool)
    try:
        await seed_default_perfis(pool, 1)
    except Exception as exc:
        logger.warning("rbac_seed_default_failed", error=str(exc))
    logger.info("server_ready")

    yield

    # Shutdown
    await close_pool()
    logger.info("server_stopped")


app = FastAPI(
    title="WhatsApp LangChain API",
    description="API para agentes conversacionais WhatsApp com LangGraph.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS para o frontend (Next.js) — origens restritas via FRONTEND_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Twilio-Signature"],
)

install_security_headers(app, is_production=settings.is_production)
install_admin_rate_limit(app, limit_per_minute=settings.admin_rate_limit_per_minute)
# Correlation ID: registrado por último pra rodar PRIMEIRO no request
# (Starlette empilha middlewares LIFO). Assim os logs do rate_limit e
# security_headers já têm `request_id` no contextvars.
install_correlation_id(app)

# Fase 0 enterprise — instrumentação OTel pro app inteiro. Cria span
# por request automaticamente. Excluí /health e /metrics pra não poluir
# traces com health-checks de monitoring.
from whatsapp_langchain.shared.telemetry import instrument_fastapi

instrument_fastapi(app)


# Middleware Prometheus — conta + cronometra cada request HTTP.
# Antes dos handlers e dos middlewares de erro pra capturar tudo.
@app.middleware("http")
async def prometheus_middleware(request, call_next):  # type: ignore[no-untyped-def]
    """Conta + cronometra cada request HTTP nas métricas Prometheus."""
    import time as _time

    from whatsapp_langchain.shared.metrics import (
        http_request_duration_seconds,
        http_requests_total,
    )

    # Path pra label (sem query) — limita cardinalidade pra evitar
    # explosão (path com IDs vira "<id>")
    path = request.url.path
    if path.startswith("/api/health") or path == "/health" or path == "/metrics":
        # Health/metrics não vão pras métricas (evita ruído + recursão)
        return await call_next(request)

    method = request.method
    start = _time.perf_counter()
    try:
        response = await call_next(request)
        status = str(response.status_code)
    except Exception:
        status = "500"
        raise
    finally:
        elapsed = _time.perf_counter() - start
        http_requests_total.labels(method=method, path=path, status=status).inc()
        http_request_duration_seconds.labels(method=method, path=path).observe(
            elapsed
        )
    return response


# Exception handlers
@app.exception_handler(AgentNotFoundError)
async def agent_not_found_handler(
    request: Request, exc: AgentNotFoundError
) -> JSONResponse:
    """Retorna 400 quando o agent_id não existe no catálogo."""
    logger.warning("agent_not_found", agent_id=exc.agent_id)
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


# Routers
app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(evolution_webhook_router)
app.include_router(admin_router)
app.include_router(empresa_admin_router)
app.include_router(conexao_router)
app.include_router(cliente_router)
app.include_router(atendimento_router)
app.include_router(modelo_mensagem_router)
app.include_router(hook_router)
app.include_router(calendar_integration_router)
app.include_router(base_conhecimento_router)
app.include_router(variavel_router)
app.include_router(departamento_router)
app.include_router(horario_router)
app.include_router(feriado_router)
app.include_router(traces_router)
app.include_router(security_router)
app.include_router(agendamento_router)
app.include_router(perfil_router)
app.include_router(pasta_router)
app.include_router(campanha_router)
app.include_router(agendamento_regras_router)
app.include_router(audit_router)
app.include_router(feature_flag_router)
app.include_router(agente_router)
app.include_router(menu_chatbot_router)
app.include_router(modelo_llm_router)
app.include_router(mcp_router)
app.include_router(dashboard_ia_router)
app.include_router(ia_budget_router)
app.include_router(atendente_router)
app.include_router(test_runner_router)
app.include_router(rag_stats_router)
app.include_router(relatorios_nps_router)
app.include_router(rag_dataset_router)
app.include_router(hitl_router)

# Webhook sincrono — apenas para dev/testes, nunca em producao.
# Em producao, use o webhook async (Twilio) que passa pela fila.
if settings.environment != "production":
    from whatsapp_langchain.server.routes.webhook_sync import (
        router as webhook_sync_router,
    )

    app.include_router(webhook_sync_router)
