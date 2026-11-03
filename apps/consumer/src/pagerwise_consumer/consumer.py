"""Consumes alerts.v1 and its two retry topics into alert_events.

Delivery is at-least-once with idempotent writes: a partition's offset is committed only up to records whose rows
are committed in Postgres, and a record seen twice inserts nothing the second time (ON CONFLICT on event_id).

  poll loop ──> per-partition queue ──> one worker per partition ──> Postgres
     │  pauses every partition when the queues or the DB pool are too full (flow.Backpressure)
     │  pauses a retry partition until its head message is due (seek back, so nothing waits in memory)
     └─ commits each partition's safe offset (offsets.OffsetTracker) every second

Records in one partition are processed in order, by one worker; partitions run in parallel. A record that fails
transiently is republished to the next retry topic and committed; a malformed one, or one out of retries, goes to
alerts.dlq and dead_letters. If Postgres or Kafka itself is down, the batch is retried in place: the partition
stalls, the queues fill, and backpressure stops fetching.

Each record gets a process span in its alert's trace, linked to its batch's span (pagerwise_kafka.tracing); the
consumer's metrics (lag, pauses, outcomes, ingest freshness) are below. docs/adr/0012."""

import asyncio
import hashlib
import json
import logging
import os
import signal
import socket
import time
import uuid
import weakref
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from aiokafka import AIOKafkaConsumer, ConsumerRebalanceListener, ConsumerRecord, TopicPartition
from aiokafka.coordinator.assignors.roundrobin import RoundRobinPartitionAssignor
from aiokafka.errors import KafkaError
from opentelemetry import metrics, propagate, trace
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.trace import Span, Status, StatusCode
from redis.exceptions import RedisError
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import pagerwise_kafka as k
import pagerwise_telemetry as telemetry
from pagerwise_api import bus
from pagerwise_api.db import DeadLetter, ServiceEdge, TriageRun
from pagerwise_api.embedding import embed_passages
from pagerwise_api.settings import settings
from pagerwise_consumer import clustering
from pagerwise_consumer.flow import Backpressure
from pagerwise_consumer.offsets import OffsetTracker

log = logging.getLogger("pagerwise.consumer")
tracer = trace.get_tracer("pagerwise.consumer")
meter = metrics.get_meter("pagerwise.consumer")

EVENTS = meter.create_counter(
    "pagerwise.consumer.events", unit="{event}",
    description="Records processed, by topic and outcome: stored, duplicate, retried, dead_lettered")
DEAD_LETTERS = meter.create_counter("pagerwise.consumer.dead_letters", unit="{event}",
                                    description="Records sent to alerts.dlq, by error class")
FRESHNESS = meter.create_histogram(
    "pagerwise.ingest.freshness", unit="s",
    description="An alert's first publish to its row's commit, retries included (the freshness SLO, docs/slo.md)",
    explicit_bucket_boundaries_advisory=[0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600])

BATCH_MAX = 500  # records per insert; 500 rows x 10 columns stays well under asyncpg's 32k parameter limit
Fault = Callable[[uuid.UUID, int], bool]  # (event_id, attempt) -> fail this attempt transiently?


def no_faults(event_id: uuid.UUID, attempt: int) -> bool:
    return False


def hashed_faults(rate: float) -> Fault:
    """Load-test fault injection. The hash of event_id picks the events, so every replica (and every redelivery)
    agrees on which ones fail: `rate` of all events fail their first attempt, a fifth of those their second too."""

    def fails(event_id: uuid.UUID, attempt: int) -> bool:
        share = int.from_bytes(hashlib.sha256(event_id.bytes).digest()[:8]) / 2**64
        return share < rate and (attempt == 0 or (attempt == 1 and share < rate / 5))

    return fails


@dataclass
class Stats:
    records: int = 0
    inserted: int = 0
    duplicates: int = 0  # valid records whose event_id was already stored (redelivery after a crash or rebalance)
    retried: int = 0
    dead_lettered: int = 0
    pauses: int = 0  # times backpressure paused fetching
    infra_retries: int = 0  # batches retried in place because Postgres or Kafka failed
    incidents_opened: int = 0
    triages_queued: int = 0
    published: int = 0  # incident updates sent to Redis
    publish_failures: int = 0  # best effort: a missed update is re-read from Postgres


