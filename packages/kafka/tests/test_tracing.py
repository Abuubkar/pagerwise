import pytest
from opentelemetry import propagate, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import pagerwise_kafka as k
from pagerwise_kafka import tracing


@pytest.fixture
def spans(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing, "tracer", provider.get_tracer("test"))
    return exporter


def published_headers(span) -> list[tuple[str, bytes]]:
    carrier: dict[str, str] = {}
    propagate.inject(carrier, context=trace.set_span_in_context(span))
    return [(name, value.encode()) for name, value in carrier.items()]


def test_a_process_span_continues_the_alerts_trace_and_links_its_batch(spans):
    send = tracing.tracer.start_span("alerts.v1 send")
    send.end()
    target, headers = k.route_failure("alerts.v1", 3, 41, published_headers(send), k.TransientError("x"))
    headers += published_headers(send)  # what the republishing producer adds

    batch = k.batch_span(target, 0, "pagerwise-consumer", 1)
    process = k.process_span(target, 0, 7, b"payments", headers, "pagerwise-consumer", batch)
    process.end()
    batch.end()

    exported = {s.name: s for s in spans.get_finished_spans()}
    span = exported["alerts.retry.30s process"]
    assert span.context.trace_id == send.get_span_context().trace_id  # same trace as the original publish
    assert span.parent.span_id == send.get_span_context().span_id
    assert [link.context.span_id for link in span.links] == [batch.get_span_context().span_id]
    assert span.attributes["pagerwise.kafka.x_attempt"] == 1
    assert span.attributes["messaging.kafka.offset"] == 7
    assert exported["alerts.retry.30s batch"].context.trace_id != span.context.trace_id  # batches have their own


def test_without_trace_headers_a_process_span_starts_a_trace(spans):
    batch = k.batch_span("alerts.v1", 0, "g", 1)
    process = k.process_span("alerts.v1", 0, 1, None, [], "g", batch)
    process.end()
    assert spans.get_finished_spans()[0].parent is None
