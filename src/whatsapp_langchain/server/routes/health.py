"""Rota de health check.

Verifica se o servidor e o banco de dados estão operacionais.

Uso:
    curl http://localhost:8000/health
    # {"status":"ok","database":"connected","version":"0.1.0"}
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from whatsapp_langchain import __version__
from whatsapp_langchain.shared.db import check_db_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> JSONResponse:
    """Verifica saúde do serviço.

    Testa conectividade com o banco de dados via SELECT 1.

    Returns:
        {"status":"ok","database":"connected","version":"..."} com HTTP 200,
        ou {"status":"degraded","database":"disconnected","version":"..."}
        com HTTP 503.
    """
    is_healthy = await check_db_health()

    if not is_healthy:
        return JSONResponse(
            content={
                "status": "degraded",
                "database": "disconnected",
                "version": __version__,
            },
            status_code=503,
        )

    return JSONResponse(
        content={
            "status": "ok",
            "database": "connected",
            "version": __version__,
        }
    )
