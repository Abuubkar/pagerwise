from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.triage_accepted import TriageAccepted
from ...types import Response, Unset


def _get_kwargs(
    incident_id: UUID,
    *,
    x_pagerwise_tenant: str | Unset = "default",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_pagerwise_tenant, Unset):
        headers["X-Pagerwise-Tenant"] = x_pagerwise_tenant

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/incidents/{incident_id}/triage".format(
            incident_id=quote(str(incident_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | TriageAccepted | None:
    if response.status_code == 202:
        response_202 = TriageAccepted.from_dict(response.json())

        return response_202

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if response.status_code == 503:
        response_503 = Problem.from_dict(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | TriageAccepted]:
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
    x_pagerwise_tenant: str | Unset = "default",
) -> Response[Problem | TriageAccepted]:
    """Queue a triage of the incident's current version

     Returns 202 with the run's id; the triage worker generates the brief and `stream_url` streams it.
    While a
    triage of this incident version is queued or running, another request gets 409 `triage_in_progress`
    with
    that run's `triage_id`. A tenant that already has its limit of triages queued or running gets 503
    `triage_capacity` with a `Retry-After` header. Triages also start by themselves when alerts open an
    incident.

    Args:
        incident_id (UUID):
        x_pagerwise_tenant (str | Unset):  Default: 'default'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | TriageAccepted]
    """

    kwargs = _get_kwargs(
        incident_id=incident_id,
        x_pagerwise_tenant=x_pagerwise_tenant,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    incident_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    x_pagerwise_tenant: str | Unset = "default",
) -> Problem | TriageAccepted | None:
    """Queue a triage of the incident's current version

     Returns 202 with the run's id; the triage worker generates the brief and `stream_url` streams it.
    While a
    triage of this incident version is queued or running, another request gets 409 `triage_in_progress`
    with
    that run's `triage_id`. A tenant that already has its limit of triages queued or running gets 503
    `triage_capacity` with a `Retry-After` header. Triages also start by themselves when alerts open an
    incident.

    Args:
        incident_id (UUID):
        x_pagerwise_tenant (str | Unset):  Default: 'default'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | TriageAccepted
    """

    return sync_detailed(
        incident_id=incident_id,
        client=client,
        x_pagerwise_tenant=x_pagerwise_tenant,
    ).parsed


async def asyncio_detailed(
    incident_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    x_pagerwise_tenant: str | Unset = "default",
) -> Response[Problem | TriageAccepted]:
    """Queue a triage of the incident's current version

     Returns 202 with the run's id; the triage worker generates the brief and `stream_url` streams it.
    While a
    triage of this incident version is queued or running, another request gets 409 `triage_in_progress`
    with
    that run's `triage_id`. A tenant that already has its limit of triages queued or running gets 503
    `triage_capacity` with a `Retry-After` header. Triages also start by themselves when alerts open an
    incident.

    Args:
        incident_id (UUID):
        x_pagerwise_tenant (str | Unset):  Default: 'default'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | TriageAccepted]
    """

    kwargs = _get_kwargs(
        incident_id=incident_id,
        x_pagerwise_tenant=x_pagerwise_tenant,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    incident_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    x_pagerwise_tenant: str | Unset = "default",
) -> Problem | TriageAccepted | None:
    """Queue a triage of the incident's current version

     Returns 202 with the run's id; the triage worker generates the brief and `stream_url` streams it.
    While a
    triage of this incident version is queued or running, another request gets 409 `triage_in_progress`
    with
    that run's `triage_id`. A tenant that already has its limit of triages queued or running gets 503
    `triage_capacity` with a `Retry-After` header. Triages also start by themselves when alerts open an
    incident.

    Args:
        incident_id (UUID):
        x_pagerwise_tenant (str | Unset):  Default: 'default'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | TriageAccepted
    """

    return (
        await asyncio_detailed(
            incident_id=incident_id,
            client=client,
            x_pagerwise_tenant=x_pagerwise_tenant,
        )
    ).parsed
