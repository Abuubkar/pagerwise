# Project 2: Pagerwise (Incident-Response Copilot)

**Pitch:** Pagerwise consumes a live stream of alerts, deploy events and error-log samples from Kafka. It deduplicates and clusters alerts into incidents, and for each new incident produces a grounded triage brief: likely cause, blast radius, the runbook steps to try first, and similar past postmortems. Every claim is cited to a specific runbook chunk, postmortem section or deploy record.

**Why it isn't a toy:** On-call tooling has to hold up during exactly the moments when everything else is falling over: alert storms, a dependency down, a database under pressure. The streaming layer must shed load gracefully, and the AI layer must say "insufficient evidence" instead of inventing a root cause.

## Real-world concerns, mapped to where they're built

| Concern | Implementation | Slice |
|---|---|---|
| Backpressure | aiokafka consumer feeds a bounded `asyncio.Queue(maxsize=500)`. At the high watermark it calls `consumer.pause(*assigned)` and resumes at the low watermark (100). A DB pool saturation probe also triggers pause. Consumer lag is exported as a metric. The triage endpoint has a per-tenant concurrency limit (Redis semaphore) and returns `503 + Retry-After` | 3, 5 |
| Retries | Non-blocking retry topics: `alerts.retry.30s` → `alerts.retry.5m` → `alerts.dlq`. The attempt count and first-failure timestamp travel in Kafka headers. The main partition never blocks on a poison message | 3 |
| Dead letters | `alerts.dlq` topic plus a `dead_letters` table, a CLI and an endpoint to replay a DLQ range by offset or by key | 3 |
| Pagination | Postmortem importer walks a mock docs API that uses `Link: rel="next"` headers and ETag conditional requests. The incident API uses keyset pagination. GraphQL uses Relay connections plus a subscription for live incident updates | 2, 4 |
| Partial failures | Retrieval fans out to 3 sources (runbooks via pgvector, postmortems via hybrid FTS+vector, deploys via HTTP) with per-source timeouts. A failed source becomes `degraded_sources[]` in the brief, the prompt is told which evidence is missing, and the brief is still produced | 5 |
| Schema migrations | (a) Convert `alert_events` from a plain table to daily range partitions online. (b) Migrate the **embedding model** from bge-small (384-d) to bge-base (768-d) with a shadow column, background re-embed, dual-read eval and atomic switch | 4, 6 |
| Exactly-once-ish | At-least-once delivery + idempotent upserts keyed on `(source, fingerprint, occurred_at)`. Offsets are committed manually only after the DB commit | 3 |

## AI scope and precise targets

**Retrieval:** hybrid search. Postgres FTS (`websearch_to_tsquery`, BM25-like via `ts_rank_cd`) plus pgvector HNSW cosine, fused with Reciprocal Rank Fusion (k=60) and then reranked by a local `bge-reranker-base` cross-encoder down to the top 8 chunks. Chunks are 300–500 tokens, split on markdown headings, with service and section metadata.

**Generation:** `qwen2.5:7b-instruct` through Ollama, streamed over SSE to the UI, with `temperature: 0` and `num_ctx: 16384`. Local models have no built-in citation feature, so each evidence chunk goes into the prompt tagged `[C1]`…`[C8]`. The model must put a tag after every factual sentence, and code maps each tag back to its chunk ID. A deterministic parser checks the fixed markdown section contract and rejects any tag that doesn't point at a supplied chunk.

**Alert clustering:** deterministic first (fingerprint + service + 10-minute window), then embedding similarity ≥ 0.86 on alert summaries within the same service graph neighborhood. No LLM in the hot path.

