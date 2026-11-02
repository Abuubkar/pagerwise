"""Business logic. REST routes and GraphQL resolvers stay thin and call these functions."""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from aiokafka.errors import KafkaError
from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import pagerwise_kafka as k
from pagerwise_api import citations, cursor, llm, prompts, schemas
from pagerwise_api.citations import Verdict, parse_answer
from pagerwise_api.db import Answer, Chunk, DeadLetter, Document, Incident, TriageRun
from pagerwise_api.embedding import count_tokens, embed_query
from pagerwise_api.schemas import ApiProblem, ProblemCode
from pagerwise_api.settings import settings

EXCERPT_CHARS = 280


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


def _evidence(retrieved: list[RetrievedChunk]) -> list[prompts.EvidenceChunk]:
    return [
        prompts.EvidenceChunk(tag=f"C{i}", source=f"runbook {r.document_path.rsplit('/', 1)[-1]}",
                              heading_path=r.heading_path, text=r.text)
        for i, r in enumerate(retrieved, start=1)
    ]


def _estimate_tokens(messages: list[dict[str, str]]) -> int:
    # Counted with the embedding tokenizer; 10% margin for the chat model counting differently (ADR 0003).
    return int(sum(count_tokens(m["content"]) for m in messages) * 1.1)


async def ask(session: AsyncSession, question: str) -> AskResult:
    retrieved = await search_chunks(session, question, settings.retrieval_top_k)
    evidence = _evidence(retrieved)
    messages = prompts.ask_messages(question, evidence)
    result = await llm.chat(messages, estimated_prompt_tokens=_estimate_tokens(messages))

    by_tag = {e.tag: r for e, r in zip(evidence, retrieved, strict=True)}
    parsed = parse_answer(result.content, set(by_tag))
    cited = [
        Citation(t, by_tag[t].chunk_id, by_tag[t].document_path, by_tag[t].heading_path, by_tag[t].text)
        for t in parsed.tags
    ]
    row = Answer(
        question=question,
        answer=result.content,
        verdict=parsed.verdict,
        citations=[{"tag": c.tag, "chunk_id": str(c.chunk_id)} for c in cited],
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
    return AskResult(row.id, result.content, parsed.verdict, cited, parsed.problems, retrieved, result)


# --- Incidents -------------------------------------------------------------------------------------------------


@dataclass
class Page:
    items: list[Incident]
    cursors: list[str]  # one per item: resume after that item (GraphQL edges need one each)
    next_cursor: str | None


async def create_incident(session: AsyncSession, body: schemas.IncidentCreate) -> Incident:
    values = body.model_dump(exclude_none=True)
    row = Incident(**values)
    session.add(row)
    await session.commit()
    await session.refresh(row)  # server defaults: id, status, opened_at, version
    return row


async def get_incident(session: AsyncSession, incident_id: uuid.UUID) -> Incident | None:
    return await session.get(Incident, incident_id)


async def list_incidents(
    session: AsyncSession,
    limit: int,
    after: str | None = None,
    status: str | None = None,
    service: str | None = None,
    severity: str | None = None,
) -> Page:
    """Newest first (opened_at DESC, id DESC). The cursor is bound to the filters it was issued with."""
    filters = {"status": status, "service": service, "severity": severity}
    query: Select[tuple[Incident]] = select(Incident)
    for column, value in ((Incident.status, status), (Incident.service, service), (Incident.severity, severity)):
        if value is not None:
            query = query.where(column == value)
    if after is not None:
        try:
            position = cursor.decode(after, filters, settings.cursor_secret)
        except cursor.InvalidCursor as exc:
            raise ApiProblem(400, ProblemCode.INVALID_CURSOR, "Invalid cursor", str(exc)) from None
        query = query.where(tuple_(Incident.opened_at, Incident.id) < (position.opened_at, position.id))
    rows = list((await session.scalars(query.order_by(Incident.opened_at.desc(), Incident.id.desc())
                                       .limit(limit + 1))).all())
    items = rows[:limit]
    cursors = [cursor.encode(cursor.Position(r.opened_at, r.id), filters, settings.cursor_secret) for r in items]
    return Page(items=items, cursors=cursors, next_cursor=cursors[-1] if len(rows) > limit else None)


# --- Triage ----------------------------------------------------------------------------------------------------


def _stale_heartbeat():  # noqa: ANN202 - a SQL expression
    return TriageRun.heartbeat_at < func.now() - timedelta(seconds=settings.triage_abandoned_after_s)


async def start_triage(session: AsyncSession, incident_id: uuid.UUID) -> TriageRun:
    """Queue a triage of the incident's current version. A second request while one is queued or running gets
    409 with the existing run's id; the partial unique index decides, so concurrent requests can't both win."""
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise ApiProblem(404, ProblemCode.NOT_FOUND, "Incident not found", f"no incident with id {incident_id}")
    # A run whose stream died without finishing would block every new triage of this version forever.
    await session.execute(
        update(TriageRun)
        .where(TriageRun.incident_id == incident_id, TriageRun.status == "running", _stale_heartbeat())
        .values(status="failed", error_code=ProblemCode.TRIAGE_ABANDONED, finished_at=func.now())
    )
    version = incident.version  # read now: a rollback below expires the loaded row
    run = TriageRun(incident_id=incident_id, incident_version=version)
    session.add(run)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_triage_runs_active" not in str(exc.orig):
            raise
        existing = await session.scalar(
            select(TriageRun.id).where(
                TriageRun.incident_id == incident_id,
                TriageRun.incident_version == version,
                TriageRun.status.in_(("queued", "running")),
            )
        )
        raise ApiProblem(
            409, ProblemCode.TRIAGE_IN_PROGRESS, "Triage already in progress",
            f"incident {incident_id} version {version} already has a queued or running triage",
            triage_id=existing,
        ) from None
    await session.refresh(run)
    return run


async def open_triage_stream(session: AsyncSession, incident_id: uuid.UUID) -> tuple[TriageRun, bool]:
    """The incident's latest triage, and whether this caller should generate it (True: claimed) or replay it.
    Raises before any byte is streamed, so failures are ordinary problem responses (ADR 0004)."""
    run = await session.scalar(
        select(TriageRun).where(TriageRun.incident_id == incident_id).order_by(TriageRun.created_at.desc()).limit(1)
    )
    if run is None:
        raise ApiProblem(404, ProblemCode.NOT_FOUND, "No triage", f"incident {incident_id} has no triage; POST one first")
    claimed = await session.scalar(
        update(TriageRun)
        .where(TriageRun.id == run.id, or_(TriageRun.status == "queued",
                                           (TriageRun.status == "running") & _stale_heartbeat()))
        .values(status="running", started_at=func.now(), heartbeat_at=func.now())
        .returning(TriageRun.id)
    )
    await session.commit()
    if claimed:
        await session.refresh(run)
        return run, True
    if run.status == "running":
        raise ApiProblem(409, ProblemCode.TRIAGE_IN_PROGRESS, "Triage is streaming elsewhere",
                         "another connection is generating this triage; open the stream again once it's done",
                         triage_id=run.id)
    return run, False


def _incident_text(incident: Incident) -> str:
    return (f"Title: {incident.title}\nService: {incident.service}\nSeverity: {incident.severity}\n"
            f"Opened: {incident.opened_at.isoformat()}\nSummary: {incident.summary or '(none)'}")


def _citation(item: dict, section: str | None) -> schemas.CitationEvent:
    text = item["text"]
    return schemas.CitationEvent(
        tag=item["tag"], source_type="runbook", source_id=item["source_id"], chunk_id=item["chunk_id"],
        chunk_excerpt=text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS].rstrip() + "…",
        section=section,  # type: ignore[arg-type]  # one of SECTIONS' values, or None
    )


