# Pagerwise

Incident-response copilot: alerts in, cited triage briefs out, built in thin slices. Slice plan: [02-pagerwise.md](02-pagerwise.md).

- **How we work:** [HOW_WE_BUILD.md](HOW_WE_BUILD.md). It wins over everything else, including slice prompts.
- **Where it's heading:** [docs/architecture.md](docs/architecture.md). A destination, not a to-do list.
- **Why things are the way they are:** [docs/adr/](docs/adr/). Add one for every real choice.
- **What went wrong before:** [docs/challenges.md](docs/challenges.md). Each slice adds what it hit.
- **Error codes:** [docs/problems.md](docs/problems.md). Every new `ProblemCode` gets a row.

## Run it

```bash
docker compose up -d --wait               # Postgres 18 + pgvector :5435, Redpanda (Kafka API) :19092, Redis :6379
uv run alembic upgrade head
make topics                               # alerts.v1, alerts.retry.30s, alerts.retry.5m, alerts.dlq (idempotent)
ollama pull qwen3.5:9b-q4_K_M             # once; Ollama runs natively on the Mac, not in Docker (ADR 0001)
uv run python scripts/seed.py corpus      # regenerate data/corpus/ + evals/planted_facts.json (deterministic; committed)
uv run python scripts/seed.py deploys     # 30 days of deploys into the deploys table
uv run python scripts/seed.py graph       # data/service_graph.yaml -> services, service_edges (clustering reads them)
uv run python scripts/seed.py alerts      # 500k historical alert_events via COPY (replaces earlier seeded history)
uv run python -m pagerwise_docs_mock      # mock docs API on :8002 serving data/runbooks + data/corpus (--fail-rate 0.1)
uv run python -m pagerwise_indexer        # import runbooks + postmortems from it; reruns send If-None-Match (304s)
uv run uvicorn pagerwise_api.main:app --port 8001
uv run python scripts/ask.py "Why is payments p99 high?"   # answer + citations resolved to chunk text
curl 'localhost:8001/v1/search?q=ledger+pool+exhaustion'    # hybrid search with every stage's rank and timings
make smoke            # generated client end to end: 3 incidents, paging, one streamed triage, GraphQL
uv run python -m pagerwise_consumer                                  # alerts.v1 + retry topics -> alert_events
uv run python -m pagerwise_simulator --rate 200 --duration 10 --malformed-rate 0.01
uv run python scripts/incidents.py        # busiest open incidents and the alerts clustered into each
make storm            # done-when load test: 2,000/s for 3 min, a replica killed; takes ~10 min (5 min retries)
make test             # unit tests, offline (no Ollama, no DB, no model download)
make test-int         # service tests (testcontainers Postgres + pgvector; needs Docker)
make codegen          # regenerate the client, contracts/schema.graphql and the Kafka alert model
make contract-check   # oasdiff: the app's emitted OpenAPI vs contracts/openapi.yaml
```

Run scripts from the repo root: document paths are stored relative to it.

## Rules that are easy to break

- Model name and options come from `settings.py`; prompts live only in `prompts.py`, and any wording change bumps
  its version. Every model call goes through `llm.chat` or `llm.chat_stream`, which refuse a prompt over the `num_ctx` budget before
  sending: Ollama truncates over-long prompts silently.
- Always pass `num_ctx` to Ollama: its default silently truncates long prompts.
- Token counts come from `embedding.count_tokens`, never from fastembed's `token_count` directly: that one stops
  at bge's 512-token window (ADR 0003).
- Changing the embedding model changes `EMBEDDING_DIM` and every stored vector: it needs a migration and a
  re-embed (slice 6), not a settings change.
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

