# Pagerwise

Incident-response copilot: alerts in, cited triage briefs out, built in thin slices. Slice plan: [02-pagerwise.md](02-pagerwise.md).

- **How we work:** [HOW_WE_BUILD.md](HOW_WE_BUILD.md). It wins over everything else, including slice prompts.
- **Where it's heading:** [docs/architecture.md](docs/architecture.md). A destination, not a to-do list.
- **Why things are the way they are:** [docs/adr/](docs/adr/). Add one for every real choice.
- **What went wrong before:** [docs/challenges.md](docs/challenges.md). Each slice adds what it hit.
- **Error codes:** [docs/problems.md](docs/problems.md). Every new `ProblemCode` gets a row.

## Run it

```bash
docker compose up -d --wait               # Postgres 18 + pgvector :5435, Redpanda (Kafka API) :19092, Redis :6379,
                                          # OTel Collector :4317, Jaeger :16686, Prometheus :9090, Loki :3100, Grafana :3000
docker compose -f docker-compose.yml -f docker-compose.release.yml up -d --wait   # the published images instead
uv run alembic upgrade head
make topics                               # alerts.v1, alerts.retry.30s, alerts.retry.5m, alerts.dlq (idempotent)
ollama pull qwen3.5:9b-q4_K_M             # once; Ollama runs natively on the Mac, not in Docker (ADR 0001)
uv run python scripts/seed.py corpus      # regenerate data/corpus/ + evals/planted_facts.json (deterministic; committed)
uv run python scripts/seed.py deploys     # 30 days of deploys into the deploys table
uv run python scripts/seed.py graph       # data/service_graph.yaml -> services, service_edges (clustering reads them)
uv run python scripts/seed.py alerts      # 500k historical alert_events via COPY (replaces earlier seeded history)
uv run python -m pagerwise_docs_mock      # mock docs API on :8002 serving data/runbooks + data/corpus (--fail-rate 0.1)
uv run python -m pagerwise_indexer        # import runbooks + postmortems from it; reruns send If-None-Match (304s)
uv run python -m pagerwise_api            # the API on :8001 with telemetry (plain `uvicorn pagerwise_api.main:app` has none)
uv run python -m pagerwise_api.worker     # triage worker: generates queued briefs (needs Ollama and docs_mock)
cd apps/web && pnpm install && pnpm dev   # UI on :3001 (proxies HTTP to :8001; subscriptions use ws://localhost:8001)
uv run python scripts/ask.py "Why is payments p99 high?"   # answer + citations resolved to chunk text
curl 'localhost:8001/v1/search?q=ledger+pool+exhaustion'    # hybrid search with every stage's rank and timings
make smoke            # generated client end to end: 3 incidents, paging, one streamed triage, GraphQL
uv run python -m pagerwise_consumer                                  # alerts.v1 + retry topics -> alert_events
uv run python -m pagerwise_simulator --rate 200 --duration 10 --malformed-rate 0.01
uv run python scripts/incidents.py        # busiest open incidents and the alerts clustered into each
make storm            # done-when load test: 2,000/s for 3 min, a replica killed; takes ~10 min (5 min retries)
make lint             # ruff, mypy, tsc, eslint: the CI lint job
make test             # unit tests, offline (no Ollama, no DB, no model download)
make test-int         # service tests (testcontainers Postgres + pgvector, Redpanda, Redis; needs Docker)
make web-test         # Jest + TypeScript check for apps/web
make eval             # retrieval, clustering and triage eval on the dev split, replayed from evals/recordings (BASELINE=..., LIVE=1)
make eval-test        # the held-out test split: for confirming a decision, never for tuning
make golden           # regenerate evals/golden/ (deterministic)
uv run python scripts/reembed.py           # fill chunks.embedding_v2 after a model change (resumable, throttled)
make codegen          # regenerate the clients (Python, web TS), contracts/schema.graphql, the Kafka alert model
make contract-check   # oasdiff: the app's emitted OpenAPI vs contracts/openapi.yaml
make breaking-check   # REST, GraphQL and Kafka contracts vs origin/main (BASE=...); needs compose Redpanda
make migration-lint   # squawk on the SQL of migrations added since origin/main
make obs-check        # collector config validates, Prometheus rules parse, promtool tests each alert
uv run python scripts/trace.py retry      # from Jaeger: one retried alert, hop by hop, and the batch that stored it
uv run python scripts/trace.py triage     # the latest triage's span tree with per-stage durations
```

Run scripts from the repo root: document paths are stored relative to it.

## Rules that are easy to break

- Model name and options come from `settings.py`; prompts live only in `prompts.py`, and any wording change bumps
  its version. Every model call goes through `llm.chat` or `llm.chat_stream`, which refuse a prompt over the `num_ctx` budget before
  sending: Ollama truncates over-long prompts silently.
