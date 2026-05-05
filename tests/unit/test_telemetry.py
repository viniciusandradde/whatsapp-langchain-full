"""Tests pra shared/telemetry — verifica init não-crashing."""

from __future__ import annotations

from whatsapp_langchain.shared import telemetry


def test_init_telemetry_idempotente(monkeypatch):
    """Múltiplas chamadas não crashem nem reset state."""
    monkeypatch.setattr(telemetry, "_initialized", False)
    telemetry.init_telemetry(service_name="test-svc")
    assert telemetry._initialized is True
    # 2ª chamada — no-op
    telemetry.init_telemetry(service_name="other-svc")
    assert telemetry._initialized is True


def test_init_telemetry_otlp_endpoint_setado(monkeypatch):
    """Quando OTEL_EXPORTER_OTLP_ENDPOINT está setado, usa OTLP exporter."""
    monkeypatch.setattr(telemetry, "_initialized", False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("ENVIRONMENT", "production")
    # Não crasha mesmo sem servidor OTLP rodando — exporter falha
    # silenciosamente em runtime, init é puro setup
    telemetry.init_telemetry(service_name="test-otlp")
    assert telemetry._initialized is True


def test_get_tracer_funciona(monkeypatch):
    """Tracer retorna objeto válido pra criar spans."""
    monkeypatch.setattr(telemetry, "_initialized", False)
    telemetry.init_telemetry(service_name="test-tracer")
    t = telemetry.get_tracer("test")
    assert t is not None
    # Cria span - não deve levantar
    with t.start_as_current_span("test-span"):
        pass
