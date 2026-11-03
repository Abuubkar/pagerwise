"""Builds the golden set (evals/golden/) from the seeded corpus. Deterministic: same --seed, same files.

  answerable    40 incidents, each a (service, failure mode) the corpus has a runbook for. Gold cause: the mode
                and the component; gold evidence: that runbook's chunks (doc path + chunk ordinal, resolved to chunk
                ids at eval time, since ids change on re-import).
  unanswerable  15 incidents with failure modes no document covers (DNS, provider rate limits, ...). The brief
                should abstain (INSUFFICIENT_EVIDENCE).
  degraded      10 incidents caused by a deploy, with that deploy in evals/golden/deploys.json; the eval forces
                the deploy source down and checks the brief makes no deploy claims.

Every incident has a replayable alert sequence (several instances of the rule, over a few minutes; in about 40% of
the answerable and deploy cases also a neighbouring service's own alerts, as callers of a failing dependency page
too) and they all fall in one six-hour window, overlapping, so clustering has to tell them apart and group across
services. Alerts carry the incident id: the
gold grouping. Each case gets a split from the hash of its id (dev/test: 25/15, 10/5, 6/4); test runs only with
`make eval-test`.

uv run python evals/build_golden.py [--seed 11]
"""

import argparse
import hashlib
import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import seed  # the corpus generator: its failure modes and alert names are the golden set's vocabulary
from pagerwise_api.chunking import chunk_markdown, parse_document
from pagerwise_api.embedding import count_tokens
from pagerwise_simulator import fingerprint, load_graph

GOLDEN = ROOT / "evals" / "golden"
WINDOW_START = datetime(2026, 10, 28, 6, 0, tzinfo=UTC)  # inside the seeded deploy log's 30 days
WINDOW_S = 6 * 3600
SPLITS = {"answerable": (40, 25), "unanswerable": (15, 10), "degraded": (10, 6)}  # total, dev

# Failure modes no document describes: (category, alert suffix, summary template).
UNKNOWN_MODES = [
    ("dns-resolution", "DnsResolutionFailures", "DNS lookups failing with SERVFAIL for {pct}% of calls on {instance}"),
    ("provider-rate-limit", "ProviderRateLimited", "external provider returned HTTP 429 for {pct}% of calls on {instance}"),
    ("license-expired", "LicenseCheckFailing", "commercial license validation failing on {instance}"),
    ("kernel-soft-lockup", "KernelSoftLockup", "kernel soft lockup on CPU {n} on {instance}"),
    ("ipv6-route-flap", "RouteFlapping", "IPv6 default route withdrawn {n} times in 5 minutes on {instance}"),
]
# Alert summaries for the corpus's modes: the metric the runbook names, at a value past its alert threshold.
UNIT_VALUE = {"high-latency": (900, 4000), "error-rate": (6, 40), "connection-pool": (300, 1500),
              "memory-pressure": (95, 99), "cpu-saturation": (93, 99), "disk-full": (93, 99),
              "dependency-timeout": (8, 30), "bad-deploy": (5, 25), "cert-expiry": (1, 3),
              "queue-backlog": (90000, 400000)}


def split_of(case_id: str, ranked: list[str], dev_count: int) -> str:
    return "dev" if ranked.index(case_id) < dev_count else "test"


def alerts_for(rng: random.Random, service: str, alertname: str, severity: str, summary: str,
               instances: int, span_s: int, values: tuple[int, int] = (5, 60)) -> list[dict]:
    names = rng.sample([f"{service}-{i}" for i in range(6)], instances)
    out = []
    for i in range(rng.randint(instances * 2, instances * 5)):
        instance = names[i % instances]
        out.append({"offset_s": round(rng.uniform(0, span_s), 1), "service": service, "alertname": alertname,
                    "instance": instance, "fingerprint": fingerprint(service, alertname, instance),
                    "severity": severity,
                    "summary": summary.format(instance=instance, pct=rng.randint(5, 60), n=rng.randint(2, 30),
                                              value=rng.randint(*values))})
    return sorted(out, key=lambda a: a["offset_s"])


def cascade(rng: random.Random, graph, service: str, span_s: int) -> list[dict]:
    """A neighbour's own alerts during the incident: a caller (or, failing that, a dependency) of the failing
    service fires its usual rule a little later, as callers of a broken dependency do. Same gold incident."""
    callers = sorted(s.name for s in graph.values() if service in s.depends_on)
    neighbour = rng.choice(callers or graph[service].depends_on or [service])
    alertname, severity, template = graph[neighbour].rules[0]
    alerts = alerts_for(rng, neighbour, alertname, severity, template.replace("{ms}", "{value}"), rng.randint(1, 2),
                        max(60, span_s), (900, 3000))
    for alert in alerts:
        alert["offset_s"] = round(alert["offset_s"] + rng.uniform(20, 90), 1)
        alert["cascade"] = True
    return alerts


def gold_chunks(doc: str) -> list[dict]:
    """The runbook's chunks as the importer makes them, as (doc, ordinal): stable across re-imports of the same
    text, unlike chunk ids. Heading paths aren't unique (merged sections share their common prefix)."""
    parsed = parse_document((ROOT / doc).read_text())
    return [{"doc": doc, "ordinal": i, "heading_path": c.heading_path}
            for i, c in enumerate(chunk_markdown(parsed.body, count_tokens))]


