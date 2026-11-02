"""Load runbooks into Postgres: chunk on headings, embed locally, store. Unchanged files (same hash) are skipped.

uv run python scripts/load_docs.py [data/runbooks]
"""

import asyncio
import hashlib
import sys
from pathlib import Path

from sqlalchemy import delete, select

from pagerwise_api.chunking import chunk_markdown, embed_text, parse_document
from pagerwise_api.db import Chunk, Document, SessionLocal, engine
from pagerwise_api.embedding import count_tokens, embed_passages


async def load(folder: Path) -> None:
    async with SessionLocal() as session:
        for path in sorted(folder.glob("*.md")):
            raw = path.read_text()
            sha = hashlib.sha256(raw.encode()).hexdigest()
            rel = str(path.relative_to(Path.cwd()))  # run from the repo root, so paths read data/runbooks/...
            existing = await session.scalar(select(Document).where(Document.path == rel))
            if existing and existing.sha256 == sha:
                print(f"unchanged  {rel}")
                continue

            doc = parse_document(raw)
            drafts = chunk_markdown(doc.body, count_tokens)
            vectors = embed_passages([embed_text(d.heading_path, d.text) for d in drafts])
            # A changed file replaces its whole chunk set in one transaction, so a search never sees half of each.
            if existing:
                await session.execute(delete(Document).where(Document.id == existing.id))
            row = Document(source_type="runbook", path=rel, service=doc.service, title=doc.title, sha256=sha)
            session.add(row)
            await session.flush()
            session.add_all(
                Chunk(
                    document_id=row.id,
                    ordinal=i,
                    heading_path=d.heading_path,
                    text=d.text,
                    token_count=d.token_count,
                    embedding=v,
                )
                for i, (d, v) in enumerate(zip(drafts, vectors, strict=True))
            )
            await session.commit()
            sizes = ", ".join(str(d.token_count) for d in drafts)
            print(f"{'reloaded' if existing else 'loaded':9}  {rel}: {len(drafts)} chunks ({sizes} tokens)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(load(Path(sys.argv[1] if len(sys.argv) > 1 else "data/runbooks").resolve()))