| Metric | Definition | Target (gate) |
|---|---|---|
| Retrieval Recall@8 | Gold evidence chunk IDs present in the final top 8 | ≥ 0.90 |
| Retrieval MRR@10 | Before rerank vs after rerank, both reported | ≥ 0.70 after rerank |
| Root-cause hit@1 / @3 | Named cause matches the gold cause category + component | ≥ 0.60 / ≥ 0.80 |
| Citation precision | Share of citations whose chunk supports the sentence it's attached to. Judged by `llama3.1:8b` (a different model family from the generator), trusted only if it agrees with 40 hand labels at Cohen's κ ≥ 0.70 | ≥ 0.90 |
| Unsupported-claim rate | Sentences in "Likely cause" / "Blast radius" with no citation, or a citation that doesn't support them | ≤ 8% |
| Abstention | On the 15 unanswerable incidents, brief says `INSUFFICIENT_EVIDENCE` instead of naming a cause | ≥ 0.80 |
| Degraded honesty | With the deploy source forced down, the brief never cites or asserts deploy facts | 100% |
| Clustering pairwise F1 | Alert pairs correctly grouped vs gold incident IDs | ≥ 0.90 |
| Ingest freshness | Kafka produce timestamp → alert searchable in DB | p95 ≤ 5s at 2,000 events/s |
| Retrieval latency | Hybrid + rerank, server-side | p95 ≤ 250ms |
| Triage latency | Time to first token / full brief, one local Ollama instance, ~7k-token prompt | p95 ≤ 10s / ≤ 45s |
| Format validity | Briefs that pass the section + citation-tag parser | ≥ 95% |

**Golden set:** a simulated 12-service system (service graph in YAML) with 120 runbooks, 60 postmortems and a deploy log, all generated from templates with planted, known facts. It includes 40 incidents with gold cause, gold evidence chunk IDs and gold alert→incident grouping, plus 15 unanswerable incidents whose cause isn't in any document. Split by hash: 25+10 dev, 15+5 test.

---

## Target architecture (the vision)

This is where the project ends up after slice 8. It is a destination, not a to-do list: slice 1 copies it into `docs/architecture.md`, and each folder, service and dependency appears only when a slice needs it (see HOW_WE_BUILD.md).

**Stack:** Python 3.12, uv workspaces, FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, Strawberry GraphQL (with subscriptions over graphql-transport-ws), aiokafka, Redpanda (Kafka API) + Redpanda Console, Postgres 16 with pgvector, Redis 7, fastembed for local embeddings and reranking, Next.js 15 + TypeScript UI, pnpm.

```text
  apps/api/          FastAPI: REST /v1, GraphQL /graphql (+ subscriptions), SSE /v1/incidents/{id}/triage/stream
  apps/consumer/     long-running aiokafka consumer service (alerts, deploys, logs)
  apps/indexer/      document importer + embedding/indexing jobs
  apps/simulator/    event generator: emits realistic alert storms, deploys, and log samples for a 12-service system; configurable rate and failure scenarios
  apps/docs_mock/    mock docs API (runbooks/postmortems) with Link-header pagination, ETags, and injectable 5xx
  apps/web/          Next.js incident list, timeline, and triage brief viewer
  packages/core/     domain types: Alert, Incident, Evidence, ServiceGraph
  packages/db/       models, sessions, Alembic
  packages/kafka/    typed producer/consumer wrappers, header schema, retry-topic router
  packages/retrieval/ chunking, embedding, hybrid search, RRF, rerank
  packages/ai/       Ollama client, prompts, citation-tag parser, token/latency accounting
  packages/clients/  generated clients (never hand-edited)
  packages/telemetry/
  contracts/         openapi.yaml, schema.graphql, kafka/ (JSON Schema per topic + AsyncAPI 3.0 doc)
  evals/ infra/ scripts/ .github/workflows/
```

---

## Pairing plan: 8 slices

Each prompt is one vertical slice that runs end to end on real input. Your 8 topics are all covered; each slice leads with one of them and pulls in only the infrastructure, packages and tests it needs.

