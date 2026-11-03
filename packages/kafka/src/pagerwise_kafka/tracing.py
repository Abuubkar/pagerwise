"""Kafka spans: one trace per alert, across every retry hop (docs/adr/0012).

Publishing and fetching are traced by opentelemetry-instrumentation-aiokafka (`instrument`): an `<topic> send`
producer span that injects traceparent into the message headers, and `<topic> receive` spans when getmany returns.
What happens to a message after the fetch is ours:

  alerts.v1 send                              simulator
  ├─ alerts.v1 receive                        consumer, at fetch
  └─ alerts.v1 process      x_attempt=0       consumer: ERROR, outcome=retried     ··· link → alerts.v1 batch
     └─ alerts.retry.30s send                 the republish, a child of the failed attempt
        ├─ alerts.retry.30s receive
        └─ alerts.retry.30s process  x_attempt=1  outcome=stored                  ··· link → alerts.retry.30s batch
                                                                                        └─ incident upsert, SQL

A process span's parent is the message's creation context, so one alert's hops form one trace and a dead-lettered
message shows its whole history. Processing happens in a batch (one transaction per partition batch), so each
process span links to its batch span, the ambient context the conventions say to link when the creation context is
the parent. Batch spans start their own traces: the batch's SQL and the incident upsert sit there."""

from collections.abc import Sequence
from typing import Any

from opentelemetry import propagate, trace
from opentelemetry.context import Context
from opentelemetry.propagators.textmap import Getter
from opentelemetry.trace import Link, Span, SpanKind

import pagerwise_kafka as k

tracer = trace.get_tracer("pagerwise.kafka")

X_ATTEMPT = "pagerwise.kafka.x_attempt"  # failures before this delivery: 0 on alerts.v1, 1 on alerts.retry.30s, ...
OUTCOME = "pagerwise.outcome"  # stored | retried | dead_lettered


class _HeaderGetter(Getter[Sequence[tuple[str, bytes]]]):
    def get(self, carrier: Sequence[tuple[str, bytes]], key: str) -> list[str] | None:
        for name, value in carrier:
            if name == key and value is not None:
                return [value.decode(errors="replace")]
        return None

    def keys(self, carrier: Sequence[tuple[str, bytes]]) -> list[str]:
        return [name for name, _ in carrier]


_getter = _HeaderGetter()


def instrument() -> None:
    """Publish and fetch spans for every AIOKafkaProducer and AIOKafkaConsumer in the process. Call after
    pagerwise_telemetry.setup."""
    from opentelemetry.instrumentation.aiokafka import AIOKafkaInstrumentor

    AIOKafkaInstrumentor().instrument(async_produce_hook=_on_send)


async def _on_send(span: Span, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    """A republish says which attempt it carries and why the last one failed."""
    headers = kwargs.get("headers") or ()
    attempt = k.header(headers, k.H_ATTEMPT)
    if attempt is not None:
        span.set_attribute(X_ATTEMPT, int(attempt))
        span.set_attribute("error.type", k.header(headers, k.H_ERROR_CLASS) or "")


def creation_context(headers: Sequence[tuple[str, bytes]] | None) -> Context:
    return propagate.extract(headers or (), getter=_getter)


def batch_span(topic: str, partition: int, group: str, count: int) -> Span:
    """Not made current here: the caller uses trace.use_span around the batch's work."""
    return tracer.start_span(f"{topic} batch", attributes={
        "messaging.system": "kafka",
        "messaging.operation.name": "process",
        "messaging.operation.type": "process",
        "messaging.destination.name": topic,
        "messaging.destination.partition.id": str(partition),
        "messaging.consumer.group.name": group,
        "messaging.batch.message_count": count,
    })


def process_span(topic: str, partition: int, offset: int, key: bytes | None,
                 headers: Sequence[tuple[str, bytes]] | None, group: str, batch: Span) -> Span:
    """One message's processing: a child of the span that published it, linked to the batch that processed it.
    The caller sets OUTCOME (and the error status) and ends it."""
    return tracer.start_span(
        f"{topic} process",
        context=creation_context(headers),
        kind=SpanKind.CONSUMER,
        links=[Link(batch.get_span_context(), {"pagerwise.link": "batch"})],
        attributes={
            "messaging.system": "kafka",
            "messaging.operation.name": "process",
            "messaging.operation.type": "process",
            "messaging.destination.name": topic,
            "messaging.destination.partition.id": str(partition),
            "messaging.kafka.offset": offset,
            "messaging.consumer.group.name": group,
            "messaging.kafka.message.key": key.decode(errors="replace") if key else "",
            X_ATTEMPT: k.attempt_of(tuple(headers or ())),
        },
    )
