"""Tests pra shared/metrics — verifica registro + render Prometheus."""

from __future__ import annotations

from whatsapp_langchain.shared.metrics import (
    CONTENT_TYPE_PROMETHEUS,
    agent_calls_total,
    http_requests_total,
    queue_size,
    render_prometheus_text,
)


def test_render_prometheus_returns_bytes():
    out = render_prometheus_text()
    assert isinstance(out, bytes)
    assert len(out) > 0


def test_content_type_is_prometheus_format():
    assert "text/plain" in CONTENT_TYPE_PROMETHEUS
    assert "version=0.0.4" in CONTENT_TYPE_PROMETHEUS


def test_counter_inc_aparece_no_render():
    # Incrementa um counter e confirma que aparece no output
    http_requests_total.labels(method="GET", path="/test", status="200").inc()
    out = render_prometheus_text().decode()
    assert "nexus_http_requests_total" in out
    assert 'method="GET"' in out
    assert 'path="/test"' in out


def test_gauge_set_aparece_no_render():
    queue_size.labels(status="queued").set(42)
    out = render_prometheus_text().decode()
    assert "nexus_queue_size" in out
    assert "42" in out


def test_agent_calls_metric_exposed():
    agent_calls_total.labels(agent_id="vsa_tech", status="ok").inc()
    out = render_prometheus_text().decode()
    assert "nexus_agent_calls_total" in out
    assert 'agent_id="vsa_tech"' in out
