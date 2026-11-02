"""The one way to call the chat model. Model name and options come from settings; prompts from prompts.py."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from ollama import AsyncClient, ChatResponse

from pagerwise_api.settings import settings


class PromptTooLong(Exception):
    """Raised before sending: Ollama would cut the prompt to fit num_ctx without an error."""


@dataclass
class ChatResult:
    content: str
    model: str
    prompt_tokens: int
    output_tokens: int
    total_ms: int
    load_ms: int
    prompt_eval_ms: int
    eval_ms: int


def _request(messages: list[dict[str, str]], estimated_prompt_tokens: int) -> dict[str, Any]:
    budget = settings.llm_num_ctx - settings.llm_max_output_tokens
    if estimated_prompt_tokens > budget:
        raise PromptTooLong(f"~{estimated_prompt_tokens} prompt tokens, budget {budget} (num_ctx {settings.llm_num_ctx})")
    return {
        "model": settings.llm_model,
        "messages": messages,
        "think": settings.llm_think,
        "keep_alive": settings.llm_keep_alive,
        "options": {
            "temperature": settings.llm_temperature,
            "num_ctx": settings.llm_num_ctx,
            "num_predict": settings.llm_max_output_tokens,
        },
    }


def _client() -> AsyncClient:
    return AsyncClient(host=settings.ollama_host, timeout=settings.llm_timeout_s)


def _result(response: ChatResponse, content: str) -> ChatResult:
    ms = lambda ns: (ns or 0) // 1_000_000  # noqa: E731 - Ollama reports nanoseconds
    return ChatResult(
        content=content,
        model=settings.llm_model,
        prompt_tokens=response.prompt_eval_count or 0,
        output_tokens=response.eval_count or 0,
        total_ms=ms(response.total_duration),
        load_ms=ms(response.load_duration),
        prompt_eval_ms=ms(response.prompt_eval_duration),
        eval_ms=ms(response.eval_duration),
    )


async def chat(messages: list[dict[str, str]], estimated_prompt_tokens: int) -> ChatResult:
    response = await _client().chat(**_request(messages, estimated_prompt_tokens))
    return _result(response, response.message.content or "")


async def chat_stream(messages: list[dict[str, str]], estimated_prompt_tokens: int) -> AsyncIterator[str | ChatResult]:
    """Yields text pieces as they arrive, then one ChatResult with the whole text and Ollama's counts (which only
    come on the final chunk)."""
    request = _request(messages, estimated_prompt_tokens)
    parts: list[str] = []
    async for chunk in await _client().chat(**request, stream=True):
        piece = chunk.message.content or ""
        if piece:
            parts.append(piece)
            yield piece
        if chunk.done:
            yield _result(chunk, "".join(parts))
