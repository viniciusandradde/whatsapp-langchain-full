"""Smoke tests da integração Twilio Content API (templates).

Mock httpx via respx (já em deps). Cobre:
- create_content monta payload correto (friendly_name/language/types/variables)
- submit_whatsapp_approval manda name+category
- fetch_approval_status + normalize_approval_status mapeiam status remoto→local
- list_remote_contents pagina
- TwilioContentError em 4xx/5xx
"""

from __future__ import annotations

import httpx
import pytest

from whatsapp_langchain.integrations.twilio import content as tc

ACCOUNT = "ACtest"
TOKEN = "authtoken32chars"


class TestCreateContent:
    @pytest.mark.respx
    async def test_posts_correct_payload(self, respx_mock):
        route = respx_mock.post("https://content.twilio.com/v1/Content").mock(
            return_value=httpx.Response(
                201, json={"sid": "HX123", "friendly_name": "x"}
            )
        )
        out = await tc.create_content(
            ACCOUNT,
            TOKEN,
            friendly_name="lembrete_consulta",
            language="pt_BR",
            types=tc.build_text_types("Olá {{1}}, sua consulta é {{2}}"),
            variables={"1": "exemplo1", "2": "exemplo2"},
        )
        assert out["sid"] == "HX123"
        import json as _json

        body = _json.loads(route.calls.last.request.content.decode())
        assert body["friendly_name"] == "lembrete_consulta"
        assert body["language"] == "pt_BR"
        assert body["types"]["twilio/text"]["body"].startswith("Olá {{1}}")
        assert body["variables"] == {"1": "exemplo1", "2": "exemplo2"}

    @pytest.mark.respx
    async def test_raises_on_error(self, respx_mock):
        respx_mock.post("https://content.twilio.com/v1/Content").mock(
            return_value=httpx.Response(400, json={"message": "dup name"})
        )
        with pytest.raises(tc.TwilioContentError) as exc:
            await tc.create_content(
                ACCOUNT, TOKEN, friendly_name="x", language="pt_BR",
                types=tc.build_text_types("oi"),
            )
        assert exc.value.status_code == 400


class TestSubmitApproval:
    @pytest.mark.respx
    async def test_submits_name_and_category(self, respx_mock):
        url = "https://content.twilio.com/v1/Content/HX123/ApprovalRequests/whatsapp"
        route = respx_mock.post(url).mock(
            return_value=httpx.Response(200, json={"status": "received"})
        )
        await tc.submit_whatsapp_approval(
            ACCOUNT, TOKEN, "HX123", name="lembrete_consulta", category="UTILITY"
        )
        import json as _json

        body = _json.loads(route.calls.last.request.content.decode())
        assert body == {"name": "lembrete_consulta", "category": "UTILITY"}


class TestApprovalStatus:
    @pytest.mark.respx
    async def test_fetch_and_normalize_approved(self, respx_mock):
        url = "https://content.twilio.com/v1/Content/HX123/ApprovalRequests"
        respx_mock.get(url).mock(
            return_value=httpx.Response(
                200,
                json={"whatsapp": {"status": "approved", "rejection_reason": ""}},
            )
        )
        data = await tc.fetch_approval_status(ACCOUNT, TOKEN, "HX123")
        status, rejection = tc.normalize_approval_status(data)
        assert status == "approved"
        assert rejection in (None, "")

    def test_normalize_rejected(self):
        status, rejection = tc.normalize_approval_status(
            {"whatsapp": {"status": "rejected", "rejection_reason": "invalid format"}}
        )
        assert status == "rejected"
        assert rejection == "invalid format"

    def test_normalize_received_maps_to_pending(self):
        status, _ = tc.normalize_approval_status({"whatsapp": {"status": "received"}})
        assert status == "pending"

    def test_normalize_unknown_defaults_pending(self):
        status, _ = tc.normalize_approval_status({"whatsapp": {"status": "weird"}})
        assert status == "pending"


class TestListRemoteContents:
    @pytest.mark.respx
    async def test_single_page(self, respx_mock):
        respx_mock.get("https://content.twilio.com/v1/Content?PageSize=100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "contents": [
                        {"sid": "HX1", "friendly_name": "t1"},
                        {"sid": "HX2", "friendly_name": "t2"},
                    ],
                    "meta": {"next_page_url": None},
                },
            )
        )
        out = await tc.list_remote_contents(ACCOUNT, TOKEN)
        assert len(out) == 2
        assert {c["sid"] for c in out} == {"HX1", "HX2"}


class TestBuildTextTypes:
    def test_wraps_body(self):
        assert tc.build_text_types("oi {{1}}") == {"twilio/text": {"body": "oi {{1}}"}}
