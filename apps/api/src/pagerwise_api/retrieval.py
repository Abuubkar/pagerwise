"""Hybrid retrieval: the one way to find evidence chunks for a question.

Two searches run at the same time, on separate connections: Postgres full-text search (exact words, error codes,
metric names) and pgvector cosine search (meaning). Their rankings are merged with Reciprocal Rank Fusion: a chunk
scores the sum of 1 / (60 + rank) over the lists it appears in, so agreeing near the top of both beats being first
in one. The best fused chunks (settings.rerank_candidates) are then rescored by a cross-encoder reranker, a model that reads the question and
each chunk together (slower, much more accurate than comparing two embeddings), and the top k are returned.

Every stage's rank is kept on each hit, for GET /v1/search and for evals."""

import asyncio
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pagerwise_api.chunking import embed_text
from pagerwise_api.db import Chunk, Document
from pagerwise_api.embedding import embed_query, rerank
from pagerwise_api.settings import settings

RRF_K = 60  # the constant from the original RRF paper; damps the difference between ranks 1 and 2
CANDIDATES = 40  # per search; the fused list is cut to settings.rerank_candidates for the reranker


@dataclass
class Hit:
    chunk_id: uuid.UUID
    document_path: str
    source_type: str
    service: str
    heading_path: str
    text: str
    token_count: int
    rrf_rank: int
    rrf_score: float
    fts_rank: int | None = None  # None: not in that search's top CANDIDATES
    fts_score: float | None = None
    vector_rank: int | None = None
    vector_distance: float | None = None
    rerank_rank: int | None = None
    rerank_score: float | None = None


@dataclass
class SearchResult:
    hits: list[Hit]  # the top k, best first
    candidates: int  # fused chunks the reranker scored
    timings_ms: dict[str, float] = field(default_factory=dict)


def reciprocal_rank_fusion(rankings: Sequence[Sequence[uuid.UUID]], k: int = RRF_K) -> list[tuple[uuid.UUID, float]]:
    """Merges best-first rankings: score = sum over rankings of 1 / (k + rank), rank starting at 1. Ties keep the
    order of first appearance, so the result is deterministic."""
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: -pair[1])


async def _fts(session: AsyncSession, query: str, limit: int) -> list[tuple[uuid.UUID, float]]:
    # websearch_to_tsquery accepts what people type ("quoted phrases", -exclusions) and never raises a syntax error.
    tsquery = func.websearch_to_tsquery("english", query)
    score = func.ts_rank_cd(Chunk.tsv, tsquery).label("score")
    rows = await session.execute(
        select(Chunk.id, score).where(Chunk.tsv.op("@@")(tsquery)).order_by(score.desc(), Chunk.id).limit(limit)
    )
    return [(i, float(s)) for i, s in rows.all()]


async def _vector(session: AsyncSession, vector: list[float], limit: int) -> list[tuple[uuid.UUID, float]]:
    distance = Chunk.embedding.cosine_distance(vector).label("distance")
    rows = await session.execute(select(Chunk.id, distance).order_by(distance).limit(limit))
    return [(i, float(d)) for i, d in rows.all()]


async def hybrid_search(session: AsyncSession, query: str, k: int | None = None) -> SearchResult:
    k = k or settings.retrieval_top_k
    timings: dict[str, float] = {}
    started = time.perf_counter()

    def lap(name: str, since: float) -> float:
        now = time.perf_counter()
        timings[name] = round((now - since) * 1000, 1)
        return now

    # Embedding and reranking are CPU-bound ONNX work; keep them off the event loop.
    vector = await asyncio.to_thread(embed_query, query)
    mark = lap("embed", started)

    async def timed(name: str, search):  # noqa: ANN001, ANN202 - a coroutine and its result
        t = time.perf_counter()
        result = await search
        lap(name, t)
        return result

    # A second session on the same engine, so the two searches really run concurrently (one connection each).
    async with AsyncSession(bind=session.bind) as other:
        fts, vec = await asyncio.gather(timed("fts", _fts(session, query, CANDIDATES)),
                                        timed("vector", _vector(other, vector, CANDIDATES)))
    mark = lap("searches", mark)

    fused = reciprocal_rank_fusion([[i for i, _ in fts], [i for i, _ in vec]])[: max(k, settings.rerank_candidates)]
    rows = {
        c.id: (c, d) for c, d in (await session.execute(
            select(Chunk, Document).join(Document).where(Chunk.id.in_([i for i, _ in fused]))
        )).all()
    }
    fts_at = {i: (rank, s) for rank, (i, s) in enumerate(fts, start=1)}
    vec_at = {i: (rank, d) for rank, (i, d) in enumerate(vec, start=1)}
    hits = []
    for rank, (chunk_id, score) in enumerate(fused, start=1):
        chunk, doc = rows[chunk_id]
        hits.append(Hit(
            chunk_id=chunk.id, document_path=doc.path, source_type=doc.source_type, service=doc.service,
            heading_path=chunk.heading_path, text=chunk.text, token_count=chunk.token_count,
            rrf_rank=rank, rrf_score=round(score, 6),
            fts_rank=fts_at.get(chunk_id, (None,))[0], fts_score=fts_at.get(chunk_id, (None, None))[1],
            vector_rank=vec_at.get(chunk_id, (None,))[0], vector_distance=vec_at.get(chunk_id, (None, None))[1],
        ))
    mark = lap("fuse", mark)

    if hits and settings.rerank_candidates:
        # Cost grows with candidates x tokens: a cross-encoder reads every candidate in full (ADR 0006).
        top = hits[: settings.rerank_candidates]
        scores = await asyncio.to_thread(rerank, query, [embed_text(h.heading_path, h.text) for h in top])
        for h, s in zip(top, scores, strict=True):
            h.rerank_score = round(s, 4)
        top.sort(key=lambda h: -(h.rerank_score or 0.0))
        for rank, h in enumerate(top, start=1):
            h.rerank_rank = rank
        hits = top + hits[settings.rerank_candidates :]  # anything past the reranked set keeps its fused order
    lap("rerank", mark)
    lap("total", started)
    return SearchResult(hits=hits[:k], candidates=len(hits), timings_ms=timings)
