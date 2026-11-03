"""What Pagerwise's producers and consumers agree on: topic names, the alert payload, the retry headers and where a
failed message goes next. contracts/kafka/asyncapi.yaml describes the same things for people.

Retry routing is non-blocking: a message that fails transiently is republished to a delay topic and its original
offset is committed, so one bad message never holds up its partition. x-attempt counts failures so far.

Every message carries a W3C traceparent, set by the producer's span (`instrument`, docs/adr/0012); a republished
message gets the republishing span's, never the one it arrived with."""

import time
from dataclasses import dataclass

from aiokafka import AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError
from pydantic import ValidationError

from pagerwise_kafka.alert_v1 import AlertV1, Severity
from pagerwise_kafka.tracing import batch_span, creation_context, instrument, process_span

__all__ = ["AlertV1", "Severity", "ValidationError", "batch_span", "creation_context", "instrument", "process_span"]

ALERTS = "alerts.v1"
RETRY_30S = "alerts.retry.30s"
RETRY_5M = "alerts.retry.5m"
DLQ = "alerts.dlq"

# Partitions per topic. Alerts are keyed by service, so one service's alerts stay in order. The DLQ has one
# partition so "replay offsets 120-180" names exactly one range.
TOPICS = {ALERTS: 12, RETRY_30S: 12, RETRY_5M: 12, DLQ: 1}
MAX_FAILURES = 3  # the third failure (in alerts.retry.5m) sends the message to the DLQ

H_ATTEMPT = "x-attempt"
H_FIRST_FAILED_AT = "x-first-failed-at"  # unix ms of the first failure
H_ORIGINAL_TOPIC = "x-original-topic"
H_ORIGINAL_PARTITION = "x-original-partition"
H_ORIGINAL_OFFSET = "x-original-offset"
H_ERROR_CLASS = "x-error-class"
H_ORIGINAL_TIMESTAMP = "x-original-timestamp"  # unix ms the message was first published (ingest freshness)
H_REPLAYED_FROM = "x-replayed-from"  # DLQ offset, on a message republished by a replay

TRACE_HEADERS = ("traceparent", "tracestate", "baggage")  # replaced by the producer on every publish

Headers = list[tuple[str, bytes]]


class TransientError(Exception):
    """Might succeed later (a dependency timed out): retried through the delay topics."""


class PermanentError(Exception):
    """Will fail the same way every time (malformed payload): straight to the DLQ."""


def encode_alert(alert: AlertV1) -> tuple[bytes, bytes]:
    """(key, value) for alerts.v1. Building the AlertV1 is the validation: an invalid alert never gets this far."""
    return alert.service.encode(), alert.model_dump_json().encode()


def decode_alert(value: bytes | None) -> AlertV1:
    try:
        return AlertV1.model_validate_json(value or b"")
    except ValidationError as e:
        raise PermanentError(f"invalid alert: {e.error_count()} errors, first: {e.errors()[0]['msg']}") from e


def header(headers: Headers | tuple, name: str) -> str | None:
    for key, value in headers or ():
        if key == name:
            return value.decode()
    return None


def attempt_of(headers: Headers | tuple) -> int:
    """Failures so far: 0 on alerts.v1, 1 on alerts.retry.30s, 2 on alerts.retry.5m."""
    return int(header(headers, H_ATTEMPT) or 0)


@dataclass(frozen=True)
class Origin:
    """Where a message was first published. Stays the same across retry hops, so it identifies the message."""

    topic: str
    partition: int
    offset: int


def origin_of(topic: str, partition: int, offset: int, headers: Headers | tuple) -> Origin:
    original_topic = header(headers, H_ORIGINAL_TOPIC)
    if original_topic is None:
        return Origin(topic, partition, offset)
    return Origin(original_topic, int(header(headers, H_ORIGINAL_PARTITION) or 0),
                  int(header(headers, H_ORIGINAL_OFFSET) or 0))


def published_ms(timestamp_ms: int, headers: Headers | tuple) -> int:
    """When the message was first published: its own timestamp on alerts.v1, carried in a header across retries."""
    return int(header(headers, H_ORIGINAL_TIMESTAMP) or timestamp_ms)


def route_failure(
    topic: str, partition: int, offset: int, headers: Headers | tuple, error: Exception, now_ms: int | None = None,
    timestamp_ms: int | None = None,
) -> tuple[str, Headers]:
    """Where a failed message goes next, and its headers there. Transient failures walk the delay topics; the
    MAX_FAILURES-th failure, or any permanent one, goes to the DLQ. `timestamp_ms` is the failed record's Kafka
    timestamp. Headers other than ours are kept, except trace context: the producer sets its own."""
    failures = attempt_of(headers) + 1
    if isinstance(error, TransientError) and failures < MAX_FAILURES:
        target = RETRY_30S if failures == 1 else RETRY_5M
    else:
        target = DLQ
    origin = origin_of(topic, partition, offset, headers)
    first_failed = header(headers, H_FIRST_FAILED_AT) or str(now_ms if now_ms is not None else int(time.time() * 1000))
    ours = {
        H_ATTEMPT: str(failures),
        H_FIRST_FAILED_AT: first_failed,
        H_ORIGINAL_TOPIC: origin.topic,
        H_ORIGINAL_PARTITION: str(origin.partition),
        H_ORIGINAL_OFFSET: str(origin.offset),
        H_ERROR_CLASS: type(error).__name__,
    }
    original = header(headers, H_ORIGINAL_TIMESTAMP) or (str(timestamp_ms) if timestamp_ms is not None else None)
    if original is not None:
        ours[H_ORIGINAL_TIMESTAMP] = original
    kept = [(k, v) for k, v in headers or () if k not in ours and k not in TRACE_HEADERS]
    return target, kept + [(k, v.encode()) for k, v in ours.items()]


def not_before_ms(topic: str, timestamp_ms: int, delays_s: dict[str, float]) -> int:
    """When a message on a delay topic may be processed: its publish time plus the topic's delay."""
    return timestamp_ms + int(delays_s.get(topic, 0) * 1000)


def producer(bootstrap: str, **overrides) -> AIOKafkaProducer:
    """acks=all with idempotence: a send retried after a timeout can't duplicate or reorder within a partition."""
    options = {"acks": "all", "enable_idempotence": True, "linger_ms": 10}
    return AIOKafkaProducer(bootstrap_servers=bootstrap, **(options | overrides))


async def create_topics(bootstrap: str, replication: int = 1) -> list[str]:
    """Creates any missing topic in TOPICS; returns the ones it created. Existing topics are left as they are."""
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap)
    await admin.start()
    try:
        existing = set(await admin.list_topics())
        missing = [NewTopic(name, partitions, replication) for name, partitions in TOPICS.items() if name not in existing]
        if missing:
            try:
                await admin.create_topics(missing)
            except TopicAlreadyExistsError:
                pass  # another process won the race
        return [t.name for t in missing]
    finally:
        await admin.close()

