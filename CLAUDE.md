# Pagerwise

Incident-response copilot: alerts in, cited triage briefs out, built in thin slices. Slice plan: [02-pagerwise.md](02-pagerwise.md).

- **How we work:** [HOW_WE_BUILD.md](HOW_WE_BUILD.md). It wins over everything else, including slice prompts.
- **Where it's heading:** [docs/architecture.md](docs/architecture.md). A destination, not a to-do list.
- **Why things are the way they are:** [docs/adr/](docs/adr/). Add one for every real choice.
- **What went wrong before:** [docs/challenges.md](docs/challenges.md). Each slice adds what it hit.
- **Error codes:** [docs/problems.md](docs/problems.md). Every new `ProblemCode` gets a row.

## Run it

```bash
docker compose up -d --wait               # Postgres 18 + pgvector on :5435
uv run alembic upgrade head
ollama pull qwen3.5:9b-q4_K_M             # once; Ollama runs natively on the Mac, not in Docker (ADR 0001)
uv run python scripts/load_docs.py        # chunk + embed data/runbooks/*.md; unchanged files are skipped
uv run uvicorn pagerwise_api.main:app --port 8001
uv run python scripts/ask.py "Why is payments p99 high?"   # answer + citations resolved to chunk text
make smoke            # generated client end to end: 3 incidents, paging, one streamed triage, GraphQL
make test             # unit tests, offline (no Ollama, no DB, no model download)
make test-int         # service tests (testcontainers Postgres + pgvector; needs Docker)
make codegen          # regenerate the client and contracts/schema.graphql after changing contracts or GraphQL
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
