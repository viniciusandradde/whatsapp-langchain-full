"""R11: guard SSRF do download de mídia (_validate_media_url).

Usa IPs literais (getaddrinfo resolve sem DNS externo) — roda em CI.
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.shared.midia_processing import _validate_media_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",  # loopback
        "http://10.0.0.5/x",  # privado
        "http://192.168.1.1/x",  # privado
        "http://169.254.169.254/latest/meta-data/",  # link-local / metadata cloud
        "http://[::1]/x",  # loopback IPv6
        "ftp://example.com/x",  # scheme não permitido
        "file:///etc/passwd",  # scheme não permitido
    ],
)
def test_rejeita_urls_perigosas(url: str) -> None:
    with pytest.raises(ValueError):
        _validate_media_url(url)


@pytest.mark.parametrize(
    "url,host",
    [
        ("https://1.1.1.1/media.jpg", "1.1.1.1"),  # IP público
        ("http://8.8.8.8/x", "8.8.8.8"),
    ],
)
def test_aceita_host_publico(url: str, host: str) -> None:
    assert _validate_media_url(url) == host
