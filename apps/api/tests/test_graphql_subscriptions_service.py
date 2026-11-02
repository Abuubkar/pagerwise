"""GraphQL subscriptions against real Redis and Postgres: what the UI's live list depends on."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pagerwise_api import bus
from pagerwise_api.graphql import Context, schema
from pagerwise_api.settings import settings

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

SUBSCRIBE = "subscription($service: String) { incidentUpdated(service: $service) { id title alertCount version } }"


async def test_incident_updated_yields_the_changed_incident_for_its_service(client, monkeypatch):
    monkeypatch.setattr(settings, "redis_url", client.redis_url)
    ledger = (await client.post("/v1/incidents", json={"title": "Ledger down", "service": "ledger", "severity": "sev1"})).json()
    other = (await client.post("/v1/incidents", json={"title": "Search slow", "service": "search", "severity": "sev3"})).json()
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        stream = await schema.subscribe(SUBSCRIBE, variable_values={"service": "ledger"},
                                        context_value=Context(session))
        first = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.3)  # let it subscribe before publishing (pub/sub keeps no history)
        redis = bus.connect(client.redis_url)
        await bus.publish_incidents(redis, [{"type": "updated", "incident_id": other["id"], "service": "search"},
                                            {"type": "opened", "incident_id": ledger["id"], "service": "ledger"}])
        result = await asyncio.wait_for(first, timeout=5)
        await redis.aclose()
        await stream.aclose()
    await engine.dispose()

    assert result.errors is None, result.errors
    assert result.data == {"incidentUpdated": {"id": ledger["id"], "title": "Ledger down", "alertCount": 0,
                                               "version": 1}}  # the search incident was filtered out