def build(seed_value: int) -> None:
    rng = random.Random(seed_value)
    graph = load_graph()
    modes = {m.slug: m for m in seed.MODES}
    cases: list[dict] = []

    pairs = rng.sample([(s, m) for s in graph for m in modes if m != "bad-deploy"], SPLITS["answerable"][0])
    for i, (service, slug) in enumerate(pairs, start=1):
        mode = modes[slug]
        alertname = seed.alert_name(service, mode)
        metric = f"{seed.snake(service)}_{mode.metric}"
        value_range = UNIT_VALUE[slug]
        component = (graph[service].depends_on or [service])[0] if slug == "dependency-timeout" else service
        severity = "critical" if slug in ("error-rate", "connection-pool", "memory-pressure", "disk-full") else "warning"
        summary = metric + " at {value} on {instance}"
        cases.append({
            "id": f"ans-{i:02}", "kind": "answerable", "service": service,
            "title": f"{alertname} on {service}", "category": slug,
            "alerts": alerts_for(rng, service, alertname, severity, summary, rng.randint(2, 4), rng.randint(60, 360),
                                 value_range),
            "gold_cause": {"category": slug, "component": component},
            "gold_evidence": gold_chunks(f"data/corpus/runbooks/{service}-{slug}.md"),
        })

    services = list(graph)
    for i in range(SPLITS["unanswerable"][0]):
        category, suffix, template = UNKNOWN_MODES[i % len(UNKNOWN_MODES)]
        service = rng.choice(services)
        alertname = "".join(p.capitalize() for p in service.split("-")) + suffix
        cases.append({
            "id": f"una-{i + 1:02}", "kind": "unanswerable", "service": service,
            "title": f"{alertname} on {service}", "category": category,
            "alerts": alerts_for(rng, service, alertname, "critical", template, rng.randint(2, 4), rng.randint(60, 300)),
            "gold_cause": {"category": category, "component": service},
            "gold_evidence": [],
        })

    deploys = []
    mode = modes["bad-deploy"]
    for i, service in enumerate(rng.sample(services, SPLITS["degraded"][0]), start=1):
        alertname = seed.alert_name(service, mode)
        summary = f"{seed.snake(service)}_{mode.metric} at " + "{pct}% on {instance}"
        version = f"{rng.randint(1, 9)}.{rng.randint(0, 40)}.{rng.randint(1, 30)}"
        deploys.append({"id": f"gdep-{i:02}", "service": service, "version": version,
                        "commit_sha": hashlib.sha1(f"golden-{service}-{version}".encode()).hexdigest(),
                        "author": "release-bot", "summary": f"Release {version}", "status": "succeeded"})  # nothing may give the cause away
        cases.append({
            "id": f"deg-{i:02}", "kind": "degraded", "service": service,
            "title": f"{alertname} on {service}", "category": "bad-deploy",
            "alerts": alerts_for(rng, service, alertname, "critical", summary, rng.randint(2, 4), rng.randint(60, 240)),
            "gold_cause": {"category": "bad-deploy", "component": service},
            "gold_evidence": gold_chunks(f"data/corpus/runbooks/{service}-bad-deploy.md"),
            "deploy": deploys[-1],
        })

    # About 40% of the answerable and deploy-caused incidents also page a neighbouring service.
    for case in cases:
        if case["kind"] != "unanswerable" and rng.random() < 0.4:
            span = int(max(a["offset_s"] for a in case["alerts"]))
            case["alerts"] = sorted(case["alerts"] + cascade(rng, graph, case["service"], span),
                                    key=lambda a: a["offset_s"])

    # One overlapping six-hour window: start times at random, so incidents in neighbouring services coincide.
    for case in cases:
        start = WINDOW_START + timedelta(seconds=rng.uniform(0, WINDOW_S - 600))
        case["opened_at"] = start.isoformat()
        case["severity"] = "sev1" if case["alerts"][0]["severity"] == "critical" else "sev3"
        case["summary"] = case["alerts"][0]["summary"]
        if "deploy" in case:
            case["deploy"]["deployed_at"] = (start - timedelta(minutes=rng.randint(8, 40))).isoformat()

    for kind, (_, dev_count) in SPLITS.items():
        ids = [c["id"] for c in cases if c["kind"] == kind]
        ranked = sorted(ids, key=lambda i: hashlib.sha256(i.encode()).hexdigest())
        for case in cases:
            if case["kind"] == kind:
                case["split"] = split_of(case["id"], ranked, dev_count)

    GOLDEN.mkdir(parents=True, exist_ok=True)
    for kind in SPLITS:
        selected = [c for c in cases if c["kind"] == kind]
        (GOLDEN / f"{kind}.json").write_text(json.dumps({"seed": seed_value, "cases": selected}, indent=1) + "\n")
    (GOLDEN / "deploys.json").write_text(json.dumps({"seed": seed_value, "deploys": deploys}, indent=1) + "\n")
    counts = {k: (sum(c["kind"] == k and c["split"] == "dev" for c in cases),
                  sum(c["kind"] == k and c["split"] == "test" for c in cases)) for k in SPLITS}
    alerts = sum(len(c["alerts"]) for c in cases)
    print(f"wrote {len(cases)} cases ({alerts} alerts) to {GOLDEN.relative_to(ROOT)}; dev/test: {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=11)
    build(parser.parse_args().seed)
