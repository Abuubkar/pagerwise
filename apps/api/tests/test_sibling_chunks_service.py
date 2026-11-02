"""Sibling expansion in retrieval, against a real Postgres: a top document's other chunks follow it."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pagerwise_api.db import Chunk, Document
from pagerwise_api.retrieval import Hit, _with_siblings

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


def hit(chunk: Chunk, doc: Document, rank: int) -> Hit:
    return Hit(chunk_id=chunk.id, document_path=doc.path, source_type=doc.source_type, service=doc.service,
               heading_path=chunk.heading_path, text=chunk.text, token_count=1, rrf_rank=rank, rrf_score=1 / rank)


async def test_a_top_documents_other_chunks_follow_it_in_order(postgres_url):
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE documents, chunks CASCADE"))
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        docs, chunks = [], {}
        for name, count in (("a", 3), ("b", 2)):
            doc = Document(source_type="runbook", path=f"runbooks/{name}.md", service="svc", title=name, sha256=name)
            session.add(doc)
            await session.flush()
            for i in range(count):
                chunk = Chunk(id=uuid.uuid4(), document_id=doc.id, ordinal=i, heading_path=f"{name} {i}",
                              text=f"{name}{i}", token_count=1, embedding=[0.0] * 384)
                session.add(chunk)
                chunks[(name, i)] = (chunk, doc)
            docs.append(doc)
        await session.commit()
        # Search found a's second chunk first, then b's first, then a's third (already a candidate).
        hits = [hit(*chunks[("a", 1)], 1), hit(*chunks[("b", 0)], 2), hit(*chunks[("a", 2)], 3)]
        expanded = await _with_siblings(session, hits, k=8)
    await engine.dispose()

    assert [h.heading_path for h in expanded] == ["a 1", "a 0", "a 2", "b 0", "b 1"]
    assert expanded[1].sibling_of == chunks[("a", 1)][0].id and expanded[1].rrf_rank == 1  # added with its ranks
    assert expanded[2] is hits[2]  # an existing candidate moved up, not duplicated
    assert expanded[0].sibling_of is None
