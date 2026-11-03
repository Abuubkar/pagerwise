"""Prints traces from Jaeger (its v3 query API): slice 8's done-when check.

  uv run python scripts/trace.py retry     # one alert that was retried: every hop, then the batch that stored it
  uv run python scripts/trace.py triage    # the latest triage's span tree with per-stage durations [--id RUN_ID]

Traces are tail-sampled (observability/collector.yaml) and reach Jaeger about a minute after their first span."""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

JAEGER = "http://localhost:16686/api/v3"


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: str
    name: str
    service: str
    start_ns: int
    end_ns: int
    attrs: dict[str, Any]
    status: str  # OTLP status code: "2" is ERROR
    links: list[tuple[str, str, dict[str, Any]]]  # (trace id, span id, attributes)
    children: list["Span"] = field(default_factory=list)

    @property
    def ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1e6


def _value(v: dict[str, Any]) -> Any:
    for kind in ("stringValue", "boolValue", "doubleValue"):
        if kind in v:
            return v[kind]
    if "intValue" in v:
        return int(v["intValue"])
    return v


def _attrs(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {a["key"]: _value(a["value"]) for a in items or []}


def _get(path: str, **query: str) -> dict[str, Any]:
    url = f"{JAEGER}/{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
    try:
        return json.load(urllib.request.urlopen(url, timeout=10))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise


def _spans(payload: dict[str, Any]) -> list[Span]:
    out = []
    for resource in payload.get("result", {}).get("resourceSpans", []):
        service = _attrs(resource["resource"].get("attributes")).get("service.name", "?")
        for scope in resource.get("scopeSpans", []):
            for s in scope.get("spans", []):
                out.append(Span(
                    s["traceId"], s["spanId"], s.get("parentSpanId", ""), s["name"], service,
                    int(s["startTimeUnixNano"]), int(s["endTimeUnixNano"]), _attrs(s.get("attributes")),
                    str(s.get("status", {}).get("code", "")),
                    [(link["traceId"], link["spanId"], _attrs(link.get("attributes"))) for link in s.get("links", [])],
                ))
    return out


def find_traces(service: str, operation: str, lookback_s: int, limit: int = 20) -> dict[str, list[Span]]:
    now = time.time()
    fmt = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
    spans = _spans(_get("traces", **{
        "query.service_name": service, "query.operation_name": operation, "query.search_depth": str(limit),
        "query.start_time_min": fmt(now - lookback_s), "query.start_time_max": fmt(now + 60),
    }))
    traces: dict[str, list[Span]] = {}
    for s in spans:
        traces.setdefault(s.trace_id, []).append(s)
    return traces


def get_trace(trace_id: str) -> list[Span]:
    return _spans(_get(f"traces/{trace_id}"))


def short(service: str) -> str:
    return service.removeprefix("pagerwise-")


def retry(lookback_s: int) -> int:
    """A trace whose alert failed on alerts.v1 and was stored on alerts.retry.30s, printed hop by hop."""
    for trace_id, spans in find_traces("pagerwise-consumer", "alerts.retry.30s process", lookback_s).items():
        by_name = {s.name: s for s in sorted(spans, key=lambda s: s.start_ns)}
        stored = [s for s in spans if s.name == "alerts.retry.30s process" and s.attrs.get("pagerwise.outcome") == "stored"]
        if not ({"alerts.v1 send", "alerts.v1 process", "alerts.retry.30s send"} <= by_name.keys() and stored):
            continue
        chain = [by_name["alerts.v1 send"], by_name["alerts.v1 process"], by_name["alerts.retry.30s send"], stored[0]]
        first = chain[0]
        print(f"trace {trace_id}: event key {chain[1].attrs.get('messaging.kafka.message.key')}, "
              f"{len(spans)} spans ({sum(s.name.endswith('receive') for s in spans)} fetch spans not shown)\n")
        for s in chain:
            line = f"  +{(s.start_ns - first.start_ns) / 1e9:7.3f}s  {s.name:26} {short(s.service):10} {s.ms:7.1f} ms"
            if s.name.endswith("process"):
                attempt = s.attrs.get("pagerwise.kafka.x_attempt", 0) + 1
                state = f"error {s.attrs.get('error.type')}" if s.status in ("2", "STATUS_CODE_ERROR") else "ok"
                line += f"  attempt {attempt}, {state} -> {s.attrs.get('pagerwise.outcome')}"
                line += f"  (offset {s.attrs.get('messaging.kafka.offset')})"
            elif s.attrs.get("pagerwise.kafka.x_attempt"):
                line += f"  publish, x-attempt {s.attrs['pagerwise.kafka.x_attempt']} ({s.attrs.get('error.type')})"
            else:
                line += "  publish"
            print(line)
        batch_trace, batch_id, _ = stored[0].links[0]
        batch_spans = get_trace(batch_trace)
        batch = next((s for s in batch_spans if s.span_id == batch_id), None)
        if batch is None:
            print(f"\n  linked batch {batch_trace}: not in Jaeger (tail sampling kept 10% of plain batches)")
            return 0
        upsert = next(s for s in batch_spans if s.name == "incident upsert")
        print(f"  {'':9} └ link -> {batch.name} (trace {batch_trace[:12]}…, {batch.ms:.1f} ms, "
              f"{batch.attrs.get('messaging.batch.message_count')} messages)")
        print(f"  {'':12} └ incident upsert  {upsert.ms:6.1f} ms  inserted {upsert.attrs.get('pagerwise.inserted')}, "
              f"incidents touched {upsert.attrs.get('pagerwise.incidents_touched')}, "
              f"opened {upsert.attrs.get('pagerwise.incidents_opened')}")
        return 0
    print("no retried-then-stored alert found; run a storm with transient failures (make storm) and wait a minute")
    return 1


KEEP = ("pagerwise.degraded", "pagerwise.result_count", "pagerwise.outcome", "pagerwise.verdict",
        "pagerwise.citation_count", "pagerwise.ttft_ms", "pagerwise.tokens_per_second", "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens", "pagerwise.degraded_reason", "http.response.status_code", "http.status_code")


def tree(span: Span, depth: int, origin: int) -> None:
    detail = ", ".join(f"{k.split('.')[-1]}={span.attrs[k]}" for k in KEEP if k in span.attrs)
    offset = (span.start_ns - origin) / 1e6
    print(f"  {offset:9.1f} ms  {'  ' * depth}{span.name:{max(1, 34 - 2 * depth)}} {span.ms:9.1f} ms  {detail}")
    children = sorted(span.children, key=lambda s: s.start_ns)
    repeated = {name for name in {c.name for c in children} if sum(c.name == name for c in children) > 3}
    for child in children:
        if child.name.startswith(("SELECT", "INSERT", "UPDATE", "connect", "BEGIN", "COMMIT")) and depth > 1:
            continue  # SQL statements under a stage span
        if child.name not in repeated:
            tree(child, depth + 1, origin)
    for name in sorted(repeated):  # e.g. one Redis XADD per streamed token: one summary line
        group = [c for c in children if c.name == name]
        print(f"  {(group[0].start_ns - origin) / 1e6:9.1f} ms  {'  ' * (depth + 1)}{name} x{len(group):<5}"
              f"{'':{max(1, 26 - 2 * depth - len(name))}} {sum(c.ms for c in group):9.1f} ms  (total)")


def triage(run_id: str | None, lookback_s: int) -> int:
    traces = find_traces("pagerwise-worker", "triage", lookback_s, limit=50)
    roots = [s for spans in traces.values() for s in spans if s.name == "triage"
             and (run_id is None or s.attrs.get("pagerwise.triage_id") == run_id)]
    if not roots:
        print("no triage trace found")
        return 1
    root = max(roots, key=lambda s: s.start_ns)
    spans = get_trace(root.trace_id)
    by_id = {s.span_id: s for s in spans}
    for s in spans:
        if s.parent_id in by_id:
            by_id[s.parent_id].children.append(s)
    root = by_id[root.span_id]
    print(f"trace {root.trace_id}: triage {root.attrs.get('pagerwise.triage_id')} for incident "
          f"{root.attrs.get('pagerwise.incident_id')}, {len(spans)} spans (SQL statements below the stage spans are "
          "left out)\n")
    tree(root, 0, root.start_ns)
    for trace_id, span_id, attrs in root.links:
        linked = next((s for s in get_trace(trace_id) if s.span_id == span_id), None)
        where = f"{linked.name} in {short(linked.service)}" if linked else "not in Jaeger (sampled out)"
        print(f"\n  link ({attrs.get('pagerwise.link')}) -> trace {trace_id}: {where}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", choices=["retry", "triage"])
    parser.add_argument("--id", help="triage run id (default: the latest)")
    parser.add_argument("--lookback", type=int, default=3600, help="seconds")
    args = parser.parse_args()
    sys.exit(retry(args.lookback) if args.what == "retry" else triage(args.id, args.lookback))


if __name__ == "__main__":
    main()
