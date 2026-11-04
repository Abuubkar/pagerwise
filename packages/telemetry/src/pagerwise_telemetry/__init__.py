"""One telemetry setup for every Pagerwise app (docs/adr/0012).

`setup("pagerwise-consumer")` at the top of an app's main():
- traces, metrics and logs go over OTLP to the OpenTelemetry Collector (OTEL_EXPORTER_OTLP_ENDPOINT, default
  localhost:4317), which tail-samples traces into Jaeger, sends metrics to Prometheus and logs to Loki;
- stdout gets one JSON object per log line (structlog), with trace_id and span_id when a span is current;
- httpx and Redis are instrumented; FastAPI apps and SQLAlchemy engines are instrumented by `instrument_app` and
  `instrument_engine`, Kafka by `pagerwise_kafka.instrument`.

Every exported span passes the DenylistSpanProcessor: prompt text, message content, query strings and credentials
never leave the process, whichever library set them. OTEL_SDK_DISABLED=true keeps the JSON logs and exports nothing.
Modules get their tracer and meter with trace.get_tracer / metrics.get_meter at import time; those are proxies until
setup runs, so code (and tests) that never call setup pay almost nothing."""

import logging
import os
import socket
import sys
from collections.abc import Iterable, Mapping, MutableMapping
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from typing import Any

import structlog
from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, Span, SpanLimits, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Link

# Attribute keys never exported. Content: prompts and model output (GenAI content attributes, opt-in in the
# conventions, denied here even if a library opts in), the search query (spans carry pagerwise.query_hash instead).
# URLs: a query string can carry the question (/v1/search?q=...). Credentials: request and response headers.
DENYLIST = frozenset({
    "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.system_instructions", "gen_ai.prompt",
    "gen_ai.completion", "gen_ai.retrieval.query.text", "pagerwise.query",
    "url.full", "url.query", "http.url", "http.target",
    "db.query.parameters", "enduser.id",
})
DENYLIST_PREFIXES = ("http.request.header.", "http.response.header.", "gen_ai.prompt.", "gen_ai.completion.")


def denied(key: str) -> bool:
    return key in DENYLIST or key.startswith(DENYLIST_PREFIXES)


def _allowed(attributes: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not attributes or not any(denied(k) for k in attributes):
        return None  # nothing to drop
    return {k: v for k, v in attributes.items() if not denied(k)}


class DenylistSpanProcessor(SpanProcessor):
    """Passes each ended span on to `next_` without denylisted attribute keys, on the span itself, its events and
    its links. A span with nothing to drop is passed on as it is."""

    def __init__(self, next_: SpanProcessor):
        self.next = next_

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        self.next.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        attributes = _allowed(span.attributes)
        events = [(e, _allowed(e.attributes)) for e in span.events]
        links = [(link, _allowed(link.attributes)) for link in span.links]
        if attributes is None and all(a is None for _, a in events) and all(a is None for _, a in links):
            self.next.on_end(span)
            return
        self.next.on_end(ReadableSpan(
            name=span.name, context=span.context, parent=span.parent, resource=span.resource,
            attributes=span.attributes if attributes is None else attributes,
            events=[e if a is None else Event(e.name, a, e.timestamp) for e, a in events],
            links=[link if a is None else Link(link.context, a) for link, a in links],
            kind=span.kind, status=span.status, start_time=span.start_time, end_time=span.end_time,
            instrumentation_scope=span.instrumentation_scope,
        ))

    def shutdown(self) -> None:
        self.next.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.next.force_flush(timeout_millis)


def setup(service: str, package: str | None = None) -> None:
    """Call once, first thing in main(). Configures JSON logging always, and OTLP export unless OTEL_SDK_DISABLED.
    `package` names the distribution whose version is service.version, when it isn't the service name."""
    exporting = os.environ.get("OTEL_SDK_DISABLED", "").lower() != "true"
    handlers: list[logging.Handler] = [_json_stdout()]
    if exporting:
        resource = Resource.create({
            "service.name": service,
            "service.version": _version(package or service),
            "service.instance.id": f"{socket.gethostname()}-{os.getpid()}",
            "deployment.environment.name": os.environ.get("PAGERWISE_ENV", "local"),
        })
        # db.statement of a multi-row insert grows with the batch (tens of KB in a storm): 2,048 characters shows the
        # statement's shape, and nothing else of ours comes close.
        tracer_provider = TracerProvider(resource=resource, span_limits=SpanLimits(max_span_attribute_length=2048))
        # The consumer makes a few spans per alert at thousands of alerts a second: a big queue, exported every
        # second, so bursts are queued rather than dropped.
        tracer_provider.add_span_processor(DenylistSpanProcessor(BatchSpanProcessor(
            OTLPSpanExporter(), max_queue_size=50_000, max_export_batch_size=2048, schedule_delay_millis=1000)))
        trace.set_tracer_provider(tracer_provider)
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[
            PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=10_000)]))
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
        handlers.append(LoggingHandler(logger_provider=logger_provider))
        _instrument_clients()
    root = logging.getLogger()
    root.handlers[:] = handlers
    root.setLevel(logging.INFO)
    for noisy in ("httpx", "httpcore", "aiokafka", "opentelemetry"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _instrument_clients() -> None:
    """httpx and Redis, where the app installs them: the instrumentations import their library, and docs-mock and
    the simulator have neither."""
    if find_spec("httpx"):
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    if find_spec("redis"):
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()


def instrument_app(app: Any) -> None:
    """FastAPI server spans. Health checks are left out: they'd be most of the traces and say nothing."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health")


def instrument_engine(engines: Iterable[Any]) -> None:
    """SQLAlchemy spans for these async engines (their sync_engine is what SQLAlchemy runs underneath)."""
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    # 0.66b2 declares sqlalchemy < 2.1 and, without skip_dep_check, logs one error and instruments nothing. Its engine
    # event hooks work on 2.1 async engines (tests/test_sqlalchemy.py checks a span appears): recheck on each bump.
    SQLAlchemyInstrumentor().instrument(engines=[e.sync_engine for e in engines], skip_dep_check=True)


def _add_trace_ids(_: Any, __: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event["trace_id"] = format(context.trace_id, "032x")
        event["span_id"] = format(context.span_id, "016x")
    return event


def _json_stdout() -> logging.Handler:
    """stdlib logging rendered by structlog as one JSON object per line. The apps keep logging.getLogger: this
    formats what they log, with level, logger, timestamp and the current trace's ids."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_trace_ids,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    ))
    return handler


def _version(service: str) -> str:
    try:
        return version(service)
    except PackageNotFoundError:
        return "unknown"
