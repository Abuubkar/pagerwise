"""Alerts into incidents. Deterministic first, similarity second, no LLM.

1. Same service and fingerprint fired in the last 10 minutes into an incident that isn't resolved: same incident.
2. Otherwise compare the alert's summary embedding with incidents that aren't resolved, had an alert in the last 15
   minutes, and belong to a service within one hop on the service graph (either direction: a failing dependency
   pages its callers too). Cosine similarity >= 0.86 joins the most similar one.
3. Otherwise open a new incident.

`decide` is the rule, pure and table-tested. `store_alerts` applies it to a batch inside one transaction. Two
consumers can see related alerts at once (neighbouring services sit on different partitions; a rebalance can split
one service's alerts), so it first takes a transaction-scoped advisory lock on every service in the batch's
neighbourhoods, in a fixed order, and locks each incident row it joins (SELECT ... FOR NO KEY UPDATE)."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import case, delete, func, literal, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagerwise_api.db import AlertEvent, Incident

FINGERPRINT_WINDOW = timedelta(minutes=10)
SIMILAR_WINDOW = timedelta(minutes=15)
SIMILARITY = 0.86
SEVERITY = {"critical": "sev1", "warning": "sev3", "info": "sev4"}  # alert severity -> incident severity


@dataclass(frozen=True)
class RecentAlert:
    """An earlier alert with the same service and fingerprint, and the incident it went into."""

    incident_id: uuid.UUID
    occurred_at: datetime
    incident_status: str


@dataclass(frozen=True)
class Candidate:
    incident_id: uuid.UUID
    service: str
    status: str
    last_alert_at: datetime
    similarity: float  # cosine similarity of the alert's summary to the incident's


@dataclass(frozen=True)
class Decision:
    kind: str  # "fingerprint" | "similar" | "new"
    incident_id: uuid.UUID | None = None
    similarity: float | None = None


def neighbourhood(service: str, edges: set[tuple[str, str]]) -> set[str]:
    """The service and every service one edge away, in either direction."""
    return {service} | {b for a, b in edges if a == service} | {a for a, b in edges if b == service}


def decide(service: str, occurred_at: datetime, recent: list[RecentAlert], candidates: list[Candidate],
           edges: set[tuple[str, str]]) -> Decision:
    for alert in sorted(recent, key=lambda a: a.occurred_at, reverse=True):
        if occurred_at - FINGERPRINT_WINDOW <= alert.occurred_at <= occurred_at and alert.incident_status != "resolved":
            return Decision("fingerprint", alert.incident_id)
    near = neighbourhood(service, edges)
    eligible = [
        c for c in candidates
        if c.status != "resolved" and c.service in near and c.similarity >= SIMILARITY
        and occurred_at - SIMILAR_WINDOW <= c.last_alert_at
    ]
    if eligible:
        # Most similar first; a tie goes to the same service, then to the most recently active incident.
        best = max(eligible, key=lambda c: (round(c.similarity, 4), c.service == service, c.last_alert_at))
        return Decision("similar", best.incident_id, best.similarity)
    return Decision("new")


@dataclass
class Touched:
    """What happened to one incident in a batch, for the post-commit update to Redis."""

    incident_id: uuid.UUID
    opened: bool
    alerts: int = 0
    after: dict = field(default_factory=dict)  # the incident's row after this batch: version, alert_count, ...


@dataclass
class StoreResult:
    inserted: int = 0
    duplicates: int = 0
    touched: dict[uuid.UUID, Touched] = field(default_factory=dict)
    decisions: dict[str, int] = field(default_factory=dict)  # kind -> groups decided that way


async def _lock_services(session: AsyncSession, services: set[str]) -> None:
    # Sorted, so two transactions always take overlapping locks in the same order and can't deadlock.
    for name in sorted(services):
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtext("incident-cluster:" + name))))


async def store_alerts(session: AsyncSession, rows: list[dict], edges: set[tuple[str, str]],
                       embed) -> StoreResult:  # noqa: ANN001 - async (list[str]) -> list[list[float]]
    """Clusters and inserts a batch of alert rows (dicts of AlertEvent columns, without incident_id). Runs in the
    caller's transaction; the caller commits. Alerts already stored (redelivery) are skipped before clustering, so
    a duplicate can never open an incident."""
    result = StoreResult()
    if not rows:
        return result
    times = [r["occurred_at"] for r in rows]
    stored = set(await session.scalars(
        select(AlertEvent.event_id).where(AlertEvent.event_id.in_([r["event_id"] for r in rows]),
                                          AlertEvent.occurred_at.between(min(times), max(times)))
    ))
    fresh = [r for r in rows if r["event_id"] not in stored]
    result.duplicates = len(rows) - len(fresh)
    if not fresh:
        return result
    await _lock_services(session, set().union(*(neighbourhood(r["service"], edges) for r in fresh)))

    # One decision per (service, fingerprint) group: its alerts are the same problem repeating.
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in sorted(fresh, key=lambda r: r["occurred_at"]):
        groups.setdefault((row["service"], row["fingerprint"]), []).append(row)

    first_of = {key: alerts[0] for key, alerts in groups.items()}
    recent: dict[tuple[str, str], list[RecentAlert]] = {key: [] for key in groups}
    for service, fingerprint, incident_id, occurred_at, status in (await session.execute(
        select(AlertEvent.service, AlertEvent.fingerprint, AlertEvent.incident_id, AlertEvent.occurred_at,
               Incident.status)
        .join(Incident, Incident.id == AlertEvent.incident_id)
        .where(tuple_(AlertEvent.service, AlertEvent.fingerprint).in_(list(groups)),
               AlertEvent.occurred_at >= min(times) - FINGERPRINT_WINDOW,
               AlertEvent.occurred_at <= max(times))
    )).all():
        recent[(service, fingerprint)].append(RecentAlert(incident_id, occurred_at, status))

    # Only groups the fingerprint rule can't place need an embedding (most of a storm repeats known fingerprints).
    unplaced = [k for k in groups
                if decide(k[0], first_of[k]["occurred_at"], recent[k], [], edges).kind != "fingerprint"]
    vectors = dict(zip(unplaced, await embed([first_of[k]["summary"] for k in unplaced]), strict=True))

    async def open_incident(first: dict, vector: list[float]) -> uuid.UUID:
        incident = Incident(
            title=f"{first['labels'].get('alertname') or first['fingerprint']} on {first['service']}",
            service=first["service"], severity=SEVERITY[first["severity"]], summary=first["summary"],
            opened_at=first["occurred_at"], last_alert_at=first["occurred_at"], alert_count=0, embedding=vector,
        )
        session.add(incident)
        await session.flush()
        result.touched[incident.id] = Touched(incident.id, opened=True)
        return incident.id

    incident_for: dict[tuple[str, str], uuid.UUID] = {}
    worst: dict[uuid.UUID, str] = {}  # incident -> most severe incident severity among this batch's alerts
    new_kind: set[uuid.UUID] = set()  # existing incidents a new fingerprint joined
    for key, alerts in groups.items():
        first = alerts[0]
        candidates: list[Candidate] = []
        if key in vectors:
            distance = Incident.embedding.cosine_distance(vectors[key])
            for incident_id, service, status, last_alert_at, d in (await session.execute(
                select(Incident.id, Incident.service, Incident.status, Incident.last_alert_at, distance)
                .where(Incident.service.in_(neighbourhood(first["service"], edges)), Incident.status != "resolved",
                       Incident.last_alert_at >= first["occurred_at"] - SIMILAR_WINDOW,
                       Incident.embedding.is_not(None))
                .order_by(distance).limit(5)
            )).all():
                candidates.append(Candidate(incident_id, service, status, last_alert_at, 1 - float(d)))
        decision = decide(first["service"], first["occurred_at"], recent[key], candidates, edges)
        result.decisions[decision.kind] = result.decisions.get(decision.kind, 0) + 1

        incident_id = decision.incident_id
        if incident_id is not None:
            # Lock the row: a request resolving it, or another batch joining it, waits until this one commits. NO KEY
            # UPDATE, because only non-key columns change: it doesn't block the FOR KEY SHARE that inserting an
            # alert row referencing this incident takes, which plain FOR UPDATE did, deadlocking with the backfill.
            status = await session.scalar(
                select(Incident.status).where(Incident.id == incident_id).with_for_update(key_share=True))
            if status == "resolved":  # resolved between the lookup and the lock
                incident_id = None
        if incident_id is None:
            vector = vectors.get(key) or (await embed([first["summary"]]))[0]
            incident_id = await open_incident(first, vector)
        else:
            if decision.kind == "similar":
                new_kind.add(incident_id)
            result.touched.setdefault(incident_id, Touched(incident_id, opened=False))
        incident_for[key] = incident_id
        for alert in alerts:
            worst[incident_id] = min(worst.get(incident_id, "sev4"), SEVERITY[alert["severity"]])

    inserted = (await session.execute(
        insert(AlertEvent)
        .values([{**r, "incident_id": incident_for[(r["service"], r["fingerprint"])]} for r in fresh])
        .on_conflict_do_nothing()  # no target: matches the plain table's key and the partitioned (event_id, occurred_at)
        .returning(AlertEvent.incident_id, AlertEvent.occurred_at)
    )).all()
    result.inserted = len(inserted)
    result.duplicates += len(fresh) - len(inserted)  # lost a race with another consumer for the same message

    last_seen: dict[uuid.UUID, datetime] = {}
    for incident_id, occurred_at in inserted:
        result.touched[incident_id].alerts += 1
        last_seen[incident_id] = max(last_seen.get(incident_id, occurred_at), occurred_at)
    for incident_id, touched in list(result.touched.items()):
        if touched.alerts == 0:
            if touched.opened:  # every alert it was opened for was stored by someone else meanwhile
                await session.execute(delete(Incident).where(Incident.id == incident_id))
            del result.touched[incident_id]
            continue
        changed = or_(literal(incident_id in new_kind), Incident.severity > worst[incident_id])
        row = (await session.execute(
            update(Incident).where(Incident.id == incident_id).values(
                alert_count=Incident.alert_count + touched.alerts,
                last_alert_at=func.greatest(Incident.last_alert_at, last_seen[incident_id]),
                severity=func.least(Incident.severity, worst[incident_id]),
                # A new kind of alert joining, or the severity rising, changes what a triage would say.
                version=Incident.version + case((changed, 1), else_=0) if not touched.opened else Incident.version,
            ).returning(Incident.title, Incident.service, Incident.severity, Incident.version, Incident.alert_count)
        )).one()
        touched.after = dict(row._mapping)
    return result
