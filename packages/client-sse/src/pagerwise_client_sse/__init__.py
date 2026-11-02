"""Typed reader for GET /v1/incidents/{id}/triage/stream.

The generated client (packages/clients/python) reads a text/event-stream response as one string once it has
ended. This yields each event as it arrives, parsed into the generated model for its event name. The request
itself comes from the generated module, so the URL stays whatever contracts/openapi.yaml says."""

import json
from collections.abc import Iterator
from uuid import UUID

from pagerwise_client import Client
from pagerwise_client.api.default import stream_triage as _stream_triage
from pagerwise_client.models import (
    CitationEvent,
    DegradedSourceEvent,
    ErrorEvent,
    Problem,
    SectionCompleteEvent,
    TokenEvent,
    TriageBrief,
)

TriageEvent = DegradedSourceEvent | TokenEvent | CitationEvent | SectionCompleteEvent | TriageBrief | ErrorEvent

EVENT_MODELS: dict[str, type[TriageEvent]] = {
    "degraded_source": DegradedSourceEvent,
    "token": TokenEvent,
    "citation": CitationEvent,
    "section_complete": SectionCompleteEvent,
    "done": TriageBrief,
    "error": ErrorEvent,
}


class TriageStreamRefused(Exception):
    """The stream didn't open (404): the server's problem document is on `.problem`."""

    def __init__(self, problem: Problem):
        super().__init__(f"{problem.status} {problem.code}: {problem.detail or problem.title}")
        self.problem = problem


def stream_triage(client: Client, incident_id: UUID) -> Iterator[TriageEvent]:
    """Events in arrival order; the last one is a TriageBrief (done) or an ErrorEvent. Unknown event names are
    skipped, so a server that adds an event type doesn't break older clients."""
    request = _stream_triage._get_kwargs(incident_id)
    # No read timeout: the model can be quiet for a while before its first token; the server sends keep-alives.
    with client.get_httpx_client().stream(request["method"], request["url"], timeout=None) as response:
        if response.status_code != 200:
            response.read()
            raise TriageStreamRefused(Problem.from_dict(response.json()))
        event, data = "message", []
        for line in response.iter_lines():
            if not line:  # a blank line ends an event
                if data and event in EVENT_MODELS:
                    yield EVENT_MODELS[event].from_dict(json.loads("\n".join(data)))
                event, data = "message", []
            elif line.startswith(":"):
                continue  # comment: the server's keep-alive
            else:
                name, _, value = line.partition(":")
                value = value.removeprefix(" ")
                if name == "event":
                    event = value
                elif name == "data":
                    data.append(value)

