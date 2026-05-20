"""Tests do WabaClient (outbound via Meta Cloud API)."""

import httpx
import pytest
import respx
from pydantic import SecretStr

from whatsapp_langchain.integrations.waba.client import (
    WabaClient,
    WabaSendError,
    _normalize_to,
    _split_long_body,
    is_valid_wamid,
)
from whatsapp_langchain.shared.config import settings


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    monkeypatch.setattr(settings, "waba_graph_api_version", "v21.0")
    monkeypatch.setattr(settings, "meta_app_secret", SecretStr("test-secret"))


def test_normalize_to_strip_whatsapp_and_plus():
    assert _normalize_to("whatsapp:+5511999990000") == "5511999990000"
    assert _normalize_to("+5511999990000") == "5511999990000"
    assert _normalize_to("5511999990000") == "5511999990000"


def test_split_long_body_keeps_short():
    short = "Olá!"
    assert _split_long_body(short) == [short]


def test_split_long_body_breaks_on_space():
    body = "ab " * 2000  # > 4096
    chunks = _split_long_body(body, limit=100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks).replace(" ", "") == body.replace(" ", "")


def test_is_valid_wamid():
    assert is_valid_wamid("wamid.HBgM5e1Z2WGw")
    assert not is_valid_wamid("xxx")


def test_mock_mode_não_chama_http():
    client = WabaClient(access_token="x", phone_id="p", delivery_mode="mock")
    assert client.delivery_mode == "mock"


@pytest.mark.asyncio
async def test_send_message_mock_retorna_id():
    client = WabaClient(access_token="x", phone_id="p", delivery_mode="mock")
    msg_id = await client.send_message("+5511999990000", "olá")
    assert msg_id.startswith("wamid.MOCK_")


@pytest.mark.asyncio
@respx.mock
async def test_send_message_real_posta_pra_meta():
    respx.post("https://graph.facebook.com/v21.0/PHONE_ID/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.ABC"}]})
    )
    client = WabaClient(access_token="EAA", phone_id="PHONE_ID", delivery_mode="real")
    msg_id = await client.send_message("+5511999990000", "olá")
    assert msg_id == "wamid.ABC"


@pytest.mark.asyncio
@respx.mock
async def test_send_message_400_levanta_erro():
    respx.post("https://graph.facebook.com/v21.0/PHONE_ID/messages").mock(
        return_value=httpx.Response(400, text="invalid number")
    )
    client = WabaClient(access_token="EAA", phone_id="PHONE_ID", delivery_mode="real")
    with pytest.raises(WabaSendError):
        await client.send_message("+5511999990000", "olá")


@pytest.mark.asyncio
async def test_constructor_rejeita_credentials_vazias_em_real():
    with pytest.raises(ValueError):
        WabaClient(access_token="", phone_id="x", delivery_mode="real")
    with pytest.raises(ValueError):
        WabaClient(access_token="x", phone_id="", delivery_mode="real")


@pytest.mark.asyncio
async def test_send_typing_mock_retorna_false():
    client = WabaClient(access_token="x", phone_id="p", delivery_mode="mock")
    assert await client.send_typing("+55", "wamid.X") is False
