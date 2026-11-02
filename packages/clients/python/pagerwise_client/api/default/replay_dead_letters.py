from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.dlq_replay_accepted import DlqReplayAccepted
from ...models.dlq_replay_request import DlqReplayRequest
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    *,
    body: DlqReplayRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/admin/dlq/replay",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DlqReplayAccepted | Problem | None:
    if response.status_code == 202:
        response_202 = DlqReplayAccepted.from_dict(response.json())

        return response_202

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if response.status_code == 503:
        response_503 = Problem.from_dict(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[DlqReplayAccepted | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: DlqReplayRequest,
) -> Response[DlqReplayAccepted | Problem]:
    """Republish dead letters to alerts.v1

     Picks dead letters either by DLQ offset range (inclusive) or by message key (the service name), and
    republishes each stored payload to `alerts.v1` with an `x-replayed-from` header holding its DLQ
    offset.
    The consumer then processes them as new messages, so replay after fixing whatever sent them to the
    DLQ: a
    payload that is still malformed is dead-lettered again. Returns once Kafka has acknowledged every
    message, before the consumer has processed them. No authentication yet.

    Args:
        body (DlqReplayRequest): Either `from_offset` and `to_offset`, or `keys`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DlqReplayAccepted | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: DlqReplayRequest,
) -> DlqReplayAccepted | Problem | None:
    """Republish dead letters to alerts.v1

     Picks dead letters either by DLQ offset range (inclusive) or by message key (the service name), and
    republishes each stored payload to `alerts.v1` with an `x-replayed-from` header holding its DLQ
    offset.
    The consumer then processes them as new messages, so replay after fixing whatever sent them to the
    DLQ: a
    payload that is still malformed is dead-lettered again. Returns once Kafka has acknowledged every
    message, before the consumer has processed them. No authentication yet.

    Args:
        body (DlqReplayRequest): Either `from_offset` and `to_offset`, or `keys`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DlqReplayAccepted | Problem
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: DlqReplayRequest,
) -> Response[DlqReplayAccepted | Problem]:
    """Republish dead letters to alerts.v1

     Picks dead letters either by DLQ offset range (inclusive) or by message key (the service name), and
    republishes each stored payload to `alerts.v1` with an `x-replayed-from` header holding its DLQ
    offset.
    The consumer then processes them as new messages, so replay after fixing whatever sent them to the
    DLQ: a
    payload that is still malformed is dead-lettered again. Returns once Kafka has acknowledged every
    message, before the consumer has processed them. No authentication yet.

    Args:
        body (DlqReplayRequest): Either `from_offset` and `to_offset`, or `keys`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DlqReplayAccepted | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: DlqReplayRequest,
) -> DlqReplayAccepted | Problem | None:
    """Republish dead letters to alerts.v1

     Picks dead letters either by DLQ offset range (inclusive) or by message key (the service name), and
    republishes each stored payload to `alerts.v1` with an `x-replayed-from` header holding its DLQ
    offset.
    The consumer then processes them as new messages, so replay after fixing whatever sent them to the
    DLQ: a
    payload that is still malformed is dead-lettered again. Returns once Kafka has acknowledged every
    message, before the consumer has processed them. No authentication yet.

    Args:
        body (DlqReplayRequest): Either `from_offset` and `to_offset`, or `keys`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DlqReplayAccepted | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