| Slice | Leads with | Delivers | First appearance of |
|---|---|---|---|
| 1 | Scaffolding | Ask a question about a few runbooks → cited answer from a local model | uv project, FastAPI, Postgres + pgvector, fastembed, Ollama, pytest |
| 2 | Contracts | Incidents and a streamed triage brief behind a spec-first API, typed client, GraphQL reads | OpenAPI + AsyncAPI specs, SSE, Strawberry, testcontainers |
| 3 | Workers | Alerts stream in through Kafka with backpressure, retry topics and a DLQ | Redpanda, aiokafka, simulator |
| 4 | Data | Alerts cluster into incidents; postmortems import with pagination; hybrid search; partitioned table migration | docs_mock, FTS + RRF + reranker, seeds with planted facts |
| 5 | AI (triage) + Tests (Jest) | Each new incident gets a triage brief from 3 evidence sources, with degraded-source handling; live UI | GraphQL subscriptions, Next.js, Jest |
| 6 | AI (evals) | Golden set, retrieval/clustering/generation evals, judge calibration, embedding-model migration gated by eval | Eval harness, recorded responses |
| 7 | CI/CD | GitHub Actions incl. a load smoke test; image build and push | Workflows, Dockerfiles, GHCR |
| 8 | Instrumentation | One alert traced through Kafka hops and retries to the brief; lag and freshness SLOs | OpenTelemetry, Jaeger, Prometheus, Grafana |

Every prompt ends with a **Done when** check. Each slice lists what it will ask to add, so you can approve in one go.

### Slice 1. Scaffolding: walking skeleton

```text
Slice 1 of 8 for Pagerwise: walking skeleton. Read HOW_WE_BUILD.md first; it wins over anything in this prompt.

Goal: load a handful of real runbook files, ask one incident question, and get an answer from a local model where every claim cites a runbook chunk. Nothing more.

Vision: copy the "Target architecture" section of 02-pagerwise.md into docs/architecture.md as the destination. Do not create folders, services or dependencies from it until a slice needs them.

Build:
- A uv project with one app, apps/api (FastAPI). Settings via pydantic-settings; .env.example lists only the keys used today.
- Write 6 realistic runbooks by hand in data/runbooks/*.md for 3 services (payments, ledger, postgres-primary), each with a few headed sections and at least one specific, checkable fact (for example "payments p99 rises when the ledger connection pool drops below 20").
- scripts/load_docs.py: split each file on markdown headings into chunks of 300–500 tokens (keep the heading path), embed with fastembed bge-small-en-v1.5, store in Postgres with pgvector.
- POST /v1/ask {question}: embed the question, take the top 8 chunks by cosine similarity, and call Ollama (qwen2.5:7b-instruct; model and options from settings; num_ctx set explicitly because the default silently truncates). Chunks go in tagged [C1]…[C8]; the system prompt requires a tag after every factual sentence and the exact token INSUFFICIENT_EVIDENCE when the chunks don't answer the question. A parser maps tags to chunk IDs and rejects tags that weren't supplied. Return {answer, citations[], verdict}.
- Prompts in one module with a version string; store model, prompt_version, token counts and durations per answer.
- docker-compose with Postgres (pgvector image) only. Ollama runs natively on the Mac (no GPU in Docker on macOS) at OLLAMA_HOST.
- Alembic baseline for documents, chunks (vector(384)) and answers.
- CLAUDE.md pointing at HOW_WE_BUILD.md and docs/architecture.md, with run instructions.
- Tests (pytest): the chunker (headings kept, no chunk over 500 tokens, code blocks never split) and the citation-tag parser (valid tags, unknown tags, no tags). Ollama stubbed.

Check current official docs (web search) for pgvector and its SQLAlchemy integration, fastembed, and the ollama Python client before using them.
Will ask before adding: fastapi, uvicorn, pydantic-settings, sqlalchemy[asyncio], asyncpg, alembic, pgvector, fastembed, ollama, pytest, pytest-asyncio; the Postgres service; the three tables.
Git: init the repo if needed, branch slice/01-walking-skeleton.

Done when: 3 questions run end to end — one answered by a planted fact, one needing two runbooks, one not covered at all. Show each answer with its citations resolved to chunk text. The third must say INSUFFICIENT_EVIDENCE. Tests pass. Merge, then report.
```

### Slice 2. Contracts: incidents, streamed triage, typed client, GraphQL

