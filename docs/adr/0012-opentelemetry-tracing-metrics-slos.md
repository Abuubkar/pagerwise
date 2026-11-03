---
status: accepted
date: 2026-11-03
---

# Telemetry: OpenTelemetry across Kafka hops, tail sampling, metrics and SLOs

**One setup for every app.** `pagerwise_telemetry.setup(service)` runs first in each main():
- **Export:** traces, metrics and logs go over OTLP gRPC to an OpenTelemetry Collector, configured with the standard
  `OTEL_*` variables (default localhost:4317).
- **Resource:** service name, version, instance and environment.
- **Logs:** stdlib logging is rendered as JSON on stdout by structlog, with `trace_id` and `span_id` when a span is
  current. The same records also go to the collector as OTLP logs.
- **Instrumentation:** httpx and Redis everywhere; FastAPI and SQLAlchemy where `instrument_app` and
  `instrument_engine` are called.
- **Proxies:** modules take their tracer and meter at import time, which are no-op proxies until setup runs, so tests
  export nothing.
- **API entry point:** the API gets `python -m pagerwise_api`. `uvicorn pagerwise_api.main:app` still works, without
  telemetry: setting up on import would turn exporting on in every test that imports the app.
- **Switch off:** `OTEL_SDK_DISABLED=true` keeps the JSON logs and exports nothing (CI's eval job, which has no
  collector).

**Versions:**
- OpenTelemetry Python 1.45.2; contrib instrumentations 0.66b2.
- Semantic conventions 1.44.0, from the Python package's schema.
- Messaging and GenAI conventions are both still "Development". The GenAI ones moved to their own repository, and use
  `gen_ai.provider.name` (not the older `gen_ai.system` the slice plan names), with `ollama` as a custom value.

**Kafka spans: the official aiokafka instrumentation, plus our own process spans.** The contrib package exists and
is maintained, so it's used:
- **What it does well:** `<topic> send` spans that inject `traceparent` into the headers.
- **Where it falls short:** its consumer side makes `<topic> receive` spans that end when `getmany` returns, before
  any processing. A retry partition seeked back to its due message is fetched several times, so a retried alert has
  several receive spans.
- **What we add (pagerwise_kafka.tracing):** a `<topic> process` span per message, covering its real processing.
  - Its parent is the message's creation context, so one alert is one trace across every hop.
  - Following the messaging conventions, it links to the ambient context: the `<topic> batch` span. The consumer
    processes a partition's records in one transaction, and the batch's SQL and the `incident upsert` sit under it.
  - It carries x-attempt (`pagerwise.kafka.x_attempt`), the outcome (`stored`, `retried`, `dead_lettered`) and, on
    failure, `error.type` with an ERROR status.
  - A republish is sent inside the failed attempt's process span, so the hop to alerts.retry.30s, alerts.retry.5m or
    the DLQ is its child, and a dead-lettered message shows its whole history.
- **Republish needs `route_failure`'s help:** the instrumentation *appends* `traceparent`, so `route_failure` drops
  the incoming trace headers. Otherwise the next hop would extract the stale parent first.
- **Alternatives considered:**
  - Batch spans only (links per message, the conventions' batch pattern) would scatter one alert's hops across
    traces, findable only by reverse link lookups Jaeger doesn't index.
  - Writing the publish side by hand too was the other option; asked, and the contrib package won.

**Triage links back to its alerts.** The consumer queues a triage in the transaction that opens its incident. It
stores the `incident upsert` span's traceparent in `triage_runs.traceparent` (migration 0012, nullable). The worker's
`triage` span links to it. The triage trace contains:
- `evidence runbooks|postmortems|deploys` spans, with `degraded` and the reason when a source was left out;
- `hybrid search` → embed / fts / vector / rerank / siblings, with result counts and a query hash, never the text;
- `deploys_http` → the httpx request;
- `chat <model>` with GenAI attributes, `ttft_ms`, `tokens_per_second`, and the brief's `citation_count` and
  `verdict`.

`chat_stream` is a generator, so its span is started, not made current: a context attached across yields would leak
into the caller. `llm.annotate_chat` reaches it through a context variable.

**Nothing sensitive leaves the process.** `DenylistSpanProcessor` wraps the exporter's processor and drops
denylisted keys from spans, events and links:
- GenAI content attributes (`gen_ai.input.messages`, `gen_ai.output.messages`, …);
- `pagerwise.query`;
- URLs and query strings (`url.full`, `url.query`, `http.url`, `http.target`: `/v1/search?q=` carries the question);
- request and response headers.

Unit-tested in packages/telemetry/tests. Redis spans are already sanitized by the instrumentation (`COMMAND ? ?`).

**Tail sampling in the collector.** The SDK samples everything; the collector decides per trace 60 s after its first
span, long enough for a 45 s triage. It keeps:
- errors;
- DLQ hops;
- degraded retrieval;
- triages over 45 s;
- every triage: one per new incident, so the volume is negligible. The plan listed only slow ones, but at 10% most
  normal triages were dropped (docs/challenges.md);
- batches that finished a retried message or opened an incident (the targets of the links above);
- 10% of the rest.

A retried alert's hops arrive 30 s and 5 min apart. The decision cache makes a late hop follow its trace's decision
instead of being judged alone.

**Metrics go over OTLP to Prometheus's OTLP receiver, with exemplars. No Prometheus client library.**

| Signal | Metrics |
|---|---|
| Consumer | lag per partition (end − committed), paused partitions by reason, events by outcome, dead letters by error class, ingest freshness |
| Retrieval | seconds by stage |
| Triage | TTFT, duration by outcome, runs by outcome and error code, verdicts, degraded sources |
| Model | tokens by type |
| Ollama | reachability, from a 15 s probe in the worker |

- **Freshness:** measured from the first publish to the commit. A new optional header, `x-original-timestamp`, carries
  the first publish time across retries; it's additive in the AsyncAPI contract.
- **Exemplars:** histograms record inside the relevant span, so their exemplars link to a trace.
- **Lag source:** lag uses the consumer's own committed offsets, not a broker-side exporter, because no new service
  was needed.

**SLOs and alerts.** docs/slo.md:
- freshness: 99% within 5 s;
- triage availability: 99.5%, with format_invalid excluded as a quality miss the eval owns.

Both SLOs have multiwindow burn-rate alerts. The six operational alerts are Prometheus rules with runbook links into
docs/alerts.md, and each fires on synthetic input in `promtool test rules` (`make obs-check`, CI lint job). There's
no Alertmanager: alerts show in Prometheus and Grafana. Paging is a deployment concern.

**Assumptions:**
- All five services (collector, Jaeger with in-memory storage, Prometheus, Loki, Grafana with anonymous admin) are
  local-development choices, in the default compose so `docker compose up -d --wait` brings them up.
- CI's load-smoke runs the same stack.
