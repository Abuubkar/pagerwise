"""Redis: the one way processes tell each other things. Postgres stays the source of truth; Redis only moves news.

- Incident updates: pub/sub on settings.incident_updates_channel, one JSON message per changed incident. Fire and
  forget; a subscriber that misses one re-reads Postgres.
- Triage events: one Redis Stream per run (triage:{id}:events). The triage worker appends every event; any
  number of readers (SSE streams, GraphQL subscriptions) read it from the start, so someone who opens the stream
  halfway still gets the whole brief. The stream expires an hour after the run ends; after that, readers replay
  the stored result from Postgres.
- Worker wake-up: a list the worker blocks on, so a new triage starts at once instead of at the next poll. The
  queue itself is triage_runs (status 'queued'); a lost wake-up only costs the poll interval.
- Tenant limit: a sorted set of run ids per tenant, scored by start time; at most settings.triage_tenant_limit
  members younger than triage_slot_ttl_s. The TTL frees slots a crashed worker never released."""

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis

from pagerwise_api.settings import settings

WAKE_KEY = "triage:wake"
STREAM_TTL_S = 3600
FINAL_EVENTS = ("done", "error")


def connect(url: str | None = None) -> aioredis.Redis:
    # redis-py's default 5 s socket timeout would cut off a blocking XREAD; reads here block for at most 2 s.
    return aioredis.from_url(url or settings.redis_url, decode_responses=True, socket_timeout=30)


async def publish_incidents(redis: aioredis.Redis, messages: list[dict[str, Any]]) -> None:
    async with redis.pipeline(transaction=False) as pipe:
        for message in messages:
            pipe.publish(settings.incident_updates_channel, json.dumps(message, default=str))
        await pipe.execute()


async def incident_updates(redis: aioredis.Redis) -> AsyncIterator[dict[str, Any]]:
    pubsub = redis.pubsub()
    await pubsub.subscribe(settings.incident_updates_channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield json.loads(message["data"])
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()


def _stream(triage_id: uuid.UUID) -> str:
    return f"triage:{triage_id}:events"


async def append_triage_event(redis: aioredis.Redis, triage_id: uuid.UUID, name: str, data: str) -> None:
    key = _stream(triage_id)
    await redis.xadd(key, {"event": name, "data": data})
    if name in FINAL_EVENTS:
        await redis.expire(key, STREAM_TTL_S)


async def has_triage_events(redis: aioredis.Redis, triage_id: uuid.UUID) -> bool:
    return bool(await redis.exists(_stream(triage_id)))


async def triage_events(redis: aioredis.Redis, triage_id: uuid.UUID,
                        block_ms: int = 2000) -> AsyncIterator[tuple[str, str] | None]:
    """Every event of the run from the start, then new ones as they arrive, until done or error. Yields None after
    each block_ms of silence, so the caller can check whether the run is still alive."""
    last = "0"
    while True:
        batch = await redis.xread({_stream(triage_id): last}, block=block_ms, count=200)
        if not batch:
            yield None
            continue
        for entry_id, fields in batch[0][1]:
            last = entry_id
            yield fields["event"], fields["data"]
            if fields["event"] in FINAL_EVENTS:
                return


async def wake_worker(redis: aioredis.Redis) -> None:
    await redis.lpush(WAKE_KEY, "1")
    await redis.ltrim(WAKE_KEY, 0, 0)  # one pending wake-up is enough


async def wait_for_work(redis: aioredis.Redis, timeout_s: float) -> None:
    await redis.blpop([WAKE_KEY], timeout=timeout_s)


# Atomic: drop expired slots, then take one if there's room. Returns 1 if taken.
_ACQUIRE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1] - ARGV[2])
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) and ARGV[5] == '0' then return 0 end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""


async def acquire_triage_slot(redis: aioredis.Redis, tenant: str, triage_id: uuid.UUID, force: bool = False) -> bool:
    """Takes one of the tenant's triage slots for this run. force=True always takes it (auto-started triages: the
    system's own work counts against the budget, so people asking for more see the queue is busy, but is never
    refused)."""
    taken = await redis.eval(_ACQUIRE, 1, f"triage:slots:{tenant}", time.time(), settings.triage_slot_ttl_s,
                             settings.triage_tenant_limit, str(triage_id), "1" if force else "0")
    return taken == 1


async def release_triage_slot(redis: aioredis.Redis, tenant: str, triage_id: uuid.UUID) -> None:
    await redis.zrem(f"triage:slots:{tenant}", str(triage_id))
