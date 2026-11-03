"""The one way to call the chat model. Model name and options come from settings; prompts from prompts.py.

Evals can record every call and replay it later without Ollama (`recording`): each response is stored under the
hash of its whole request (model, options, messages, output format), with the wall-clock time to its first piece
and to its end, so offline runs reproduce the live run's metrics, latency included.

Every call is a `chat <model>` span with the GenAI semantic-convention attributes (docs/adr/0012); prompt and output
text are never put on it."""

import difflib
import hashlib
import json
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ollama import AsyncClient, ChatResponse
from opentelemetry import metrics, trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from pagerwise_api.settings import settings

tracer = trace.get_tracer("pagerwise.llm")
TOKENS = metrics.get_meter("pagerwise.llm").create_counter(
    "pagerwise.llm.tokens", unit="{token}", description="Model tokens, by type (input, output) and model")
_streaming: ContextVar[Span | None] = ContextVar("pagerwise_chat_span", default=None)


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
    if not _recorder.fill:
        return True
    path = _recorder.path(request)  # with fill, each repeat needs its own recorded run
    return path.exists() and _recorder._calls.get(path.name, 0) < len(json.loads(path.read_text())["runs"])


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
    with tracer.start_as_current_span(f"chat {request['model']}", kind=SpanKind.CLIENT,
                                      attributes=_span_attributes(request)) as span:
        if _replaying(request):
            span.set_attribute("pagerwise.replayed", True)
            _, result, ttft_ms, _ = _replayed(request)
            _finish(span, result, ttft_ms)
            return result
        started = time.monotonic()
        response = await _client().chat(**request)
        result = _result(response, response.message.content or "", request["model"])
        elapsed = int((time.monotonic() - started) * 1000)
        if _recorder is not None:
            _record(request, [result.content], result, elapsed, elapsed)
        _finish(span, result, elapsed)
        return result


async def chat_stream(messages: list[dict[str, str]], estimated_prompt_tokens: int) -> AsyncIterator[str | ChatResult]:
    """Yields text pieces as they arrive, then one ChatResult with the whole text and Ollama's counts (which only
    come on the final chunk)."""
    request = _request(messages, estimated_prompt_tokens)
    # Started, not made current: a generator that attaches a context across its yields would leak it into the
    # caller. annotate_chat finds it through _streaming instead.
    span = tracer.start_span(f"chat {request['model']}", kind=SpanKind.CLIENT, attributes=_span_attributes(request))
    token = _streaming.set(span)
    try:
        if _replaying(request):
            span.set_attribute("pagerwise.replayed", True)
            pieces, result, ttft_ms, _ = _replayed(request)
            for piece in pieces:
                yield piece
            _finish(span, result, ttft_ms)
            yield result
            return
        parts: list[str] = []
        started, first = time.monotonic(), None
        with trace.use_span(span):  # the HTTP request to Ollama becomes a child of the chat span
            stream = aiter(await _client().chat(**request, stream=True))
            head = await anext(stream, None)  # the request is sent on the first iteration, not by chat()
        pending = [head] if head is not None else []
        while (chunk := pending.pop() if pending else await anext(stream, None)) is not None:
            piece = chunk.message.content or ""
            if piece:
                first = first or time.monotonic()
                parts.append(piece)
                yield piece
            if chunk.done:
                result = _result(chunk, "".join(parts), request["model"])
                now = time.monotonic()
                ttft_ms = int(((first or now) - started) * 1000)
                if _recorder is not None:
                    _record(request, parts, result, ttft_ms, int((now - started) * 1000))
                _finish(span, result, ttft_ms)
                yield result
    except Exception as e:
        span.record_exception(e)
        span.set_status(Status(StatusCode.ERROR, type(e).__name__))
        raise
    finally:
        span.end()
        try:
            _streaming.reset(token)
        except ValueError:  # closed from another context (garbage collection): nothing of ours is left in it
            pass


def annotate_chat(**attributes: str | float | bool) -> None:
    """Adds pagerwise.* attributes (citation_count, verdict) to the span of the chat_stream being read. Call it when
    the stream's ChatResult arrives, before the stream is finished."""
    span = _streaming.get()
    if span is not None:
        span.set_attributes({f"pagerwise.{key}": value for key, value in attributes.items()})


def _span_attributes(request: dict[str, Any]) -> dict[str, Any]:
    host = urlsplit(settings.ollama_host)
    return {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": request["model"],
        "gen_ai.request.temperature": request["options"]["temperature"],
        "gen_ai.request.max_tokens": request["options"]["num_predict"],
        "server.address": host.hostname or "",
        "server.port": host.port or 11434,
        "pagerwise.num_ctx": request["options"]["num_ctx"],
    }


def _finish(span: Span, result: ChatResult, ttft_ms: int) -> None:
    span.set_attributes({
        "gen_ai.response.model": result.model,
        "gen_ai.usage.input_tokens": result.prompt_tokens,
        "gen_ai.usage.output_tokens": result.output_tokens,
        "pagerwise.ttft_ms": ttft_ms,
        "pagerwise.tokens_per_second": round(result.output_tokens / (result.eval_ms / 1000), 1) if result.eval_ms else 0.0,
    })
    TOKENS.add(result.prompt_tokens, {"gen_ai.token.type": "input", "gen_ai.request.model": result.model})
    TOKENS.add(result.output_tokens, {"gen_ai.token.type": "output", "gen_ai.request.model": result.model})
