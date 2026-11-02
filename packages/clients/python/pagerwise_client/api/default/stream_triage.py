from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    incident_id: UUID,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/incidents/{incident_id}/triage/stream".format(
            incident_id=quote(str(incident_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Problem | str | None:
    if response.status_code == 200:
        response_200 = response.text
        return response_200

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Problem | str]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    incident_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Problem | str]:
    """Stream the incident's latest triage

     Server-sent events, from the triage's first event: live while the triage worker generates it,
    replayed
    from the stored result once it's finished. Any number of clients can watch the same triage. Each
    event's
    `data` is JSON:

    | event | data | when |
    |---|---|---|
    | `degraded_source` | DegradedSourceEvent | before the first token, once per evidence source left
    out |
    | `token` | TokenEvent | a piece of the brief's markdown, as the model writes it |
    | `citation` | CitationEvent | a complete [Cn] tag has arrived (a tag can be split across tokens) |
    | `section_complete` | SectionCompleteEvent | a section's text is finished |
    | `done` | TriageBrief | the brief passed the section and citation contract; last event |
    | `error` | ErrorEvent | generation failed or the brief broke the contract; last event |

    Concatenating the `token` texts gives exactly what the model wrote.

    Args:
        incident_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | str]
    """

    kwargs = _get_kwargs(
        incident_id=incident_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    incident_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Problem | str | None:
    """Stream the incident's latest triage

     Server-sent events, from the triage's first event: live while the triage worker generates it,
    replayed
    from the stored result once it's finished. Any number of clients can watch the same triage. Each
    event's
    `data` is JSON:

    | event | data | when |
    |---|---|---|
    | `degraded_source` | DegradedSourceEvent | before the first token, once per evidence source left
    out |
    | `token` | TokenEvent | a piece of the brief's markdown, as the model writes it |
    | `citation` | CitationEvent | a complete [Cn] tag has arrived (a tag can be split across tokens) |
    | `section_complete` | SectionCompleteEvent | a section's text is finished |
    | `done` | TriageBrief | the brief passed the section and citation contract; last event |
    | `error` | ErrorEvent | generation failed or the brief broke the contract; last event |

    Concatenating the `token` texts gives exactly what the model wrote.

    Args:
        incident_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | str
    """

    return sync_detailed(
        incident_id=incident_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    incident_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Problem | str]:
    """Stream the incident's latest triage

     Server-sent events, from the triage's first event: live while the triage worker generates it,
    replayed
    from the stored result once it's finished. Any number of clients can watch the same triage. Each
    event's
    `data` is JSON:

    | event | data | when |
    |---|---|---|
    | `degraded_source` | DegradedSourceEvent | before the first token, once per evidence source left
    out |
    | `token` | TokenEvent | a piece of the brief's markdown, as the model writes it |
    | `citation` | CitationEvent | a complete [Cn] tag has arrived (a tag can be split across tokens) |
    | `section_complete` | SectionCompleteEvent | a section's text is finished |
    | `done` | TriageBrief | the brief passed the section and citation contract; last event |
    | `error` | ErrorEvent | generation failed or the brief broke the contract; last event |

    Concatenating the `token` texts gives exactly what the model wrote.

    Args:
        incident_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | str]
    """

    kwargs = _get_kwargs(
        incident_id=incident_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    incident_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Problem | str | None:
    """Stream the incident's latest triage

     Server-sent events, from the triage's first event: live while the triage worker generates it,
    replayed
    from the stored result once it's finished. Any number of clients can watch the same triage. Each
    event's
    `data` is JSON:

    | event | data | when |
    |---|---|---|
    | `degraded_source` | DegradedSourceEvent | before the first token, once per evidence source left
    out |
    | `token` | TokenEvent | a piece of the brief's markdown, as the model writes it |
    | `citation` | CitationEvent | a complete [Cn] tag has arrived (a tag can be split across tokens) |
    | `section_complete` | SectionCompleteEvent | a section's text is finished |
    | `done` | TriageBrief | the brief passed the section and citation contract; last event |
    | `error` | ErrorEvent | generation failed or the brief broke the contract; last event |

    Concatenating the `token` texts gives exactly what the model wrote.

    Args:
        incident_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | str
    """

    return (
        await asyncio_detailed(
            incident_id=incident_id,
            client=client,
        )
    ).parsed
