"""GraphQL for the UI: reads, live updates and its one mutation. Resolvers call the same service functions as REST,
so no rule is written twice.

Subscriptions run over graphql-transport-ws on the same /graphql path. incidentUpdated follows the consumer's
Redis pub/sub of changed incidents; triageProgress reads a triage's Redis stream, the same one the SSE endpoint
reads, from its first event."""

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated
from datetime import datetime, timedelta

import strawberry
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry import relay
from strawberry.fastapi import BaseContext, GraphQLRouter
from strawberry.scalars import JSON

from pagerwise_api import bus, service, triage
from pagerwise_api.db import AlertEvent, TriageRun, get_session
from pagerwise_api.db import Incident as IncidentRow
from pagerwise_api.schemas import ApiProblem
from pagerwise_api.settings import settings


class Context(BaseContext):
    def __init__(self, session: AsyncSession):
        super().__init__()
        self.session = session


async def get_context(session: AsyncSession = Depends(get_session)) -> Context:  # noqa: B008 - FastAPI's DI
    return Context(session)


@strawberry.type
class AlertGroup:
    """The alerts of one rule on one target (one fingerprint) within an incident."""

    service: str
    alertname: str | None
    instance: str | None
    fingerprint: str
    count: int
    first_at: datetime
    last_at: datetime


@strawberry.type
class Triage:
    id: uuid.UUID
    status: str
    verdict: str | None
    incident_version: int
    degraded_sources: list[str]
    created_at: datetime
    finished_at: datetime | None


@strawberry.type
class Incident:
    id: uuid.UUID
    title: str
    service: str
    severity: str
    status: str
    summary: str
    opened_at: datetime
    version: int
    alert_count: int
    last_alert_at: datetime | None

    @classmethod
    def from_row(cls, row: IncidentRow) -> "Incident":
        return cls(id=row.id, title=row.title, service=row.service, severity=row.severity, status=row.status,
                   summary=row.summary, opened_at=row.opened_at, version=row.version, alert_count=row.alert_count,
                   last_alert_at=row.last_alert_at)

    @strawberry.field(description="Alert groups by fingerprint, busiest first: the incident's timeline material.")
    async def alerts(self, info: strawberry.Info["Context"], first: int = 20) -> list[AlertGroup]:
        alertname, instance = AlertEvent.labels["alertname"].astext, AlertEvent.labels["instance"].astext
        rows = (await info.context.session.execute(
            select(AlertEvent.service, alertname, instance, AlertEvent.fingerprint, func.count(),
                   func.min(AlertEvent.occurred_at), func.max(AlertEvent.occurred_at))
            .where(AlertEvent.incident_id == self.id,
                   # Bounded on occurred_at so only the incident's partitions are read.
                   AlertEvent.occurred_at >= self.opened_at - timedelta(minutes=1),
                   AlertEvent.occurred_at <= (self.last_alert_at or self.opened_at) + timedelta(minutes=1))
            .group_by(AlertEvent.service, alertname, instance, AlertEvent.fingerprint)
            .order_by(func.count().desc()).limit(min(first, 100))
        )).all()
        return [AlertGroup(service=r[0], alertname=r[1], instance=r[2], fingerprint=r[3], count=r[4], first_at=r[5],
                           last_at=r[6]) for r in rows]

    @strawberry.field(description="The latest triage of this incident, if any.")
    async def triage(self, info: strawberry.Info["Context"]) -> Triage | None:
        run = await info.context.session.scalar(
            select(TriageRun).where(TriageRun.incident_id == self.id).order_by(TriageRun.created_at.desc()).limit(1))
        if run is None:
            return None
        return Triage(id=run.id, status=run.status, verdict=run.verdict, incident_version=run.incident_version,
                      degraded_sources=[d["source"] for d in run.degraded_sources], created_at=run.created_at,
                      finished_at=run.finished_at)


@strawberry.input
class IncidentFilter:
    status: str | None = None
    service: str | None = None
    severity: str | None = None


@strawberry.type
class IncidentConnection(relay.Connection[Incident]):  # type: ignore[type-var]  # Incident isn't a relay.Node: our cursors are signed keysets, not global ids
    """Relay-style connection backed by the same signed keyset cursors as REST, not by offsets."""


