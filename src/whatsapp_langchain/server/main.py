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
from whatsapp_langchain.server.routes.admin import router as admin_router
from whatsapp_langchain.server.routes.health import router as health_router
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
    logger.info("server_starting", port=settings.port)

    pool = await get_pool()
    await run_migrations(pool)
    await bootstrap_langgraph_schema()
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

# CORS para o frontend (Next.js)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(admin_router)

# Webhook sincrono — apenas para dev/testes, nunca em producao.
# Em producao, use o webhook async (Twilio) que passa pela fila.
if settings.environment != "production":
    from whatsapp_langchain.server.routes.webhook_sync import (
        router as webhook_sync_router,
    )

    app.include_router(webhook_sync_router)
