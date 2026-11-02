from collections.abc import AsyncIterator

import pytest


@pytest.fixture
async def client(postgres_url: str, redis_url: str) -> AsyncIterator:
    """The real app over ASGI against the container database and Redis, both emptied first. Each request gets its
    own session, as in production, so concurrent requests really race in Postgres."""
    import httpx
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from pagerwise_api import bus
    from pagerwise_api.db import get_session
    from pagerwise_api.main import app, get_redis

    # One engine per test: asyncpg connections are bound to the event loop that created them.
    engine = create_async_engine(postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE incidents, triage_runs, answers, documents CASCADE"))

    async def test_session() -> AsyncIterator:
        async with sessions() as session:
            yield session

    async def test_redis() -> AsyncIterator:
        redis = bus.connect(redis_url)
        try:
            yield redis
        finally:
            await redis.aclose()

    flush = bus.connect(redis_url)
    await flush.flushdb()
    await flush.aclose()
    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_redis] = test_redis
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        http.sessions = sessions  # type: ignore[attr-defined]  # for tests that set up rows directly
        http.redis_url = redis_url  # type: ignore[attr-defined]
        yield http
    app.dependency_overrides.clear()
    await engine.dispose()
