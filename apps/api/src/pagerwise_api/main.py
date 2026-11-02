import uuid
from collections.abc import AsyncIterable
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from pagerwise_api import llm, prompts, schemas, service
from pagerwise_api.db import TriageRun, get_session
from pagerwise_api.graphql import graphql_router
from pagerwise_api.schemas import ApiProblem, Problem, ProblemCode

app = FastAPI(title="Pagerwise", version="0.2.0")
app.include_router(graphql_router, prefix="/graphql", include_in_schema=False)

PROBLEM_JSON = "application/problem+json"
EVENT_STREAM = "text/event-stream"
Session = Annotated[AsyncSession, Depends(get_session)]


def problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(problem.model_dump(mode="json", exclude_none=True), status_code=problem.status,
                        media_type=PROBLEM_JSON)


@app.exception_handler(ApiProblem)
async def api_problem_handler(_: Request, exc: ApiProblem) -> JSONResponse:
    return problem_response(exc.problem)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors())
    return problem_response(ApiProblem(400, ProblemCode.INVALID_REQUEST, "Invalid request", details).problem)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = ProblemCode.NOT_FOUND if exc.status_code == 404 else ProblemCode.INVALID_REQUEST
    return problem_response(ApiProblem(exc.status_code, code, str(exc.detail)).problem)


def _problems(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: {"model": Problem, "description": "An RFC 9457 problem."} for status in statuses}


@app.post("/v1/ask", operation_id="ask", responses=_problems(400, 422, 503))
async def ask(body: schemas.AskRequest, session: Session) -> schemas.AskResponse:
    try:
        result = await service.ask(session, body.question)
    except llm.PromptTooLong as e:
        raise ApiProblem(422, ProblemCode.PROMPT_TOO_LONG, "Prompt too long", str(e)) from e
    except ConnectionError as e:  # the ollama client's own error when Ollama isn't running
        raise ApiProblem(503, ProblemCode.MODEL_UNAVAILABLE, "Model unavailable", "model server unreachable") from e
    assert result.chat is not None
    return schemas.AskResponse(
        answer_id=result.answer_id,
        answer=result.answer,
        verdict=result.verdict,
        citations=[schemas.AskCitation(**c.__dict__) for c in result.citations],
        problems=result.problems,
        usage=schemas.AskUsage(
            model=result.chat.model,
            prompt_version=prompts.ASK_PROMPT_VERSION,
            prompt_tokens=result.chat.prompt_tokens,
            output_tokens=result.chat.output_tokens,
            total_ms=result.chat.total_ms,
        ),
    )


@app.post("/v1/incidents", operation_id="createIncident", status_code=201, responses=_problems(400))
async def create_incident(body: schemas.IncidentCreate, session: Session) -> schemas.Incident:
    return schemas.Incident.model_validate(await service.create_incident(session, body))


@app.get("/v1/incidents", operation_id="listIncidents", responses=_problems(400))
async def list_incidents(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    after: Annotated[str | None, Query(description="next_cursor from the previous page")] = None,
    status: schemas.IncidentStatus | None = None,
    service_name: Annotated[str | None, Query(alias="service")] = None,
    severity: schemas.Severity | None = None,
) -> schemas.IncidentPage:
    page = await service.list_incidents(session, limit, after, status=status, service=service_name, severity=severity)
    return schemas.IncidentPage(items=[schemas.Incident.model_validate(r) for r in page.items],
                                next_cursor=page.next_cursor)


@app.get("/v1/incidents/{incident_id}", operation_id="getIncident", responses=_problems(404))
async def get_incident(incident_id: uuid.UUID, session: Session) -> schemas.Incident:
    row = await service.get_incident(session, incident_id)
    if row is None:
        raise ApiProblem(404, ProblemCode.NOT_FOUND, "Incident not found", f"no incident with id {incident_id}")
    return schemas.Incident.model_validate(row)


@app.post("/v1/incidents/{incident_id}/triage", operation_id="startTriage", status_code=202, responses=_problems(404, 409))
async def start_triage(incident_id: uuid.UUID, session: Session) -> schemas.TriageAccepted:
    run = await service.start_triage(session, incident_id)
    return schemas.TriageAccepted(triage_id=run.id, incident_id=run.incident_id, incident_version=run.incident_version,
                                  stream_url=f"/v1/incidents/{incident_id}/triage/stream")


async def _open_triage_stream(incident_id: uuid.UUID, session: Session) -> tuple[TriageRun, bool]:
    """A dependency, not the first line of the endpoint: a streaming endpoint has already sent 200 and its headers
    by the time its body runs, so a 404 or 409 raised there would be lost. Dependencies run before the response."""
    return await service.open_triage_stream(session, incident_id)


@app.get(
    "/v1/incidents/{incident_id}/triage/stream",
    operation_id="streamTriage",
    response_class=EventSourceResponse,
    responses=_problems(404, 409),
    description=(
        "The incident's latest triage as server-sent events. The first connection generates it; later ones replay "
        "the stored result. Events, each with a JSON `data` payload: `token` (TokenEvent), `citation` "
        "(CitationEvent, once a complete [Cn] tag has arrived), `section_complete` (SectionCompleteEvent), then "
        "either `done` (TriageBrief) or `error` (ErrorEvent)."
    ),
)
async def stream_triage(
    session: Session, opened: Annotated[tuple[TriageRun, bool], Depends(_open_triage_stream)]
) -> AsyncIterable[ServerSentEvent]:
    run, claimed = opened
    async for name, payload in service.triage_events(session, run, claimed):
        yield ServerSentEvent(event=name, data=payload)


_default_openapi = app.openapi


def openapi_with_problem_json() -> dict[str, Any]:
    """FastAPI documents every response model as application/json and adds a 422 validation response to each
    route. Ours differ: errors are application/problem+json, and validation failures are 400 problems. The
    triage stream's event payloads are added as components so generated clients get a model for each."""
    if app.openapi_schema is None:
        schema = _default_openapi()
        for operations in schema["paths"].values():
            for operation in operations.values():
                responses = operation.get("responses", {})
                if "HTTPValidationError" in str(responses.get("422", "")):
                    del responses["422"]
                for status, response in responses.items():
                    content = response.get("content", {})
                    if int(status) >= 400 and content:  # the stream route labels its problems text/event-stream
                        response["content"] = {PROBLEM_JSON: next(iter(content.values()))}
                    elif "itemSchema" in content.get(EVENT_STREAM, {}):
                        # FastAPI emits OpenAPI 3.2's itemSchema; this is a 3.1 document, where the stream is a
                        # string and the events are described in the operation and the *Event components.
                        content[EVENT_STREAM] = {"schema": {"type": "string"}}
        components = schema["components"]["schemas"]
        for unused in ("HTTPValidationError", "ValidationError"):
            components.pop(unused, None)
        for model in (schemas.TokenEvent, schemas.CitationEvent, schemas.SectionCompleteEvent, schemas.TriageBrief,
                      schemas.ErrorEvent):
            definition = model.model_json_schema(ref_template="#/components/schemas/{model}")
            for name, nested in definition.pop("$defs", {}).items():
                components.setdefault(name, nested)
            components[model.__name__] = definition
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = openapi_with_problem_json  # type: ignore[method-assign]  # FastAPI's documented way to customize the schema
