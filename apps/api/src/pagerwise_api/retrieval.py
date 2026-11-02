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
from pagerwise_api.embedding import embed_query, embed_query_v2, rerank
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
    sibling_of: uuid.UUID | None = None  # brought in next to this chunk of the same document (sibling expansion)


@dataclass
class SearchResult:
    hits: list[Hit]  # the top k, best first
    candidates: int  # fused chunks the reranker scored
    timings_ms: dict[str, float] = field(default_factory=dict)
    before_siblings: list[uuid.UUID] = field(default_factory=list)  # chunk ids in order before expansion (evals)


def reciprocal_rank_fusion(rankings: Sequence[Sequence[uuid.UUID]], k: int = RRF_K) -> list[tuple[uuid.UUID, float]]:
    """Merges best-first rankings: score = sum over rankings of 1 / (k + rank), rank starting at 1. Ties keep the
    order of first appearance, so the result is deterministic."""
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: -pair[1])


def _only(statement, source_type: str | None):  # noqa: ANN001, ANN202 - a Select
    return statement.join(Document).where(Document.source_type == source_type) if source_type else statement


async def _fts(session: AsyncSession, query: str, limit: int, source_type: str | None) -> list[tuple[uuid.UUID, float]]:
    # websearch_to_tsquery accepts what people type ("quoted phrases", -exclusions) and never raises a syntax error.
    tsquery = func.websearch_to_tsquery("english", query)
    score = func.ts_rank_cd(Chunk.tsv, tsquery).label("score")
    rows = await session.execute(
        _only(select(Chunk.id, score), source_type).where(Chunk.tsv.op("@@")(tsquery))
        .order_by(score.desc(), Chunk.id).limit(limit)
    )
    return [(i, float(s)) for i, s in rows.all()]


async def _vector(session: AsyncSession, column, vector: list[float], limit: int,  # noqa: ANN001 - a Column
                  source_type: str | None) -> list[tuple[uuid.UUID, float]]:
    distance = column.cosine_distance(vector).label("distance")
    rows = await session.execute(
        _only(select(Chunk.id, distance), source_type).where(column.is_not(None)).order_by(distance).limit(limit)
    )
    return [(i, float(d)) for i, d in rows.all()]


# Which embedding column vector search reads, and the query embedding for it (settings.retrieval_embedding_version).
EMBEDDINGS = {"v1": (Chunk.embedding, embed_query), "v2": (Chunk.embedding_v2, embed_query_v2)}


async def hybrid_search(session: AsyncSession, query: str, k: int | None = None,
                        source_type: str | None = None) -> SearchResult:
    """source_type ("runbook" or "postmortem") limits both searches to that kind of document."""
    k = k or settings.retrieval_top_k
    timings: dict[str, float] = {}
    started = time.perf_counter()

    def lap(name: str, since: float) -> float:
        now = time.perf_counter()
        timings[name] = round((now - since) * 1000, 1)
        return now

    # v1 or v2 reads one embedding column; dual reads both and fuses them with full-text search (three lists), for
    # comparing and switching models without a cliff.
    version = settings.retrieval_embedding_version
    versions = ["v1", "v2"] if version == "dual" else [version]
    # Embedding and reranking are CPU-bound ONNX work; keep them off the event loop.
    vectors = {v: await asyncio.to_thread(EMBEDDINGS[v][1], query) for v in versions}
    mark = lap("embed", started)

    async def timed(name: str, search):  # noqa: ANN001, ANN202 - a coroutine and its result
        t = time.perf_counter()
        result = await search
        lap(name, t)
        return result

    # More sessions on the same engine, so the searches really run concurrently (one connection each).
    async with AsyncSession(bind=session.bind) as one, AsyncSession(bind=session.bind) as two:
        own = {"v1": one, "v2": two}
        fts, *vector_lists = await asyncio.gather(
            timed("fts", _fts(session, query, CANDIDATES, source_type)),
            *[timed("vector", _vector(own[v], EMBEDDINGS[v][0], vectors[v], CANDIDATES, source_type)) for v in versions],
        )
    mark = lap("searches", mark)
    vec = vector_lists[-1]  # the ranks reported as vector_rank: v2's in dual mode, the newer model

    fused = reciprocal_rank_fusion([[i for i, _ in fts], *[[i for i, _ in lst] for lst in vector_lists]])[
        : max(k, settings.rerank_candidates)]
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
    mark = lap("rerank", mark)
    before = [h.chunk_id for h in hits]
    if settings.retrieval_sibling_chunks and hits:
        hits = await _with_siblings(session, hits, k)
    lap("siblings", mark)
    lap("total", started)
    return SearchResult(hits=hits[:k], candidates=len(before), timings_ms=timings, before_siblings=before)


async def _with_siblings(session: AsyncSession, hits: list[Hit], k: int) -> list[Hit]:
    """Small-to-big: a document chunk in the top k brings the document's other chunks in right after it, in their
    order. A runbook's diagnosis and mitigation chunk rarely restates the symptoms a query names, so it ranks low on
    its own; next to the chunk that does, it completes the evidence. A sibling that was already a candidate moves
    up; one that wasn't is added with the ranks of the chunk that brought it."""
    top_docs = list(dict.fromkeys(h.document_path for h in hits[:k]))
    rows = (await session.execute(
        select(Chunk, Document).join(Document).where(Document.path.in_(top_docs)).order_by(Document.path, Chunk.ordinal)
    )).all()
    chunks_of: dict[str, list] = {}
    for chunk, doc in rows:
        chunks_of.setdefault(doc.path, []).append((chunk, doc))
    by_id = {h.chunk_id: h for h in hits}
    out: list[Hit] = []
    emitted: set[uuid.UUID] = set()
    expanded: set[str] = set()
    for hit in hits:
        if hit.chunk_id in emitted:
            continue
        out.append(hit)
        emitted.add(hit.chunk_id)
        if hit.document_path in expanded or hit.document_path not in chunks_of:
            continue
        expanded.add(hit.document_path)
        for chunk, doc in chunks_of[hit.document_path]:
            if chunk.id in emitted:
                continue
            sibling = by_id.get(chunk.id) or Hit(
                chunk_id=chunk.id, document_path=doc.path, source_type=doc.source_type, service=doc.service,
                heading_path=chunk.heading_path, text=chunk.text, token_count=chunk.token_count,
                rrf_rank=hit.rrf_rank, rrf_score=0.0, rerank_rank=hit.rerank_rank)
            sibling.sibling_of = hit.chunk_id
            out.append(sibling)
            emitted.add(chunk.id)
    return out
