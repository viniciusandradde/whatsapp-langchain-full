"""Tests dos templates HSM (submit/sync/send/list/delete)."""

import httpx
import pytest
import respx
from pydantic import SecretStr

from whatsapp_langchain.integrations.waba import templates
from whatsapp_langchain.shared.config import settings


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    monkeypatch.setattr(settings, "waba_graph_api_version", "v21.0")
    monkeypatch.setattr(settings, "meta_app_secret", SecretStr("test-secret"))


@pytest.mark.asyncio
@respx.mock
async def test_submit_template_envia_payload_correto():
    route = respx.post("https://graph.facebook.com/v21.0/WABA1/message_templates").mock(
        return_value=httpx.Response(200, json={"id": "TMPL1", "status": "PENDING"})
    )
    result = await templates.submit_template(
        access_token="EAA",
        waba_account_id="WABA1",
        nome="boas_vindas",
        categoria="UTILITY",
        idioma="pt_BR",
        componentes_json=[{"type": "BODY", "text": "olá {{1}}"}],
    )
    assert result["id"] == "TMPL1"
    assert route.called
    sent = route.calls[0].request
    body = sent.read()
    assert b"boas_vindas" in body
    assert b"UTILITY" in body


@pytest.mark.asyncio
@respx.mock
async def test_submit_template_400_levanta():
    respx.post("https://graph.facebook.com/v21.0/WABA1/message_templates").mock(
        return_value=httpx.Response(400, text="invalid components")
    )
    with pytest.raises(templates.WabaTemplateError):
        await templates.submit_template(
            access_token="EAA",
            waba_account_id="WABA1",
            nome="x",
            categoria="UTILITY",
            idioma="pt_BR",
            componentes_json=[],
        )


@pytest.mark.asyncio
@respx.mock
async def test_sync_template_status_retorna_status_atual():
    respx.get("https://graph.facebook.com/v21.0/TMPL1").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "boas_vindas",
                "status": "APPROVED",
                "category": "UTILITY",
                "language": "pt_BR",
            },
        )
    )
    data = await templates.sync_template_status("EAA", "TMPL1")
    assert data["status"] == "APPROVED"


@pytest.mark.asyncio
@respx.mock
async def test_list_remote_templates_retorna_array():
    respx.get("https://graph.facebook.com/v21.0/WABA1/message_templates").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": "T1", "name": "x", "status": "APPROVED"},
                    {"id": "T2", "name": "y", "status": "PENDING"},
                ]
            },
        )
    )
    data = await templates.list_remote_templates("EAA", "WABA1")
    assert len(data) == 2


@pytest.mark.asyncio
@respx.mock
async def test_send_template_message_substitui_variables():
    route = respx.post("https://graph.facebook.com/v21.0/PHONE1/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.SENT"}]})
    )
    msg_id = await templates.send_template_message(
        access_token="EAA",
        phone_id="PHONE1",
        to="+5511999990000",
        template_name="boas_vindas",
        language="pt_BR",
        variables={"1": "João", "2": "12345"},
    )
    assert msg_id == "wamid.SENT"
    body = route.calls[0].request.read()
    assert b'"type":"template"' in body or b'"type": "template"' in body
    # Variable values devem aparecer no payload
    assert b"Jo" in body  # "João" pode estar urlencoded ou direto
    assert b"12345" in body


@pytest.mark.asyncio
@respx.mock
async def test_delete_template_chama_meta_delete():
    respx.delete("https://graph.facebook.com/v21.0/WABA1/message_templates").mock(
        return_value=httpx.Response(200)
    )
    ok = await templates.delete_template("EAA", "WABA1", "boas_vindas")
    assert ok is True
