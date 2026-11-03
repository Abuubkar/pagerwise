"""Triage: evidence from three sources, the brief, and the events it streams as.

The triage worker (pagerwise_api.worker) runs `generate` for each queued run and appends its events to the run's
Redis stream; readers (SSE, GraphQL) use `events`, which reads that stream, or the stored result once it's gone.

Evidence comes from runbooks and postmortems (hybrid search, each limited to its kind) and recent deploys (HTTP,
the deploy source), fetched at the same time with a timeout each. A source that fails or is too slow is left out
and named in degraded_sources; the triage runs anyway, and the prompt forbids saying anything about it."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pagerwise_api import bus, citations, llm, prompts, schemas
from pagerwise_api.db import AlertEvent, Incident, ServiceEdge, TriageRun
from pagerwise_api.embedding import count_tokens
from pagerwise_api.retrieval import hybrid_search
from pagerwise_api.schemas import ProblemCode
from pagerwise_api.settings import settings

log = logging.getLogger("pagerwise.triage")

EXCERPT_CHARS = 280
TriageEvent = tuple[str, BaseModel]  # (SSE event name, payload)


@dataclass
class EvidenceItem:
    source_type: str  # runbook | postmortem | deploy
    source_id: str  # document path or deploy id
    chunk_id: uuid.UUID | None
    heading_path: str
    text: str


@dataclass
class Gathered:
    items: list[EvidenceItem] = field(default_factory=list)
    degraded: list[dict[str, str]] = field(default_factory=list)  # [{source, reason}]
    timings_ms: dict[str, int] = field(default_factory=dict)


def build_query(title: str, service: str, neighbours: list[str], alert_summaries: list[str]) -> str:
    """The search query, from the incident alone: no model call. Title and the most frequent alert summaries carry
    the symptoms; service names steer full-text search to the right runbooks."""
    parts = [title, f"service {service}"]
    if neighbours:
        parts.append("related services " + ", ".join(sorted(neighbours)))
    parts += alert_summaries
    return ". ".join(parts)


async def incident_context(session: AsyncSession, incident: Incident, top: int = 3) -> tuple[list[str], list[str]]:
    """The incident's service-graph neighbours, and its most frequent alert summaries (one per alert rule)."""
    neighbours = sorted({b for a, b in (await session.execute(
        select(ServiceEdge.from_service, ServiceEdge.to_service).where(
            (ServiceEdge.from_service == incident.service) | (ServiceEdge.to_service == incident.service))
    )).all() for b in (a, b) if b != incident.service})
    alertname = AlertEvent.labels["alertname"].astext
    rows = (await session.execute(
        select(alertname, func.min(AlertEvent.summary), func.count().label("n"))
        .where(AlertEvent.incident_id == incident.id,
               # Bounded on occurred_at so only the incident's partitions are read.
               AlertEvent.occurred_at >= incident.opened_at - timedelta(minutes=1),
               AlertEvent.occurred_at <= (incident.last_alert_at or incident.opened_at) + timedelta(minutes=1))
        .group_by(alertname).order_by(func.count().desc()).limit(top)
    )).all()
    return neighbours, [summary for _, summary, _ in rows]


async def _documents(session: AsyncSession, query: str, source_type: str, k: int) -> list[EvidenceItem]:
    async with AsyncSession(bind=session.bind) as own:  # its own connection: the sources run concurrently
        hits = (await hybrid_search(own, query, k, source_type=source_type)).hits
    return [EvidenceItem(h.source_type, h.document_path, h.chunk_id, h.heading_path, h.text) for h in hits]


async def _deploys(client: httpx.AsyncClient, services: list[str], at: datetime) -> list[EvidenceItem]:
    response = await client.get("/v1/deploys", params={
        "service": services, "since": (at - timedelta(hours=settings.triage_deploy_window_h)).isoformat(),
        "until": at.isoformat(), "limit": settings.triage_deploys_max,  # a later deploy can't be the cause
    })
    response.raise_for_status()
    return [
        EvidenceItem("deploy", d["id"], None, f"deploy {d['service']} {d['version']}",
                     f"Deploy {d['id']}: {d['service']} version {d['version']} deployed at {d['deployed_at']} by "
                     f"{d['author']} (commit {d['commit_sha'][:10]}, {d['status']}). Change: {d['summary']}. "
                     f"{_before(at, d['deployed_at'])}")
        for d in response.json()
    ]


def _before(at: datetime, deployed_at: str) -> str:
    """How long before the incident a deploy was, so the model needn't compare timestamps (small models misread
    them: docs/adr/0010)."""
    minutes = max(0, round((at - datetime.fromisoformat(deployed_at)).total_seconds() / 60))
    return f"It was {minutes} minutes before the incident opened."


