from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Link

from pagerwise_telemetry import DenylistSpanProcessor, denied


def tracer_and_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(DenylistSpanProcessor(SimpleSpanProcessor(exporter)))
    return provider.get_tracer("test"), exporter


def test_denylisted_keys_never_reach_the_exporter():
    tracer, exporter = tracer_and_exporter()
    with tracer.start_as_current_span("chat qwen") as span:
        span.set_attributes({
            "gen_ai.request.model": "qwen",
            "gen_ai.input.messages": '[{"role": "user", "content": "Why is payments p99 high?"}]',
            "url.query": "q=ledger+pool+exhaustion",
            "http.request.header.authorization": ("Bearer secret",),
            "pagerwise.query_hash": "3f2a9c",
        })
        span.add_event("token", {"gen_ai.output.messages": "the brief", "index": 3})

    [exported] = exporter.get_finished_spans()
    assert dict(exported.attributes or {}) == {"gen_ai.request.model": "qwen", "pagerwise.query_hash": "3f2a9c"}
    assert dict(exported.events[0].attributes or {}) == {"index": 3}
    assert exported.name == "chat qwen" and exported.context == span.get_span_context()


def test_link_attributes_are_filtered_too():
    tracer, exporter = tracer_and_exporter()
    with tracer.start_as_current_span("batch") as batch:
        pass
    link = Link(batch.get_span_context(), {"url.full": "http://x/?q=secret", "kind": "batch"})
    with tracer.start_as_current_span("process", links=[link]):
        pass
    exported = exporter.get_finished_spans()[-1]
    assert dict(exported.links[0].attributes or {}) == {"kind": "batch"}


def test_a_span_with_nothing_denied_is_passed_on_unchanged():
    tracer, exporter = tracer_and_exporter()
    with tracer.start_as_current_span("fts") as span:
        span.set_attribute("pagerwise.result_count", 12)
    [exported] = exporter.get_finished_spans()
    assert dict(exported.attributes or {}) == {"pagerwise.result_count": 12}


def test_prefixes():
    assert denied("http.response.header.set_cookie") and denied("gen_ai.prompt.0.content")
    assert not denied("gen_ai.usage.input_tokens") and not denied("http.route")