- Always pass `num_ctx` to Ollama: its default silently truncates long prompts.
- Token counts come from `embedding.count_tokens`, never from fastembed's `token_count` directly: that one stops
  at bge's 512-token window (ADR 0003).
- Changing an embedding model changes its dimension and every stored vector: it needs a migration and a re-embed
  (chunks went bge-small -> bge-base in migrations 0009-0011), not a settings change. Incidents still use bge-small.
- Routes and GraphQL resolvers stay thin; both call `service.py`, so no rule is written twice.
- `contracts/openapi.yaml` is the source of truth: change it first, then the code, then `make codegen`.
  `packages/clients/python` is generated; never edit it by hand. Hand-written client code goes in
  `packages/client-sse`.
- A streaming endpoint has sent `200` before its body runs: anything that can fail as a 4xx (lookups, claims)
  goes in a dependency, like `_open_triage_stream`.
- After a rollback (e.g. catching `IntegrityError`) every loaded ORM object is expired; read the values you need
  before committing. Under asyncio a lazy reload raises `MissingGreenlet`. Likewise assign Python datetimes, not
  `func.now()`, to ORM attributes you might read again.
- Answers are checked by `citations.parse_answer`, briefs by `citations.parse_brief`, never by the model. Only
  exact `[Cn]` tags that were supplied count; a `REJECTED` answer or `format_invalid` brief is still stored with its
  `problems`. Tag syntax lives only in `citations.py` (`scan_tags`, `TagScanner`).
