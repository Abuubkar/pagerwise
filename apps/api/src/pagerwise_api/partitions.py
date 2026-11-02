"""Step 2 of the alert_events partition migration (docs/migrations.md): copy the existing rows into the shadow.

Copies in batches along (occurred_at, event_id), one transaction per batch, and records its position after each,
so it can be stopped and restarted at any time. It only copies up to the last row that existed when it first
started; everything written after that reaches the shadow through the mirror trigger (created by migration 0006
before this ever runs). Inserts use ON CONFLICT DO NOTHING, so a row the trigger already copied is skipped."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ZERO_UUID = uuid.UUID(int=0)


@dataclass
class Progress:
    rows_copied: int
    batches: int
    finished: bool


async def backfill(engine: AsyncEngine, batch_size: int = 50_000,
                   on_batch: Callable[[int, datetime], None] | None = None) -> Progress:
    async with engine.begin() as conn:
        state = (await conn.execute(text("SELECT * FROM alert_events_backfill"))).mappings().first()
        if state is None:
            top = (await conn.execute(text(
                "SELECT occurred_at, event_id FROM alert_events ORDER BY occurred_at DESC, event_id DESC LIMIT 1"
            ))).first()
            await conn.execute(
                text("INSERT INTO alert_events_backfill (upper_occurred_at, upper_event_id) VALUES (:t, :id)"),
                {"t": top.occurred_at if top else None, "id": top.event_id if top else None},
            )
            state = (await conn.execute(text("SELECT * FROM alert_events_backfill"))).mappings().one()
    if state["finished_at"] is not None:
        return Progress(state["rows_copied"], 0, True)

    upper = (state["upper_occurred_at"], state["upper_event_id"])
    position = (state["last_occurred_at"] or datetime.min.replace(tzinfo=UTC), state["last_event_id"] or ZERO_UUID)
    copied, batches = state["rows_copied"], 0
    while upper[0] is not None:
        async with engine.begin() as conn:
            row = (await conn.execute(text("""
                WITH batch AS (
                    SELECT * FROM alert_events
                     WHERE (occurred_at, event_id) > (:after_t, :after_id)
                       AND (occurred_at, event_id) <= (:upper_t, :upper_id)
                     ORDER BY occurred_at, event_id
                     LIMIT :n),
                copied AS (INSERT INTO alert_events_p SELECT * FROM batch ON CONFLICT DO NOTHING RETURNING 1),
                last AS (SELECT occurred_at, event_id FROM batch ORDER BY occurred_at DESC, event_id DESC LIMIT 1)
                SELECT (SELECT count(*) FROM batch) AS seen, (SELECT count(*) FROM copied) AS copied,
                       (SELECT occurred_at FROM last) AS last_t, (SELECT event_id FROM last) AS last_id
            """), {"after_t": position[0], "after_id": position[1], "upper_t": upper[0], "upper_id": upper[1],
                   "n": batch_size})).one()
            if row.seen == 0:
                break
            position = (row.last_t, row.last_id)
            copied += row.copied
            batches += 1
            await conn.execute(text("""
                UPDATE alert_events_backfill SET last_occurred_at = :t, last_event_id = :id,
                       rows_copied = :copied, updated_at = now()
            """), {"t": row.last_t, "id": row.last_id, "copied": copied})
        if on_batch:
            on_batch(copied, row.last_t)
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE alert_events_backfill SET finished_at = now(), updated_at = now()"))
    return Progress(copied, batches, True)