TriageEvent = tuple[str, BaseModel]  # (SSE event name, payload)


async def triage_events(session: AsyncSession, run: TriageRun, claimed: bool) -> AsyncIterator[TriageEvent]:
    if not claimed:
        async for event in _replay(run):
            yield event
        return

    incident = await session.get(Incident, run.incident_id)
    assert incident is not None  # triage_runs.incident_id is a foreign key
    # Slice 1's retrieval, queried with the incident itself. Slice 5 builds a better query (neighbours, alerts).
    retrieved = await search_chunks(session, f"{incident.title}\n{incident.summary}", settings.retrieval_top_k)
    evidence = _evidence(retrieved)
    run.evidence = [
        {"tag": e.tag, "source_type": "runbook", "source_id": r.document_path, "chunk_id": str(r.chunk_id),
         "heading_path": r.heading_path, "text": r.text}
        for e, r in zip(evidence, retrieved, strict=True)
    ]
    run.model, run.prompt_version = settings.llm_model, prompts.TRIAGE_PROMPT_VERSION
    await session.commit()
    by_tag = {item["tag"]: item for item in run.evidence}

    messages = prompts.triage_messages(_incident_text(incident), evidence)
    scanner = citations.TagScanner(set(by_tag))
    started = last_beat = time.monotonic()
    result: llm.ChatResult | None = None
    try:
        async for piece in llm.chat_stream(messages, estimated_prompt_tokens=_estimate_tokens(messages)):
            if isinstance(piece, llm.ChatResult):
                result = piece
                continue
            if run.ttft_ms is None:
                run.ttft_ms = int((time.monotonic() - started) * 1000)
            for event in scanner.feed(piece):
                yield _scan_event(event, by_tag)
            if time.monotonic() - last_beat >= settings.triage_heartbeat_s:
                run.heartbeat_at = datetime.now(UTC)
                await session.commit()
                last_beat = time.monotonic()
    except llm.PromptTooLong as exc:
        yield await _fail(session, run, ProblemCode.PROMPT_TOO_LONG, str(exc))
        return
    except ConnectionError:  # the ollama client's own error when Ollama isn't running
        yield await _fail(session, run, ProblemCode.MODEL_UNAVAILABLE, "model server unreachable")
        return
    for event in scanner.finish():
        yield _scan_event(event, by_tag)

    assert result is not None  # Ollama's last chunk (done=True) carries the counts
    run.raw_text = result.content
    run.prompt_tokens, run.output_tokens = result.prompt_tokens, result.output_tokens
    run.total_ms = int((time.monotonic() - started) * 1000)
    parsed = citations.parse_brief(result.content, set(by_tag))
    if parsed.verdict is None:
        yield await _fail(session, run, ProblemCode.FORMAT_INVALID, "the brief broke the section contract",
                          parsed.problems)
        return
    brief = _brief(run, parsed, by_tag)
    # Python timestamps, not func.now(): a SQL expression on an ORM attribute expires it, and reading it back
    # under asyncio would need a lazy load.
    run.status, run.verdict, run.finished_at = "completed", brief.verdict, datetime.now(UTC)
    run.brief = brief.model_dump(mode="json")
    await session.commit()
    yield "done", brief


