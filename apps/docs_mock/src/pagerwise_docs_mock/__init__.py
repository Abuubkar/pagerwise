"""A stand-in for a team's docs API (a wiki or docs platform), serving the seeded corpus the way such APIs do:

- GET /v1/{runbooks|postmortems}: pages of 20 documents, oldest change first, with the next page in a
  `Link: <...>; rel="next"` header (RFC 8288). `since` filters to documents changed at or after a time.
- Each page has an ETag; a request with a matching If-None-Match gets 304 and no body.
- Next-page cursors belong to one version of the listing. Any change to the corpus makes them stale, and a stale
  cursor gets 404, as a real API's expired cursor would: the client has to restart, ideally with `since`.

Test hooks, not part of the imitation: POST /_faults injects 5xx responses (randomly, or on given pages) or expires
every cursor; POST /_touch edits a document; GET /_stats counts responses by status.

uv run python -m pagerwise_docs_mock [--port 8002] [--fail-rate 0.1]
"""

import argparse
import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_COLLECTIONS = {
    "runbooks": [ROOT / "data" / "runbooks", ROOT / "data" / "corpus" / "runbooks"],
    "postmortems": [ROOT / "data" / "corpus" / "postmortems"],
}
UNDATED = "2026-10-01T00:00:00+00:00"  # documents whose frontmatter has no updated_at (the hand-written runbooks)


class Document(BaseModel):
    id: str  # repo-relative path (folder/file outside the repo), stable across edits
    title: str
    service: str
    updated_at: datetime
    body: str  # the whole markdown file, frontmatter included


class Faults(BaseModel):
    fail_rate: float = 0.0  # share of listing requests answered with fail_status
    fail_pages: dict[int, int] = {}  # page number -> how many more requests for it fail
    fail_status: int = 503
    expire_cursors: bool = False  # make every cursor issued so far stale, once
    seed: int = 0


class Touch(BaseModel):
    id: str
    append: str = "\nEdited for a test.\n"


@dataclass
class State:
    collections: dict[str, list[Document]]
    faults: Faults = field(default_factory=Faults)
    rng: random.Random = field(default_factory=random.Random)
    generation: int = 1  # version of every listing; cursors from older generations are stale
    stats: dict[str, int] = field(default_factory=dict)


def load_documents(folders: list[Path]) -> list[Document]:
    docs = []
    for folder in folders:
        for path in sorted(folder.glob("*.md")):
            text = path.read_text()
            service = re.search(r"^service:\s*(\S+)", text, re.MULTILINE)
            updated = re.search(r"^updated_at:\s*(\S+)", text, re.MULTILINE)
            title = re.search(r"^# (.+)$", text, re.MULTILINE)
            docs.append(Document(
                id=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else f"{folder.name}/{path.name}", title=title.group(1) if title else path.stem,
                service=service.group(1) if service else "unknown",
                updated_at=datetime.fromisoformat(updated.group(1) if updated else UNDATED).replace(tzinfo=UTC),
                body=text,
            ))
    return docs


def create_app(collections: dict[str, list[Path]] | None = None, faults: Faults | None = None) -> FastAPI:
    app = FastAPI(title="docs mock")
    state = State({name: load_documents(folders) for name, folders in (collections or DEFAULT_COLLECTIONS).items()})
    state.faults = faults or Faults()
    state.rng.seed(state.faults.seed)
    app.state.docs = state

    def count(key: str) -> None:
        state.stats[key] = state.stats.get(key, 0) + 1

    @app.get("/v1/{collection}")
    def listing(
        collection: str, request: Request,
        cursor: str | None = None,
        since: datetime | None = None,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> Response:
        if collection not in state.collections:
            raise HTTPException(404, f"no collection {collection}")
        offset = 0
        if cursor is not None:
            generation, _, raw_offset = cursor.partition(".")
            if generation != str(state.generation) or not raw_offset.isdigit():
                count("404")
                raise HTTPException(404, "cursor expired; restart the listing")
            offset = int(raw_offset)
        page = offset // page_size + 1
        f = state.faults
        if f.fail_pages.get(page, 0) > 0 or state.rng.random() < f.fail_rate:
            if f.fail_pages.get(page, 0) > 0:
                f.fail_pages[page] -= 1
            count(str(f.fail_status))
            raise HTTPException(f.fail_status, "injected failure")

        docs = sorted(state.collections[collection], key=lambda d: (d.updated_at, d.id))
        if since is not None:
            docs = [d for d in docs if d.updated_at >= since]
        items = docs[offset : offset + page_size]
        next_url = None
        if offset + page_size < len(docs):
            query = {"cursor": f"{state.generation}.{offset + page_size}", "page_size": page_size}
            if since is not None:
                query["since"] = since.isoformat()
            next_url = str(request.url.replace_query_params(**query))
        body = json.dumps({"items": [d.model_dump(mode="json") for d in items]})
        etag = '"' + hashlib.sha256((body + (next_url or "")).encode()).hexdigest()[:32] + '"'
        headers = {"ETag": etag}
        if next_url:
            headers["Link"] = f'<{next_url}>; rel="next"'
        if request.headers.get("if-none-match") == etag:
            count("304")
            return Response(status_code=304, headers=headers)
        count("200")
        return Response(body, media_type="application/json", headers=headers)

    @app.post("/_faults")
    def set_faults(body: Faults) -> Faults:
        state.faults = body
        state.rng.seed(body.seed)
        if body.expire_cursors:
            state.generation += 1
            body.expire_cursors = False
        return body

    @app.post("/_touch")
    def touch(body: Touch) -> Document:
        for docs in state.collections.values():
            for i, doc in enumerate(docs):
                if doc.id == body.id:
                    docs[i] = doc.model_copy(update={"body": doc.body + body.append, "updated_at": datetime.now(UTC)})
                    state.generation += 1  # the listing changed, so outstanding cursors are stale
                    return docs[i]
        raise HTTPException(404, f"no document {body.id}")

    @app.get("/_stats")
    def stats() -> dict[str, int]:
        return state.stats

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--fail-rate", type=float, default=0.0, help="share of listing requests that get a 503")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    uvicorn.run(create_app(faults=Faults(fail_rate=args.fail_rate, seed=args.seed)), port=args.port)
