"""Middlewares HTTP para hardening de segurança."""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.types import ASGIApp


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
