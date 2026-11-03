"""The one way to call the chat model. Model name and options come from settings; prompts from prompts.py.

Evals can record every call and replay it later without Ollama (`recording`): each response is stored under the
hash of its whole request (model, options, messages, output format), with the wall-clock time to its first piece
and to its end, so offline runs reproduce the live run's metrics, latency included."""

import difflib
import hashlib
import json
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
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


def _request(messages: list[dict[str, str]], estimated_prompt_tokens: int, model: str | None = None,
             format: dict[str, Any] | None = None) -> dict[str, Any]:
    budget = settings.llm_num_ctx - settings.llm_max_output_tokens
    if estimated_prompt_tokens > budget:
        raise PromptTooLong(f"~{estimated_prompt_tokens} prompt tokens, budget {budget} (num_ctx {settings.llm_num_ctx})")
    request = {
        "model": model or settings.llm_model,
        "messages": messages,
        "think": settings.llm_think if model is None else False,
        "keep_alive": settings.llm_keep_alive,
        "options": {
            "temperature": settings.llm_temperature,
            "num_ctx": settings.llm_num_ctx,
            "num_predict": settings.llm_max_output_tokens,
        },
    }
    if format is not None:
        request["format"] = format  # a JSON schema: Ollama constrains the output to it
    return request


@dataclass
class Recorder:
    """Where calls are recorded to or replayed from. `timings` collects (ttft_ms, total_ms) per call, in order, for
    the eval's latency metrics: measured live, or read back from the recording."""

    folder: Path
    replay: bool
    fill: bool = False  # with replay: a call that wasn't recorded goes to the model and is recorded
    timings: list[tuple[int, int]] = field(default_factory=list)
    _calls: dict[str, int] = field(default_factory=dict)  # key -> how many times seen this run (repeats)

    def path(self, request: dict[str, Any]) -> Path:
        key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()[:24]
        return self.folder / f"{key}.json"


_recorder: Recorder | None = None


@contextmanager
def recording(folder: Path, replay: bool, fill: bool = False) -> Iterator[Recorder]:
    """Record every model call made inside the block into `folder` (replay=False), or answer them from it
    (replay=True; a call that wasn't recorded raises, or with fill=True is made and recorded). A request made several
    times keeps one recording per repeat."""
    global _recorder
    folder.mkdir(parents=True, exist_ok=True)
    _recorder = Recorder(folder, replay, fill)
    try:
        yield _recorder
    finally:
        _recorder = None


def _replaying(request: dict[str, Any]) -> bool:
    """Whether this call is answered from the recording (False: it goes to the model, and is recorded)."""
    if _recorder is None or not _recorder.replay:
        return False
    return not _recorder.fill or _recorder.path(request).exists()


def _replayed(request: dict[str, Any]) -> tuple[list[str], ChatResult, int, int]:
    assert _recorder is not None
    path = _recorder.path(request)
    if not path.exists():
        raise FileNotFoundError(f"no recording for this request ({path.name}); run the eval with LIVE=1 first\n"
                                + _nearest_recording_diff(request))
    runs = json.loads(path.read_text())["runs"]
    i = _recorder._calls.get(path.name, 0)
    _recorder._calls[path.name] = i + 1
    run = runs[min(i, len(runs) - 1)]
    _recorder.timings.append((run["ttft_ms"], run["total_ms"]))
    return run["pieces"], ChatResult(**run["result"]), run["ttft_ms"], run["total_ms"]


def _nearest_recording_diff(request: dict[str, Any]) -> str:
    """Why a replay missed: the request's last message against the most similar recorded one."""
    assert _recorder is not None
    wanted = request["messages"][-1]["content"]
    recorded = [json.loads(p.read_text())["request"] for p in _recorder.folder.glob("*.json")]
    candidates = [r["messages"][-1]["content"] for r in recorded if r["messages"][:-1] == request["messages"][:-1]]
    if not candidates:
        return "no recording has the same earlier messages (system prompt)"
    def similarity(c: str, quick: bool) -> float:
        matcher = difflib.SequenceMatcher(None, c.splitlines(), wanted.splitlines(), autojunk=False)
        return matcher.quick_ratio() if quick else matcher.ratio()
    shortlist = sorted(candidates, key=lambda c: similarity(c, quick=True))[-5:]
    nearest = max(shortlist, key=lambda c: similarity(c, quick=False))
    diff = difflib.unified_diff(nearest.splitlines(), wanted.splitlines(), "recorded", "requested", lineterm="", n=1)
    return "\n".join(list(diff)[:80])


def _record(request: dict[str, Any], pieces: list[str], result: ChatResult, ttft_ms: int, total_ms: int) -> None:
    assert _recorder is not None
    path = _recorder.path(request)
    i = _recorder._calls.get(path.name, 0)
    _recorder._calls[path.name] = i + 1
    runs = json.loads(path.read_text())["runs"] if path.exists() else []
    run = {"pieces": pieces, "result": asdict(result), "ttft_ms": ttft_ms, "total_ms": total_ms}
    runs = runs[:i] + [run] + runs[i + 1 :]  # this run's i-th repeat replaces an older one
    path.write_text(json.dumps({"request": request, "runs": runs}, indent=1) + "\n")
    _recorder.timings.append((ttft_ms, total_ms))


def _client() -> AsyncClient:
    return AsyncClient(host=settings.ollama_host, timeout=settings.llm_timeout_s)


def _result(response: ChatResponse, content: str, model: str) -> ChatResult:
    ms = lambda ns: (ns or 0) // 1_000_000
    return ChatResult(
        content=content,
        model=model,
        prompt_tokens=response.prompt_eval_count or 0,
        output_tokens=response.eval_count or 0,
        total_ms=ms(response.total_duration),
        load_ms=ms(response.load_duration),
        prompt_eval_ms=ms(response.prompt_eval_duration),
        eval_ms=ms(response.eval_duration),
    )


async def chat(messages: list[dict[str, str]], estimated_prompt_tokens: int, model: str | None = None,
               format: dict[str, Any] | None = None) -> ChatResult:
    """One whole response. `model` overrides settings.llm_model (the eval's judge); `format` is a JSON schema the
    output must follow (structured output)."""
    request = _request(messages, estimated_prompt_tokens, model, format)
    if _replaying(request):
        return _replayed(request)[1]
    started = time.monotonic()
    response = await _client().chat(**request)
    result = _result(response, response.message.content or "", request["model"])
    if _recorder is not None:
        elapsed = int((time.monotonic() - started) * 1000)
        _record(request, [result.content], result, elapsed, elapsed)
    return result


async def chat_stream(messages: list[dict[str, str]], estimated_prompt_tokens: int) -> AsyncIterator[str | ChatResult]:
    """Yields text pieces as they arrive, then one ChatResult with the whole text and Ollama's counts (which only
    come on the final chunk)."""
    request = _request(messages, estimated_prompt_tokens)
    if _replaying(request):
        pieces, result, _, _ = _replayed(request)
        for piece in pieces:
            yield piece
        yield result
        return
    parts: list[str] = []
    started, first = time.monotonic(), None
    async for chunk in await _client().chat(**request, stream=True):
        piece = chunk.message.content or ""
        if piece:
            first = first or time.monotonic()
            parts.append(piece)
            yield piece
        if chunk.done:
            result = _result(chunk, "".join(parts), request["model"])
            if _recorder is not None:
                now = time.monotonic()
                _record(request, parts, result, int(((first or now) - started) * 1000), int((now - started) * 1000))
            yield result
