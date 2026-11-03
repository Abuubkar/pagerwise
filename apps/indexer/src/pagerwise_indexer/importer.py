"""Imports a docs API collection into documents and chunks. The only way documents get into the store.

Walks the listing by its `Link: rel="next"` headers and saves its place (import_state) after every page, in the same
transaction as that page's documents, so a run that dies resumes at the page it was on. Pages it has seen before are
requested with If-None-Match; a 304 costs nothing and the stored next link carries the walk on. 5xx and network
errors are retried with backoff. If the docs API answers a saved cursor with 404 (cursors expire when the corpus
changes), the walk restarts from page 1 with `since` set to the newest change already stored.

A document whose content hash is unchanged is skipped; a changed one has its whole chunk set replaced in one
transaction, so a search never sees half of each."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagerwise_api.chunking import ChunkDraft, chunk_markdown, embed_text, parse_document
from pagerwise_api.db import Chunk, Document, ImportState
from pagerwise_api.embedding import count_tokens, embed_passages_v2

log = logging.getLogger("pagerwise.indexer")

SOURCE_TYPES = {"runbooks": "runbook", "postmortems": "postmortem"}
RETRIES = 5  # after the first attempt
BACKOFF_S = 0.5  # doubles per retry: 0.5, 1, 2, 4, 8 s


class ImportFailed(Exception):
    """The docs API kept failing. Progress up to the last complete page is saved; rerun to resume."""


@dataclass
class Report:
    source: str
    pages: int = 0  # 200 responses
    not_modified: int = 0  # 304 responses
    retries: int = 0
    restarts: int = 0  # listings restarted with `since` after a stale cursor
    resumed: bool = False  # started from a saved next_url rather than page 1
    loaded: int = 0
    reloaded: int = 0
    unchanged: int = 0
    chunks: int = 0
    seconds: float = 0.0
    requests: list[tuple[str, int]] = field(default_factory=list)  # (url, status) in order, for tests and logs


async def fetch(client: httpx.AsyncClient, url: str, etag: str | None, report: Report) -> httpx.Response:
    headers = {"If-None-Match": etag} if etag else {}
    for attempt in range(RETRIES + 1):
        try:
            response = await client.get(url, headers=headers)
            report.requests.append((url, response.status_code))
            if response.status_code < 500 and response.status_code != 429:
                return response
            problem = f"HTTP {response.status_code}"
        except httpx.TransportError as e:
            report.requests.append((url, 0))
            problem = f"{type(e).__name__}: {e}"
        if attempt == RETRIES:
            raise ImportFailed(f"{url}: {problem} after {RETRIES + 1} attempts")
        report.retries += 1
        delay = BACKOFF_S * 2**attempt
        log.warning("%s: %s; retry %d in %.1fs", url, problem, attempt + 1, delay)
        await asyncio.sleep(delay)
    raise AssertionError("unreachable")


async def import_collection(client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession],
                            source: str, page_size: int = 20) -> Report:
    report = Report(source)
    started = asyncio.get_running_loop().time()
    first_page = f"/v1/{source}?{urlencode({'page_size': page_size})}"
    async with sessions() as session:
        state = await session.get(ImportState, source) or ImportState(source=source, pages={})
        session.add(state)
        await session.commit()
        url = state.next_url or first_page
        report.resumed = state.next_url is not None

        while url:
            seen = state.pages.get(url, {})
            response = await fetch(client, url, seen.get("etag"), report)
            if response.status_code == 404 and url != first_page:
                # A stale cursor. Everything up to resume_since is stored, so ask only for what changed since then.
                report.restarts += 1
                since = state.resume_since.isoformat() if state.resume_since else None
                log.info("%s: cursor expired; restarting from page 1 since %s", source, since)
                url = f"/v1/{source}?{urlencode({'page_size': page_size, **({'since': since} if since else {})})}"
                continue
            if response.status_code == 304:
                report.not_modified += 1
                next_url = seen.get("next")
            elif response.status_code == 200:
                report.pages += 1
                next_url = response.links.get("next", {}).get("url")
                if next_url:
                    next_url = httpx.URL(next_url).raw_path.decode()  # path + query: the base URL is the client's
                await store_page(session, SOURCE_TYPES[source], response.json()["items"], report)
                newest = max((datetime.fromisoformat(i["updated_at"]) for i in response.json()["items"]), default=None)
                if newest and (state.resume_since is None or newest > state.resume_since):
                    state.resume_since = newest
                state.pages = {**state.pages, url: {"etag": response.headers.get("etag"), "next": next_url}}
            else:
                raise ImportFailed(f"{url}: HTTP {response.status_code}: {response.text[:200]}")
            state.next_url = next_url
            state.updated_at = datetime.now(UTC)
            await session.commit()  # the page's documents and the importer's place in one transaction
            url = next_url

        state.last_completed_at = datetime.now(UTC)
        await session.commit()
    report.seconds = asyncio.get_running_loop().time() - started
    return report


async def store_page(session: AsyncSession, source_type: str, items: list[dict], report: Report) -> None:
    """Re-chunks and re-embeds the page's new or changed documents (one embedding batch per page) and replaces their
    rows. Doesn't commit: the caller commits the page together with the import state."""
    existing = {
        d.path: d for d in await session.scalars(select(Document).where(Document.path.in_([i["id"] for i in items])))
    }
    changed: list[tuple[dict, str, list[ChunkDraft], Document | None]] = []
    for item in items:
        sha = hashlib.sha256(item["body"].encode()).hexdigest()
        old = existing.get(item["id"])
        if old is not None and old.sha256 == sha:
            report.unchanged += 1
            continue
        changed.append((item, sha, chunk_markdown(parse_document(item["body"]).body, count_tokens), old))
    if not changed:
        return

    texts = [embed_text(d.heading_path, d.text) for _, _, drafts, _ in changed for d in drafts]
    vectors = iter(await asyncio.to_thread(embed_passages_v2, texts))  # CPU-bound; keep the event loop free
    for item, sha, drafts, old in changed:
        doc = parse_document(item["body"])
        if old is not None:
            await session.execute(delete(Document).where(Document.id == old.id))  # chunks go with it (cascade)
            report.reloaded += 1
        else:
            report.loaded += 1
        row = Document(source_type=source_type, path=item["id"], service=doc.service, title=doc.title, sha256=sha,
                       source_updated_at=datetime.fromisoformat(item["updated_at"]))
        session.add(row)
        await session.flush()
        session.add_all(
            Chunk(document_id=row.id, ordinal=i, heading_path=d.heading_path, text=d.text, token_count=d.token_count,
                  embedding_v2=next(vectors))
            for i, d in enumerate(drafts)
        )
        report.chunks += len(drafts)
