"""OpenTelemetry — inicialização + helpers.

Filosofia: setup zero-config por default (console exporter), opt-in
pra OTLP via env (`OTEL_EXPORTER_OTLP_ENDPOINT`). Backend (Tempo,
Jaeger, Honeycomb, Grafana Cloud, Datadog…) fica como decisão ops, não
de código.

Uso típico:

    from whatsapp_langchain.shared.telemetry import init_telemetry

    init_telemetry(service_name="whatsapp-langchain-api")

Pra trace custom dentro de função:

    from whatsapp_langchain.shared.telemetry import tracer

    with tracer.start_as_current_span("preprocess_media"):
        ...

Em produção, plugar OTLP:

    OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318
    OTEL_EXPORTER_OTLP_HEADERS=x-api-key=...
    OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

logger = structlog.get_logger()

_initialized: bool = False


def init_telemetry(
    service_name: str = "whatsapp-langchain",
    service_version: str = "0.1.0",
    environment: str | None = None,
) -> None:
    """Inicializa OTel global. Idempotente — chamadas extra são no-op.

    Args:
        service_name: identificador do serviço nos traces (api, worker)
        service_version: versão do serviço (pra correlacionar deploys)
        environment: production/staging/dev. Default: env ENVIRONMENT
    """
    global _initialized
    if _initialized:
        return

    env = environment or os.environ.get("ENVIRONMENT", "dev")
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": env,
        }
    )
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        # Production-grade: BatchProcessor + OTLP HTTP
        exporter = OTLPSpanExporter(
            endpoint=f"{otlp_endpoint}/v1/traces",
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info(
            "telemetry_initialized",
            mode="otlp",
            endpoint=otlp_endpoint,
            service=service_name,
            env=env,
        )
    elif env == "dev":
        # Dev: console exporter pra fácil debug local
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        logger.info(
            "telemetry_initialized",
            mode="console",
            service=service_name,
            env=env,
        )
    else:
        # Production sem OTLP configurado — silencioso (não polui logs)
        logger.info(
            "telemetry_initialized",
            mode="noop",
            service=service_name,
            env=env,
            note="OTEL_EXPORTER_OTLP_ENDPOINT não setado",
        )

    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer(name: str = "whatsapp_langchain") -> Any:
    """Retorna tracer pra criar spans manuais."""
    return trace.get_tracer(name)


# Tracer singleton pronto pra import direto
tracer = get_tracer()


def instrument_fastapi(app: Any) -> None:
    """Instrumenta FastAPI pra criar span por request automaticamente.

    Não retroage — chame ANTES de app.add_route/include_router se quiser
    cobertura total (mas em prática, depois também funciona pra requests
    novos).
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="/api/health,/metrics",
        )
        logger.info("telemetry_fastapi_instrumented")
    except Exception as exc:  # noqa: BLE001 — instrumentação não-crítica
        logger.warning("telemetry_fastapi_instrument_failed", error=str(exc))
