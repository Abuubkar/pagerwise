---
status: accepted; "Where the model call runs" superseded by ADR 0008
date: 2026-11-02
---

# Spec-first REST contract, FastAPI's built-in SSE, triage generated when its stream opens

**Contract.** `contracts/openapi.yaml` (OpenAPI 3.1) is hand-written and is the source of truth, as in Ledgerline
(its ADR 0007). `make contract-check` dumps the app's emitted OpenAPI and runs `oasdiff breaking --fail-on ERR`
(tufin/oasdiff v1.35.0); it was checked to exit 1 when a required response field is removed. `make codegen`
generates `packages/clients/python` with openapi-python-client 0.29.1 and prints `contracts/schema.graphql`; a
unit test fails if the GraphQL schema drifts. Errors are RFC 9457 `application/problem+json` with a `code` enum
(docs/problems.md). Pagination cursors are opaque HMAC-signed keysets bound to their filters (same scheme as
Ledgerline's ADR 0006), shared by REST and the GraphQL Relay connection.

**Streaming.** `GET /v1/incidents/{id}/triage/stream` uses FastAPI's own `fastapi.sse.EventSourceResponse`
(FastAPI 0.162), which also sends keep-alive comments. Events: `token`, `citation`, `section_complete`, then `done`
(the TriageBrief) or `error`. `citations.TagScanner` emits a citation only once a complete `[Cn]` has arrived and
splits token events at event boundaries, so events arrive in text order and the tokens concatenate to exactly
what the model wrote. The brief is checked by `citations.parse_brief` when the stream ends; a broken contract is
an `error` event with code `format_invalid`, never a `done`.

**Where the model call runs.** `POST /triage` inserts a `queued` row and returns 202. The first `GET /stream`
claims it (`UPDATE ... WHERE status = 'queued'`) and generates the brief while streaming it; any later connection
replays the stored result in the same event shapes. A partial unique index on `(incident_id, incident_version)
WHERE status IN ('queued', 'running')` makes a concurrent second POST a 409 `triage_in_progress` carrying the
winner's `triage_id`. A running triage renews `heartbeat_at` every 15 s; one silent for 120 s is abandoned and
stops blocking.

## Considered options

- **sse-starlette**: the usual choice before FastAPI shipped SSE. Not needed now; one dependency fewer.
- **Generate in a background task started by POST**: the brief starts sooner, but its events live in one process's
  memory, are lost on a restart and can't be served by another API replica.
- **Hold back `[C`-prefixed text until the tag closes**, so tokens never contain half a tag: cleaner tokens, but
  the UI's text lags the model and the scanner gets more state. Passing text through and emitting `citation`
  separately keeps tokens immediate.
- **OpenAPI 3.2's `itemSchema`** for the event stream, as FastAPI emits it: the document is 3.1, so the stream is
  `type: string` and each event's payload is its own component (`TokenEvent`, `CitationEvent`, ...), which also
  makes the generated client produce a model for each.

## Consequences and workarounds

- A streaming endpoint has already sent `200` by the time its body runs, so the open-and-claim step is a FastAPI
  dependency (`_open_triage_stream`): a missing triage is a real 404 problem, not an empty 200 stream.
- openapi-python-client reads `text/event-stream` as one string after the stream ends, so
  `packages/client-sse` (hand-written, outside the generated `packages/clients/`) reads events as they arrive and
  parses each into its generated model.
- Only one connection can watch a triage while it is generating; a second gets 409 until it finishes, then a
  replay. Slice 5 moves generation to a worker publishing to Redis, and every viewer subscribes; the SSE contract
  stays the same.
- A client that disconnects mid-stream leaves the run `running` until its heartbeat goes stale (≤ 2 min). The
  generator is cancelled with the connection, which should close the Ollama request too; not verified yet.

## Assumptions

- One API process during development; the heartbeat covers a process that dies mid-triage.
- Ollama's final stream chunk carries the token counts (true for ollama-python 0.6.3 / Ollama 0.40.6).
