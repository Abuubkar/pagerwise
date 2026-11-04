"""The triage worker: runs queued triages one at a time and streams each one's events to Redis.

The queue is the triage_runs table. A run is claimed with UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED),
so several workers could share it, though one is enough for one local model. The worker waits on a Redis wake-up
(sent when a run is queued) and also polls, in case a wake-up was lost. While it generates it renews the run's
heartbeat; a run whose worker died is failed as abandoned by the next request for that incident (service.start_
triage) or claimed again here.

Each run is a `triage` span, linked to the consumer span that queued it (triage_runs.traceparent), so a brief's trace
leads back to its alerts. The worker also probes Ollama, for the "model unreachable" alert (docs/adr/0012).

uv run python -m pagerwise_api.worker
"""

import asyncio
import logging
import signal
import time

import httpx
from opentelemetry import metrics, propagate, trace
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.trace import Link, SpanKind, Status, StatusCode
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import pagerwise_telemetry as telemetry
from pagerwise_api import bus, triage
from pagerwise_api.db import SessionLocal, TriageRun, engine
from pagerwise_api.embedding import embed_query_v2, rerank
from pagerwise_api.schemas import ErrorEvent, ProblemCode
from pagerwise_api.service import stale_heartbeat
from pagerwise_api.settings import settings

log = logging.getLogger("pagerwise.worker")
tracer = trace.get_tracer("pagerwise.worker")
meter = metrics.get_meter("pagerwise.worker")
RUNS = meter.create_counter(
    "pagerwise.triage.runs", unit="{triage}",
    description="Finished triages, by outcome (done, error) and error code: the availability SLO (docs/slo.md)")
TOTAL = meter.create_histogram(
    "pagerwise.triage.duration", unit="s", description="Claim to the last event of a triage, by outcome",
    explicit_bucket_boundaries_advisory=[1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180])
_ollama_up: list[int] = []  # the last probe's result, read by the gauge


def _observe_ollama(options: CallbackOptions):
    if _ollama_up:
        yield Observation(_ollama_up[-1])


meter.create_observable_gauge("pagerwise.ollama.up", callbacks=[_observe_ollama],
                              description="1 if the worker's last probe of Ollama answered, else 0")


async def claim_next(sessions: async_sessionmaker[AsyncSession]) -> TriageRun | None:
    async with sessions() as session:
        next_id = (
            select(TriageRun.id)
            .where(or_(TriageRun.status == "queued", (TriageRun.status == "running") & stale_heartbeat()))
            .order_by(TriageRun.created_at).limit(1).with_for_update(skip_locked=True).scalar_subquery()
        )
        run = await session.scalar(
            update(TriageRun).where(TriageRun.id == next_id)
            .values(status="running", started_at=func.now(), heartbeat_at=func.now()).returning(TriageRun)
        )
        await session.commit()
        return run


async def run_one(sessions: async_sessionmaker[AsyncSession], redis, client: httpx.AsyncClient,
                  claimed: TriageRun) -> None:
    queued_by = trace.get_current_span(propagate.extract({"traceparent": claimed.traceparent or ""}))
    links = [Link(queued_by.get_span_context(), {"pagerwise.link": "queued_by"})] if claimed.traceparent else []
    with tracer.start_as_current_span("triage", kind=SpanKind.CONSUMER, links=links, attributes={
        "pagerwise.triage_id": str(claimed.id), "pagerwise.incident_id": str(claimed.incident_id),
    }) as span:
        started = time.monotonic()
        final, code = await _generate(sessions, redis, client, claimed)
        span.set_attributes({"pagerwise.outcome": final, "pagerwise.error_code": code})
        if final != "done":
            span.set_status(Status(StatusCode.ERROR, code))
        RUNS.add(1, {"outcome": final, "error_code": code})
        TOTAL.record(time.monotonic() - started, {"outcome": final})
    log.info("triage %s for incident %s: %s in %.1fs", claimed.id, claimed.incident_id, final,
             time.monotonic() - started)


async def _generate(sessions: async_sessionmaker[AsyncSession], redis, client: httpx.AsyncClient,
                    claimed: TriageRun) -> tuple[str, str]:
    """Runs triage.generate for the run, publishing its events. (last event name, error code or "")."""
    final, code = "error", ""
    async with sessions() as session:
        run = await session.get(TriageRun, claimed.id)
        assert run is not None
        try:
            async for name, payload in triage.generate(session, client, run):
                await triage.publish(redis, run.id, name, payload)
                final = name
                if isinstance(payload, ErrorEvent):
                    code = str(payload.code)
        except Exception as e:  # a bug, not a model failure: record it, keep the worker alive
            log.exception("triage %s crashed", run.id)
            await session.rollback()
            run = await session.get(TriageRun, claimed.id)
            assert run is not None
            event = await triage.fail(session, run, ProblemCode.TRIAGE_FAILED, f"worker error: {e!r}")
            await triage.publish(redis, run.id, *event)
            final, code = "error", str(ProblemCode.TRIAGE_FAILED)
        finally:
            await bus.release_triage_slot(redis, claimed.tenant, claimed.id)
    return final, code


async def probe_ollama(stopping: asyncio.Event, every_s: float = 15) -> None:
    async with httpx.AsyncClient(base_url=settings.ollama_host, timeout=5) as client:
        while not stopping.is_set():
            try:
                with suppress_instrumentation():  # a trace every 15 s that says nothing
                    (await client.get("/api/version")).raise_for_status()
                _ollama_up[:] = [1]
            except httpx.HTTPError:
                _ollama_up[:] = [0]
            try:
                await asyncio.wait_for(stopping.wait(), every_s)
            except TimeoutError:
                pass


async def main() -> None:
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopping.set)
    # Load the embedding model and the reranker before the first triage, so its document searches don't spend their
    # timeouts loading models and come back degraded.
    await asyncio.to_thread(embed_query_v2, "warm up")
    await asyncio.to_thread(rerank, "warm up", ["load the reranker"])
    redis = bus.connect()
    probing = asyncio.create_task(probe_ollama(stopping))
    async with httpx.AsyncClient(base_url=settings.deploy_source_url, timeout=5) as client:
        log.info("triage worker started (deploy source %s)", settings.deploy_source_url)
        try:
            while not stopping.is_set():
                with suppress_instrumentation():  # polling: a SQL and a Redis trace every 5 s that say nothing
                    run = await claim_next(SessionLocal)
                    if run is None:
                        waiting = asyncio.create_task(bus.wait_for_work(redis, settings.triage_poll_s))
                if run is None:
                    stop = asyncio.create_task(stopping.wait())
                    await asyncio.wait({waiting, stop}, return_when=asyncio.FIRST_COMPLETED)
                    for task in (waiting, stop):
                        task.cancel()
                    continue
                await run_one(SessionLocal, redis, client, run)  # finishes the current triage even if asked to stop
        finally:
            probing.cancel()
            await redis.aclose()
            await engine.dispose()
            log.info("triage worker stopped")


if __name__ == "__main__":
    telemetry.setup("pagerwise-worker", package="pagerwise-api")
    telemetry.instrument_engine([engine])
    asyncio.run(main())
