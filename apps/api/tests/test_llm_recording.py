"""Recording and replaying model calls (llm.recording): the eval's offline mode depends on an exact replay."""

from types import SimpleNamespace

import pytest

from pagerwise_api import llm

pytestmark = pytest.mark.anyio


class FakeClient:
    """Stands in for ollama.AsyncClient: streams three pieces, then a done chunk with Ollama's counts."""

    calls = 0

    async def chat(self, **request):
        FakeClient.calls += 1

        async def stream():
            for piece in ("## Likely", " cause\n", "Pool [C1]."):
                yield SimpleNamespace(message=SimpleNamespace(content=piece), done=False)
            yield SimpleNamespace(message=SimpleNamespace(content=""), done=True, prompt_eval_count=900,
                                  eval_count=12, total_duration=2_000_000_000, load_duration=0,
                                  prompt_eval_duration=1_500_000_000, eval_duration=500_000_000)

        return stream()


async def collect(messages):
    pieces, result = [], None
    async for item in llm.chat_stream(messages, estimated_prompt_tokens=100):
        if isinstance(item, llm.ChatResult):
            result = item
        else:
            pieces.append(item)
    return pieces, result


async def test_a_recorded_call_replays_identically_without_the_model(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: FakeClient())
    messages = [{"role": "user", "content": "triage this"}]
    with llm.recording(tmp_path, replay=False) as recorder:
        live = await collect(messages)
    live_timing = recorder.timings[0]
    assert FakeClient.calls == 1 and len(list(tmp_path.glob("*.json"))) == 1

    monkeypatch.setattr(llm, "_client", lambda: pytest.fail("replay must not call the model"))
    with llm.recording(tmp_path, replay=True) as recorder:
        replayed = await collect(messages)
    assert replayed == live
    assert recorder.timings == [live_timing]  # the live timings come back, not the instant replay's

    with llm.recording(tmp_path, replay=True), pytest.raises(FileNotFoundError):
        await collect([{"role": "user", "content": "something never recorded"}])
