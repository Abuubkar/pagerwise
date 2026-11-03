"""Fill chunks.embedding_v2 (bge-base-en-v1.5) for chunks that don't have it yet: how the v1 -> v2 switch was filled (ADR 0009); the importer writes it for new
chunks, so this is only needed after a model change.

Walks chunks in id order in batches, one transaction each, so it can be stopped and rerun at any time: it only ever
picks rows still missing embedding_v2. Throttled so it doesn't crowd out the API: after each batch it sleeps for a
share of the time the batch took, and waits while more than --max-active database connections are busy.

uv run python scripts/reembed.py [--batch-size 64] [--throttle 0.5] [--max-active 8]
"""

import argparse
import asyncio
import time

from sqlalchemy import func, select, text, update

from pagerwise_api.chunking import embed_text
from pagerwise_api.db import Chunk, SessionLocal, engine
from pagerwise_api.embedding import embed_passages_v2


async def busy_connections(session) -> int:
    return await session.scalar(text(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'active' "
        "AND pid <> pg_backend_pid()"))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--throttle", type=float, default=0.5, help="sleep this share of each batch's duration")
    parser.add_argument("--max-active", type=int, default=8, help="wait while more connections than this are busy")
    args = parser.parse_args()
    started, done, last_id = time.monotonic(), 0, None
    async with SessionLocal() as session:
        todo = await session.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding_v2.is_(None)))
    print(f"{todo} chunks to re-embed with bge-base")
    while True:
        batch_started = time.monotonic()
        async with SessionLocal() as session:
            while (active := await busy_connections(session)) > args.max_active:
                print(f"  {active} busy connections; waiting")
                await asyncio.sleep(2)
            query = select(Chunk.id, Chunk.heading_path, Chunk.text).where(Chunk.embedding_v2.is_(None))
            if last_id is not None:
                query = query.where(Chunk.id > last_id)
            rows = (await session.execute(query.order_by(Chunk.id).limit(args.batch_size))).all()
            if not rows:
                break
            vectors = await asyncio.to_thread(embed_passages_v2, [embed_text(h, t) for _, h, t in rows])
            for (chunk_id, _, _), vector in zip(rows, vectors, strict=True):
                await session.execute(update(Chunk).where(Chunk.id == chunk_id).values(embedding_v2=vector))
            await session.commit()
        done += len(rows)
        last_id = rows[-1][0]
        took = time.monotonic() - batch_started
        print(f"  {done}/{todo} re-embedded ({took:.1f}s for {len(rows)})")
        await asyncio.sleep(took * args.throttle)
    await engine.dispose()
    print(f"done: {done} chunks in {time.monotonic() - started:.1f}s")


asyncio.run(main())