```text
Slice 2 of 8 for Pagerwise: contracts. Follow HOW_WE_BUILD.md.

Goal: incidents exist as first-class records, a triage brief streams to the client token by token, and the API is defined by checked-in specs with a generated typed client and GraphQL reads.

Build:
- contracts/openapi.yaml (OpenAPI 3.1), source of truth for:
  - POST /v1/incidents (manual creation for now; alerts create them in slice 4), GET /v1/incidents with keyset pagination (opened_at DESC, id DESC; limit ≤ 100; HMAC-signed opaque cursor) and filters status, service, severity; GET /v1/incidents/{id}.
  - POST /v1/incidents/{id}/triage → 202 with triage_id; 409 with the existing id if a triage for this incident version is already running.
  - GET /v1/incidents/{id}/triage/stream as text/event-stream, with documented event types token, citation, section_complete, done, error.
  - RFC 9457 problem+json errors with a code enum.
- TriageBrief schema: sections (likely_cause, blast_radius, first_steps, similar_incidents), each with text and citations {tag, source_type, source_id, chunk_id, chunk_excerpt}; verdict (CAUSE_IDENTIFIED | INSUFFICIENT_EVIDENCE); model; prompt_version; usage.
- The triage reuses slice 1's retrieval and prompt, now streaming from Ollama. A small scanner emits a citation event only when a complete [Cn] tag has arrived, because a tag can be split across stream chunks.
- `make contract-check` with oasdiff (Docker image), failing on breaking changes.
- Python client via openapi-python-client into packages/clients/python, plus a typed SSE helper; first user is scripts/smoke.py.
- Strawberry GraphQL at /graphql: incident(id) and incidents(filter, first, after) as a Relay connection, calling the same service functions as REST. Schema printed to contracts/schema.graphql with a drift test.
- Tables: incidents (with version), triage_runs.
- Unit tests: cursor round-trip and tamper rejection, the streaming tag scanner (tag split across two chunks), the section-contract parser.
- Service test (testcontainers Postgres): two concurrent triage requests for the same incident version → one run, the other gets 409.

Check current official docs (web search) for FastAPI's StreamingResponse or sse-starlette, Ollama streaming, oasdiff, openapi-python-client and Strawberry's Relay support.
Will ask before adding: strawberry-graphql, sse-starlette (if FastAPI's built-in streaming isn't enough, with one line on why), openapi-python-client (dev), testcontainers (dev); the two tables; the public API shape above.
Git: branch slice/02-contracts.

Done when: scripts/smoke.py, using only the generated client, creates 3 incidents, pages through them 2 at a time, and streams one triage, printing events as they arrive. A GraphQL query returns the same incidents. Show the outputs.
```

### Slice 3. Workers: Kafka ingestion with backpressure, retry topics and a DLQ

