"""Tests do admin Evolution (provision/connect/state/disconnect)."""

import httpx
import pytest
import respx
from pydantic import SecretStr

from whatsapp_langchain.integrations.evolution import admin
from whatsapp_langchain.shared.config import settings


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    monkeypatch.setattr(settings, "evolution_admin_url", "https://evo.test")
    monkeypatch.setattr(settings, "evolution_api_url", "https://evo.test")
    monkeypatch.setattr(settings, "evolution_global_api_key", SecretStr("global-xyz"))


@pytest.mark.asyncio
@respx.mock
async def test_provision_instance_envia_payload():
    route = respx.post("https://evo.test/instance/create").mock(
        return_value=httpx.Response(201, json={"instance": {"instanceName": "x"}})
    )
    result = await admin.provision_instance("x", webhook_url="https://app/wh")
    assert route.called
    body = route.calls[0].request.read()
    assert b'"instanceName":"x"' in body or b'"instanceName": "x"' in body
    assert b"webhook" in body
    assert result["instance"]["instanceName"] == "x"


@pytest.mark.asyncio
@respx.mock
async def test_connect_instance_retorna_qr():
    respx.get("https://evo.test/instance/connect/test1").mock(
        return_value=httpx.Response(
            200, json={"base64": "data:image/png;base64,IIIIIII"}
        )
    )
    data = await admin.connect_instance("test1")
    assert data["base64"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
@respx.mock
async def test_get_connection_state_open():
    respx.get("https://evo.test/instance/connectionState/inst").mock(
        return_value=httpx.Response(
            200, json={"instance": {"instanceName": "inst", "state": "open"}}
        )
    )
    raw = await admin.get_connection_state("inst")
    assert admin.normalize_state(raw) == "open"


@pytest.mark.asyncio
@respx.mock
async def test_disconnect_instance_ok():
    respx.delete("https://evo.test/instance/logout/inst").mock(
        return_value=httpx.Response(200)
    )
    assert await admin.disconnect_instance("inst") is True


def test_normalize_state_mapping():
    assert admin.normalize_state({"instance": {"state": "open"}}) == "open"
    assert admin.normalize_state({"instance": {"state": "connecting"}}) == "connecting"
    assert admin.normalize_state({"instance": {"state": "close"}}) == "disconnected"
    assert admin.normalize_state({"state": "open"}) == "open"
    assert admin.normalize_state({}) == "error"


def test_headers_falha_sem_config(monkeypatch):
    monkeypatch.setattr(settings, "evolution_admin_url", "")
    monkeypatch.setattr(settings, "evolution_api_url", "")
    with pytest.raises(admin.EvolutionAdminError):
        admin._headers()
