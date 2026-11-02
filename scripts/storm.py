"""Slice 3's done-when check: an alert storm with bad input, transient failures and a replica dying mid-storm.

Starts consumer replicas as separate processes (with transient-fault injection on), publishes alerts at a steady
rate with a share malformed, SIGKILLs one replica partway through, and samples consumer lag every second. Then waits
for the retries to drain and checks: no valid alert lost, every malformed one dead-lettered, lag recovered.

Needs Redpanda and Postgres from docker compose, topics created, migrations applied.

uv run python scripts/storm.py [--rate 2000] [--duration 180] [--kill-at 60]
"""

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import pagerwise_kafka as k
from pagerwise_api.settings import settings
from pagerwise_simulator import produce

LOGS = Path("build/storm")
BARS = " ▁▂▃▄▅▆▇█"

parser = argparse.ArgumentParser()
parser.add_argument("--rate", type=float, default=2000)
parser.add_argument("--duration", type=float, default=180)
parser.add_argument("--malformed-rate", type=float, default=0.01)
parser.add_argument("--transient-rate", type=float, default=0.05)
parser.add_argument("--replicas", type=int, default=2)
parser.add_argument("--kill-at", type=float, default=60, help="seconds into the storm to SIGKILL replica 0")
parser.add_argument("--settle-timeout", type=float, default=600, help="seconds to wait for retries to drain")
args = parser.parse_args()


class LagSampler:
    """Committed-offset lag per topic, once a second, from the broker's point of view (not the consumers')."""

    def __init__(self) -> None:
        self.samples: list[tuple[float, dict[str, int]]] = []
        self.started = time.monotonic()

    async def run(self, stop: asyncio.Event) -> None:
        admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap)
        reader = AIOKafkaConsumer(bootstrap_servers=settings.kafka_bootstrap)
        await admin.start()
        await reader.start()
        tps = [TopicPartition(t, p) for t in (k.ALERTS, k.RETRY_30S, k.RETRY_5M) for p in range(k.TOPICS[t])]
        try:
            while not stop.is_set():
                ends = await reader.end_offsets(tps)
                committed = await admin.list_consumer_group_offsets(settings.consumer_group)
                lag = {k.ALERTS: 0, k.RETRY_30S: 0, k.RETRY_5M: 0}
                for tp in tps:
                    meta = committed.get(tp)
                    lag[tp.topic] += ends[tp] - (meta.offset if meta and meta.offset >= 0 else 0)
                self.samples.append((time.monotonic() - self.started, lag))
                await asyncio.sleep(1)
        finally:
            await reader.stop()
            await admin.close()

    def latest(self, topic: str) -> int:
        return self.samples[-1][1][topic] if self.samples else 0


