"""Business logic. REST routes and GraphQL resolvers stay thin and call these functions."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from aiokafka.errors import KafkaError
from sqlalchemy import Select, func, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import pagerwise_kafka as k
from pagerwise_api import bus, cursor, llm, prompts, schemas
from pagerwise_api.citations import Verdict, parse_answer
from pagerwise_api.db import Answer, DeadLetter, Incident, TriageRun
from pagerwise_api.embedding import count_tokens
from pagerwise_api.retrieval import Hit, hybrid_search
from pagerwise_api.schemas import ApiProblem, ProblemCode
from pagerwise_api.settings import settings

EXCERPT_CHARS = 280


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
    retrieved: list[Hit] = field(default_factory=list)
    chat: llm.ChatResult | None = None


def _evidence(retrieved: list[Hit]) -> list[prompts.EvidenceChunk]:
    return [
        prompts.EvidenceChunk(tag=f"C{i}", source=f"{r.source_type} {r.document_path.rsplit('/', 1)[-1]}",
                              heading_path=r.heading_path, text=r.text)
        for i, r in enumerate(retrieved, start=1)
    ]


def _estimate_tokens(messages: list[dict[str, str]]) -> int:
    # Counted with the embedding tokenizer; 10% margin for the chat model counting differently (ADR 0003).
    return int(sum(count_tokens(m["content"]) for m in messages) * 1.1)


async def ask(session: AsyncSession, question: str) -> AskResult:
    retrieved = (await hybrid_search(session, question)).hits
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


def stale_heartbeat():  # noqa: ANN202 - a SQL expression
    """A running triage whose heartbeat is this old was abandoned (its worker died)."""
    return TriageRun.heartbeat_at < func.now() - timedelta(seconds=settings.triage_abandoned_after_s)


async def start_triage(session: AsyncSession, redis, incident_id: uuid.UUID,  # noqa: ANN001 - Redis
                       tenant: str = "default") -> TriageRun:
    """Queue a triage of the incident's current version for the triage worker. A second request while one is queued
    or running gets 409 with the existing run's id (the partial unique index decides, so concurrent requests can't
    both win); a tenant already at its limit of queued + running triages gets 503 with Retry-After."""
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise ApiProblem(404, ProblemCode.NOT_FOUND, "Incident not found", f"no incident with id {incident_id}")
    # A run whose worker died without finishing would block every new triage of this version forever.
    await session.execute(
        update(TriageRun)
        .where(TriageRun.incident_id == incident_id, TriageRun.status == "running", stale_heartbeat())
        .values(status="failed", error_code=ProblemCode.TRIAGE_ABANDONED, finished_at=func.now())
    )
    version = incident.version  # read now: a rollback below expires the loaded row
    run = TriageRun(incident_id=incident_id, incident_version=version, tenant=tenant)
    session.add(run)
    try:
        await session.flush()
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
    run_id = run.id
    if not await bus.acquire_triage_slot(redis, tenant, run_id):
        await session.rollback()  # the run was never committed
        raise ApiProblem(503, ProblemCode.TRIAGE_CAPACITY, "Triage capacity reached",
                         f"tenant {tenant} already has {settings.triage_tenant_limit} triages queued or running",
                         retry_after=settings.triage_retry_after_s)
    try:
        await session.commit()
    except Exception:
        await bus.release_triage_slot(redis, tenant, run_id)
        raise
    await bus.wake_worker(redis)
    await session.refresh(run)
    return run


async def latest_triage(session: AsyncSession, incident_id: uuid.UUID) -> TriageRun:
    run = await session.scalar(
        select(TriageRun).where(TriageRun.incident_id == incident_id).order_by(TriageRun.created_at.desc()).limit(1)
    )
    if run is None:
        raise ApiProblem(404, ProblemCode.NOT_FOUND, "No triage", f"incident {incident_id} has no triage; POST one first")
    return run


async def acknowledge_incident(session: AsyncSession, incident_id: uuid.UUID,
                               expected_version: int) -> Incident | int:
    """Marks the incident acknowledged if it's still the version the caller saw. Returns the incident, or the
    current version on a conflict (a new kind of alert joined, or severity rose, since the caller looked).
    Acknowledging doesn't change the version: the version tracks what a triage would see, not the status."""
    row = await session.scalar(
        update(Incident).where(Incident.id == incident_id, Incident.version == expected_version,
                               Incident.status != "resolved")
        .values(status="acknowledged").returning(Incident)
    )
    if row is None:
        current = await session.scalar(select(Incident.version).where(Incident.id == incident_id))
        await session.rollback()
        if current is None:
            raise ApiProblem(404, ProblemCode.NOT_FOUND, "Incident not found", f"no incident with id {incident_id}")
        return current
    await session.commit()
    return row


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

