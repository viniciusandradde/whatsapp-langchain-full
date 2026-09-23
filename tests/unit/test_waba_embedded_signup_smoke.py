"""Smoke tests do WABA Embedded Signup (FB SDK flow).

Cobre:
- fetch_phone_details (lib oauth) monta GET correto + parseia
- endpoints /waba/config e /waba/embedded-signup exigem service token (401)
- /waba/config nunca vaza meta_app_secret

Mock httpx via respx. Endpoints via TestClient (sem DB — só valida gateway auth).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeAuth:
    """Sem service token, o router de conexões nega tudo (401)."""

    def test_config_requires_auth(self) -> None:
        resp = _client().get("/api/conexoes/waba/config")
        assert resp.status_code == 401, resp.text

    def test_embedded_signup_requires_auth(self) -> None:
        resp = _client().post(
            "/api/conexoes/waba/embedded-signup",
            json={
                "code": "AQDxxxxxxxxxx",
                "waba_account_id": "123",
                "phone_number_id": "456",
            },
        )
        assert resp.status_code == 401, resp.text


class TestFetchPhoneDetails:
    """GET /{phone_id}?fields=display_phone_number,verified_name."""

    @pytest.mark.respx
    async def test_parses_phone_fields(self, respx_mock):
        from whatsapp_langchain.integrations.waba import oauth
        from whatsapp_langchain.shared.config import settings

        version = settings.waba_graph_api_version
        url = f"https://graph.facebook.com/{version}/PHONE123"
        respx_mock.get(url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "display_phone_number": "+55 67 9999-8888",
                    "verified_name": "VSA Tech",
                    "quality_rating": "GREEN",
                },
            )
        )
        out = await oauth.fetch_phone_details("tok", "PHONE123")
        assert out["display_phone_number"] == "+55 67 9999-8888"
        assert out["verified_name"] == "VSA Tech"

    @pytest.mark.respx
    async def test_raises_on_error(self, respx_mock):
        from whatsapp_langchain.integrations.waba import oauth
        from whatsapp_langchain.shared.config import settings

        version = settings.waba_graph_api_version
        respx_mock.get(f"https://graph.facebook.com/{version}/BAD").mock(
            return_value=httpx.Response(400, json={"error": "invalid"})
        )
        with pytest.raises(oauth.WabaOAuthError):
            await oauth.fetch_phone_details("tok", "BAD")


class TestConfigNoSecret:
    """Quando WABA habilitado, /waba/config retorna app_id+config_id, nunca secret."""

    def test_config_payload_shape(self, monkeypatch) -> None:
        from whatsapp_langchain.shared.config import settings

        # Habilita WABA via monkeypatch (sem persistir)
        monkeypatch.setattr(settings, "meta_app_id", "APPID123", raising=False)
        monkeypatch.setattr(settings, "meta_config_id", "CFG456", raising=False)
        from pydantic import SecretStr

        monkeypatch.setattr(
            settings, "meta_app_secret", SecretStr("topsecret"), raising=False
        )
        monkeypatch.setattr(
            settings, "waba_webhook_verify_token", SecretStr("vtok"), raising=False
        )

        # waba_enabled é property derivada — recompute deve dar True agora
        assert settings.waba_enabled is True

        # Importa a função do router diretamente (evita gateway auth no unit)
        import asyncio

        from whatsapp_langchain.server.routes.conexao import waba_config

        result = asyncio.get_event_loop().run_until_complete(waba_config())
        dumped = result.model_dump()
        assert dumped["app_id"] == "APPID123"
        assert dumped["config_id"] == "CFG456"
        # Secret JAMAIS aparece no payload
        assert "topsecret" not in str(dumped)
        assert "secret" not in dumped


# --- estado da conexão reflete register_phone + subscribe_webhook ---
#
# Antes, `state="open"` era gravado ANTES das duas chamadas e os retornos eram
# descartados: a tela dizia "Conectada" mesmo quando o app não ficava inscrito
# nos webhooks — conexão que não recebe uma única mensagem.


async def _criar_conexao_fake(
    monkeypatch,
    *,
    registrou: bool,
    inscreveu: bool,
    waba_mode: str = "cloud_api",
    sync: dict | None = None,
    mocks: dict | None = None,
):
    """Roda `_create_waba_conexao` com todo o I/O mockado e devolve o estado."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from whatsapp_langchain.server.routes import conexao as rotas
    from whatsapp_langchain.shared.models import Conexao

    conexao_fake = Conexao(
        id=1,
        empresa_id=1,
        provider="waba",
        sid="",
        from_number="+5567999999999",
        display_name="teste",
        default_agent_id="agente",
        status="active",
        is_default=False,
        payload_json={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    estados: list[tuple[str, str | None]] = []

    async def _set_state(_pool, _cid, *, state, message):
        estados.append((state, message))

    monkeypatch.setattr(rotas, "upsert_conexao", AsyncMock(return_value=conexao_fake))
    monkeypatch.setattr(rotas, "save_credentials", AsyncMock())
    update = AsyncMock()
    register = AsyncMock(return_value=registrou)
    sincronizar = AsyncMock(
        return_value=sync
        if sync is not None
        else {"smb_app_state_sync": "r1", "history": "r2"}
    )
    monkeypatch.setattr(rotas, "update_waba_fields", update)
    monkeypatch.setattr(rotas, "set_connection_state", _set_state)
    monkeypatch.setattr(rotas.waba_oauth, "register_phone", register)
    monkeypatch.setattr(
        rotas.waba_oauth, "subscribe_webhook", AsyncMock(return_value=inscreveu)
    )
    monkeypatch.setattr(rotas.waba_oauth, "sincronizar_smb", sincronizar)
    if mocks is not None:
        mocks.update(update=update, register=register, sincronizar=sincronizar)

    await rotas._create_waba_conexao(
        None,
        empresa_id=1,
        access_token="tok",
        waba_account_id="waba-1",
        phone_id="phone-1",
        display_name="teste",
        account_description=None,
        from_number="+5567999999999",
        register_phone=True,
        waba_mode=waba_mode,
    )
    return estados


async def test_conexao_fica_aberta_quando_tudo_da_certo(monkeypatch):
    estados = await _criar_conexao_fake(monkeypatch, registrou=True, inscreveu=True)
    assert estados == [("open", None)]


async def test_webhook_nao_assinado_nao_vira_conectada(monkeypatch):
    estados = await _criar_conexao_fake(monkeypatch, registrou=True, inscreveu=False)
    assert len(estados) == 1
    estado, mensagem = estados[0]
    # "error", não "close": o CHECK de connection_state (mig 128) recusa "close".
    assert estado == "error"
    assert mensagem is not None and "webhooks" in mensagem


async def test_numero_nao_registrado_nao_vira_conectada(monkeypatch):
    estados = await _criar_conexao_fake(monkeypatch, registrou=False, inscreveu=True)
    estado, mensagem = estados[0]
    # "error", não "close": o CHECK de connection_state (mig 128) recusa "close".
    assert estado == "error"
    assert mensagem is not None and "registrado" in mensagem


# --- Coexistence (mig 200): pula o /register e sincroniza smb_app_data ---


async def test_cloud_api_registra_e_nao_sincroniza(monkeypatch):
    mocks: dict = {}
    estados = await _criar_conexao_fake(
        monkeypatch, registrou=True, inscreveu=True, mocks=mocks
    )
    assert estados == [("open", None)]
    mocks["register"].assert_awaited_once()
    mocks["sincronizar"].assert_not_awaited()
    assert mocks["update"].await_args.kwargs["waba_mode"] == "cloud_api"


async def test_coexistence_nao_registra_e_sincroniza(monkeypatch):
    mocks: dict = {}
    estados = await _criar_conexao_fake(
        monkeypatch,
        registrou=True,
        inscreveu=True,
        waba_mode="coexistence",
        mocks=mocks,
    )
    assert estados == [("open", None)]
    # A Meta manda pular o register para número do WhatsApp Business app.
    mocks["register"].assert_not_awaited()
    mocks["sincronizar"].assert_awaited_once_with("tok", "phone-1")
    assert mocks["update"].await_args.kwargs["waba_mode"] == "coexistence"


async def test_coexistence_sync_falhou_fica_aberta_com_aviso(monkeypatch):
    estados = await _criar_conexao_fake(
        monkeypatch,
        registrou=True,
        inscreveu=True,
        waba_mode="coexistence",
        sync={"smb_app_state_sync": "r1", "history": None},
    )
    estado, mensagem = estados[0]
    # Recebe e envia — só falta trazer contatos e histórico (rota sincronizar).
    assert estado == "open"
    assert mensagem is not None and "24 horas" in mensagem


class TestSmokeSincronizar:
    def test_sincronizar_requires_auth(self) -> None:
        resp = _client().post("/api/conexoes/1/waba/sincronizar")
        assert resp.status_code == 401, resp.text


class TestSincronizarSmb:
    """POST /{phone}/smb_app_data: contatos primeiro, depois histórico."""

    @pytest.mark.respx
    async def test_chama_os_dois_sync_types_em_ordem(self, respx_mock):
        import json

        from whatsapp_langchain.integrations.waba import oauth
        from whatsapp_langchain.shared.config import settings

        version = settings.waba_graph_api_version
        rota = respx_mock.post(
            f"https://graph.facebook.com/{version}/PHONE1/smb_app_data"
        ).mock(
            return_value=httpx.Response(
                200, json={"messaging_product": "whatsapp", "request_id": "REQ"}
            )
        )
        out = await oauth.sincronizar_smb("tok", "PHONE1")
        assert out == {"smb_app_state_sync": "REQ", "history": "REQ"}
        corpos = [json.loads(c.request.content) for c in rota.calls]
        assert corpos == [
            {"messaging_product": "whatsapp", "sync_type": "smb_app_state_sync"},
            {"messaging_product": "whatsapp", "sync_type": "history"},
        ]
        assert rota.calls[0].request.headers["Authorization"] == "Bearer tok"

    @pytest.mark.respx
    async def test_falha_nao_levanta_e_nao_vaza_token(self, respx_mock, capsys):
        from whatsapp_langchain.integrations.waba import oauth
        from whatsapp_langchain.shared.config import settings

        version = settings.waba_graph_api_version
        respx_mock.post(
            f"https://graph.facebook.com/{version}/PHONE1/smb_app_data"
        ).mock(return_value=httpx.Response(400, json={"error": {"code": 100}}))
        out = await oauth.sincronizar_smb("SEGREDO-TOKEN", "PHONE1")
        assert out == {"smb_app_state_sync": None, "history": None}
        assert "SEGREDO-TOKEN" not in capsys.readouterr().out


class TestListPhoneNumbers:
    @pytest.mark.respx
    async def test_lista_os_numeros_da_waba(self, respx_mock):
        from whatsapp_langchain.integrations.waba import oauth
        from whatsapp_langchain.shared.config import settings

        version = settings.waba_graph_api_version
        respx_mock.get(
            f"https://graph.facebook.com/{version}/WABA1/phone_numbers"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "PH1",
                            "display_phone_number": "+55 67 99999-8888",
                            "verified_name": "Loja",
                        }
                    ]
                },
            )
        )
        numeros = await oauth.list_phone_numbers("tok", "WABA1")
        assert [n.id for n in numeros] == ["PH1"]


