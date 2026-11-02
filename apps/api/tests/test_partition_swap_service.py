"""The online partition migration of alert_events (migrations 0006 and 0007 plus the backfill), run while a writer
keeps inserting: no row lost, none duplicated, and the result really is partitioned."""

import asyncio
import random
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from pagerwise_api.partitions import backfill

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

NOW = datetime.now(UTC)
INSERT = text("""INSERT INTO alert_events (event_id, source, service, fingerprint, severity, occurred_at, summary)
                 VALUES (:id, 'test', 'ledger', 'fp', 'warning', :at, 'x')""")


async def migrate(revision: str) -> None:
    from conftest import REPO

    config = Config(str(REPO / "alembic.ini"))
    upgrade = command.upgrade if revision == "head" or revision >= "0006" else command.downgrade
    await asyncio.to_thread(upgrade, config, revision)  # env.py runs its own event loop


async def test_partition_swap_under_concurrent_inserts_loses_no_rows(postgres_url):
    engine = create_async_engine(postgres_url, pool_size=4)
    await migrate("0005")  # back to the plain table
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE alert_events, dead_letters"))
    rng = random.Random(1)
    history = [{"id": uuid.uuid4(), "at": NOW - timedelta(days=rng.uniform(0, 20))} for _ in range(20_000)]
    async with engine.begin() as conn:
        await conn.execute(INSERT, history)

    written: list[uuid.UUID] = []
    stop = asyncio.Event()

    async def writer() -> None:
        """One alert per commit, as the consumer would; a few with old timestamps, like delayed retries."""
        while not stop.is_set():
            row = {"id": uuid.uuid4(), "at": NOW - timedelta(days=rng.choice([0, 0, 0, 3]), seconds=rng.uniform(0, 60))}
            while True:
                try:
                    async with engine.begin() as conn:
                        await conn.execute(INSERT, row)
                    break
                except DBAPIError:  # e.g. a cached statement invalidated by the swap's renames: retry the row
                    await asyncio.sleep(0.01)
            written.append(row["id"])
            await asyncio.sleep(0.002)

    writing = asyncio.create_task(writer())
    await migrate("0006")  # shadow + mirror trigger, while the writer runs
    progress = await backfill(engine, batch_size=5_000)
    before_swap = len(written)
    await migrate("0007")  # the swap, while the writer runs
    await asyncio.sleep(1)  # keep writing into the partitioned table for a moment
    stop.set()
    await writing
    await migrate("head")  # leave the shared test database where the other tests expect it

    async with engine.connect() as conn:
        stored = set(await conn.scalars(text("SELECT event_id FROM alert_events")))
        count = await conn.scalar(text("SELECT count(*) FROM alert_events"))
        kind = await conn.scalar(text("SELECT relkind::text FROM pg_class WHERE relname = 'alert_events'"))
        plan = "\n".join(await conn.scalars(text(
            "EXPLAIN SELECT count(*) FROM alert_events "
            "WHERE occurred_at >= now() - interval '7 days' AND occurred_at < now()")))
        partitions = await conn.scalar(text("SELECT count(*) FROM pg_inherits WHERE inhparent = 'alert_events'::regclass"))
    await engine.dispose()

    expected = {h["id"] for h in history} | set(written)
    assert progress.finished and progress.rows_copied > 0
    assert before_swap > 0 and len(written) > before_swap  # writes landed before, during and after the swap
    assert count == len(stored) == len(expected)  # no duplicates
    assert stored == expected  # no row lost
    assert kind == "p"
    # 8 day partitions overlap the window, plus DEFAULT (always a candidate); the other ~20 are pruned.
    scanned = len(re.findall(r" on alert_events_(?:\d{8}|default) ", plan))
    assert 0 < scanned <= 9 and partitions >= 25 and "Subplans Removed" in plan, plan