async def gather_evidence(session: AsyncSession, client: httpx.AsyncClient, incident: Incident, query: str,
                          neighbours: list[str]) -> Gathered:
    gathered = Gathered()
    results: dict[str, list[EvidenceItem]] = {}

    async def fetch(source: str, work, timeout_s: float) -> None:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(timeout_s):
                results[source] = await work
        except TimeoutError:
            gathered.degraded.append({"source": source, "reason": f"timed out after {timeout_s * 1000:.0f} ms"})
        except httpx.HTTPStatusError as e:
            gathered.degraded.append({"source": source, "reason": f"HTTP {e.response.status_code}"})
        except Exception as e:  # noqa: BLE001 - any failure of one source degrades it; the others carry on
            log.warning("evidence source %s failed: %r", source, e)
            gathered.degraded.append({"source": source, "reason": type(e).__name__})
        gathered.timings_ms[source] = int((time.perf_counter() - started) * 1000)

    # Each task catches its own failure, so one source failing never cancels the others.
    async with asyncio.TaskGroup() as group:
        group.create_task(fetch("runbooks", _documents(session, query, "runbook", settings.triage_runbooks_k),
                                settings.triage_timeout_runbooks_s))
        group.create_task(fetch("postmortems", _documents(session, query, "postmortem", settings.triage_postmortems_k),
                                settings.triage_timeout_postmortems_s))
        group.create_task(fetch("deploys", _deploys(client, [incident.service, *neighbours], incident.opened_at),
                                settings.triage_timeout_deploys_s))
    for source in ("runbooks", "postmortems", "deploys"):  # a fixed order, so tags are stable for the same evidence
        gathered.items += results.get(source, [])
    gathered.degraded.sort(key=lambda d: d["source"])
    return gathered


def _incident_text(incident: Incident) -> str:
    return (f"Title: {incident.title}\nService: {incident.service}\nSeverity: {incident.severity}\n"
            f"Opened: {incident.opened_at.isoformat()}\nSummary: {incident.summary or '(none)'}")


def _estimate_tokens(messages: list[dict[str, str]]) -> int:
    # Counted with the embedding tokenizer; 10% margin for the chat model counting differently (ADR 0003).
    return int(sum(count_tokens(m["content"]) for m in messages) * 1.1)


def _citation(item: dict, section: str | None) -> schemas.CitationEvent:
    text = item["text"]
    return schemas.CitationEvent(
        tag=item["tag"], source_type=item["source_type"], source_id=item["source_id"],
        chunk_id=item["chunk_id"],
        chunk_excerpt=text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS].rstrip() + "…",
        section=section,  # type: ignore[arg-type]  # one of SECTIONS' values, or None
    )


async def generate(session: AsyncSession, client: httpx.AsyncClient, run: TriageRun) -> AsyncIterator[TriageEvent]:
    """Gathers evidence and streams the brief for a run the caller has claimed (status 'running'). Stores the
    outcome on the run; the last event is always done or error."""
    incident = await session.get(Incident, run.incident_id)
    assert incident is not None  # triage_runs.incident_id is a foreign key
    neighbours, summaries = await incident_context(session, incident)
    gathered = await gather_evidence(session, client, incident,
                                     build_query(incident.title, incident.service, neighbours, summaries), neighbours)
    run.evidence = [
        {"tag": f"C{i}", "source_type": e.source_type, "source_id": e.source_id,
         "chunk_id": str(e.chunk_id) if e.chunk_id else None, "heading_path": e.heading_path, "text": e.text}
        for i, e in enumerate(gathered.items, start=1)
    ]
    run.degraded_sources = gathered.degraded
    run.model, run.prompt_version = settings.llm_model, prompts.TRIAGE_PROMPT_VERSION
    await session.commit()
    log.info("triage %s: %d evidence items, degraded %s, source ms %s", run.id, len(run.evidence),
             [d["source"] for d in gathered.degraded] or "none", gathered.timings_ms)
    for degraded in gathered.degraded:
        yield "degraded_source", schemas.DegradedSourceEvent.model_validate(degraded)

    by_tag = {item["tag"]: item for item in run.evidence}
    evidence = [prompts.EvidenceChunk(tag=i["tag"], source=f"{i['source_type']} {i['source_id'].rsplit('/', 1)[-1]}",
                                      heading_path=i["heading_path"], text=i["text"]) for i in run.evidence]
    messages = prompts.triage_messages(_incident_text(incident), evidence, [d["source"] for d in gathered.degraded])
    gate = citations.LikelyCauseGate(cause_tags(run.evidence))
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
            for event in scanner.feed(gate.feed(piece)):
                yield _scan_event(event, by_tag)
            if time.monotonic() - last_beat >= settings.triage_heartbeat_s:
                run.heartbeat_at = datetime.now(UTC)
                await session.commit()
                last_beat = time.monotonic()
    except llm.PromptTooLong as exc:
        yield await fail(session, run, ProblemCode.PROMPT_TOO_LONG, str(exc))
        return
    except ConnectionError:  # the ollama client's own error when Ollama isn't running
        yield await fail(session, run, ProblemCode.MODEL_UNAVAILABLE, "model server unreachable")
        return
    for event in [*scanner.feed(gate.finish()), *scanner.finish()]:
        yield _scan_event(event, by_tag)

    assert result is not None  # Ollama's last chunk (done=True) carries the counts
    run.raw_text = result.content  # what the model wrote, decision line included; the brief is scanner.text
    run.prompt_tokens, run.output_tokens = result.prompt_tokens, result.output_tokens
    run.total_ms = int((time.monotonic() - started) * 1000)
    log.info("triage %s: cause decision %s", run.id, gate.decision)
    parsed = citations.parse_brief(scanner.text, set(by_tag))
    if gate.decision == "missing":
        parsed.problems.append("likely_cause: no Match line")
    if parsed.verdict is None or parsed.problems:
        yield await fail(session, run, ProblemCode.FORMAT_INVALID, "the brief broke the section contract",
                          parsed.problems)
        return
    brief = _brief(run, parsed, by_tag)
    # Python timestamps, not func.now(): a SQL expression on an ORM attribute expires it, and reading it back
    # under asyncio would need a lazy load.
    run.status, run.verdict, run.finished_at = "completed", brief.verdict, datetime.now(UTC)
    run.brief = brief.model_dump(mode="json")
    await session.commit()
    yield "done", brief