```text
Slice 3 of 8 for Pagerwise: workers. Follow HOW_WE_BUILD.md.

Goal: alerts arrive through Kafka at storm rates and land in Postgres exactly once in effect, without the consumer falling over, blocking on a poison message, or losing data when a replica dies.

Build:
- Redpanda in compose (Kafka API). A topic script creates alerts.v1 (12 partitions, key = service), alerts.retry.30s, alerts.retry.5m and alerts.dlq.
- contracts/kafka/alert.v1.json (JSON Schema) and contracts/kafka/asyncapi.yaml describing channels, keys, headers (x-attempt, x-first-failed-at, x-original-topic, x-error-class) and the consumer group. Pydantic models generated from the schema. The producer validates before sending; a consumer validation failure goes straight to the DLQ.
- apps/simulator: produces realistic alerts for the 12-service system at a configurable rate, with optional malformed events.
- apps/consumer (aiokafka):
  - Auto-commit off. Offsets are committed per partition only up to the highest contiguous processed offset, and only after the DB commit.
  - Ordered processing within a partition, parallel across partitions.
  - A bounded asyncio.Queue between polling and processing: pause all assigned partitions at 500 queued, resume at 100. Also pause when the DB pool is 90% checked out. Hysteresis prevents flapping.
  - Idempotent insert: INSERT ... ON CONFLICT (event_id) DO NOTHING; count duplicates.
  - TransientError → publish to alerts.retry.30s, then alerts.retry.5m, incrementing x-attempt, and commit the original offset. Retry consumers wait until the message's not-before time by pausing that partition, not by sleeping in the loop. After attempt 3, or on PermanentError → alerts.dlq plus a dead_letters row.
  - On rebalance, commit processed offsets for revoked partitions. On SIGTERM, stop polling, drain up to 20s, commit, exit.
- POST /v1/admin/dlq/replay {from_offset, to_offset | keys}.
- Table: alert_events (event_id unique, source, service, fingerprint, severity, occurred_at, labels, summary), dead_letters.
- Unit tests: the contiguous-offset tracker (hypothesis-generated completion orders never skip or commit past a gap), the pause/resume controller, retry header math.
- Service tests (testcontainers Redpanda + Postgres): one malformed alert among 100 → 100 rows, 1 DLQ message, offsets fully committed; transient failure twice then success → one row, x-attempt 2; a second consumer joining mid-batch → no duplicates, no gaps.

Check current official docs (web search) for aiokafka (pause/resume, manual commits, rebalance listeners and the assignment strategies it actually supports), Redpanda's rpk and testcontainers module, and AsyncAPI 3.0.
Will ask before adding: aiokafka, datamodel-code-generator (dev), hypothesis (dev); the Redpanda service and topics; the tables.
Git: branch slice/03-workers.

Done when: scripts/storm.py drives 2,000 events/s for 3 minutes with 1% malformed and 5% transient failures while one consumer replica is killed. Show: 0 lost valid events (produced IDs vs DB), malformed count == DLQ count, lag back under 1,000 within 60s after the storm, and lag over time as a text sparkline.
```

### Slice 4. Data: clustering, postmortem import, hybrid search, partition migration

```text
Slice 4 of 8 for Pagerwise: data. Follow HOW_WE_BUILD.md.

Goal: alerts become incidents automatically, a realistic corpus is imported from a paginated docs API, retrieval gets much better than pure vector search, and the alert table is partitioned without downtime.

Build:
- Clustering in the consumer: same fingerprint + service within 10 minutes → same incident; otherwise compare summary embeddings (cosine ≥ 0.86) against open incidents from the last 15 minutes in services within 1 hop on the service graph. Lock the incident row (SELECT ... FOR UPDATE) so two consumers can't open duplicates. Publish incident updates to Redis pub/sub.
- Tables: services and service_edges (the graph), deploys, import_state; incident_id on alert_events.
- apps/docs_mock serving runbooks and postmortems with Link rel="next" pagination (page size 20), ETags, and injectable 5xx.
- Importer (apps/indexer): follow Link headers, send If-None-Match (304 → skip), save next_url after each page so a crash resumes, retry 5xx with backoff, and restart from page 1 with a since filter on a 404 mid-listing. Changed documents are re-chunked and their chunk set replaced atomically.
- Hybrid retrieval replaces slice 1's vector-only search (one way per thing): Postgres FTS (generated tsvector column, websearch_to_tsquery, ts_rank_cd) and pgvector HNSW run concurrently, fused with Reciprocal Rank Fusion (k=60), top 40 reranked by bge-reranker-base to 8. GET /v1/search returns per-stage ranks for debugging.
- Seeds (deterministic --seed): the 12-service graph; 120 runbooks and 60 postmortems from Jinja templates with planted facts, indexed in evals/planted_facts.json; 30 days of deploys; 500k alert_events via COPY with diurnal patterns and 3 historical storms. docs_mock serves the same documents.
- Partition migration: alert_events was a plain table. Create a range-partitioned table by day (plus a DEFAULT partition and a create_alert_partitions(days_ahead) function), copy history in 50k-row resumable batches while a trigger mirrors new writes, then swap names in one short transaction (lock_timeout 2s with retries). Procedure and rollback in docs/migrations.md.
- Unit tests: clustering decisions (table-driven), RRF on a hand-computed example.
- Service tests: two consumers racing on alerts for the same fingerprint → one incident; the importer resumes after a failure on page 3 and a second run sends only 304s; every migration up → down → up; partition swap under concurrent inserts loses no rows.

Check current official docs (web search) for Postgres declarative partitioning and websearch_to_tsquery, pgvector HNSW options, fastembed's reranker support, and HTTP Link-header pagination.
Will ask before adding: jinja2, faker (dev); the docs_mock and Redis services; every table and migration above.
Git: branch slice/04-data.

Done when: a storm produces incidents (show 5 with their grouped alerts); the importer loads the corpus with injected 5xx; GET /v1/search shows per-stage ranks for 3 queries; row counts match before and after the partition migration and EXPLAIN on a 7-day query shows partition pruning.
```