# --- PIN do registro (Cloud API): a Meta exige 6 dígitos ---


class TestPinDoRegistro:
    def _input(self, **kw):
        from whatsapp_langchain.server.routes.conexao import WabaEmbeddedSignupInput

        base = {
            "code": "AQDxxxxxxxxxx",
            "waba_account_id": "W1",
            "phone_number_id": "P1",
        }
        base.update(kw)
        return WabaEmbeddedSignupInput(**base)

    def test_cloud_api_sem_pin_recusa(self) -> None:
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="PIN de 6"):
            self._input()

    def test_pin_precisa_de_6_digitos(self) -> None:
        import pydantic

        for ruim in ("12345", "1234567", "12a456"):
            with pytest.raises(pydantic.ValidationError):
                self._input(pin=ruim)

    def test_cloud_api_com_pin_ok_e_coexistence_dispensa(self) -> None:
        assert self._input(pin="123456").pin == "123456"
        coex = self._input(waba_mode="coexistence", register_phone=False)
        assert coex.pin is None


async def test_pin_vai_ao_registro_e_fica_cifrado_nas_credenciais(monkeypatch):
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from whatsapp_langchain.server.routes import conexao as rotas
    from whatsapp_langchain.shared.models import Conexao

    conexao_fake = Conexao(
        id=1,
        empresa_id=1,
        provider="waba",
        from_number="+5567999999999",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    creds = AsyncMock()
    register = AsyncMock(return_value=True)
    monkeypatch.setattr(rotas, "upsert_conexao", AsyncMock(return_value=conexao_fake))
    monkeypatch.setattr(rotas, "save_credentials", creds)
    monkeypatch.setattr(rotas, "update_waba_fields", AsyncMock())
    monkeypatch.setattr(rotas, "set_connection_state", AsyncMock())
    monkeypatch.setattr(rotas.waba_oauth, "register_phone", register)
    monkeypatch.setattr(
        rotas.waba_oauth, "subscribe_webhook", AsyncMock(return_value=True)
    )

    await rotas._create_waba_conexao(
        None,
        empresa_id=1,
        access_token="tok",
        waba_account_id="W1",
        phone_id="P1",
        display_name="x",
        account_description=None,
        from_number="+5567999999999",
        register_phone=True,
        pin="654321",
    )

    assert register.await_args.kwargs["pin"] == "654321"
    # Guardado junto das credenciais (a coluna é cifrada): o próximo registro
    # do mesmo número exige o mesmo PIN.
    assert creds.await_args.args[2]["pin"] == "654321"