@strawberry.type
class VersionConflict:
    """The incident changed since the caller read it: re-read it, then decide again."""

    incident_id: uuid.UUID
    expected_version: int
    current_version: int


AcknowledgeResult = Annotated[Incident | VersionConflict, strawberry.union("AcknowledgeResult")]


@strawberry.type
class TriageProgress:
    """One event of a triage stream: the same names and JSON payloads as the SSE endpoint's events."""

    triage_id: uuid.UUID
    event: str
    data: JSON


@strawberry.type
class Query:
    @strawberry.field
    async def incident(self, info: strawberry.Info[Context], id: uuid.UUID) -> Incident | None:
        row = await service.get_incident(info.context.session, id)
        return Incident.from_row(row) if row else None

    @strawberry.field(description="Newest first. `after` takes an endCursor from a previous page.")
    async def incidents(
        self, info: strawberry.Info[Context], filter: IncidentFilter | None = None, first: int = 25,
        after: str | None = None,
    ) -> IncidentConnection:
        if not 1 <= first <= 100:
            raise ValueError("first must be between 1 and 100")
        f = filter or IncidentFilter()
        try:
            page = await service.list_incidents(info.context.session, first, after, status=f.status,
                                                service=f.service, severity=f.severity)
        except ApiProblem as exc:
            raise ValueError(exc.problem.detail) from None
        edges = [relay.Edge(node=Incident.from_row(r), cursor=c) for r, c in zip(page.items, page.cursors, strict=True)]  # type: ignore[type-var]
        return IncidentConnection(
            edges=edges,
            page_info=relay.PageInfo(
                has_next_page=page.next_cursor is not None,
                has_previous_page=after is not None,
                start_cursor=edges[0].cursor if edges else None,
                end_cursor=edges[-1].cursor if edges else None,
            ),
        )


@strawberry.type
class Mutation:
    @strawberry.mutation(description="Acknowledge the incident as of the version you saw. If a new kind of alert "
                                     "joined or severity rose since, you get VersionConflict and nothing changes.")
    async def acknowledge_incident(self, info: strawberry.Info[Context], id: uuid.UUID,
                                   expected_version: int) -> AcknowledgeResult:
        result = await service.acknowledge_incident(info.context.session, id, expected_version)
        if isinstance(result, int):
            return VersionConflict(incident_id=id, expected_version=expected_version, current_version=result)
        redis = bus.connect()
        try:
            await bus.publish_incidents(redis, [{"type": "updated", "incident_id": str(id), "status": result.status,
                                                 "version": result.version}])
        finally:
            await redis.aclose()
        return Incident.from_row(result)


@strawberry.type
class Subscription:
    @strawberry.subscription(description="Incidents as they open or change, optionally for one service.")
    async def incident_updated(
        self, info: strawberry.Info[Context],
        service_name: Annotated[str | None, strawberry.argument(name="service")] = None,
    ) -> AsyncGenerator[Incident, None]:
        session = info.context.session
        redis = bus.connect()
        try:
            async for message in bus.incident_updates(redis):
                if service_name and message.get("service") not in (None, service_name):
                    continue
                row = await service.get_incident(session, uuid.UUID(message["incident_id"]))
                # Copy the row out before ending the read: the rollback expires it, and reloading an expired
                # attribute under asyncio raises MissingGreenlet.
                incident = Incident.from_row(row) if row is not None else None
                await session.rollback()  # a long-lived connection mustn't sit in an open transaction
                if incident is not None and (not service_name or incident.service == service_name):
                    yield incident
        finally:
            await redis.aclose()

    @strawberry.subscription(description="A triage's events from its first one, live, ending with done or error.")
    async def triage_progress(self, info: strawberry.Info[Context],
                              triage_id: uuid.UUID) -> AsyncGenerator[TriageProgress, None]:
        redis = bus.connect()
        try:
            async for name, data in triage.events(info.context.session, redis, triage_id):
                yield TriageProgress(triage_id=triage_id, event=name, data=json.loads(data))
        finally:
            await redis.aclose()


schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
graphql_router: GraphQLRouter = GraphQLRouter(schema, context_getter=get_context,
                                              allowed_origins=settings.web_origins)