def sparkline(values: list[int], width: int = 72) -> str:
    if not values:
        return ""
    step = max(1, -(-len(values) // width))
    buckets = [max(values[i : i + step]) for i in range(0, len(values), step)]
    top = max(buckets) or 1
    return "".join(BARS[min(len(BARS) - 1, round(v / top * (len(BARS) - 1)))] for v in buckets)


def start_replica(i: int) -> subprocess.Popen:
    env = os.environ | {"CONSUMER_FAULT_TRANSIENT_RATE": str(args.transient_rate)}
    log = open(LOGS / f"consumer-{i}.log", "w")  # noqa: SIM115 - closed when the process exits
    return subprocess.Popen([sys.executable, "-m", "pagerwise_consumer"], env=env, stdout=log, stderr=subprocess.STDOUT)


async def group_members() -> int:
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap)
    await admin.start()
    try:
        [response] = await admin.describe_consumer_groups([settings.consumer_group])
        # A raw DescribeGroups response: each group is (error_code, group, state, protocol_type, protocol, members).
        *_, members = response.groups[0]
        return len(members)
    finally:
        await admin.close()


async def main() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    await k.create_topics(settings.kafka_bootstrap)
    engine = create_async_engine(settings.database_url)
    storm_start = datetime.now(UTC)

    print(f"== Storm: {args.rate:.0f} events/s for {args.duration:.0f}s, {args.malformed_rate:.0%} malformed, "
          f"{args.transient_rate:.0%} transient failures, {args.replicas} replicas, replica 0 killed at "
          f"{args.kill_at:.0f}s")
    replicas = [start_replica(i) for i in range(args.replicas)]
    deadline = time.monotonic() + 60
    while await group_members() < args.replicas:
        assert time.monotonic() < deadline, "replicas didn't join the group"
        await asyncio.sleep(1)
    await asyncio.sleep(5)  # let the last rebalance settle
    print(f"  {args.replicas} replicas in group {settings.consumer_group}")

    sampler, stop_sampling = LagSampler(), asyncio.Event()
    sampling = asyncio.create_task(sampler.run(stop_sampling))

    async def kill_later() -> float:
        await asyncio.sleep(args.kill_at)
        replicas[0].send_signal(signal.SIGKILL)
        print(f"  t={time.monotonic() - sampler.started:.0f}s SIGKILL replica 0 (pid {replicas[0].pid})")
        return time.monotonic() - sampler.started

    killing = asyncio.create_task(kill_later())
    produced = await produce(settings.kafka_bootstrap, args.rate, args.duration, args.malformed_rate)
    storm_end = time.monotonic() - sampler.started
    killed_at = await killing
    print(f"  produced {produced.sent} events in {produced.seconds:.1f}s ({produced.sent / produced.seconds:.0f}/s): "
          f"{len(produced.valid_ids)} valid, {produced.malformed} malformed; run {produced.run_id}")
    print(f"  alerts.v1 lag at storm end: {sampler.latest(k.ALERTS)}")

    recovered_after = None
    while recovered_after is None and time.monotonic() - sampler.started - storm_end < 120:
        if sampler.samples and sampler.samples[-1][0] > storm_end and sampler.latest(k.ALERTS) < 1000:
            recovered_after = sampler.samples[-1][0] - storm_end
        await asyncio.sleep(0.5)

    print("\n== Waiting for retries to drain (alerts.retry.5m holds messages for 5 minutes)")
    expected = len(produced.valid_ids)
    settle_deadline = time.monotonic() + args.settle_timeout
    last_report = 0.0
    while True:
        async with engine.connect() as conn:
            stored = await conn.scalar(text("SELECT count(*) FROM alert_events WHERE labels->>'run' = :run"),
                                       {"run": produced.run_id})
        if stored >= expected or time.monotonic() > settle_deadline:
            break
        if time.monotonic() - last_report > 30:
            print(f"  t={time.monotonic() - sampler.started:.0f}s stored {stored}/{expected}, retry lag "
                  f"30s={sampler.latest(k.RETRY_30S)} 5m={sampler.latest(k.RETRY_5M)}")
            last_report = time.monotonic()
        await asyncio.sleep(2)
    await asyncio.sleep(3)  # one more commit cycle before the final lag sample
    stop_sampling.set()
    await sampling

    for replica in replicas[1:]:
        replica.send_signal(signal.SIGTERM)
    finals = []
    for i, replica in enumerate(replicas[1:], start=1):
        replica.wait(timeout=60)
        last = (LOGS / f"consumer-{i}.log").read_text().strip().splitlines()[-1]
        finals.append(json.loads(last))

    async with engine.connect() as conn:
        rows = (await conn.execute(
            text("SELECT event_id, attempt, extract(epoch FROM ingested_at - occurred_at) AS age "
                 "FROM alert_events WHERE labels->>'run' = :run"), {"run": produced.run_id})).all()
        dead = await conn.scalar(
            text("SELECT count(*) FROM dead_letters WHERE created_at >= :t AND original_topic = :topic"),
            {"t": storm_start, "topic": k.ALERTS})
    await engine.dispose()

    stored_ids = {r.event_id for r in rows}
    lost = set(produced.valid_ids) - stored_ids
    attempts = {a: sum(1 for r in rows if r.attempt == a) for a in (0, 1, 2)}
    ages = sorted(float(r.age) for r in rows if r.attempt == 0)
    p50, p95 = (ages[int(len(ages) * q)] if ages else 0 for q in (0.5, 0.95))
    alerts_lag = [lag[k.ALERTS] for _, lag in sampler.samples]

    print("\n== Lag over time (committed-offset lag, one bar per "
          f"{max(1, -(-len(alerts_lag) // 72))}s, scaled to the max)")
    print(f"  alerts.v1        max {max(alerts_lag):>6}  {sparkline(alerts_lag)}")
    for topic in (k.RETRY_30S, k.RETRY_5M):
        series = [lag[topic] for _, lag in sampler.samples]
        print(f"  {topic:16} max {max(series):>6}  {sparkline(series)}")
    width = len(sparkline(alerts_lag))
    marks = [" "] * width
    seconds = sampler.samples[-1][0] or 1
    for at, mark in ((killed_at, "K"), (storm_end, "E")):
        marks[min(width - 1, int(at / seconds * width))] = mark
    print(f"  {'':16}     {'':6}  {''.join(marks)}   K = replica killed, E = storm ended")

    print("\n== Results")
    checks = [
        ("valid events lost (produced IDs vs DB)", len(lost), len(lost) == 0),
        ("malformed produced vs dead-lettered", f"{produced.malformed} vs {dead}", produced.malformed == dead),
        ("alerts.v1 lag < 1,000 within 60s of storm end",
         f"after {recovered_after:.0f}s" if recovered_after is not None else "not within 120s",
         recovered_after is not None and recovered_after <= 60),
    ]
    for name, value, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {value}")
    print(f"  stored by attempt: {attempts[0]} first try, {attempts[1]} after one retry, {attempts[2]} after two")
    print(f"  ingest freshness (first-try events, occurred_at -> row committed): p50 {p50:.2f}s, p95 {p95:.2f}s")
    for final in finals:
        print(f"  surviving replica: {final}")
    print(f"  logs: {LOGS}/consumer-*.log")
    sys.exit(0 if all(ok for _, _, ok in checks) else 1)


asyncio.run(main())