### Slice 5. AI triage + live UI (with Jest)

```text
Slice 5 of 8 for Pagerwise: triage and UI. Follow HOW_WE_BUILD.md.

Goal: every new incident gets a cited triage brief built from three evidence sources; when one source is down, the brief says so and makes no claims about it; on-call engineers watch it update live.

Build:
- Triage pulls evidence from runbooks (hybrid search), postmortems (hybrid search) and recent deploys (HTTP call to a small deploys endpoint on docs_mock), concurrently with asyncio.TaskGroup and per-source timeouts (300ms, 300ms, 500ms). A failed or slow source is added to degraded_sources; the triage still runs.
- The query is built from the incident without a model call: primary service, neighbour services, top alert summaries, deploys in the last 2 hours.
- The prompt gets the four-section contract, the tagged evidence, and the list of degraded sources with an instruction never to state facts about them. A degraded_source event goes out on the SSE stream.
- Per-tenant concurrency limit on triage (Redis semaphore): over the limit → 503 with Retry-After.
- Triage starts automatically when the consumer opens an incident (enqueued after commit).
- GraphQL subscriptions over graphql-transport-ws: incidentUpdated(service) and triageProgress(triageId). Add acknowledgeIncident(id, expectedVersion) returning success or VersionConflict.
- apps/web (Next.js + TypeScript): incident list (cursor paging, live updates via subscription), incident timeline, and the brief with citations as footnotes linked to source panels and a warning banner for degraded sources. TS types from contracts/schema.graphql via @graphql-codegen; the SSE stream through the generated TS client (openapi-typescript + openapi-fetch).
- Jest setup (next/jest, React Testing Library, MSW, a mock EventSource). Tests: citations render as linked footnotes; a degraded_source event shows the banner; a subscription update moves the incident to the top; the list pages with cursors.
- Python unit tests: query construction, degraded-source handling (the source list reaches the prompt; a timeout marks the source degraded).
- Service test: SSE stream with a recorded Ollama response emits token → citation → section_complete → done in order.

Check current official docs (web search) for Strawberry subscriptions over graphql-transport-ws, Next.js App Router, graphql-codegen client-preset, openapi-typescript and openapi-fetch, Jest with next/jest, and MSW.
Will ask before adding: next, react, a GraphQL client with subscription support (with one line on why), @graphql-codegen/*, openapi-typescript, openapi-fetch, jest, @testing-library/react, msw; the deploys endpoint; the new mutation and subscriptions.
Git: branch slice/05-triage-ui.

Done when: replaying one seeded incident produces a brief that cites a planted fact; the same incident with the deploys source forced down shows the banner and no deploy claims; the UI shows a new incident appearing live during a small storm. Jest and pytest pass.
```

### Slice 6. AI evals: golden set, judge calibration, embedding migration