def _scan_event(event: citations.ScanEvent, by_tag: dict[str, dict]) -> TriageEvent:
    match event:
        case citations.TokenEvent(text):
            return "token", schemas.TokenEvent(text=text)
        case citations.CitationEvent(tag, section):
            return "citation", _citation(by_tag[tag], section)
        case citations.SectionCompleteEvent(section):
            return "section_complete", schemas.SectionCompleteEvent(section=section)  # type: ignore[arg-type]
    raise AssertionError(event)


def _brief(run: TriageRun, parsed: citations.ParsedBrief, by_tag: dict[str, dict]) -> schemas.TriageBrief:
    def section(key: str) -> schemas.BriefSection:
        s = parsed.sections[key]
        cited = [schemas.Citation(**_citation(by_tag[t], key).model_dump(exclude={"section"})) for t in s.tags]
        return schemas.BriefSection(text=s.text, citations=cited)

    assert parsed.verdict is not None and run.model and run.prompt_version
    return schemas.TriageBrief(
        triage_id=run.id, incident_id=run.incident_id, incident_version=run.incident_version, verdict=parsed.verdict,
        sections=schemas.BriefSections(**{key: section(key) for key in citations.SECTIONS.values()}),
        model=run.model, prompt_version=run.prompt_version,
        usage=schemas.TriageUsage(prompt_tokens=run.prompt_tokens or 0, output_tokens=run.output_tokens or 0,
                                  ttft_ms=run.ttft_ms or 0, total_ms=run.total_ms or 0),
    )


