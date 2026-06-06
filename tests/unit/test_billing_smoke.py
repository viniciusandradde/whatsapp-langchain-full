"""Sprint B.6 — smoke tests endpoints billing + webhook Asaas."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeBillingEndpoints:
    def test_checkout_sem_auth_401(self) -> None:
        resp = _client().post("/api/billing/checkout", json={"plano": "pro"})
        assert resp.status_code == 401, resp.text

    def test_historico_sem_auth_401(self) -> None:
        resp = _client().get("/api/billing/historico")
        assert resp.status_code == 401, resp.text

    def test_cancel_sem_auth_401(self) -> None:
        resp = _client().post("/api/billing/cancel")
        assert resp.status_code == 401, resp.text

    def test_status_sem_auth_401(self) -> None:
        resp = _client().get("/api/billing/status")
        assert resp.status_code == 401, resp.text

    def test_checkout_plano_invalido_rejeita(self) -> None:
        # Mesmo sem auth, body inválido deve dar 422 antes
        # (Pydantic valida antes de Depends)
        resp = _client().post(
            "/api/billing/checkout",
            headers={"Authorization": "Bearer fake"},
            json={"plano": "ultra"},  # não bate o pattern (pro|enterprise)
        )
        assert resp.status_code in (401, 422), resp.text


class TestSmokeAsaasWebhook:
    # O webhook resolve o token efetivo (DB>env) via get_asaas_effective — mockado
    # aqui pra não tocar Postgres (em prod o DB é rápido; sem DB no teste travaria).
    @staticmethod
    def _patch_resolver(monkeypatch, webhook_token: str):
        from unittest.mock import AsyncMock

        from whatsapp_langchain.server.routes import asaas_webhook as wh

        monkeypatch.setattr(wh, "get_pool", AsyncMock(return_value=object()))
        monkeypatch.setattr(
            wh,
            "get_asaas_effective",
            AsyncMock(return_value={"webhook_token": webhook_token}),
        )

    def test_webhook_sem_token_401(self, monkeypatch) -> None:
        self._patch_resolver(monkeypatch, "tok-configurado")
        resp = _client().post("/webhook/asaas", json={"event": "PAYMENT_CONFIRMED"})
        assert resp.status_code == 401, resp.text

    def test_webhook_token_errado_401(self, monkeypatch) -> None:
        self._patch_resolver(monkeypatch, "tok-configurado")
        resp = _client().post(
            "/webhook/asaas",
            headers={"asaas-access-token": "valor-errado"},
            json={"event": "PAYMENT_CONFIRMED"},
        )
        assert resp.status_code == 401, resp.text

    def test_webhook_sem_config_503(self, monkeypatch) -> None:
        # Sem token configurado (nem DB nem env) → 503.
        self._patch_resolver(monkeypatch, "")
        resp = _client().post(
            "/webhook/asaas",
            headers={"asaas-access-token": "qualquer"},
            json={"event": "PAYMENT_CONFIRMED"},
        )
        assert resp.status_code == 503, resp.text


class TestAsaasClientConfig:
    def test_raises_se_nao_configurado(self):
        import pytest

        from whatsapp_langchain.integrations.asaas import AsaasClient, AsaasError

        # Settings em dev tem asaas_api_key=None
        from whatsapp_langchain.shared.config import settings

        if settings.asaas_enabled:
            pytest.skip(
                "ASAAS_API_KEY configurado nesse env — teste só faz sentido sem"
            )

        with pytest.raises(AsaasError, match="não configurado"):
            AsaasClient()

    def test_base_url_environment(self):
        from whatsapp_langchain.shared.config import Settings

        s_sandbox = Settings(asaas_environment="sandbox")
        assert s_sandbox.asaas_base_url == "https://api-sandbox.asaas.com/v3"

        s_prod = Settings(asaas_environment="production")
        assert s_prod.asaas_base_url == "https://api.asaas.com/v3"


class TestWebhookEventProcessing:
    """Unit tests do dispatcher process_asaas_webhook (sem DB real)."""

    async def test_evento_desconhecido_nao_explode(self, monkeypatch):
        """Eventos não-mapeados devem retornar action_taken=ignored."""
        from unittest.mock import AsyncMock

        from whatsapp_langchain.shared import asaas as asaas_mod

        # Mock _resolve, _log, _mark_log
        monkeypatch.setattr(
            asaas_mod,
            "_resolve_empresa_from_event",
            AsyncMock(return_value=1),
        )
        monkeypatch.setattr(asaas_mod, "_log_billing_event", AsyncMock(return_value=99))
        monkeypatch.setattr(asaas_mod, "_mark_log_processado", AsyncMock())

        result = await asaas_mod.process_asaas_webhook(
            pool=None,  # type: ignore
            event={
                "event": "SUBSCRIPTION_UPDATED",  # não mapeado
                "payment": {"id": "p1", "customer": "c1"},
            },
        )
        assert result["processado"] is True
        assert result["action_taken"] == "ignored"

    async def test_evento_sem_customer_unknown(self, monkeypatch):
        from unittest.mock import AsyncMock

        from whatsapp_langchain.shared import asaas as asaas_mod

        monkeypatch.setattr(
            asaas_mod,
            "_resolve_empresa_from_event",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(asaas_mod, "_log_billing_event", AsyncMock(return_value=99))

        result = await asaas_mod.process_asaas_webhook(
            pool=None,  # type: ignore
            event={"event": "PAYMENT_CONFIRMED", "payment": {}},
        )
        assert result["processado"] is False
        assert result["reason"] == "unknown_customer"