- `contracts/kafka/alert.v1.json` is the alert contract; `pagerwise_kafka/alert_v1.py` is generated from it. Topic
  names, header names and retry routing live only in `pagerwise_kafka`. Producers build an `AlertV1` before
  sending (that's the validation); only the simulator's malformed events skip it, on purpose.
- Consumer: mark a record done (`OffsetTracker.done`) only after its row is committed or it has been republished.
  Writes must stay idempotent (`ON CONFLICT DO NOTHING`): redelivery after a crash or rebalance is normal.
- A failure of Postgres or Kafka itself is retried in place, never routed to a retry topic; only a failure that
  belongs to the message (`TransientError`, `PermanentError`) moves it.
- Keep the round-robin assignor: the sticky one can give a replica no `alerts.v1` partitions at all (ADR 0005).
- Documents get into the store only through the importer (`pagerwise_indexer`), and retrieval only through
  `retrieval.hybrid_search`. Don't add a second loader or a vector-only search path.
- `data/corpus/` and `evals/planted_facts.json` are generated by `scripts/seed.py corpus`: change the templates or
  the generator and regenerate, never hand-edit. The service graph is `data/service_graph.yaml`, read by the
  simulator and the seeds.
- Clustering decisions live in `clustering.decide` (pure, table-tested); `store_alerts` applies them under
  advisory locks on the batch's service neighbourhoods. Don't open or join incidents anywhere else.
- `alert_events` is partitioned by day (migration 0007): its key is `(event_id, occurred_at)`, so queries that look
  up alerts by id should also bound `occurred_at` (pruning), and inserts use `ON CONFLICT DO NOTHING` without a
  target. Partitions are created a week ahead by the consumer (`create_alert_partitions`). docs/migrations.md
  has the online migration procedure and rollback.
- Triage briefs are generated only by the worker (`triage.generate`), and read only through `triage.events` (Redis
  stream, then the stored result). Don't generate in a request handler. Redis is used only through `bus`.
- An evidence source may fail: keep each one in its own timeout and `try` inside `gather_evidence`, and never let
  the prompt or the brief say anything about a degraded source.
- `apps/web/src/gql` and `apps/web/src/api/schema.d.ts` are generated (`make codegen`); never edit them by hand.
- Eval results are never deleted: every run is kept in `evals/results/`, and a replaced `evals/REPORT.md` moves to
  `evals/archive/`. Tune on the dev split only; the test split confirms decisions.
- `evals/golden/` is generated by `evals/build_golden.py`; gold evidence is (document, chunk ordinal), not chunk ids.
- Retrieval reads `chunks.embedding_v2` (bge-base) only; v1 was dropped in migration 0011. Sibling chunks are on and
  the reranker is off by default (ADR 0009); change either only with eval numbers.
- Citations in the triage eval are checked deterministically (`triage_eval.check_citations`, ADR 0010), not by a
  model: no local judge reached kappa 0.70 against `evals/golden/calibration.csv`. Change a check only with its
  agreement with those labels (tune rows to develop, held-out rows to confirm); the labels are hand-reviewed.
- Whether a brief names a cause is decided by `citations.LikelyCauseGate` from the model's `Match:` line (ADR 0010),
  never by the model writing the token: a cause needs a runbook or postmortem, never a deploy alone.
  `triage_runs.raw_text` is what the model wrote; the stream, the parsed brief and replays all go through the gate.
- A deploy in triage evidence is never after the incident opened, and says how long before it was: small models
  misread timestamps. Golden deploys must look like any other deploy (nothing may give the cause away).
- CI (`.github/workflows/`, ADR 0011): pin every action to a commit SHA with its tag in a comment, give each job
  only the permissions it uses, and keep `persist-credentials: false`. actionlint runs in the lint job.
- Images: every Python app builds from `docker/python.Dockerfile` (PACKAGE, COMMAND); apps that embed or rerank use
  the models base image as RUNTIME. Each image installs only its own package's dependencies, so shared code
  (pagerwise_telemetry) imports optional libraries only when they're installed; docker-compose.release.yml runs
  them all. A new model in settings.py changes that image's tag, so release.yml rebuilds it.
- In CI the eval runs with `--baseline` main's baseline: a gate main already misses is reported, not failed; a new
  miss or a quality drop fails. That's not a reason to move a gate.
- Telemetry (ADR 0012): every app calls `pagerwise_telemetry.setup` first in its main, never on import (tests import
  the modules). Take tracers and meters with `trace.get_tracer` / `metrics.get_meter` at module level.
- Never put a query, prompt, model output or any user text on a span, event, log field or metric label: use
  `retrieval.query_hash`. The denylist processor is a backstop, not the rule. Metric labels stay low-cardinality
  (no ids).
- A consumed record's work goes in `pagerwise_kafka.process_span` (parent: its creation context; link: the batch). A
  republish is sent inside that span so the hop stays in the alert's trace; `route_failure` drops the old trace
  headers because the producer instrumentation appends its own.
- Don't `start_as_current_span` inside an async generator: the context leaks into the caller across yields. Start
  the span and use `trace.use_span` around the awaits that need it (see `llm.chat_stream`).
- Metric names and labels are an interface: a rename must update observability/prometheus/rules.yml, its tests and
  the Grafana dashboards. Prometheus sees `pagerwise.ingest.freshness` (unit s) as
  `pagerwise_ingest_freshness_seconds_bucket`, counters get `_total`, dots in labels become underscores.

## Lessons from Ledgerline

Ledgerline (`../ledgerline`) hit these first; the full stories are in `../ledgerline/docs/challenges.md`. Each is a
trap nothing in this repo's config will warn about.

- **An Ollama `format` schema forces the answer into the schema, even when that means null.** A field typed `string`
  while the model writes bare numbers comes back null every time (Ledgerline lost every amount from Qwen this way).
  Type fields the way the model writes them (`string | number`), parse numbers with `json.loads(parse_float=Decimal)`,
  and keep the prompt's wording consistent with the schema.
- **Check the scorer before trusting a low score.** Ledgerline's first real-data line F1 (6%) measured its scoring
  rule, not the model. Reading the per-case failure reasons (not the averages) found that, and found the one gap
  (no currency read) behind most real failures.
- **Models measured on this Mac** (M1 Pro 16 GB, Ledgerline's sweep, `think: false`):
  - gemma4:12b: best quality and tool choice (8.7 GB, ~34 s per page).
  - qwen3.5:9b-q4_K_M: close behind, 1.6× faster, 6.6 GB.
  - qwen2.5:7b: fast and reads well, but weakest at picking a tool action (10 of 15).

  Pin explicit quant tags; a bare tag can pull different builds.
- **OpenTelemetry Python:**
  - The SDK and the contrib instrumentations release in matched pairs (SDK 1.45.0 with 0.66b0); a mismatched pin
    won't resolve.
  - An instrumentation switches itself off silently when a library is newer than it declares (0.66b0's SQLAlchemy
    says < 2.1). Confirm its spans appear; if its hooks still fit, `instrument(skip_dep_check=True)` with a comment.
- **Metrics over OTLP into Prometheus:**
  - A new series' first measurement never counts in `rate()` or `increase()`, because the receiver ignores start
    times: report counters at 0 when a process starts.
  - A stopped process's gauges linger for 5 minutes (no staleness marker): gauge alerts and panels use
    `last_over_time(x[1m])`.
  - A worker process that exits without atexit hooks loses its last export: flush the providers on shutdown.
  - A unit suffix can double: unit `{token}/s` on a metric named `…_per_second` became `…_per_second_per_second`.
- **httpx logs every request at INFO, URL included:** set the `httpx` logger to WARNING. A management URL carrying
  credentials reached Ledgerline's logs that way.
- **Next.js 16:**
  - `next lint` is gone: use the ESLint CLI with a flat config.
  - `rewrites()` are fixed at build time, so the API address a container proxies to is a build argument.
  - `next dev` writes `apps/web/AGENTS.md`: gitignore it.
- **Images and pins:**
  - GHCR packages come out public, linked to the repo; name them `<project>-<service>`.
  - A collector-contrib release can lack its image (0.163.0 did): check the tag exists before pinning.
