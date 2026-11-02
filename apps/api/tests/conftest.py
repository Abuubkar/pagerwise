from collections.abc import AsyncIterator

import pytest


@pytest.fixture
async def client(postgres_url: str) -> AsyncIterator:
    """The real app over ASGI against the container database, emptied first. Each request gets its own session,
    as in production, so concurrent requests really race in Postgres."""
    import httpx
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from pagerwise_api.db import get_session
    from pagerwise_api.main import app

    # One engine per test: asyncpg connections are bound to the event loop that created them.
    engine = create_async_engine(postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE incidents, triage_runs, answers, documents CASCADE"))

    async def test_session() -> AsyncIterator:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        http.sessions = sessions  # type: ignore[attr-defined]  # for tests that set up rows directly
        yield http
    app.dependency_overrides.clear()
    await engine.dispose()
