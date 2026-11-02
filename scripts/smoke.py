"""End to end through the generated client: create 3 incidents, page through them 2 at a time, stream one triage,
then read the same incidents over GraphQL. Needs the API running (and Ollama, for the triage).

uv run python scripts/smoke.py [--api http://localhost:8001]
"""

import argparse
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta

from pagerwise_client import Client
from pagerwise_client.api.default import create_incident, list_incidents, start_triage
from pagerwise_client.models import (
    CitationEvent,
    ErrorEvent,
    IncidentCreate,
    IncidentPage,
    SectionCompleteEvent,
    Severity,
    TokenEvent,
    TriageAccepted,
    TriageBrief,
)
from pagerwise_client.types import UNSET
from pagerwise_client_sse import stream_triage

INCIDENTS = [
    ("Card authorizations timing out at 6%", "payments", Severity.SEV2,
     "PaymentsAcquirerTimeouts firing. payments_acquirer_call_seconds p99 is 4 s; ledger call time is normal."),
    ("Payments p99 above 800 ms", "payments", Severity.SEV2,
     "PaymentsP99LatencyHigh for 12 minutes. payments_ledger_call_seconds is most of the increase; "
     "ledgerctl pool stats on a ledger pod shows idle=12 in_use=28 waiting=7."),
    ("Ledger writes failing with SQLSTATE 25006", "ledger", Severity.SEV1,
     "LedgerWriteErrors at 9% since 14:02 UTC: 'cannot execute INSERT in a read-only transaction'. "
     "postgres-primary failed over to postgres-primary-1 at 14:01 UTC."),
]

parser = argparse.ArgumentParser()
parser.add_argument("--api", default="http://localhost:8001")
args = parser.parse_args()
client = Client(base_url=args.api, raise_on_unexpected_status=True)
run = uuid.uuid4().hex[:6]

print(f"== Create 3 incidents (run {run})")
now = datetime.now(UTC)
created = []
for i, (title, service, severity, summary) in enumerate(INCIDENTS):
    body = IncidentCreate(title=f"{title} [smoke {run}]", service=service, severity=severity, summary=summary,
                          opened_at=now - timedelta(seconds=len(INCIDENTS) - i))
    incident = create_incident.sync(client=client, body=body)
    assert incident is not None and not hasattr(incident, "code"), incident
    created.append(incident)
    print(f"  {incident.id}  {incident.severity.value}  {incident.service:9}  {incident.title}")

print("\n== Page through incidents, 2 at a time (newest first)")
wanted, seen, after, page_no = {i.id for i in created}, [], UNSET, 0
while wanted - set(seen) and page_no < 10:
    page = list_incidents.sync(client=client, limit=2, after=after)
    assert isinstance(page, IncidentPage), page
    page_no += 1
    print(f"  page {page_no}: " + " | ".join(f"{i.title}" for i in page.items))
    seen += [i.id for i in page.items]
    if not isinstance(page.next_cursor, str):
        break
    after = page.next_cursor
assert wanted <= set(seen), "didn't see all three incidents"
order = [i for i in seen if i in wanted]
assert order == [i.id for i in reversed(created)], "pages were not newest first"
print(f"  all 3 seen in {page_no} pages, newest first")

target = created[-1]
print(f"\n== Triage {target.title}")
accepted = start_triage.sync(target.id, client=client)
assert isinstance(accepted, TriageAccepted), accepted
again = start_triage.sync(target.id, client=client)
print(f"  202 triage_id={accepted.triage_id}; a second POST -> {again.status} {again.code.value} "
      f"triage_id={again.triage_id}")

print("\n== Stream (tokens inline; other events on their own lines)\n")
counts: dict[str, int] = {}
started, first_token = time.monotonic(), None
for event in stream_triage(client, target.id):
    name = type(event).__name__
    counts[name] = counts.get(name, 0) + 1
    match event:
        case TokenEvent():
            first_token = first_token or time.monotonic()
            sys.stdout.write(event.text)
            sys.stdout.flush()
        case CitationEvent():
            print(f"\n    >> citation {event.tag} in {event.section}: {event.source_id}")
        case SectionCompleteEvent():
            print(f"\n    >> section_complete {event.section.value}")
        case TriageBrief():
            print(f"\n    >> done: verdict={event.verdict.value} model={event.model} prompt={event.prompt_version} "
                  f"usage={event.usage.to_dict()}")
            for key, section in event.sections.to_dict().items():
                print(f"       {key}: {len(section['citations'])} citations "
                      f"({', '.join(c['tag'] for c in section['citations']) or '-'})")
        case ErrorEvent():
            print(f"\n    >> error {event.code.value}: {event.detail} {event.problems}")
elapsed = time.monotonic() - started
print(f"\n  events: {counts}")
print(f"  first token after {first_token - started:.1f}s, stream ended after {elapsed:.1f}s" if first_token else "")

print("\n== GraphQL: the same incidents")
query = """query($first: Int!) { incidents(first: $first) {
  edges { cursor node { id title severity service openedAt version } } pageInfo { hasNextPage endCursor } } }"""
reply = client.get_httpx_client().post("/graphql", json={"query": query, "variables": {"first": 3}}).json()
assert "errors" not in reply, reply
nodes = [e["node"] for e in reply["data"]["incidents"]["edges"]]
for node in nodes:
    print(f"  {node['id']}  {node['severity']}  {node['title']}")
assert [uuid.UUID(n["id"]) for n in nodes] == [i.id for i in reversed(created)], "GraphQL disagrees with REST"
print("  same 3 incidents, same order as REST")
