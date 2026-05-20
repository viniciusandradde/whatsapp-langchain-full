"""Tests do OAuth Meta Embedded Signup (WABA)."""

import httpx
import pytest
import respx
from pydantic import SecretStr

from whatsapp_langchain.integrations.waba import oauth
from whatsapp_langchain.shared.config import settings


@pytest.fixture(autouse=True)
def _patch_meta_settings(monkeypatch):
    monkeypatch.setattr(settings, "meta_app_id", "1234567890")
    monkeypatch.setattr(settings, "meta_app_secret", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "meta_config_id", "config_abc")
    monkeypatch.setattr(settings, "waba_webhook_verify_token", SecretStr("verify_xx"))
    monkeypatch.setattr(settings, "waba_graph_api_version", "v21.0")
    monkeypatch.setattr(
        settings,
        "meta_oauth_redirect_uri",
        "https://x.com/api/conexoes/waba/oauth/callback",
    )


def test_state_token_unique():
    a = oauth.generate_state_token()
    b = oauth.generate_state_token()
    assert a != b
    assert len(a) >= 32


def test_build_oauth_url_inclui_scopes_e_solution():
    url = oauth.build_oauth_url(state="xyz123")
    assert "client_id=1234567890" in url
    assert "whatsapp_business_management" in url
    assert "whatsapp_business_messaging" in url
    assert "state=xyz123" in url
    assert "whatsapp_embedded_signup" in url
    assert "config_abc" in url


def test_build_oauth_url_falha_sem_config(monkeypatch):
    monkeypatch.setattr(settings, "meta_app_id", "")
    with pytest.raises(oauth.WabaOAuthError):
        oauth.build_oauth_url("state")


@pytest.mark.asyncio
@respx.mock
async def test_exchange_code_retorna_token():
    respx.get("https://graph.facebook.com/v21.0/oauth/access_token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "EAAxxx", "token_type": "bearer"}
        )
    )
    data = await oauth.exchange_code_for_token("authcode")
    assert data["access_token"] == "EAAxxx"


@pytest.mark.asyncio
@respx.mock
async def test_exchange_code_levanta_erro_em_400():
    respx.get("https://graph.facebook.com/v21.0/oauth/access_token").mock(
        return_value=httpx.Response(400, text="bad code")
    )
    with pytest.raises(oauth.WabaOAuthError):
        await oauth.exchange_code_for_token("badcode")


@pytest.mark.asyncio
@respx.mock
async def test_list_waba_accounts_combina_business_waba_phones():
    base = "https://graph.facebook.com/v21.0"
    respx.get(f"{base}/me/businesses").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "biz1"}]})
    )
    respx.get(f"{base}/biz1/owned_whatsapp_business_accounts").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "waba1", "name": "Loja Aurora"}]}
        )
    )
    respx.get(f"{base}/waba1/phone_numbers").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "phone1",
                        "display_phone_number": "+55 11 99999-0000",
                        "verified_name": "Loja Aurora",
                    }
                ]
            },
        )
    )
    accounts = await oauth.list_waba_accounts("EAAxxx")
    assert len(accounts) == 1
    assert accounts[0].id == "waba1"
    assert accounts[0].name == "Loja Aurora"
    assert len(accounts[0].phone_numbers) == 1
    assert accounts[0].phone_numbers[0].id == "phone1"
