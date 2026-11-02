"""The importer against the real docs_mock app (in process) and a real Postgres: the cases that would lose,
duplicate or needlessly redo documents if they broke."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pagerwise_api.db import Chunk, Document, ImportState
from pagerwise_docs_mock import Faults, create_app
from pagerwise_indexer import importer
from pagerwise_indexer.importer import ImportFailed, import_collection

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

DOCS = 70  # 4 pages of 20


@pytest.fixture
def corpus(tmp_path):
    folder = tmp_path / "runbooks"
    folder.mkdir()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(DOCS):
        (folder / f"doc-{i:02}.md").write_text(
            f"---\nservice: svc-{i % 5}\nupdated_at: {(start + timedelta(days=i)).date()}\n---\n"
            f"# Runbook {i}\n\n## Symptoms\n\nService {i % 5} is slow because of reason {i}.\n"
        )
    return {"runbooks": [folder]}


@pytest.fixture
async def sessions(postgres_url, monkeypatch):
    monkeypatch.setattr(importer, "BACKOFF_S", 0.01)
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE documents, chunks, import_state CASCADE"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def client_for(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://docs")


async def documents(sessions) -> int:
    async with sessions() as s:
        return await s.scalar(select(func.count()).select_from(Document))


async def test_resumes_after_a_failure_on_page_3_and_a_rerun_sends_only_304s(corpus, sessions):
    app = create_app(corpus, Faults(fail_pages={3: 99}))
    async with client_for(app) as client:
        with pytest.raises(ImportFailed):
            await import_collection(client, sessions, "runbooks")
        assert await documents(sessions) == 40  # pages 1 and 2 were committed before page 3 failed
        async with sessions() as s:
            assert "cursor=1.40" in (await s.get(ImportState, "runbooks")).next_url

        app.state.docs.faults = Faults()  # the docs API recovers
        resumed = await import_collection(client, sessions, "runbooks")
        assert resumed.resumed and "cursor=1.40" in resumed.requests[0][0]  # started at page 3, not page 1
        assert (resumed.pages, resumed.loaded) == (2, 30)
        assert await documents(sessions) == DOCS

        again = await import_collection(client, sessions, "runbooks")
        assert [status for _, status in again.requests] == [304] * 4
        assert (again.pages, again.loaded, again.reloaded) == (0, 0, 0)


async def test_a_stale_cursor_restarts_with_since_and_only_changed_documents_are_rechunked(corpus, sessions):
    app = create_app(corpus, Faults(fail_pages={3: 99}))
    async with client_for(app) as client:
        with pytest.raises(ImportFailed):
            await import_collection(client, sessions, "runbooks")
        # The corpus changes while the import is stopped, so the saved page-3 cursor is stale.
        await client.post("/_faults", json={"expire_cursors": True})
        report = await import_collection(client, sessions, "runbooks")
        assert report.restarts == 1
        restart_url = next(url for url, _ in report.requests if "since=" in url)
        assert "since=2026-02-09" in restart_url  # the newest document already stored (doc 39)
        assert report.loaded == 30 and await documents(sessions) == DOCS  # nothing lost, nothing duplicated

        async with sessions() as s:
            doc = await s.scalar(select(Document).where(Document.path == "runbooks/doc-05.md"))
            old_chunks = set(await s.scalars(select(Chunk.id).where(Chunk.document_id == doc.id)))
        await client.post("/_touch", json={"id": "runbooks/doc-05.md", "append": "\nNew step: restart it.\n"})
        changed = await import_collection(client, sessions, "runbooks")
        assert (changed.reloaded, changed.loaded, changed.unchanged) == (1, 0, DOCS - 1)
        async with sessions() as s:
            doc = await s.scalar(select(Document).where(Document.path == "runbooks/doc-05.md"))
            new_chunks = list(await s.scalars(select(Chunk).where(Chunk.document_id == doc.id)))
        assert old_chunks.isdisjoint(c.id for c in new_chunks)  # the whole chunk set was replaced
        assert "restart it" in new_chunks[-1].text
        assert await documents(sessions) == DOCS