def cause_tags(evidence: list[dict]) -> set[str]:
    """The items a Likely cause may rest on: runbooks and postmortems, never a deploy alone."""
    return {item["tag"] for item in evidence if item["source_type"] in ("runbook", "postmortem")}


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
        degraded_sources=[schemas.DegradedSource.model_validate(d) for d in run.degraded_sources],
    )


async def fail(session: AsyncSession, run: TriageRun, code: ProblemCode, detail: str,
                problems: list[str] | None = None) -> TriageEvent:
    run.status, run.error_code, run.problems, run.finished_at = "failed", code, problems or [], datetime.now(UTC)
    await session.commit()
    return "error", schemas.ErrorEvent(code=code, detail=detail, problems=problems or [])


def replay(run: TriageRun) -> list[TriageEvent]:
    """A finished run's events again, from what was stored, in the same shapes as the live stream."""
    events: list[TriageEvent] = [("degraded_source", schemas.DegradedSourceEvent.model_validate(d))
                                  for d in run.degraded_sources]
    if run.status == "failed":
        assert run.error_code is not None  # fail() always stores one
        return [*events, ("error", schemas.ErrorEvent(code=ProblemCode(run.error_code), detail="this triage failed",
                                                      problems=run.problems))]
    assert run.brief is not None
    brief = schemas.TriageBrief.model_validate(run.brief)
    text, _ = citations.gate_brief(run.raw_text, cause_tags(run.evidence))
    events.append(("token", schemas.TokenEvent(text=text)))
    for key in citations.SECTIONS.values():
        for c in getattr(brief.sections, key).citations:
            events.append(("citation", schemas.CitationEvent.model_validate({**c.model_dump(), "section": key})))
        events.append(("section_complete", schemas.SectionCompleteEvent.model_validate({"section": key})))
    events.append(("done", brief))
    return events


async def events(session: AsyncSession, redis, run_id: uuid.UUID) -> AsyncIterator[tuple[str, str]]:
    """Every event of the run as (name, JSON data), from its start, live until done or error, for any number of
    readers. Reads the run's Redis stream; if the run finished before this reader came and its stream has expired,
    or the stream goes silent while the database says the run is over, falls back to the stored result."""
    run = await session.get(TriageRun, run_id)
    if run is not None and run.status in ("completed", "failed") and not await bus.has_triage_events(redis, run_id):
        for name, payload in replay(run):  # finished long ago: its stream has expired
            yield name, payload.model_dump_json()
        return
    sent = 0
    async for item in bus.triage_events(redis, run_id):
        if item is not None:
            sent += 1
            yield item
            continue
        session.expire_all()
        run = await session.get(TriageRun, run_id)
        if run is None or run.status not in ("completed", "failed"):
            continue  # still queued or generating: keep waiting
        stored = replay(run)
        for name, payload in (stored if sent == 0 else stored[-1:]):  # mid-stream: only the outcome is missing
            yield name, payload.model_dump_json()
        return


async def publish(redis, run_id: uuid.UUID, name: str, payload: BaseModel) -> None:
    await bus.append_triage_event(redis, run_id, name, payload.model_dump_json())
