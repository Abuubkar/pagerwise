"""The triage worker: runs queued triages one at a time and streams each one's events to Redis.

The queue is the triage_runs table. A run is claimed with UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED),
so several workers could share it, though one is enough for one local model. The worker waits on a Redis wake-up
(sent when a run is queued) and also polls, in case a wake-up was lost. While it generates it renews the run's
heartbeat; a run whose worker died is failed as abandoned by the next request for that incident (service.start_
triage) or claimed again here.

uv run python -m pagerwise_api.worker
"""

import asyncio
import logging
import signal
import time

import httpx
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagerwise_api import bus, triage
from pagerwise_api.db import SessionLocal, TriageRun, engine
from pagerwise_api.embedding import embed_query_v2, rerank
from pagerwise_api.schemas import ProblemCode
from pagerwise_api.service import stale_heartbeat
from pagerwise_api.settings import settings

log = logging.getLogger("pagerwise.worker")


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


async def run_one(sessions: async_sessionmaker[AsyncSession], redis, client: httpx.AsyncClient,  # noqa: ANN001
                  claimed: TriageRun) -> None:
    started = time.monotonic()
    final = "error"
    async with sessions() as session:
        run = await session.get(TriageRun, claimed.id)
        assert run is not None
        try:
            async for name, payload in triage.generate(session, client, run):
                await triage.publish(redis, run.id, name, payload)
                final = name
        except Exception as e:  # a bug, not a model failure: record it, keep the worker alive
            log.exception("triage %s crashed", run.id)
            await session.rollback()
            run = await session.get(TriageRun, claimed.id)
            assert run is not None
            event = await triage.fail(session, run, ProblemCode.TRIAGE_FAILED, f"worker error: {e!r}")
            await triage.publish(redis, run.id, *event)
        finally:
            await bus.release_triage_slot(redis, claimed.tenant, claimed.id)
    log.info("triage %s for incident %s: %s in %.1fs", claimed.id, claimed.incident_id, final,
             time.monotonic() - started)


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
    async with httpx.AsyncClient(base_url=settings.deploy_source_url, timeout=5) as client:
        log.info("triage worker started (deploy source %s)", settings.deploy_source_url)
        try:
            while not stopping.is_set():
                run = await claim_next(SessionLocal)
                if run is None:
                    waiting = asyncio.create_task(bus.wait_for_work(redis, settings.triage_poll_s))
                    stop = asyncio.create_task(stopping.wait())
                    await asyncio.wait({waiting, stop}, return_when=asyncio.FIRST_COMPLETED)
                    for task in (waiting, stop):
                        task.cancel()
                    continue
                await run_one(SessionLocal, redis, client, run)  # finishes the current triage even if asked to stop
        finally:
            await redis.aclose()
            await engine.dispose()
            log.info("triage worker stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    asyncio.run(main())
