"""A triage end to end without a live model: the worker claims a queued run, "generates" it from a recorded Ollama
response, and streams it through Redis to SSE readers, one watching live and one arriving after it finished."""

import asyncio
import json
from pathlib import Path

import pytest

from pagerwise_api import bus, llm, triage, worker

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

RECORDING = json.loads((Path(__file__).parent / "fixtures" / "triage_recording.json").read_text())


async def read_stream(client, incident_id: str) -> list[tuple[str, dict]]:
    events, name = [], None
    async with client.stream("GET", f"/v1/incidents/{incident_id}/triage/stream") as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((name, json.loads(line.removeprefix("data: "))))
                if name in ("done", "error"):
                    break
    return events


@pytest.fixture
def recorded(monkeypatch):
    """Evidence and model output from a real triage run (fixtures/triage_recording.json), with the deploy source
    marked down. The model's text is replayed in 5-character pieces: only the final text was stored, not Ollama's
    original chunks, so this also exercises tags and headings split across pieces."""
    items = [triage.EvidenceItem(e["source_type"], e["source_id"], e["chunk_id"], e["heading_path"], e["text"])
             for e in RECORDING["evidence"]]

    async def gather(session, client, incident, query, neighbours):
        return triage.Gathered(items=items, degraded=[{"source": "deploys", "reason": "HTTP 503"}])

    async def chat_stream(messages, estimated_prompt_tokens):
        text = RECORDING["raw_text"]
        for i in range(0, len(text), 5):
            await asyncio.sleep(0.002)
            yield text[i : i + 5]
        yield llm.ChatResult(content=text, model="recorded", prompt_tokens=3200, output_tokens=300, total_ms=1,
                             load_ms=0, prompt_eval_ms=0, eval_ms=0)

    async def no_context(session, incident):
        return [], []

    monkeypatch.setattr(triage, "gather_evidence", gather)
    monkeypatch.setattr(triage, "incident_context", no_context)
    monkeypatch.setattr(llm, "chat_stream", chat_stream)


async def test_worker_streams_events_in_order_to_live_and_late_readers(client, recorded):
    incident = (await client.post("/v1/incidents", json={"title": "Ledger writes failing with SQLSTATE 25006",
                                                         "service": "ledger", "severity": "sev1"})).json()
    accepted = await client.post(f"/v1/incidents/{incident['id']}/triage")
    assert accepted.status_code == 202

    live = asyncio.create_task(read_stream(client, incident["id"]))  # opens before the worker has started
    await asyncio.sleep(0.2)
    redis = bus.connect(client.redis_url)
    claimed = await worker.claim_next(client.sessions)
    assert claimed is not None and str(claimed.id) == accepted.json()["triage_id"]
    await worker.run_one(client.sessions, redis, None, claimed)  # type: ignore[arg-type]  # no deploy client needed
    live_events = await asyncio.wait_for(live, timeout=10)
    late_events = await read_stream(client, incident["id"])  # after it finished: from the Redis stream
    await redis.delete(f"triage:{claimed.id}:events")  # as if an hour had passed and the stream expired
    stored_events = await read_stream(client, incident["id"])  # from Postgres
    await redis.aclose()

    names = [name for name, _ in live_events]
    assert names[0] == "degraded_source" and live_events[0][1] == {"source": "deploys", "reason": "HTTP 503"}
    assert names[-1] == "done"
    # The decision line is the gate's, not the reader's: tokens are the model's text without it.
    shown = RECORDING["raw_text"].replace("Match: [C1]\n", "", 1)
    assert "".join(data["text"] for name, data in live_events if name == "token") == shown
    # Each section completes after its citations and before the next section's, in the contract's order.
    sections = [data["section"] for name, data in live_events if name == "section_complete"]
    assert sections == ["likely_cause", "blast_radius", "first_steps", "similar_incidents"]
    for i, (name, data) in enumerate(live_events):
        if name == "citation":
            done_at = names.index("section_complete", i)
            assert live_events[done_at][1]["section"] == data["section"]
    first_token, first_citation = names.index("token"), names.index("citation")
    assert first_token < first_citation  # a citation follows the text it closes
    brief = live_events[-1][1]
    assert brief["verdict"] == "CAUSE_IDENTIFIED"
    assert brief["degraded_sources"] == [{"source": "deploys", "reason": "HTTP 503"}]

    assert late_events == live_events  # a reader who came late gets every event, the same
    assert next(n for n, _ in stored_events) == "degraded_source" and stored_events[-1] == live_events[-1]
