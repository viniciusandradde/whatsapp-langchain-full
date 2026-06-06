"""R9 — idempotência (dedup) do webhook Asaas + 5xx em falha (não perder pagamento).

Mock-based: os helpers de DB de `shared.asaas` são monkeypatchados, então não
toca Postgres. Verifica o fluxo de dispatch/dedup e o status code do handler.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from whatsapp_langchain.shared import asaas

_EVENT = {
    "id": "evt_123",
    "event": "PAYMENT_CONFIRMED",
    "payment": {"id": "pay_1", "customer": "cus_1", "subscription": "sub_1"},
}


async def test_skips_duplicate_event(monkeypatch):
    """Evento duplicado (log_id None via ON CONFLICT) NÃO reprocessa."""
    monkeypatch.setattr(asaas, "_resolve_empresa_from_event", AsyncMock(return_value=1))
    monkeypatch.setattr(asaas, "_log_billing_event", AsyncMock(return_value=None))
    marca = AsyncMock(return_value=99)
    monkeypatch.setattr(asaas, "_mark_transacao_paga", marca)
    monkeypatch.setattr(asaas, "_ativar_plano_pos_pagamento", AsyncMock())

    result = await asaas.process_asaas_webhook(object(), _EVENT)

    assert result == {"processado": False, "reason": "duplicate_event"}
    marca.assert_not_called()  # não dispara efeito de novo


async def test_dispatches_new_event_and_passes_dedup_key(monkeypatch):
    """Evento novo: registra (com dedup_key=event.id) e dispara o efeito."""
    monkeypatch.setattr(asaas, "_resolve_empresa_from_event", AsyncMock(return_value=1))
    log_mock = AsyncMock(return_value=10)
    monkeypatch.setattr(asaas, "_log_billing_event", log_mock)
    monkeypatch.setattr(asaas, "_mark_log_processado", AsyncMock())
    marca = AsyncMock(return_value=99)
    ativa = AsyncMock()
    monkeypatch.setattr(asaas, "_mark_transacao_paga", marca)
    monkeypatch.setattr(asaas, "_ativar_plano_pos_pagamento", ativa)

    result = await asaas.process_asaas_webhook(object(), _EVENT)

    assert result["processado"] is True
    assert result["action_taken"] == "plano_ativado"
    marca.assert_awaited_once()
    ativa.assert_awaited_once()
    # dedup_key = event.id do Asaas
    assert log_mock.await_args.kwargs["dedup_key"] == "evt_123"


async def test_dedup_key_sintetizada_sem_event_id(monkeypatch):
    """Sem event.id, dedup_key é sintetizada como event_type:payment_id."""
    monkeypatch.setattr(asaas, "_resolve_empresa_from_event", AsyncMock(return_value=1))
    log_mock = AsyncMock(return_value=10)
    monkeypatch.setattr(asaas, "_log_billing_event", log_mock)
    monkeypatch.setattr(asaas, "_mark_log_processado", AsyncMock())
    monkeypatch.setattr(asaas, "_mark_transacao_paga", AsyncMock(return_value=1))
    monkeypatch.setattr(asaas, "_ativar_plano_pos_pagamento", AsyncMock())

    event = {"event": "PAYMENT_CONFIRMED", "payment": {"id": "pay_9", "customer": "c"}}
    await asaas.process_asaas_webhook(object(), event)

    assert log_mock.await_args.kwargs["dedup_key"] == "PAYMENT_CONFIRMED:pay_9"


def test_webhook_5xx_on_processing_error(monkeypatch):
    """Falha de processamento → 503 (Asaas retenta), não 200 (perda silenciosa)."""
    from fastapi.testclient import TestClient

    from whatsapp_langchain.server.main import app
    from whatsapp_langchain.server.routes import asaas_webhook as wh

    monkeypatch.setattr(wh, "get_pool", AsyncMock(return_value=object()))
    # token efetivo vem do resolver (DB>env) — mock retorna token configurado
    monkeypatch.setattr(
        wh, "get_asaas_effective", AsyncMock(return_value={"webhook_token": "tok"})
    )

    async def boom(pool, event):
        raise RuntimeError("db transient down")

    monkeypatch.setattr(wh, "process_asaas_webhook", boom)

    resp = TestClient(app).post(
        "/webhook/asaas",
        headers={"asaas-access-token": "tok"},
        json={"event": "PAYMENT_CONFIRMED", "payment": {}},
    )
    assert resp.status_code == 503, resp.text


async def test_get_asaas_effective_empty_key_disabled(monkeypatch):
    """API key vazia/whitespace NÃO conta como configurado (bug: chamava Asaas
    com token vazio → 401 access_token_not_found, que o front mostrava como
    'Sessão expirada')."""
    from pydantic import SecretStr

    from whatsapp_langchain.shared.config import settings

    monkeypatch.setattr(asaas, "get_platform_config", AsyncMock(return_value=None))
    monkeypatch.setattr(settings, "asaas_api_key", SecretStr("   "))

    cfg = await asaas.get_asaas_effective(object())
    assert cfg["enabled"] is False
    assert cfg["source"] == "none"


async def test_get_asaas_effective_real_env_key_enabled(monkeypatch):
    """API key real no env → enabled, source=env, key strip-ada."""
    from pydantic import SecretStr

    from whatsapp_langchain.shared.config import settings

    monkeypatch.setattr(asaas, "get_platform_config", AsyncMock(return_value=None))
    monkeypatch.setattr(settings, "asaas_api_key", SecretStr(" $aact_real "))

    cfg = await asaas.get_asaas_effective(object())
    assert cfg["enabled"] is True
    assert cfg["source"] == "env"
    assert cfg["api_key"] == "$aact_real"
