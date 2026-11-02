"""GraphQL reads for the UI. Resolvers call the same service functions as REST, so no rule is written twice."""

import uuid
from datetime import datetime

import strawberry
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry import relay
from strawberry.fastapi import BaseContext, GraphQLRouter

from pagerwise_api import service
from pagerwise_api.db import Incident as IncidentRow
from pagerwise_api.db import get_session
from pagerwise_api.schemas import ApiProblem


class Context(BaseContext):
    def __init__(self, session: AsyncSession):
        super().__init__()
        self.session = session


async def get_context(session: AsyncSession = Depends(get_session)) -> Context:  # noqa: B008 - FastAPI's DI
    return Context(session)


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

    @classmethod
    def from_row(cls, row: IncidentRow) -> "Incident":
        return cls(id=row.id, title=row.title, service=row.service, severity=row.severity, status=row.status,
                   summary=row.summary, opened_at=row.opened_at, version=row.version)


@strawberry.input
class IncidentFilter:
    status: str | None = None
    service: str | None = None
    severity: str | None = None


@strawberry.type
class IncidentConnection(relay.Connection[Incident]):  # type: ignore[type-var]  # Incident isn't a relay.Node: our cursors are signed keysets, not global ids
    """Relay-style connection backed by the same signed keyset cursors as REST, not by offsets."""


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


schema = strawberry.Schema(query=Query)
graphql_router: GraphQLRouter = GraphQLRouter(schema, context_getter=get_context)