class AlertConsumer:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        bootstrap: str = settings.kafka_bootstrap,
        group: str = settings.consumer_group,
        client_id: str | None = None,
        faults: Fault = no_faults,
        retry_delays_s: dict[str, float] | None = None,
        drain_s: float = settings.consumer_drain_s,
        redis_url: str | None = settings.redis_url,  # None: no Redis (tests): no updates, no worker wake-ups
    ):
        self.engine = engine
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self.faults = faults
        self.retry_delays_s = retry_delays_s or {
            k.RETRY_30S: settings.retry_delay_30s_s,
            k.RETRY_5M: settings.retry_delay_5m_s,
        }
        self.drain_s = drain_s
        self.group = group
        self.client_id = client_id or f"consumer-{socket.gethostname()}-{os.getpid()}"
        self.consumer = AIOKafkaConsumer(
            bootstrap_servers=bootstrap,
            group_id=group,
            client_id=self.client_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            # Round-robin deals each topic's partitions out evenly. The sticky assignor balances only the total over
            # all three topics, so a second replica could get just retry partitions and none of alerts.v1 (seen in
            # test_a_consumer_joining_mid_stream...). aiokafka has no cooperative assignor: every rebalance revokes
            # everything, so stickiness bought little anyway.
            partition_assignment_strategy=(RoundRobinPartitionAssignor,),
        )
        self.producer = k.producer(bootstrap)
        self.redis = bus.connect(redis_url) if redis_url else None
        self.edges: set[tuple[str, str]] = set()  # the service graph, for clustering
        self.backpressure = Backpressure(settings.consumer_queue_high, settings.consumer_queue_low,
                                         settings.consumer_pool_high, settings.consumer_pool_low)
        self.stats = Stats()

        self.queues: dict[TopicPartition, deque[ConsumerRecord]] = {}
        self.trackers: dict[TopicPartition, OffsetTracker] = {}
        self.workers: dict[TopicPartition, asyncio.Task] = {}
        self.wakeups: dict[TopicPartition, asyncio.Event] = {}
        self.closing: set[TopicPartition] = set()  # being revoked or shut down: worker exits once its queue is empty
        self.delayed: dict[TopicPartition, int] = {}  # retry partition -> unix ms its head message is due
        self.seek_to: dict[TopicPartition, int] = {}  # partition was seeked back here; drop records until it shows up
        self.committed: dict[TopicPartition, int] = {}
        self.stopping = asyncio.Event()
        self.failure: BaseException | None = None
        _live.add(self)

    def stop(self) -> None:
        self.stopping.set()

    async def run(self) -> None:
        await self._load_edges()
        await self._ensure_partitions()
        await self.producer.start()
        await self.consumer.start()
        self.consumer.subscribe([k.ALERTS, k.RETRY_30S, k.RETRY_5M], listener=_Rebalance(self))
        log.info("%s started", self.client_id)
        last_commit = last_status = last_partitions = time.monotonic()
        try:
            while not self.stopping.is_set():
                self._apply_pauses()
                batches = await self.consumer.getmany(timeout_ms=100, max_records=BATCH_MAX)
                for tp, records in batches.items():
                    self._dispatch(tp, records)
                now = time.monotonic()
                if now - last_commit >= 1:
                    await self._commit()
                    last_commit = now
                if now - last_status >= 5:
                    self._log_status()
                    last_status = now
                if now - last_partitions >= 3600:
                    await self._ensure_partitions()
                    last_partitions = now
        finally:
            # Not called by aiokafka on stop(), so the final drain and commit are ours.
            await self._release(list(self.workers), drain=True)
            await self.consumer.stop()
            await self.producer.stop()
            if self.redis:
                await self.redis.aclose()
            log.info("%s stopped: %s", self.client_id, asdict(self.stats))
        if self.failure:
            raise self.failure

    async def _load_edges(self) -> None:
        async with self.sessions() as session:
            self.edges = {(a, b) for a, b in (await session.execute(
                select(ServiceEdge.from_service, ServiceEdge.to_service))).all()}
        log.info("service graph: %d edges", len(self.edges))

    async def _ensure_partitions(self) -> None:
        """Keeps a week of daily alert_events partitions ahead (create_alert_partitions is a no-op before the table
        is partitioned). Without this, alerts would pile into the DEFAULT partition."""
        try:
            async with self.sessions() as session, session.begin():
                created = await session.scalar(text("SELECT create_alert_partitions(7)"))
            if created:
                log.info("created %d alert_events partitions", created)
        except SQLAlchemyError as e:
            log.warning("couldn't ensure alert_events partitions (%s)", type(e).__name__)

    # --- poll loop side ---

    def _apply_pauses(self) -> None:
        now_ms = int(time.time() * 1000)
        for tp, due in list(self.delayed.items()):
            if due <= now_ms:
                del self.delayed[tp]
        queued = sum(len(q) for q in self.queues.values())
        was_paused = self.backpressure.paused
        if self.backpressure.update(queued, self._pool_used()) and not was_paused:
            self.stats.pauses += 1
            log.warning("backpressure: pausing all partitions (%s)", self.backpressure.reason)
        elif was_paused and not self.backpressure.paused:
            log.info("backpressure: resuming (queue %d)", queued)

        assigned = self.consumer.assignment()
        want = set(assigned) if self.backpressure.paused else {tp for tp in assigned if tp in self.delayed}
        paused = self.consumer.paused()
        if want - paused:
            self.consumer.pause(*(want - paused))
        if paused - want:
            self.consumer.resume(*(paused - want))

    def _pool_used(self) -> float:
        pool = self.engine.pool
        return pool.checkedout() / pool.size()  # type: ignore[attr-defined]  # QueuePool

    def _dispatch(self, tp: TopicPartition, records: list[ConsumerRecord]) -> None:
        if tp in self.closing:
            return
        tracker = self.trackers.setdefault(tp, OffsetTracker())
        queue = self.queues.setdefault(tp, deque())
        now_ms = int(time.time() * 1000)
        for record in records:
            target = self.seek_to.get(tp)
            if target is not None:
                if record.offset != target:
                    continue  # fetched before the seek back; it will be fetched again
                del self.seek_to[tp]
            if tp.topic in self.retry_delays_s:
                due = k.not_before_ms(tp.topic, record.timestamp, self.retry_delays_s)
                if due > now_ms:
                    # Not due yet, and nothing behind it is either (same delay, later publish time). Rewind to it and
                    # pause until it's due instead of holding records in memory.
                    self.delayed[tp] = due
                    self.seek_to[tp] = record.offset
                    self.consumer.seek(tp, record.offset)
                    self.consumer.pause(tp)
                    break
            tracker.add(record.offset)
            queue.append(record)
        if tp not in self.workers:
            self.wakeups[tp] = asyncio.Event()
            self.workers[tp] = asyncio.create_task(self._work(tp), name=f"worker {tp.topic}[{tp.partition}]")
            self.workers[tp].add_done_callback(self._worker_done)
        self.wakeups[tp].set()

    async def _commit(self) -> None:
        offsets = {}
        for tp, tracker in self.trackers.items():
            offset = tracker.committable()
            if offset is not None and offset != self.committed.get(tp):
                offsets[tp] = offset
        if not offsets:
            return
        try:
            await self.consumer.commit(offsets)
            self.committed.update(offsets)
        except KafkaError as e:
            # Mid-rebalance: the partition's next owner re-reads from the last successful commit; rows dedupe.
            log.warning("commit failed (%s: %s)", type(e).__name__, e)

    def _log_status(self) -> None:
        lag = 0
        for tp in self.consumer.assignment():
            highwater = self.consumer.highwater(tp)
            if highwater is not None and tp.topic == k.ALERTS:
                lag += highwater - self.committed.get(tp, highwater)
        log.info(
            "partitions=%d queued=%d paused=%s alerts_lag=%d pool=%.0f%% %s",
            len(self.consumer.assignment()), sum(len(q) for q in self.queues.values()),
            self.backpressure.paused, lag, 100 * self._pool_used(), asdict(self.stats),
        )

    async def _release(self, tps: list[TopicPartition], drain: bool) -> None:
        """Hands partitions back: on revoke, drop what's queued (the next owner re-reads it from the last commit)
        and let in-flight batches finish; on shutdown, drain the queues first. Then commit, within drain_s."""
        tps = [tp for tp in tps if tp in self.workers]
        for tp in tps:
            self.closing.add(tp)
            queue = self.queues[tp]
            if not drain and queue:
                self.trackers[tp].discard_from(queue[0].offset)
                queue.clear()
            self.wakeups[tp].set()
        tasks = [self.workers[tp] for tp in tps]
        if tasks:
            _, unfinished = await asyncio.wait(tasks, timeout=self.drain_s)
            for task in unfinished:
                task.cancel()  # its batch isn't marked done, so it isn't committed: redelivered, deduped
            if unfinished:
                log.warning("%d partitions didn't finish within %.0fs", len(unfinished), self.drain_s)
        await self._commit()
        for tp in tps:
            for state in (self.queues, self.trackers, self.workers, self.wakeups, self.delayed, self.seek_to,
                          self.committed):
                state.pop(tp, None)
            self.closing.discard(tp)

    # --- worker side ---

    def _worker_done(self, task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception() is not None:
            # A bug, not a bad message: stop the process rather than stall the partition silently.
            log.error("%s crashed", task.get_name(), exc_info=task.exception())
            self.failure = task.exception()
            self.stop()

    async def _work(self, tp: TopicPartition) -> None:
        queue, wakeup, tracker = self.queues[tp], self.wakeups[tp], self.trackers[tp]
        while True:
            if not queue:
                if tp in self.closing:
                    return
                wakeup.clear()
                await wakeup.wait()
                continue
            batch = [queue.popleft() for _ in range(min(len(queue), BATCH_MAX))]
            await self._process(tp, batch)
            for record in batch:
                tracker.done(record.offset)

    async def _process(self, tp: TopicPartition, records: list[ConsumerRecord]) -> None:
        batch = k.batch_span(tp.topic, tp.partition, self.group, len(records))
        spans = [k.process_span(r.topic, r.partition, r.offset, r.key, r.headers, self.group, batch) for r in records]
        rows, stored, failures = [], [], []
        for record, span in zip(records, spans, strict=True):
            attempt = k.attempt_of(record.headers)
            try:
                alert = k.decode_alert(record.value)
                if self.faults(alert.event_id, attempt):
                    raise k.TransientError("injected fault")
            except (k.TransientError, k.PermanentError) as e:
                failures.append((record, span, e))
                continue
            rows.append({**alert.model_dump(), "severity": alert.severity.value, "attempt": attempt})
            stored.append((record, span))

        try:
            with trace.use_span(batch, end_on_exit=True):
                batch.set_attribute("pagerwise.kafka.max_x_attempt", max(k.attempt_of(r.headers) for r in records))
                delay = 0.5
                while True:
                    try:
                        inserted = await self._insert(rows)
                        await asyncio.gather(*(self._route(record, span, error) for record, span, error in failures))
                        break
                    except (OSError, SQLAlchemyError, KafkaError) as e:
                        # Postgres or Kafka is failing, not this message. Retrying in place keeps the partition's
                        # order and offsets; a retried route may publish twice, which the event_id and dead_letters
                        # keys absorb.
                        self.stats.infra_retries += 1
                        batch.add_event("retry in place", {"error.type": type(e).__name__})
                        log.warning("batch failed (%s: %s); retrying in %.1fs", type(e).__name__, e, delay)
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 30)
                batch.set_attributes({"pagerwise.inserted": inserted, "pagerwise.failed": len(failures)})
            committed_at = time.time()
            for record, span in stored:
                span.set_attribute(k.tracing.OUTCOME, "stored")
                FRESHNESS.record(committed_at - k.published_ms(record.timestamp, record.headers) / 1000,
                                 {"messaging.destination.name": record.topic}, context=trace.set_span_in_context(span))
        finally:
            for span in spans:
                span.end()
        EVENTS.add(inserted, {"messaging.destination.name": tp.topic, "outcome": "stored"})
        EVENTS.add(len(rows) - inserted, {"messaging.destination.name": tp.topic, "outcome": "duplicate"})
        self.stats.records += len(records)
        self.stats.inserted += inserted
        self.stats.duplicates += len(rows) - inserted

    async def _insert(self, rows: list[dict]) -> int:
        """Clusters and stores the batch in one transaction, queueing a triage for each incident it opened, then tells
        Redis which incidents changed and wakes the triage worker."""
        if not rows:
            return 0
        async with self.sessions() as session, session.begin():
            with tracer.start_as_current_span("incident upsert") as span:
                result = await clustering.store_alerts(session, rows, self.edges, self._embed)
                opened = [t for t in result.touched.values() if t.opened]
                span.set_attributes({"pagerwise.alerts": len(rows), "pagerwise.inserted": result.inserted,
                                     "pagerwise.incidents_touched": len(result.touched),
                                     "pagerwise.incidents_opened": len(opened)})
                carrier: dict[str, str] = {}
                propagate.inject(carrier)  # this span's context: the triage trace links back to it
            trace.get_current_span().set_attribute("pagerwise.incidents_opened", len(opened))
            # In the same transaction: an incident is never committed without its triage queued.
            runs = [TriageRun(incident_id=t.incident_id, incident_version=1, tenant="default",
                              traceparent=carrier.get("traceparent")) for t in opened]
            session.add_all(runs)
            await session.flush()
            queued = [(run.id, run.tenant) for run in runs]
        self.stats.incidents_opened += len(opened)
        self.stats.triages_queued += len(queued)
        await self._notify(result.touched.values(), queued)
        return result.inserted

    @staticmethod
    async def _embed(texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(embed_passages, texts) if texts else []  # CPU-bound ONNX work

    async def _notify(self, touched, queued: list) -> None:
        """Best effort: a missed incident update is re-read from Postgres, and a missed wake-up only delays the
        triage worker until its next poll. Auto-started triages count against the default tenant's slots (force:
        never refused), so people asking for more see the queue is busy."""
        if self.redis is None or not (touched or queued):
            return
        messages = [{"type": "opened" if t.opened else "updated", "incident_id": str(t.incident_id),
                     "alerts_added": t.alerts, **t.after} for t in touched]
        try:
            if messages:
                await bus.publish_incidents(self.redis, messages)
                self.stats.published += len(messages)
            for run_id, tenant in queued:
                await bus.acquire_triage_slot(self.redis, tenant, run_id, force=True)
            if queued:
                await bus.wake_worker(self.redis)
        except (RedisError, OSError) as e:
            self.stats.publish_failures += len(messages)
            if self.stats.publish_failures == len(messages):  # log the first failure, not every batch
                log.warning("Redis unavailable (%s); continuing without incident updates", e)

    async def _route(self, record: ConsumerRecord, span: Span, error: Exception) -> None:
        """Republishes a failed record to its next topic. The send span is a child of the record's process span, so
        the hop stays in the alert's trace."""
        error_class = type(error).__name__
        span.set_status(Status(StatusCode.ERROR, f"{error_class}: {str(error)[:200]}"))
        span.set_attribute("error.type", error_class)
        target, headers = k.route_failure(record.topic, record.partition, record.offset, record.headers, error,
                                          timestamp_ms=record.timestamp)
        with trace.use_span(span):
            sent = await self.producer.send_and_wait(target, record.value, key=record.key, headers=headers)
        outcome = "dead_lettered" if target == k.DLQ else "retried"
        span.set_attribute(k.tracing.OUTCOME, outcome)
        EVENTS.add(1, {"messaging.destination.name": record.topic, "outcome": outcome})
        if target != k.DLQ:
            self.stats.retried += 1
            return
        DEAD_LETTERS.add(1, {"error.type": error_class})
        origin = k.origin_of(record.topic, record.partition, record.offset, record.headers)
        named = {name: value.decode(errors="replace") for name, value in headers}
        row = {
            "original_topic": origin.topic,
            "original_partition": origin.partition,
            "original_offset": origin.offset,
            "dlq_offset": sent.offset,
            "key": record.key.decode(errors="replace") if record.key else None,
            "payload": record.value or b"",
            "headers": named,
            "error_class": type(error).__name__,
            "error": str(error)[:2000],
            "attempt": int(named[k.H_ATTEMPT]),
            "first_failed_at": datetime.fromtimestamp(int(named[k.H_FIRST_FAILED_AT]) / 1000, UTC),
        }
        statement = insert(DeadLetter).values(row).on_conflict_do_nothing(
            index_elements=["original_topic", "original_partition", "original_offset"]
        )
        async with self.sessions() as session:
            await session.execute(statement)
            await session.commit()
        self.stats.dead_lettered += 1


_live: weakref.WeakSet[AlertConsumer] = weakref.WeakSet()  # what the gauges below read


def _observe_lag(options: CallbackOptions) -> Iterable[Observation]:
    """End offset minus committed offset, per assigned partition (runs on the metric reader's thread)."""
    for consumer in list(_live):
        try:
            assigned = consumer.consumer.assignment()
        except Exception:  # noqa: BLE001, S112 - mid-rebalance or stopped: nothing to report this time
            continue
        for tp in assigned:
            highwater, committed = consumer.consumer.highwater(tp), consumer.committed.get(tp)
            if highwater is not None and committed is not None:
                yield Observation(highwater - committed, {"messaging.destination.name": tp.topic,
                                                          "messaging.destination.partition.id": str(tp.partition)})


def _observe_paused(options: CallbackOptions) -> Iterable[Observation]:
    """Paused partitions by reason: backpressure (queue or db_pool, which pause every partition) or retry_delay (a
    retry partition waiting for its head message to be due)."""
    for consumer in list(_live):
        try:
            assigned = len(consumer.consumer.assignment())
        except Exception:  # noqa: BLE001, S112 - as above
            continue
        for cause in ("queue", "db_pool"):
            yield Observation(assigned if consumer.backpressure.cause == cause else 0, {"reason": cause})
        yield Observation(len(consumer.delayed), {"reason": "retry_delay"})


meter.create_observable_gauge("pagerwise.consumer.lag", callbacks=[_observe_lag], unit="{message}",
                              description="End offset minus committed offset, per partition")
meter.create_observable_gauge("pagerwise.consumer.paused", callbacks=[_observe_paused], unit="{partition}",
                              description="Paused partitions, by reason")


class _Rebalance(ConsumerRebalanceListener):
    """aiokafka awaits these and holds getmany() until they return."""

    def __init__(self, owner: AlertConsumer):
        self.owner = owner

    async def on_partitions_revoked(self, revoked: set[TopicPartition]) -> None:
        if revoked:
            log.info("revoked %d partitions", len(revoked))
        await self.owner._release(list(revoked), drain=False)

    async def on_partitions_assigned(self, assigned: set[TopicPartition]) -> None:
        log.info("assigned %d partitions: %s", len(assigned), _summarize(assigned))


def _summarize(tps: set[TopicPartition]) -> str:
    by_topic: dict[str, list[int]] = {}
    for tp in tps:
        by_topic.setdefault(tp.topic, []).append(tp.partition)
    return " ".join(f"{topic}{sorted(parts)}" for topic, parts in sorted(by_topic.items()))


async def _main() -> None:
    engine = create_async_engine(settings.database_url, pool_size=settings.consumer_db_pool_size, max_overflow=0)
    telemetry.instrument_engine([engine])
    consumer = AlertConsumer(engine, faults=hashed_faults(settings.consumer_fault_transient_rate))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, consumer.stop)
    try:
        await consumer.run()
    finally:
        await engine.dispose()
        print(json.dumps({"client_id": consumer.client_id, **asdict(consumer.stats)}), flush=True)


def main() -> None:
    telemetry.setup("pagerwise-consumer")
    k.instrument()
    asyncio.run(_main())
