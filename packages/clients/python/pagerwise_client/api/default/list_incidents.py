from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.incident_page import IncidentPage
from ...models.incident_status import IncidentStatus
from ...models.problem import Problem
from ...models.severity import Severity
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 25,
    after: None | str | Unset = UNSET,
    status: IncidentStatus | None | Unset = UNSET,
    service: None | str | Unset = UNSET,
    severity: None | Severity | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limit"] = limit

    json_after: None | str | Unset
    if isinstance(after, Unset):
        json_after = UNSET
    else:
        json_after = after
    params["after"] = json_after

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    elif isinstance(status, IncidentStatus):
        json_status = status.value
    else:
        json_status = status
    params["status"] = json_status

    json_service: None | str | Unset
    if isinstance(service, Unset):
        json_service = UNSET
    else:
        json_service = service
    params["service"] = json_service

    json_severity: None | str | Unset
    if isinstance(severity, Unset):
        json_severity = UNSET
    elif isinstance(severity, Severity):
        json_severity = severity.value
    else:
        json_severity = severity
    params["severity"] = json_severity

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/incidents",
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> IncidentPage | Problem | None:
    if response.status_code == 200:
        response_200 = IncidentPage.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[IncidentPage | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 25,
    after: None | str | Unset = UNSET,
    status: IncidentStatus | None | Unset = UNSET,
    service: None | str | Unset = UNSET,
    severity: None | Severity | Unset = UNSET,
) -> Response[IncidentPage | Problem]:
    """List incidents, newest first

     Keyset pagination on (opened_at DESC, id DESC). `next_cursor` is opaque and signed, and only valid
    with
    the same filters it was issued for; anything else is a 400 `invalid_cursor`.

    Args:
        limit (int | Unset):  Default: 25.
        after (None | str | Unset):
        status (IncidentStatus | None | Unset):
        service (None | str | Unset):
        severity (None | Severity | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[IncidentPage | Problem]
    """

    kwargs = _get_kwargs(
        limit=limit,
        after=after,
        status=status,
        service=service,
        severity=severity,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 25,
    after: None | str | Unset = UNSET,
    status: IncidentStatus | None | Unset = UNSET,
    service: None | str | Unset = UNSET,
    severity: None | Severity | Unset = UNSET,
) -> IncidentPage | Problem | None:
    """List incidents, newest first

     Keyset pagination on (opened_at DESC, id DESC). `next_cursor` is opaque and signed, and only valid
    with
    the same filters it was issued for; anything else is a 400 `invalid_cursor`.

    Args:
        limit (int | Unset):  Default: 25.
        after (None | str | Unset):
        status (IncidentStatus | None | Unset):
        service (None | str | Unset):
        severity (None | Severity | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        IncidentPage | Problem
    """

    return sync_detailed(
        client=client,
        limit=limit,
        after=after,
        status=status,
        service=service,
        severity=severity,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 25,
    after: None | str | Unset = UNSET,
    status: IncidentStatus | None | Unset = UNSET,
    service: None | str | Unset = UNSET,
    severity: None | Severity | Unset = UNSET,
) -> Response[IncidentPage | Problem]:
    """List incidents, newest first

     Keyset pagination on (opened_at DESC, id DESC). `next_cursor` is opaque and signed, and only valid
    with
    the same filters it was issued for; anything else is a 400 `invalid_cursor`.

    Args:
        limit (int | Unset):  Default: 25.
        after (None | str | Unset):
        status (IncidentStatus | None | Unset):
        service (None | str | Unset):
        severity (None | Severity | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[IncidentPage | Problem]
    """

    kwargs = _get_kwargs(
        limit=limit,
        after=after,
        status=status,
        service=service,
        severity=severity,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 25,
    after: None | str | Unset = UNSET,
    status: IncidentStatus | None | Unset = UNSET,
    service: None | str | Unset = UNSET,
    severity: None | Severity | Unset = UNSET,
) -> IncidentPage | Problem | None:
    """List incidents, newest first

     Keyset pagination on (opened_at DESC, id DESC). `next_cursor` is opaque and signed, and only valid
    with
    the same filters it was issued for; anything else is a 400 `invalid_cursor`.

    Args:
        limit (int | Unset):  Default: 25.
        after (None | str | Unset):
        status (IncidentStatus | None | Unset):
        service (None | str | Unset):
        severity (None | Severity | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        IncidentPage | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            after=after,
            status=status,
            service=service,
            severity=severity,
        )
    ).parsed
