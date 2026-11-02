"""Slice 5's done-when: replay a seeded incident through the triage worker and check the brief.

Opens an incident like the one the seeded postmortem of 2026-10-25 describes (card-auth memory pressure, shortly
after a redis-cache deploy), starts its triage, streams it, then checks which planted facts
(evals/planted_facts.json) the brief cited and repeated. With --deploys-down the deploy source answers 503 for the
run: the brief must show the source as degraded and make no claims about deploys.

Needs the API, the triage worker, docs_mock and Ollama running.

uv run python scripts/triage_replay.py [--deploys-down]
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

from pagerwise_client import Client
from pagerwise_client.api.default import create_incident, start_triage
from pagerwise_client.models import (
    CitationEvent,
    DegradedSourceEvent,
    ErrorEvent,
    IncidentCreate,
    Severity,
    TokenEvent,
    TriageAccepted,
    TriageBrief,
)
from pagerwise_client_sse import stream_triage

FACTS = json.loads((Path(__file__).resolve().parents[1] / "evals" / "planted_facts.json").read_text())["facts"]

parser = argparse.ArgumentParser()
parser.add_argument("--api", default="http://localhost:8001")
parser.add_argument("--docs", default="http://localhost:8002")
parser.add_argument("--deploys-down", action="store_true")
parser.add_argument("--opened-at", default="2026-10-25T11:05:00Z",
                    help="when the incident opened; the default replays the seeded postmortem's own incident")
args = parser.parse_args()

client = Client(base_url=args.api, raise_on_unexpected_status=True)
httpx.post(f"{args.docs}/_faults", json={"down": ["deploys"]} if args.deploys_down else {}).raise_for_status()
try:
    incident = create_incident.sync(client=client, body=IncidentCreate(
        title="CardAuthMemoryPressure on card-auth", service="card-auth", severity=Severity.SEV1,
        summary="card-auth pods restarting with OOMKilled; card_auth_rss_pct_of_limit above 95% on card-auth-3",
        opened_at=args.opened_at,  # type: ignore[arg-type]  # the generated model takes a datetime or ISO text
    ))
    print(f"== Incident {incident.id}: {incident.title} (opened {incident.opened_at:%Y-%m-%d %H:%M} UTC)"
          f"{'  [deploy source forced down]' if args.deploys_down else ''}")
    accepted = start_triage.sync(incident.id, client=client)
    assert isinstance(accepted, TriageAccepted), accepted
    print(f"   triage {accepted.triage_id} queued; streaming\n")

    started, first_token, text, cited = time.monotonic(), None, "", {}
    brief = None
    for event in stream_triage(client, incident.id):
        match event:
            case DegradedSourceEvent():
                print(f">> degraded_source {event.source.value}: {event.reason}")
            case TokenEvent():
                first_token = first_token or time.monotonic()
                text += event.text
                sys.stdout.write(event.text)
                sys.stdout.flush()
            case CitationEvent():
                cited[event.tag] = event
            case TriageBrief():
                brief = event
            case ErrorEvent():
                print(f"\n>> error {event.code.value}: {event.detail} {event.problems}")
finally:
    httpx.post(f"{args.docs}/_faults", json={}).raise_for_status()

print(f"\n\n== Result")
if brief is None:
    sys.exit(1)
print(f"verdict {brief.verdict.value}, {brief.model}, {brief.prompt_version}; first token after "
      f"{(first_token or started) - started:.1f}s, done after {time.monotonic() - started:.1f}s; "
      f"degraded: {[d.source.value for d in brief.degraded_sources] or 'none'}")
print("citations:")
for tag, c in sorted(cited.items(), key=lambda kv: int(kv[0][1:])):
    print(f"  [{tag}] {c.source_type.value:10} {c.source_id}")

cited_docs = {c.source_id for c in cited.values()}
print("planted facts in cited documents, and whether the brief repeats them:")
hits = 0
for fact in FACTS:
    if fact["doc"] in cited_docs:
        repeated = all(s.lower() in text.lower() for s in fact["must_contain"])
        hits += repeated
        print(f"  [{'x' if repeated else ' '}] {fact['id']}: {fact['answer']}")
deploy_lines = [line.strip() for line in text.splitlines() if re.search(r"\bdeploy", line, re.IGNORECASE)]
deploy_citations = [t for t, c in cited.items() if c.source_type.value == "deploy"]
print(f"lines mentioning a deploy: {len(deploy_lines)}; deploy citations: {deploy_citations or 'none'}")
for line in deploy_lines:
    print(f"  | {line}")
ok = hits > 0 if not args.deploys_down else (not deploy_citations and "deploys" in
                                              [d.source.value for d in brief.degraded_sources])
print(f"\n{'PASS' if ok else 'CHECK'}: " + (f"{hits} planted fact(s) cited and repeated" if not args.deploys_down else
      "deploys marked degraded, no deploy citations (deploy lines above are for a person to judge)"))
