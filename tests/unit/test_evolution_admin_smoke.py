"""Smoke + regression test pra provision_instance (fix #448).

Garante que payload do POST /instance/create inclui webhook.headers.apikey
quando EVOLUTION_API_KEY está configurado.

Histórico: Sprint D ativou EVOLUTION_VALIDATE_APIKEY=true em prod, mas
instances criadas via provision_instance NÃO setavam headers.apikey no
webhook config. Resultado: webhooks Evolution chegavam sem apikey, eram
rejeitados 401 e agente parava de responder.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response


@pytest.mark.asyncio
async def test_provision_instance_webhook_inclui_apikey_header(monkeypatch):
    """Regression #448 — webhook config deve ter headers.apikey."""
    from whatsapp_langchain.integrations.evolution import admin as evo_admin
    from whatsapp_langchain.shared.config import settings

    # Stub config: evolution admin habilitado + apikey conhecida
    monkeypatch.setattr(settings, "evolution_admin_url", "https://evo.test/api")
    from pydantic import SecretStr

    monkeypatch.setattr(
        settings, "evolution_global_api_key", SecretStr("TEST_KEY_123")
    )
    monkeypatch.setattr(
        settings, "evolution_api_key", SecretStr("TEST_KEY_123")
    )

    with respx.mock(base_url="https://evo.test/api") as mock:
        mock.post("/instance/create").mock(
            return_value=Response(201, json={"instance": {"instanceName": "x"}})
        )

        await evo_admin.provision_instance(
            "test-instance",
            webhook_url="https://api.example.com/webhook/evolution",
        )

        # Captura o request enviado
        sent = mock.calls[0].request
        import json as _json

        body = _json.loads(sent.content)
        assert "webhook" in body, "payload deve incluir webhook config"
        webhook = body["webhook"]
        assert webhook["url"] == "https://api.example.com/webhook/evolution"
        assert "headers" in webhook, (
            "Fix #448: webhook.headers ausente — Evolution não vai enviar "
            "apikey, /webhook/evolution rejeita 401 se VALIDATE_APIKEY=true"
        )
        assert webhook["headers"].get("apikey") == "TEST_KEY_123", (
            "Fix #448: apikey no header não bate com config"
        )


@pytest.mark.asyncio
async def test_provision_instance_sem_apikey_503(monkeypatch):
    """Sem EVOLUTION_API_KEY, _headers() fail-fast com 503 (esperado)."""
    from whatsapp_langchain.integrations.evolution import admin as evo_admin
    from whatsapp_langchain.shared.config import settings

    monkeypatch.setattr(settings, "evolution_admin_url", "https://evo.test/api")
    monkeypatch.setattr(settings, "evolution_global_api_key", None)
    monkeypatch.setattr(settings, "evolution_api_key", None)

    with pytest.raises(evo_admin.EvolutionAdminError) as exc_info:
        await evo_admin.provision_instance(
            "test-instance",
            webhook_url="https://api.example.com/webhook/evolution",
        )
    assert exc_info.value.status_code == 503