```text
Slice 6 of 8 for Pagerwise: evals. Follow HOW_WE_BUILD.md.

Goal: retrieval, clustering and triage quality are measured by a script over a fixed golden set with gates, and the embedding-model upgrade is decided by those numbers.

Build:
- Golden set (evals/golden/) built from planted_facts.json: 40 answerable incidents (a replayable alert sequence, gold cause {category, component}, gold evidence chunk IDs, gold alert grouping); 15 unanswerable incidents; 10 degraded cases where the true cause is a deploy and the deploy source is forced down; 40 hand-labelled (claim, chunk text, supports yes/no) rows for judge calibration, at least 15 of them "no" (label them by reviewing real generated briefs). Hash split: dev/test 25/15 answerable, 10/5 unanswerable, 6/4 degraded. The test split runs only with `make eval-test`.
- evals/run.py (a plain script, not part of the test suite):
  - Retrieval, no model needed: Recall@8 and MRR@10 before and after reranking, plus an ablation table (FTS only, vector only, hybrid, hybrid + rerank) with latency.
  - Clustering: pairwise precision, recall and F1 from replaying alert sequences through the real consumer code in-process.
  - Triage: root-cause hit@1 and @3 (match the cause named under Likely cause against an alias table, not a model), abstention rate on unanswerable cases, degraded honesty (deterministic: no tag pointing at a deploy chunk and no commit SHAs in the text), format-violation rate.
  - Citation precision and unsupported-claim rate from a judge: llama3.1:8b via Ollama with structured output {supports, reason}. Run it on the 40 calibration rows first and compute Cohen's kappa; below 0.70, stop and report instead of scoring.
  - TTFT and total p50/p95 over 3 repeats per case; retrieval p95 over 500 synthetic queries; tokens/sec.
  - Gates (exit 1 if missed): Recall@8 ≥ 0.90, MRR@10 ≥ 0.70, hit@1 ≥ 0.60, hit@3 ≥ 0.80, citation precision ≥ 0.90, unsupported ≤ 0.08, abstention ≥ 0.80, degraded honesty = 1.0, format validity ≥ 0.95, clustering F1 ≥ 0.90, retrieval p95 ≤ 250ms, TTFT p95 ≤ 10s, total p95 ≤ 45s. After the first baseline run, propose recalibrated gates with reasons; I decide.
  - `--baseline evals/baseline.json` fails on any drop over 1.5 points. REPORT.md shows per-case failures with retrieved vs gold chunks.
- Offline mode: record live model responses keyed by prompt hash so the eval replays without Ollama.
- Embedding-model migration (bge-small 384-d → bge-base 768-d): add embedding_v2 and its HNSW index (built concurrently), a resumable re-embed job in id-range batches with a DB-load throttle, and RETRIEVAL_EMBEDDING_VERSION = v1 | v2 | dual. Run the retrieval eval on both. Drop the old column only if v2's Recall@8 ≥ v1's — that's my call after seeing the numbers.
- Unit tests for the metric code: Recall/MRR, pairwise F1 and Cohen's kappa on hand-computed examples.

Check current official docs (web search) for pgvector index builds on large tables and the bge-base model card in fastembed.
Will ask before adding: scikit-learn (for cohen_kappa_score) or a 10-line implementation instead, your choice with a reason; the embedding_v2 migration.
Git: branch slice/06-evals.

Done when: `make eval LIVE=1` runs the dev split on local Ollama and `make eval` replays it offline with identical metrics. Before the first live run, print the projected wall-clock time. Show REPORT.md, the ablation table and the v1-vs-v2 comparison.
```

### Slice 7. CI/CD: GitHub Actions with a load smoke test

