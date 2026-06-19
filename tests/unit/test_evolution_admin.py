"""Tests do admin Evolution (provision/connect/state/disconnect)."""

import json

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
    monkeypatch.setattr(settings, "evolution_api_key", SecretStr("instance-abc"))


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
    # O header do webhook (Evolution→nós) tem que carregar a chave per-instance
    # que o handler valida — NÃO a global key (regressão 2026-05-31).
    sent = json.loads(body)
    assert sent["webhook"]["headers"]["apikey"] == "instance-abc"
    assert sent["webhook"]["headers"]["apikey"] != "global-xyz"
    # byEvents=False: Evolution posta na rota BASE (/webhook/evolution); True
    # postaria em subpaths inexistentes → 404 → inbound nunca chega (regressão).
    assert sent["webhook"]["byEvents"] is False
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


@pytest.mark.asyncio
@respx.mock
async def test_get_instance_owner_number_extrai_jid():
    respx.get("https://evo.test/instance/fetchInstances").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "inst1", "connectionStatus": "open",
                 "ownerJid": "556784249725@s.whatsapp.net"}
            ],
        )
    )
    num = await admin.get_instance_owner_number("inst1")
    assert num == "+556784249725"


@pytest.mark.asyncio
@respx.mock
async def test_get_instance_owner_number_sem_dono():
    respx.get("https://evo.test/instance/fetchInstances").mock(
        return_value=httpx.Response(
            200, json=[{"name": "inst1", "connectionStatus": "close"}]
        )
    )
    assert await admin.get_instance_owner_number("inst1") is None


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


# ---- Diagnóstico de 401/403 (Mudança 1) ----


def test_classify_admin_error_401():
    msg = admin.classify_admin_error(admin.EvolutionAdminError(401, "Unauthorized"))
    assert msg is not None
    assert "rejeitada (401)" in msg
    assert "evo.test" in msg  # aponta o servidor
    assert "global-xyz" not in msg  # nunca vaza o segredo


def test_classify_admin_error_403_missing_key():
    msg = admin.classify_admin_error(
        admin.EvolutionAdminError(403, "Missing global api key")
    )
    assert msg is not None
    assert "rejeitada (403)" in msg


def test_classify_admin_error_non_auth_returns_none():
    assert admin.classify_admin_error(admin.EvolutionAdminError(409, "in use")) is None
    assert admin.classify_admin_error(admin.EvolutionAdminError(403, "Forbidden")) is None


def test_describe_key_source(monkeypatch):
    assert admin.describe_key_source() == "EVOLUTION_GLOBAL_API_KEY"
    monkeypatch.setattr(settings, "evolution_global_api_key", None)
    assert admin.describe_key_source() == "EVOLUTION_API_KEY (fallback)"
    monkeypatch.setattr(settings, "evolution_api_key", None)
    assert admin.describe_key_source() == "(nenhuma key configurada)"


# ---- Código de pareamento (Mudança 2) ----


@pytest.mark.asyncio
@respx.mock
async def test_connect_instance_com_pairing_code():
    route = respx.get("https://evo.test/instance/connect/test1").mock(
        return_value=httpx.Response(
            200, json={"pairingCode": "WZYEH1YY", "code": "x", "count": 1}
        )
    )
    data = await admin.connect_instance("test1", phone_number="+55 11 99999-9999")
    assert data["pairingCode"] == "WZYEH1YY"
    # número normalizado (só dígitos) vai no ?number=
    assert route.calls[0].request.url.params["number"] == "5511999999999"


@pytest.mark.asyncio
@respx.mock
async def test_connect_instance_pairing_retry_on_null(monkeypatch):
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(admin.asyncio, "sleep", _noop)
    route = respx.get("https://evo.test/instance/connect/test1").mock(
        side_effect=[
            httpx.Response(200, json={"pairingCode": None, "count": 0}),
            httpx.Response(200, json={"pairingCode": "ABCD1234", "count": 1}),
        ]
    )
    data = await admin.connect_instance("test1", phone_number="5511999999999")
    assert data["pairingCode"] == "ABCD1234"
    assert route.call_count == 2  # re-tentou 1×
