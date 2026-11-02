"""The consumer against real Redpanda and Postgres: the cases that would lose or duplicate alerts if they broke."""

import asyncio
import random
import time
import uuid

import pytest
from aiokafka import AIOKafkaConsumer, TopicPartition
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

import pagerwise_kafka as k
from pagerwise_api.db import AlertEvent, DeadLetter
from pagerwise_consumer.consumer import AlertConsumer, Fault, no_faults
from pagerwise_simulator import make_alert, make_malformed
from pagerwise_simulator import produce as simulate

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

FAST_RETRIES = {k.RETRY_30S: 0.5, k.RETRY_5M: 1.0}


@pytest.fixture
async def engine(postgres_url: str):
    engine = create_async_engine(postgres_url, pool_size=5, max_overflow=0)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE alert_events, dead_letters"))
    yield engine
    await engine.dispose()


async def produce(bootstrap: str, valid: int, malformed: int = 0, seed: int = 1) -> list[uuid.UUID]:
    """Publishes the alerts in a shuffled order; returns the valid event IDs."""
    rng = random.Random(seed)
    messages, ids = [], []
    for _ in range(valid):
        alert = make_alert(rng, "test")
        ids.append(alert.event_id)
        messages.append(k.encode_alert(alert))
    messages += [make_malformed(rng, "test") for _ in range(malformed)]
    rng.shuffle(messages)
    producer = k.producer(bootstrap)
    await producer.start()
    try:
        await asyncio.gather(*[await producer.send(k.ALERTS, value, key=key) for key, value in messages])
    finally:
        await producer.stop()
    return ids


def start(engine, bootstrap: str, name: str, faults: Fault = no_faults) -> tuple[AlertConsumer, asyncio.Task]:
    consumer = AlertConsumer(engine, bootstrap=bootstrap, group="test", client_id=name, faults=faults,
                             retry_delays_s=FAST_RETRIES, drain_s=10, redis_url=None)
    return consumer, asyncio.create_task(consumer.run())


async def wait_for(engine, alerts: int, dead_letters: int = 0, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while True:
        async with engine.connect() as conn:
            got = (await conn.scalar(select(func.count()).select_from(AlertEvent)),
                   await conn.scalar(select(func.count()).select_from(DeadLetter)))
        if got == (alerts, dead_letters):
            return
        assert time.monotonic() < deadline, f"timed out: (alerts, dead letters) = {got}, want {(alerts, dead_letters)}"
        await asyncio.sleep(0.2)


async def stop(*running: tuple[AlertConsumer, asyncio.Task]) -> None:
    for consumer, _ in running:
        consumer.stop()
    await asyncio.gather(*(task for _, task in running))


async def lag(bootstrap: str, topic: str) -> int:
    """End offsets minus the group's committed offsets, summed over the topic's partitions."""
    reader = AIOKafkaConsumer(bootstrap_servers=bootstrap, group_id="test", enable_auto_commit=False)
    await reader.start()
    try:
        tps = [TopicPartition(topic, p) for p in range(k.TOPICS[topic])]
        ends = await reader.end_offsets(tps)
        return sum([ends[tp] - (await reader.committed(tp) or 0) for tp in tps])
    finally:
        await reader.stop()


async def topic_messages(bootstrap: str, topic: str) -> list:
    reader = AIOKafkaConsumer(topic, bootstrap_servers=bootstrap, auto_offset_reset="earliest")
    await reader.start()
    try:
        return [r for records in (await reader.getmany(timeout_ms=3000)).values() for r in records]
    finally:
        await reader.stop()


async def test_a_malformed_alert_goes_to_the_dlq_and_the_rest_land(engine, kafka_bootstrap):
    ids = await produce(kafka_bootstrap, valid=100, malformed=1)
    running = start(engine, kafka_bootstrap, "a")
    await wait_for(engine, alerts=100, dead_letters=1)
    await stop(running)

    async with engine.connect() as conn:
        stored = set((await conn.scalars(select(AlertEvent.event_id))).all())
        dead = (await conn.execute(select(DeadLetter))).one()
    assert stored == set(ids)
    assert dead.error_class == "PermanentError" and dead.original_topic == k.ALERTS and dead.attempt == 1
    assert len(await topic_messages(kafka_bootstrap, k.DLQ)) == 1
    assert await lag(kafka_bootstrap, k.ALERTS) == 0  # every offset committed, the malformed one included


async def test_two_transient_failures_then_success_lands_once_after_both_delays(engine, kafka_bootstrap):
    [event_id] = await produce(kafka_bootstrap, valid=1)
    running = start(engine, kafka_bootstrap, "a", faults=lambda _, attempt: attempt < 2)
    await wait_for(engine, alerts=1)
    await stop(running)

    async with engine.connect() as conn:
        row = (await conn.execute(select(AlertEvent))).one()
    assert row.event_id == event_id and row.attempt == 2
    assert (row.ingested_at - row.occurred_at).total_seconds() >= sum(FAST_RETRIES.values())  # waited, not hot-looped
    [first] = await topic_messages(kafka_bootstrap, k.RETRY_30S)
    [second] = await topic_messages(kafka_bootstrap, k.RETRY_5M)
    assert k.header(first.headers, k.H_ATTEMPT) == "1" and k.header(second.headers, k.H_ATTEMPT) == "2"
    assert k.header(second.headers, k.H_ORIGINAL_TOPIC) == k.ALERTS
    for topic in (k.ALERTS, k.RETRY_30S, k.RETRY_5M):
        assert await lag(kafka_bootstrap, topic) == 0


async def test_a_consumer_joining_mid_stream_causes_no_duplicates_or_gaps(engine, kafka_bootstrap):
    producing = asyncio.create_task(simulate(kafka_bootstrap, rate=500, duration_s=8))
    first = start(engine, kafka_bootstrap, "a")
    await asyncio.sleep(1)
    second = start(engine, kafka_bootstrap, "b")  # joins while alerts are flowing and the first is busy: a rebalance
    ids = (await producing).valid_ids
    # Each replica gets its share of every topic, so adding one adds alerts.v1 throughput.
    for running in (first, second):
        assert {tp.topic for tp in running[0].consumer.assignment()} == {k.ALERTS, k.RETRY_30S, k.RETRY_5M}
    await wait_for(engine, alerts=len(ids))
    await stop(first, second)

    async with engine.connect() as conn:
        stored = (await conn.scalars(select(AlertEvent.event_id))).all()
    assert sorted(stored) == sorted(ids)  # no gaps
    # No duplicates: revoked partitions committed what they'd finished, so nothing was processed twice.
    assert first[0].stats.duplicates + second[0].stats.duplicates == 0
    assert first[0].stats.records > 0 and second[0].stats.records > 0  # both really took part
    assert await lag(kafka_bootstrap, k.ALERTS) == 0
