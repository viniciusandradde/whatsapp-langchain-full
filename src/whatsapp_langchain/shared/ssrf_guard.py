"""Guarda anti-SSRF única para URLs de saída controladas por tenant.

Extraída de `midia_processing` (que já defendia o download de mídia) para ser
reusada por TODO canal que faz requisição de saída para uma URL configurada
pela empresa: hooks (`hook_dispatcher`), item de menu `chamar_webhook`
(`worker/processor`) e health-check/runtime de MCP (`routes/catalogo`). Antes,
só o download de mídia validava host/IP — os demais aceitavam
`http://169.254.169.254/...` (metadata de nuvem) ou `http://minio:9000/...`.

`host_is_public` faz DNS resolve bloqueante; em código async use
`assert_url_externa` (roda em thread). Nota: a validação resolve o DNS uma vez
e o cliente HTTP resolve de novo no request — há uma janela de DNS rebinding
(TOCTOU) que esta guarda não fecha; mitigá-la exige pin de IP no transporte.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

__all__ = ["host_is_public", "validar_url_externa", "assert_url_externa"]


def host_is_public(host: str) -> bool:
    """True se TODOS os IPs resolvidos do host são públicos (anti-SSRF).

    Bloqueia loopback, privados, link-local (169.254.x — metadata cloud!),
    reservados, multicast e unspecified. Bloqueante (DNS) — em async, chamar
    via `asyncio.to_thread` / `assert_url_externa`.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def validar_url_externa(url: str) -> str:
    """Valida scheme http(s) + host público. Retorna o host. Levanta ValueError."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"scheme de URL não permitido: {parsed.scheme!r}")
    host = parsed.hostname or ""
    if not host or not host_is_public(host):
        raise ValueError(f"host de URL não permitido (privado/interno): {host!r}")
    return host


async def assert_url_externa(url: str) -> None:
    """Versão async: valida a URL fora do event loop (DNS é bloqueante).

    Deixa o `ValueError` propagar para o chamador tratar (bloquear o request).
    """
    await asyncio.to_thread(validar_url_externa, url)
