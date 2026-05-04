"""Middlewares HTTP para hardening de segurança."""

import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp

from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.rate_limit import (
    RateLimitExceeded,
    enforce_bucket_limit,
)

logger = structlog.get_logger()


REQUEST_ID_HEADER = "X-Request-Id"
REQUEST_ID_MAX_LEN = 100  # mitiga abuse: client passando ID gigante

# Paths que recebem rate limit por user_id. Webhooks (twilio, evolution)
# têm rate limit próprio por phone_number e ficam fora.
# `/api/health` fica fora pra healthcheck do Dokploy não consumir bucket.
_ADMIN_PATH_PREFIXES = ("/api/",)
_ADMIN_PATH_EXCLUDED = ("/api/health",)


async def security_headers_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    *,
    is_production: bool,
) -> Response:
    """Adiciona cabeçalhos de segurança a toda resposta."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


def install_security_headers(app: ASGIApp, *, is_production: bool) -> None:
    """Registra o middleware de security headers no app."""

    @app.middleware("http")  # type: ignore[attr-defined]
    async def _wrapper(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        return await security_headers_middleware(
            request, call_next, is_production=is_production
        )


def _is_admin_request(path: str) -> bool:
    """True quando path bate com prefixo admin e não está excluído."""
    if not any(path.startswith(p) for p in _ADMIN_PATH_PREFIXES):
        return False
    return not any(path.startswith(e) for e in _ADMIN_PATH_EXCLUDED)


async def admin_rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    *,
    limit_per_minute: int,
) -> Response:
    """Rate limit por user_id em endpoints admin (`/api/*`).

    Estratégia: bucket de 60s por (user_id, "admin"). Sem header
    X-User-Id, deixa passar — o `verify_service_token` ou
    `get_user_id_from_request` da rota vai retornar 401 com mensagem
    clara, melhor que esconder atrás de um 429 genérico.

    OPTIONS sempre passa (CORS preflight não conta).
    """
    if request.method == "OPTIONS" or not _is_admin_request(request.url.path):
        return await call_next(request)

    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id:
        return await call_next(request)

    try:
        pool = await get_pool()
        await enforce_bucket_limit(
            pool,
            f"user:{user_id}:admin",
            limit=limit_per_minute,
            window_seconds=60,
        )
    except RateLimitExceeded as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers or {},
        )

    return await call_next(request)


def install_admin_rate_limit(app: ASGIApp, *, limit_per_minute: int) -> None:
    """Registra o middleware de rate limit admin no app."""

    @app.middleware("http")  # type: ignore[attr-defined]
    async def _wrapper(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        return await admin_rate_limit_middleware(
            request, call_next, limit_per_minute=limit_per_minute
        )


async def correlation_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Propaga `X-Request-Id` em todas as requisições.

    Aceita ID enviado pelo client (frontend Next.js, integração externa);
    gera UUID4 quando ausente. Faz `bind_contextvars` no structlog pra
    que TODOS os logs daquela request tenham `request_id=<id>` —
    permite correlacionar webhook → enqueue → claim → llm → outbound em
    grep / Grafana.

    Header `X-Request-Id` da resposta sempre carrega o ID final pra que
    o client possa logar/exibir e referenciar em incidentes.
    """
    # Aceita ID do client se válido (curto, não vazio); senão gera.
    client_id = request.headers.get(REQUEST_ID_HEADER, "").strip()
    if client_id and len(client_id) <= REQUEST_ID_MAX_LEN:
        request_id = client_id
    else:
        request_id = uuid.uuid4().hex[:16]

    # Bind no contextvars — TODA chamada logger.* dentro deste request
    # vai ter request_id como campo extra.
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.unbind_contextvars("request_id")

    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def install_correlation_id(app: ASGIApp) -> None:
    """Registra o middleware de correlation_id no app."""

    @app.middleware("http")  # type: ignore[attr-defined]
    async def _wrapper(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        return await correlation_id_middleware(request, call_next)
