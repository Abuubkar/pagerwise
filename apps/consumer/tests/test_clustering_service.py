"""Clustering against a real Postgres: two consumers seeing related alerts at the same moment must not open two
incidents for one problem."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pagerwise_api.db import AlertEvent, Incident
from pagerwise_consumer.clustering import store_alerts

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

EDGES = {("payments", "ledger")}


@pytest.fixture
async def sessions(postgres_url):
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE alert_events, incidents CASCADE"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def slow_embed(texts: list[str]) -> list[list[float]]:
    """Every summary embeds to the same vector (similarity 1.0), slowly, which widens the window in which two
    transactions could both decide that no incident exists yet."""
    await asyncio.sleep(0.05)
    return [[1.0] + [0.0] * 383 for _ in texts]


def alert(service: str, fingerprint: str, at: datetime) -> dict:
    return {"event_id": uuid.uuid4(), "source": "test", "service": service, "fingerprint": fingerprint,
            "severity": "critical", "occurred_at": at, "labels": {"alertname": "Test"}, "summary": "it broke",
            "attempt": 0}


async def store(sessions, rows: list[dict]) -> None:
    async with sessions() as session, session.begin():
        await store_alerts(session, rows, EDGES, slow_embed)


@pytest.mark.parametrize(("first", "second"), [
    (("ledger", "fp-1"), ("ledger", "fp-1")),  # same service and fingerprint (split across a rebalance)
    (("ledger", "fp-1"), ("payments", "fp-2")),  # neighbouring services, similar summaries, different partitions
], ids=["same-fingerprint", "neighbouring-services"])
async def test_two_consumers_racing_open_one_incident(sessions, first, second):
    for round_ in range(10):
        at = datetime(2026, 11, 2, 12, tzinfo=UTC) + timedelta(hours=round_)  # each round its own time window
        await asyncio.gather(store(sessions, [alert(*first, at)]),
                             store(sessions, [alert(*second, at + timedelta(seconds=1))]))
        async with sessions() as s:
            incidents = (await s.execute(
                select(Incident.id, Incident.alert_count).where(Incident.opened_at >= at,
                                                                Incident.opened_at < at + timedelta(hours=1))
            )).all()
            alerts = await s.scalar(select(func.count()).select_from(AlertEvent).where(
                AlertEvent.occurred_at >= at, AlertEvent.occurred_at < at + timedelta(hours=1)))
        assert len(incidents) == 1, f"round {round_}: {len(incidents)} incidents"
        assert incidents[0].alert_count == alerts == 2
