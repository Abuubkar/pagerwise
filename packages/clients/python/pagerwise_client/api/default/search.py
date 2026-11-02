from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.search_response import SearchResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    q: str,
    k: int | Unset = 8,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["q"] = q

    params["k"] = k

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/search",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | SearchResponse | None:
    if response.status_code == 200:
        response_200 = SearchResponse.from_dict(response.json())

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
) -> Response[Problem | SearchResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    q: str,
    k: int | Unset = 8,
) -> Response[Problem | SearchResponse]:
    """Hybrid search over runbooks and postmortems, with every stage's rank

     The retrieval that `ask` and triage use, exposed for debugging and evals. Full-text search and
    vector
    search each return their top 40 chunks; Reciprocal Rank Fusion (k=60) merges them; a cross-encoder
    reranker rescores the fused 40 and the top `k` are returned. Each result carries its rank and score
    at
    every stage (null where a chunk wasn't in that stage's top 40), and the response has per-stage
    timings.

    Args:
        q (str):
        k (int | Unset):  Default: 8.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | SearchResponse]
    """

    kwargs = _get_kwargs(
        q=q,
        k=k,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    q: str,
    k: int | Unset = 8,
) -> Problem | SearchResponse | None:
    """Hybrid search over runbooks and postmortems, with every stage's rank

     The retrieval that `ask` and triage use, exposed for debugging and evals. Full-text search and
    vector
    search each return their top 40 chunks; Reciprocal Rank Fusion (k=60) merges them; a cross-encoder
    reranker rescores the fused 40 and the top `k` are returned. Each result carries its rank and score
    at
    every stage (null where a chunk wasn't in that stage's top 40), and the response has per-stage
    timings.

    Args:
        q (str):
        k (int | Unset):  Default: 8.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | SearchResponse
    """

    return sync_detailed(
        client=client,
        q=q,
        k=k,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    q: str,
    k: int | Unset = 8,
) -> Response[Problem | SearchResponse]:
    """Hybrid search over runbooks and postmortems, with every stage's rank

     The retrieval that `ask` and triage use, exposed for debugging and evals. Full-text search and
    vector
    search each return their top 40 chunks; Reciprocal Rank Fusion (k=60) merges them; a cross-encoder
    reranker rescores the fused 40 and the top `k` are returned. Each result carries its rank and score
    at
    every stage (null where a chunk wasn't in that stage's top 40), and the response has per-stage
    timings.

    Args:
        q (str):
        k (int | Unset):  Default: 8.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | SearchResponse]
    """

    kwargs = _get_kwargs(
        q=q,
        k=k,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    q: str,
    k: int | Unset = 8,
) -> Problem | SearchResponse | None:
    """Hybrid search over runbooks and postmortems, with every stage's rank

     The retrieval that `ask` and triage use, exposed for debugging and evals. Full-text search and
    vector
    search each return their top 40 chunks; Reciprocal Rank Fusion (k=60) merges them; a cross-encoder
    reranker rescores the fused 40 and the top `k` are returned. Each result carries its rank and score
    at
    every stage (null where a chunk wasn't in that stage's top 40), and the response has per-stage
    timings.

    Args:
        q (str):
        k (int | Unset):  Default: 8.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | SearchResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            q=q,
            k=k,
        )
    ).parsed
