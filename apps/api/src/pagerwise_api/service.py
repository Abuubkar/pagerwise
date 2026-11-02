"""Business logic. Routes stay thin and call these functions."""

import asyncio
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pagerwise_api import llm, prompts
from pagerwise_api.citations import Verdict, parse_answer
from pagerwise_api.db import Answer, Chunk, Document
from pagerwise_api.embedding import count_tokens, embed_query
from pagerwise_api.settings import settings


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_path: str
    heading_path: str
    text: str
    token_count: int
    distance: float  # cosine distance, 0 = same direction


@dataclass
class Citation:
    tag: str
    chunk_id: uuid.UUID
    document_path: str
    heading_path: str
    text: str


@dataclass
class AskResult:
    answer_id: uuid.UUID
    answer: str
    verdict: Verdict
    citations: list[Citation]
    problems: list[str] = field(default_factory=list)
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    chat: llm.ChatResult | None = None


async def search_chunks(session: AsyncSession, question: str, k: int) -> list[RetrievedChunk]:
    # Embedding is CPU-bound ONNX work; keep it off the event loop.
    vector = await asyncio.to_thread(embed_query, question)
    distance = Chunk.embedding.cosine_distance(vector).label("distance")
    rows = await session.execute(
        select(Chunk, Document.path, distance).join(Document).order_by(distance).limit(k)
    )
    return [
        RetrievedChunk(c.id, path, c.heading_path, c.text, c.token_count, float(d)) for c, path, d in rows.all()
    ]


async def ask(session: AsyncSession, question: str) -> AskResult:
    retrieved = await search_chunks(session, question, settings.retrieval_top_k)
    evidence = [
        prompts.EvidenceChunk(tag=f"C{i}", source=f"runbook {r.document_path.rsplit('/', 1)[-1]}",
                              heading_path=r.heading_path, text=r.text)
        for i, r in enumerate(retrieved, start=1)
    ]
    messages = prompts.ask_messages(question, evidence)
    # Chunk token counts come from the embedding tokenizer; 10% margin for the chat model counting differently.
    estimate = int(sum(count_tokens(m["content"]) for m in messages) * 1.1)
    result = await llm.chat(messages, estimated_prompt_tokens=estimate)

    by_tag = {e.tag: r for e, r in zip(evidence, retrieved, strict=True)}
    parsed = parse_answer(result.content, set(by_tag))
    citations = [
        Citation(t, by_tag[t].chunk_id, by_tag[t].document_path, by_tag[t].heading_path, by_tag[t].text)
        for t in parsed.tags
    ]
    row = Answer(
        question=question,
        answer=result.content,
        verdict=parsed.verdict,
        citations=[{"tag": c.tag, "chunk_id": str(c.chunk_id)} for c in citations],
        problems=parsed.problems,
        model=result.model,
        prompt_version=prompts.ASK_PROMPT_VERSION,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
        total_ms=result.total_ms,
        load_ms=result.load_ms,
        prompt_eval_ms=result.prompt_eval_ms,
        eval_ms=result.eval_ms,
    )
    session.add(row)
    await session.commit()
    return AskResult(row.id, result.content, parsed.verdict, citations, parsed.problems, retrieved, result)
