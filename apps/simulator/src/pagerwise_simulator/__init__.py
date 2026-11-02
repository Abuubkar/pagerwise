"""Alerts for a simulated 12-service system, published to alerts.v1 at a steady rate.

Valid alerts go through the shared AlertV1 model before sending, as every producer's do. Malformed ones (a set share,
for load tests) deliberately skip it: bad JSON, a missing field, an unknown severity, an extra field.

uv run python -m pagerwise_simulator --rate 200 --duration 10 [--malformed-rate 0.01]
"""

import argparse
import asyncio
import hashlib
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pagerwise_kafka as k

# service -> (share of traffic, alert rules as (alertname, severity, summary)). Skewed like a real storm: a few
# services raise most of the alerts.
SERVICES: dict[str, tuple[int, list[tuple[str, str, str]]]] = {
    "api-gateway": (14, [("GatewayHigh5xxRate", "critical", "5xx rate {pct}% on {instance}"),
                         ("GatewayLatencyHigh", "warning", "p99 {ms} ms on {instance}")]),
    "auth": (6, [("AuthTokenErrors", "warning", "token validation errors {pct}% on {instance}")]),
    "payments": (18, [("PaymentsP99LatencyHigh", "critical", "payments p99 {ms} ms on {instance}"),
                      ("PaymentsAcquirerTimeouts", "critical", "acquirer timeouts {pct}% on {instance}")]),
    "card-auth": (8, [("CardAuthDeclineSpike", "warning", "decline rate {pct}% on {instance}")]),
    "ledger": (16, [("LedgerWriteErrors", "critical", "write errors {pct}% on {instance}"),
                    ("LedgerPoolExhausted", "critical", "connection pool waiting={n} on {instance}")]),
    "postgres-primary": (10, [("PostgresReplicationLag", "warning", "replica lag {ms} ms on {instance}"),
                              ("PostgresFailover", "critical", "primary failed over to {instance}")]),
    "redis-cache": (5, [("RedisEvictionsHigh", "warning", "evictions {n}/s on {instance}")]),
    "notifications": (4, [("NotificationQueueBacklog", "warning", "backlog {n} messages on {instance}")]),
    "search": (5, [("SearchLatencyHigh", "warning", "query p95 {ms} ms on {instance}")]),
    "inventory": (4, [("InventorySyncStale", "info", "last sync {n}s ago on {instance}")]),
    "orders": (7, [("OrdersCheckoutErrors", "critical", "checkout errors {pct}% on {instance}")]),
    "kafka-broker": (3, [("BrokerUnderReplicated", "warning", "{n} under-replicated partitions on {instance}")]),
}
_NAMES = list(SERVICES)
_WEIGHTS = [weight for weight, _ in SERVICES.values()]


def make_alert(rng: random.Random, run_id: str) -> k.AlertV1:
    service = rng.choices(_NAMES, _WEIGHTS)[0]
    alertname, severity, summary = rng.choice(SERVICES[service][1])
    instance = f"{service}-{rng.randint(0, 5)}"
    return k.AlertV1(
        event_id=uuid.uuid4(),
        source="simulator",
        service=service,
        fingerprint=hashlib.sha1(f"{service}/{alertname}/{instance}".encode()).hexdigest()[:16],
        severity=k.Severity(severity),
        occurred_at=datetime.now(UTC),
        labels={"alertname": alertname, "instance": instance, "region": rng.choice(["eu-west-1", "us-east-1"]),
                "run": run_id},
        summary=summary.format(instance=instance, pct=rng.randint(2, 40), ms=rng.randint(400, 5000),
                               n=rng.randint(5, 900)),
    )


def make_malformed(rng: random.Random, run_id: str) -> tuple[bytes, bytes]:
    alert = json.loads(make_alert(rng, run_id).model_dump_json())
    match rng.randrange(4):
        case 0:
            value = b'{"event_id": "' + alert["event_id"].encode() + b'", "service": '  # truncated JSON
        case 1:
            del alert["fingerprint"]
            value = json.dumps(alert).encode()
        case 2:
            alert["severity"] = "page-everyone"
            value = json.dumps(alert).encode()
        case _:
            alert["priority"] = "P1"  # not in the schema, which forbids extra fields
            value = json.dumps(alert).encode()
    return alert["service"].encode(), value


@dataclass
class Produced:
    run_id: str
    valid_ids: list[uuid.UUID] = field(default_factory=list)
    malformed: int = 0
    seconds: float = 0.0

    @property
    def sent(self) -> int:
        return len(self.valid_ids) + self.malformed


async def produce(bootstrap: str, rate: float, duration_s: float, malformed_rate: float = 0.0,
                  run_id: str | None = None, seed: int | None = None) -> Produced:
    """Publishes `rate` events a second for `duration_s`, in 10 ms ticks. Falls behind only if Kafka does."""
    rng = random.Random(seed)
    result = Produced(run_id or uuid.uuid4().hex[:8])
    producer = k.producer(bootstrap)
    await producer.start()
    try:
        tick, owed, in_flight = 0.01, 0.0, []
        started = time.monotonic()
        next_tick = started
        while time.monotonic() - started < duration_s:
            owed += rate * tick
            for _ in range(int(owed)):
                if rng.random() < malformed_rate:
                    key, value = make_malformed(rng, result.run_id)
                    result.malformed += 1
                else:
                    alert = make_alert(rng, result.run_id)
                    key, value = k.encode_alert(alert)
                    result.valid_ids.append(alert.event_id)
                in_flight.append(await producer.send(k.ALERTS, value, key=key))
            owed -= int(owed)
            if len(in_flight) >= 5000:
                await asyncio.gather(*in_flight)  # surfaces delivery errors instead of losing them
                in_flight.clear()
            next_tick += tick
            await asyncio.sleep(max(0.0, next_tick - time.monotonic()))
        await asyncio.gather(*in_flight)
        result.seconds = time.monotonic() - started
    finally:
        await producer.stop()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bootstrap", default="localhost:19092")
    parser.add_argument("--rate", type=float, default=50, help="events per second")
    parser.add_argument("--duration", type=float, default=10, help="seconds")
    parser.add_argument("--malformed-rate", type=float, default=0.0, help="share of events that are malformed")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    result = asyncio.run(produce(args.bootstrap, args.rate, args.duration, args.malformed_rate, seed=args.seed))
    print(f"run {result.run_id}: {result.sent} events ({len(result.valid_ids)} valid, {result.malformed} malformed) "
          f"in {result.seconds:.1f}s = {result.sent / result.seconds:.0f}/s")