async def _fail(session: AsyncSession, run: TriageRun, code: ProblemCode, detail: str,
                problems: list[str] | None = None) -> TriageEvent:
    run.status, run.error_code, run.problems, run.finished_at = "failed", code, problems or [], datetime.now(UTC)
    await session.commit()
    return "error", schemas.ErrorEvent(code=code, detail=detail, problems=problems or [])


async def _replay(run: TriageRun) -> AsyncIterator[TriageEvent]:
    """A finished run streams again from what was stored, in the same event shapes as the live stream."""
    if run.status == "failed":
        yield "error", schemas.ErrorEvent(code=ProblemCode(run.error_code), detail="this triage failed",
                                          problems=run.problems)
        return
    assert run.brief is not None
    brief = schemas.TriageBrief.model_validate(run.brief)
    yield "token", schemas.TokenEvent(text=run.raw_text)
    for key in citations.SECTIONS.values():
        for c in getattr(brief.sections, key).citations:
            yield "citation", schemas.CitationEvent(**c.model_dump(), section=key)
        yield "section_complete", schemas.SectionCompleteEvent(section=key)  # type: ignore[arg-type]
    yield "done", brief


async def replay_dead_letters(session: AsyncSession, body: schemas.DlqReplayRequest) -> list[int]:
    """Republishes the selected dead letters' stored payloads to alerts.v1 as fresh messages (attempt 0), marked
    with the DLQ offset they came from. Returns their DLQ offsets once Kafka has acknowledged all of them."""
    query = select(DeadLetter).order_by(DeadLetter.dlq_offset).limit(schemas.REPLAY_MAX + 1)
    if body.keys is not None:
        query = query.where(DeadLetter.key.in_(body.keys))
    else:
        query = query.where(DeadLetter.dlq_offset.between(body.from_offset, body.to_offset))
    rows = (await session.scalars(query)).all()
    if len(rows) > schemas.REPLAY_MAX:
        raise ApiProblem(400, ProblemCode.INVALID_REQUEST, "Too many dead letters",
                         f"more than {schemas.REPLAY_MAX} match; replay them in offset ranges")
    if not rows:
        return []

    producer = k.producer(settings.kafka_bootstrap, request_timeout_ms=10_000)
    try:
        await producer.start()
        sent = [
            await producer.send(k.ALERTS, row.payload, key=row.key.encode() if row.key else None,
                                headers=[(k.H_REPLAYED_FROM, str(row.dlq_offset).encode())])
            for row in rows
        ]
        await asyncio.gather(*sent)
    except KafkaError as e:
        raise ApiProblem(503, ProblemCode.BROKER_UNAVAILABLE, "Broker unavailable", f"Kafka: {e}") from e
    finally:
        await producer.stop()

    await session.execute(
        update(DeadLetter)
        .where(DeadLetter.id.in_([row.id for row in rows]))
        .values(replayed_at=datetime.now(UTC), replay_count=DeadLetter.replay_count + 1)
    )
    await session.commit()
    return [row.dlq_offset for row in rows]