```text
Slice 7 of 8 for Pagerwise: CI/CD. Follow HOW_WE_BUILD.md.

Goal: every pull request is checked automatically, including a short load test for the streaming path, and every merge to main produces signed images.

Build (only for what exists today):
- Dockerfiles for api, consumer, indexer, simulator, docs_mock and web if missing (multi-stage, uv sync --frozen, non-root). A separate base image with the embedding and reranker weights baked in, rebuilt only when model versions change, so service builds stay fast.
- ci.yml on pull requests and main: concurrency cancel-in-progress, least-privilege permissions per job, every action pinned to a commit SHA.
  - lint: ruff, mypy, tsc, eslint, actionlint.
  - contracts: client regeneration diff, oasdiff, graphql-inspector, and a BACKWARD compatibility check of contracts/kafka against main. Breaking changes need the label breaking-change-approved.
  - unit, integration (testcontainers: Redpanda, Postgres, Redis; fastembed models cached with actions/cache), migrations (up/down/up + squawk), web (jest --ci).
  - eval-offline: retrieval and clustering evals run for real (no model needed); triage evals replay recorded responses. Sticky PR comment with metrics and deltas against main.
  - load-smoke, only when apps/consumer or the Kafka code changes (paths filter): compose up with --wait, 60s at 500 events/s, assert zero lost events and lag recovery.
- release.yml on main and v* tags: multi-arch Buildx with gha cache, push to GHCR with sha/branch/semver tags, SBOM + provenance, trivy (fail on CRITICAL), cosign keyless signing.
- No live-eval workflow (no GPU on runners); live REPORT.md and baseline.json are committed from local runs.
- From now on, slices merge through PRs (HOW_WE_BUILD.md section 7).

Check current official docs (web search) for every action used and pin current SHAs.
Will ask before: creating the GitHub repo or remote if none exists; any repository settings or branch protection.
Git: branch slice/07-ci-cd, opened as the first PR through the new flow.

Done when: actionlint is clean; the PR's checks pass on GitHub, including load-smoke; after merge, images are pushed and signed. Show the run summary and the load-smoke output.
```

### Slice 8. Instrumentation: OpenTelemetry across Kafka hops

```text
Slice 8 of 8 for Pagerwise: instrumentation. Follow HOW_WE_BUILD.md.

Goal: one alert can be followed from the simulator through Kafka, its retry hops, clustering, incident creation, retrieval and the model stream; lag, freshness and triage SLOs have metrics and alerts.

Build:
- One telemetry setup function for every Python app: OTLP to an OpenTelemetry Collector, resource attributes, structlog JSON with trace and span IDs shipped to Loki. Auto-instrument FastAPI, SQLAlchemy, Redis and httpx.
- Kafka spans by hand (check first whether a maintained aiokafka instrumentation exists; use it if so):
  - Producer span `alerts.v1 publish` with messaging semantic-convention attributes (system, destination, key, partition) and traceparent injected into headers.
  - Consumer span `alerts.v1 process` that links to the producer context (span links, as the messaging conventions recommend for batch receive), with partition, offset and group.
  - Retry hops link back to the original trace and record x-attempt, so a dead-lettered message shows its full history.
- Retrieval spans per source (fts, vector, deploys_http, rerank) with result counts and degraded=true on timeout; a query hash, never the query text.
- Model spans `chat <model>` with GenAI semantic-convention attributes (gen_ai.system=ollama, models, token counts) plus ttft_ms, tokens_per_second, citation_count and verdict.
- A span processor dropping denylisted attribute keys, with a unit test.
- Metrics: consumer lag per partition (end offset − committed), paused state by reason, events processed by outcome, DLQ by error class, ingest freshness (produce timestamp → DB commit), retrieval seconds by stage, TTFT and total triage seconds, LLM tokens, degraded sources, verdicts. Exemplars on histograms.
- Collector tail sampling: keep everything with errors, DLQ hops, degraded retrieval or triage over 45s; 10% of the rest.
- Grafana "Pagerwise / Stream" and "Pagerwise / Triage" dashboards. Alerts with runbook links: lag > 10k for 5m; freshness p95 > 5s for 10m; DLQ > 50 in 10m; INSUFFICIENT_EVIDENCE rate > 2× its 7-day baseline (a sign retrieval broke); triage p95 > 45s for 15m; Ollama unreachable for 2m.
- docs/slo.md: freshness 99% ≤ 5s; triage availability 99.5%; multiwindow burn-rate alerts.

Check current official docs (web search) for the OpenTelemetry messaging and GenAI semantic conventions (both still evolving, so note the versions used), span links in the Python SDK, and the collector's tail_sampling processor.
Will ask before adding: opentelemetry-* packages, structlog; the collector, Jaeger, Prometheus, Grafana and Loki services.
Git: branch slice/08-instrumentation, merged by PR.

Done when: after a 60s storm, the Jaeger API returns a trace with a retry hop; print it as publish → process (attempt 1, error) → retry.30s publish → process (attempt 2, ok) → incident upsert. Trigger one triage and print its span tree with per-stage durations. The denylist test passes.
```
