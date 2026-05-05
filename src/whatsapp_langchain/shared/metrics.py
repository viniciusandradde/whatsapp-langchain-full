"""Prometheus metrics — counters/histograms expostos em `/metrics`.

Uso:

    from whatsapp_langchain.shared.metrics import (
        agent_calls_total, agent_call_duration_seconds, http_requests_total,
    )

    with agent_call_duration_seconds.labels(agent_id="vsa_tech").time():
        result = await invoke_agent(...)
    agent_calls_total.labels(agent_id="vsa_tech", status="ok").inc()

Métricas registradas no `REGISTRY` global do prometheus_client. Endpoint
`/metrics` (instalado em `routes/health.py`) serializa pro formato
Prometheus.
"""

from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Registry global — todas as métricas registram aqui automaticamente.
# (Pra testar, passa registry custom; pra produção, usa o default).

# ---- HTTP ----

http_requests_total = Counter(
    "nexus_http_requests_total",
    "Total HTTP requests por endpoint + status",
    labelnames=["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "nexus_http_request_duration_seconds",
    "Latência HTTP por endpoint",
    labelnames=["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# ---- Worker queue ----

queue_size = Gauge(
    "nexus_queue_size",
    "Tamanho atual da message_queue por status",
    labelnames=["status"],  # queued, processing, failed, done
)

queue_messages_processed_total = Counter(
    "nexus_queue_messages_processed_total",
    "Mensagens processadas pelo worker (com status final)",
    labelnames=["agent_id", "status"],  # status: done, failed
)

queue_processing_duration_seconds = Histogram(
    "nexus_queue_processing_duration_seconds",
    "Tempo total de processamento (claim → done) por mensagem",
    labelnames=["agent_id"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

# ---- Agent / LLM ----

agent_calls_total = Counter(
    "nexus_agent_calls_total",
    "Total invocações do agente",
    labelnames=["agent_id", "status"],  # ok, error, timeout
)

agent_call_duration_seconds = Histogram(
    "nexus_agent_call_duration_seconds",
    "Latência por invocação do agente (inclui tools)",
    labelnames=["agent_id"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0),
)

llm_tokens_total = Counter(
    "nexus_llm_tokens_total",
    "Tokens consumidos por modelo + tipo (in/out)",
    labelnames=["model", "kind"],  # kind: prompt, completion
)

# ---- Outbound ----

outbound_messages_total = Counter(
    "nexus_outbound_messages_total",
    "Mensagens enviadas via provider",
    labelnames=["provider", "status"],  # status: ok, error
)

# ---- Hooks ----

hooks_dispatched_total = Counter(
    "nexus_hooks_dispatched_total",
    "Hooks disparados",
    labelnames=["evento", "status"],  # status: delivered, retry, dlq
)


def render_prometheus_text() -> bytes:
    """Renderiza métricas no formato text/plain do Prometheus."""
    return generate_latest()


CONTENT_TYPE_PROMETHEUS = "text/plain; version=0.0.4; charset=utf-8"
