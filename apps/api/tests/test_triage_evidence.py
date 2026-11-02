"""Building the triage query and gathering evidence from its three sources. Offline: the sources are stubbed."""

import asyncio
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from pagerwise_api import prompts, triage
from pagerwise_api.settings import settings

pytestmark = pytest.mark.anyio


def test_query_has_title_service_neighbours_and_alert_summaries():
    query = triage.build_query("LedgerWriteErrors on ledger", "ledger", ["postgres-primary", "payments"],
                               ["write errors 9% on ledger-2", "connection pool waiting=40 on ledger-0"])
    assert query == ("LedgerWriteErrors on ledger. service ledger. related services payments, postgres-primary. "
                     "write errors 9% on ledger-2. connection pool waiting=40 on ledger-0")


def test_query_without_neighbours_or_alerts_is_just_the_incident():
    assert triage.build_query("Disk full on search", "search", [], []) == "Disk full on search. service search"


def item(source_type: str, n: int) -> triage.EvidenceItem:
    return triage.EvidenceItem(source_type, f"{source_type}-{n}", None, f"{source_type} {n}", f"text {n}")


class Incident:  # what gather_evidence reads from the row
    id = uuid.uuid4()
    service = "card-auth"
    opened_at = datetime(2026, 10, 25, 11, 0, tzinfo=UTC)


@pytest.fixture
def sources(monkeypatch):
    """Stubbed sources; each test decides how each one behaves."""
    behaviour: dict[str, object] = {"runbook": [item("runbook", 1)], "postmortem": [item("postmortem", 1)],
                                    "deploys": [item("deploy", 1)]}

    async def act(key: str):  # noqa: ANN202
        value = behaviour[key]
        if isinstance(value, float):  # seconds to hang
            await asyncio.sleep(value)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(triage, "_documents", lambda session, query, source_type, k: act(source_type))
    monkeypatch.setattr(triage, "_deploys", lambda client, services, at: act("deploys"))
    monkeypatch.setattr(settings, "triage_timeout_runbooks_s", 0.2)
    monkeypatch.setattr(settings, "triage_timeout_postmortems_s", 0.2)
    monkeypatch.setattr(settings, "triage_timeout_deploys_s", 0.1)
    return behaviour


async def test_all_sources_answer_in_a_fixed_order(sources):
    gathered = await triage.gather_evidence(None, None, Incident, "q", [])  # type: ignore[arg-type]
    assert [e.source_type for e in gathered.items] == ["runbook", "postmortem", "deploy"]
    assert gathered.degraded == []


async def test_a_slow_source_is_degraded_and_the_others_still_arrive(sources):
    sources["deploys"] = 1.0  # hangs past its 100 ms timeout
    gathered = await triage.gather_evidence(None, None, Incident, "q", [])  # type: ignore[arg-type]
    assert [e.source_type for e in gathered.items] == ["runbook", "postmortem"]
    assert gathered.degraded == [{"source": "deploys", "reason": "timed out after 100 ms"}]
    assert gathered.timings_ms["deploys"] < 500  # gave up at the timeout, didn't wait for it


async def test_a_failing_source_is_degraded_with_its_reason(sources):
    request = httpx.Request("GET", "http://deploys/v1/deploys")
    sources["deploys"] = httpx.HTTPStatusError("down", request=request, response=httpx.Response(503, request=request))
    sources["postmortem"] = RuntimeError("index broken")
    gathered = await triage.gather_evidence(None, None, Incident, "q", [])  # type: ignore[arg-type]
    assert [e.source_type for e in gathered.items] == ["runbook"]
    assert gathered.degraded == [{"source": "deploys", "reason": "HTTP 503"},
                                 {"source": "postmortems", "reason": "RuntimeError"}]


def test_degraded_sources_reach_the_prompt_with_the_rule_against_claims():
    evidence = [prompts.EvidenceChunk("C1", "runbook a.md", "A > Diagnosis", "text")]
    messages = prompts.triage_messages("Title: x", evidence, ["deploys"])
    assert "Unavailable sources (rule 7 applies): deploys" in messages[1]["content"]
    assert "never say there was or wasn't a recent deploy" in messages[0]["content"]
    assert "Unavailable sources" not in prompts.triage_messages("Title: x", evidence, [])[1]["content"]
