# Challenges and how we handled them

What went wrong or got in the way while building Pagerwise, slice by slice: what happened, what we did, why, and
what else we could have done. ADRs record the choices; this file records the bumps that led to some of them.

## Slice 1: walking skeleton

**fastembed's `token_count` caps at 512.** It counts the tokens the model would see, so it never returns more
than bge-small's 512-token window. Chunk sizing was unaffected (anything over 500 still read as too big), but the
prompt-budget guard estimated 680 tokens for a 3,255-token prompt and would never have fired.
- *Did:* `count_tokens` counts line by line and sums (exact for WordPiece; within 0.3% of Ollama's count on a real
  prompt). Found by measuring the estimate before writing it into ADR 0003, not by a test.
- *Alternatives:* reach into fastembed's internal tokenizer and turn truncation off (private attribute, breaks
  on upgrade); add `tokenizers` as a direct dependency (a second way to load the same tokenizer).

**Bare headings became their own chunks.** "## Likely causes" directly above "### Ledger pool" made a two-word
piece that merged upward and moved the whole chunk's heading path to the document title.
- *Did:* a heading with no text of its own is carried into the next section.

**Small tail sections.** Each runbook's short "Escalation" section became a 47-token chunk, because merging only
looked forward from a small chunk.
- *Did:* a piece merges into the previous chunk when either side is under 300 tokens and the result fits in 500.
  One tail (49 tokens) still stands alone where the merge would reach 515.

**Prompt evaluation, not generation, is the slow part.** qwen3.5:9b evaluates ~213 prompt tokens/s on the M1 Pro:
15.3 s of a 24 s answer for a 3,250-token prompt. The plan's TTFT target (≤ 10 s on ~7k tokens) won't hold
as written; recorded as an at-risk assumption in ADR 0001 for slices 5–6.

**Six runbooks are one retrieval window.** They make 8 chunks, and top-8 retrieval returns all of them, so slice 1
tests grounding and abstention, not retrieval. The cosine order is still sensible (the planted fact's chunk ranks
first at distance 0.114; the off-topic question's best match is 0.366). Retrieval is measured from slice 4.

## Slice 2: contracts and streamed triage

**A streamed 404 came back as an empty 200.** The stream endpoint looked up the triage on its first line, but a
generator endpoint has already sent `200` and its headers by the time its body runs, so the problem was lost.
- *Did:* the lookup-and-claim moved into a FastAPI dependency, which runs before the response starts.
- *Alternatives:* return a plain `StreamingResponse` from a normal function (loses FastAPI's SSE encoding and
  keep-alives); check twice (once in a dependency, once in the body).

**The 409 path crashed with `MissingGreenlet`.** After catching the unique-index violation and rolling back, the
code read `incident.version` again; the rollback had expired it, and the lazy reload isn't allowed under asyncio.
- *Did:* read the version into a local before committing. Found by the smoke script's second POST.

**`section_complete` arrived after the next section's first word.** Token events were emitted a whole stream
piece at a time, so a piece like `"\nThe"` went out before the scanner noticed the heading line had ended.
- *Did:* token events are split at event boundaries; a test checks the order and that tokens concatenate to the
  model's exact text for pieces of 1, 3, 7 and 50 characters.

**The model filled "Similar incidents" with the incident itself.** With no postmortems in the evidence,
`triage/1` echoed the incident description under that heading. `parse_brief` rejected it (`format_invalid`,
`similar_incidents: no citations`), as it should.
- *Did:* `triage/2` says plainly that the incident description is not evidence and that a runbook is not a past
  incident. The next run wrote "None in the evidence." One example, not an eval: slice 6 measures format
  validity over the golden set.

**FastAPI emits OpenAPI 3.2's `itemSchema` in a 3.1 document** for SSE routes, and labels the route's 404/409
problems `text/event-stream`.
- *Did:* the OpenAPI hook rewrites the stream to `type: string`, moves problems to `application/problem+json`, and
  adds each event payload as a component (ADR 0004).

## Slice 3: Kafka ingestion

**The sticky assignor could give a new replica no alert partitions.** The rebalance service test failed about
two runs in three: the second consumer was assigned 18 partitions but processed nothing. Sticky balances the
total across the three subscribed topics, and its picks were 12 of `alerts.retry.30s` plus 6 of
`alerts.retry.5m`, which are idle unless something is failing.
- *Did:* round-robin, which splits each topic evenly; the test now also asserts every replica owns part of every
  topic. Three runs in a row pass.
- *Alternatives:* range (per topic, but uneven across topics with more members); a separate consumer group for
  the retry topics.

**Not-yet-due retries would have tripped backpressure.** At 5% transient failures and 2,000/s, about 3,000
messages sit in `alerts.retry.30s` at any moment. Holding fetched-but-not-due messages in memory would have counted
them against the 500-record high-water mark and paused ingest of healthy alerts.
- *Did:* the poll loop seeks a retry partition back to its first not-due message and pauses it until then; records
  fetched before the seek are dropped when they arrive (`seek_to`), and the offset tracker forgets them.

**A killed replica stalls its partitions for the session timeout.** In the storm, replica 0 was SIGKILLed at
60 s; the survivor took its partitions about 10 s later (aiokafka's default `session_timeout_ms`), by which time
alerts.v1 lag was 21k. It caught up in about 16 s, pausing fetches 68 times on the way (500 records queued every
poll), and redelivery cost 477 duplicates (absorbed by `ON CONFLICT`). That stall is why first-try ingest
freshness p95 was 6.3 s against the plan's 5 s target.
- *Not done:* tuning the session timeout; slice 8 adds lag and freshness metrics and SLOs to tune it against.

**Small surprises from current versions.**
- `uuid.uuid7()` is Python 3.14; this project is on 3.13, so producers use `uuid4`.
- aiokafka's zstd compression needs an extra on Python < 3.14; producers send uncompressed.
- `rpk redpanda start --set=key=value` is passed through to Redpanda, which rejects it; `--set` and the value must
  be separate arguments.
- `testcontainers.kafka` is deprecated in testcontainers 4.15; the Redpanda container is in
  `testcontainers.community.kafka` and needs no extra.
- aiokafka's `describe_consumer_groups` returns raw protocol tuples, not objects.

## Slice 4a: corpus, import, hybrid search

**The plan's reranker can't meet the plan's latency target on a CPU.** bge-reranker-base took 15 s at the median
to rescore 40 candidates; ms-marco-MiniLM-L-6-v2 took 2.4 s. Not a bug: a cross-encoder reads every candidate in
full, about 17k tokens per query here. Neither beat plain RRF by much on the planted-fact questions (hit@1 0.94
before reranking).
- *Did:* MiniLM-L-6 on the top 10 fused candidates (about 0.55 s, hit@1 0.96). ADR 0006 has the table.
- *Not done:* retrieval p95 is 595 ms against the 250 ms target. `RERANK_CANDIDATES=0` meets it; slice 6's harder
  questions decide whether reranking earns its cost.

**Full-text search finds little for natural questions.** `websearch_to_tsquery` requires every word to match, so
"what caused the card-auth OOM kills in October?" has no full-text hits at all; full-text alone has hit@8 0.71.
It's still what finds exact tokens: for the error code `LED-POOL-626` it ranked the right runbook 1st where
vector search ranked it 18th.
- *Not done:* an OR-of-terms query; measure it in slice 6.

**A 304 carries no body, so it doesn't say where the next page is.** A Link header on a 304 isn't guaranteed.
- *Did:* the importer stores each page's next link next to its ETag (`import_state.pages`), so a run of 304s still
  walks the whole listing.

**Generated text needed care to read like the real thing.** The first render used the service's first alert for
every failure mode, lowercased "OOM" and "TLS", dated some postmortems after the anchor day, and filled contributing
factors with Faker's Latin placeholder sentences.
- *Did:* an alert name per service and failure mode, phrase-case mode titles, dates clamped to the anchor, and
  written factor sentences. Faker is only used for people's names.

## Slice 4b: clustering, Redis, partitioned alerts

**The online migration deadlocked with the consumer, and my first fix was for the wrong cause.** Both live runs of
the partition migration under writes logged one "deadlock detected"; the consumer retried the batch and lost
nothing. I guessed the backfill's foreign-key checks (`FOR KEY SHARE`) against clustering's `FOR UPDATE` on
incidents and changed it to `FOR NO KEY UPDATE`. The second run deadlocked again. The Postgres log said what was
actually happening: migration 0006 had locked `incidents` (adding the shadow's foreign key) and was waiting for
`alert_events` (creating the trigger), while a consumer transaction held `alert_events` and wanted `incidents`.
- *Did:* 0006 now builds everything slow first, then locks both tables together with a 500 ms `lock_timeout`
  (under the 1 s deadlock check) and retries, so it backs off instead of a writer being killed. The third run had
  no deadlock and no failed batch. `FOR NO KEY UPDATE` stayed: it's the right lock for a non-key update anyway.
- *Lesson:* read the deadlock report (`docker compose logs postgres`) before fixing; it names both statements.
- *Not verified:* one clean run isn't proof; the deadlock hit once per run before. The swap's own test writer
  doesn't touch incidents, so no test covers this interleaving.

**Slice 4a's corpus wasn't deterministic across processes.** Regenerating changed 6 postmortems: the action-item
owner came from `rng.choice` over a set, and set order depends on the per-process hash seed.
- *Did:* sorted the set; the corpus is now byte-identical under three different `PYTHONHASHSEED`s, and the 6 files
  are regenerated in this change.

**Clustering costs ingest headroom.** At 2,000 alerts/s on one replica, lag peaked at 3,398 against 293 in slice 3,
with 227 backpressure pauses; it drained within 5 s of the storm ending. Most batches only add repeat alerts to
known incidents, but each still takes advisory locks, looks up recent fingerprints and updates incident rows.
- *Not done:* an in-memory fingerprint -> incident cache per partition would skip most lookups; measure first.

**Small things.** asyncpg runs one statement per `execute`, so multi-statement migration strings failed until split.
`pg_class.relkind` is Postgres's `"char"` type: it comes back as bytes and won't concatenate with text without a
cast. `docker compose logs --since` reads a timestamp without a zone as local time.

## Slice 5: triage worker, evidence sources, live UI

**A refactor silently deleted the DLQ replay route.** Replacing the triage routes in `main.py` cut everything up to
the next marker, including `POST /v1/admin/dlq/replay`. `make contract-check` failed with
`api-path-removed-without-deprecation` before anything else noticed.
- *Did:* restored it. The contract check is what makes a refactor of the route file safe.

**The subscription crashed with `MissingGreenlet`, a mistake CLAUDE.md already warns about.** It ended the read
transaction (rollback) and then built the response from the row, whose attributes the rollback had expired. The UI
saw a WebSocket that connected and never delivered.
- *Did:* copy the row out first; a service test now runs the subscription against real Redis and Postgres and fails
  with the old order.

**uvicorn can't accept WebSockets without a WebSocket library.** The browser's WebSocket failed with "Unsupported
upgrade request" in the API log; HTTP and SSE had worked all along because they're plain HTTP.
- *Did:* added `websockets` (asked first; `uvicorn[standard]` would also change the event loop and HTTP parser).

**Live updates that arrive before the first page were lost.** The list replaced its rows when the first page
landed, dropping any incident the subscription had already put on top. The Jest test caught it.
- *Did:* live updates are kept and re-applied on top of the first page.

**The plan's evidence timeouts don't fit the reranker.** 300 ms for runbooks and postmortems would degrade both on
every triage: hybrid search with reranking takes ~0.5 s, and two run at once.
- *Did:* 2 s for the document sources (500 ms for deploys), and the worker warms both models before its first run.

**Slice 4a's postmortem citations were labelled `runbook`.** `Citation.source_type` was the constant `runbook`.
- *Did:* `runbook | postmortem | deploy`; deploys cite with a null `chunk_id`.

**With the deploy source down, the replayed incident's brief still claimed a deploy.** The first sentence said the
incident followed the redis-cache 6.38.7 deploy, cited to the postmortem. Banner shown, no deploy citations, so the
script's automatic check said PASS; reading it, rule 7 ("never say there was or wasn't a recent deploy") was broken.
Tightening the rule (`triage/4`: other evidence doesn't stand in for an unavailable source; a postmortem describes a
past incident) changed nothing for the replay. The same incident opened *today*, so that the postmortem really is
about a past incident, gave a clean brief: "since deploys are unavailable … we cannot confirm".
- *Learned:* the replay is a special case: the postmortem describes this exact incident, so it does "know" about
  the deploy. It's also a warning that the automatic check (citations only) misses claims sourced elsewhere.
- *Not done:* a deterministic guard (reject or flag deploy claims in Likely cause / Blast radius when deploys are
  degraded). Slice 6's degraded-honesty eval with the calibrated judge measures this over the golden set first.

**A blocking Redis read was cut off by redis-py's default 5 s socket timeout.** The SSE reader waited up to 5 s per
`XREAD`; the live run, where the model takes 20+ s to its first token, crashed the stream. Tests never waited that long.
- *Did:* 2 s blocking reads and a 30 s socket timeout in `bus.connect`.

**The contract's `CitationEvent` schema still said `source_type: runbook`.** I'd updated `Citation` and missed its
copy; `make contract-check` can't see SSE event schemas (no operation references them). The generated Python client
rejected the first postmortem citation of the live run.
- *Did:* fixed the contract; a unit test now parses every event payload the API builds with the generated client.

## Slice 6a: golden set, retrieval and clustering evals, v2 embeddings

**The first golden set made clustering look perfect.** F1 1.000, because every golden incident was one alert rule
on one service: the service-graph rule was never exercised.
- *Did:* about 40% of incidents also page a neighbouring service. F1 dropped to 0.847, which is the real number.

**A lower similarity bar for neighbours can't group cascades.** Measured on dev: cascade alerts score 0.56–0.69
against their incident, unrelated neighbour incidents 0.59–0.76.
- *Did:* kept clustering as is, recalibrated the gate (to 0.84, after first proposing 0.85, which the baseline
  itself missed by 0.003). Cross-service grouping needs topology and timing signals; real data first.

**Recall@8 0.6–0.7 was one pattern, and the reranker made it worse.** The gold runbook's second chunk didn't restate
the symptoms, so it ranked low; the cross-encoder, scoring each chunk alone, pushed it further down.
- *Did:* sibling chunks (Recall@8 1.00 on both splits); reranker off (no metric changed, ~490 ms saved).

**My own tooling was wrong twice; the baseline check caught both.** `make eval` still forced v1 after the default
became v2, and the baseline treated a faster clustering run (fewer seconds) as a quality drop.
- *Did:* the Makefile passes `--embedding` only when given; the baseline guards an explicit list of quality
  metrics.

**Full-text search contributes nothing on incident queries** (0.00 on both metrics): `websearch_to_tsquery` ANDs
every word. Noted in ADR 0009; OR-of-terms is the next thing to try.

## Slice 6b: triage eval, citation checks, cause decision line

**No local judge model could be trusted for citations.** judge/1 with llama3.1:8b got kappa 0.371 against the hand
labels; three of those disagreements were my own labelling mistakes (one inconsistent with another row, one needing
a time the judge couldn't see). Per-fact statuses with the yes/no rule in code helped gemma4:12b to 0.60–0.61 on the
tune rows, but held-out rows gave 0.26: the prompt was fitting the tune rows.
- *Did:* stopped tuning; citations are checked deterministically (tokens in the cited source, deploy timing,
  postmortems framed as past). Held-out agreement 0.81, kappa 0.61. ADR 0010.

**The label check compared labels with the wrong briefs.** It took each labelled sentence's other citations from the
run being scored; after a fresh live run those sentences didn't exist, multi-cite rows failed, and kappa "fell" from
0.61 to 0.375.
- *Did:* the check reads the run the labels were drawn from (`CALIBRATION_BRIEFS`): it measures the check, not a run.

**The model cited deploys from after the incident as its cause.** The deploy window ran 15 minutes past the open
time, and a 9B model can't compare ISO timestamps reliably. The golden deploys also gave the cause away (author
"Golden Set", summaries naming the failure).
- *Did:* deploys end at the open time and each says "It was N minutes before the incident opened"; golden deploys
  look like any release. Deploy citations after start: 5 → 0.

**The model reasons its way to "no match" but won't write the token.** With every rule in prose, 12 of 30
unanswerable briefs explained that nothing matched and still came out CAUSE_IDENTIFIED; 12 blamed a nearby deploy.
- *Did:* Likely cause opens with `Match: [Cn]` or `Match: none`, applied in code (`LikelyCauseGate`); a deploy alone is
  never a cause. Abstention 0.10 → 0.40 on the full dev run, still under its 0.80 gate. What's left is the model
  matching a runbook for a different failure (kernel soft lockup → "CPU saturation"), the misleading-context failure
  small models are known for; no wording change will fix it on this model.

**The gate dropped causes written on the decision line.** The model sometimes wrote `Match: [C1] The pool is
exhausted…` on one line; the gate dropped the whole line and left Likely cause empty (3 `format_invalid` briefs in
the full run).
- *Did:* the gate keeps what follows the tags on that line; a test covers it. Replaying the same recorded outputs
  through the fixed gate: format validity 0.902 → 0.927, hit@1 0.76 → 0.80.

**The decision line cost citation discipline.** triage/6 briefs have 13 uncited cause or impact sentences in the
first repeat, triage/5 had 3; many are sentences about the rule itself ("A deploy shortly before the incident is not
mentioned"). Unsupported-claim rate 0.046 → 0.158 and format validity under its gate.
- *Did:* kept triage/6 anyway: a wrong cause on an unanswerable incident looks exactly like a right one, while a
  missing tag is visible. Recorded as a miss in ADR 0010; not tuned further.

**I moved gates after seeing results, and showed smoke-run noise as misses.** I proposed TTFT 20 s from one 18.8 s
run, then lengthened the prompt and went over it; a 26-brief smoke run's numbers read as new failures.
- *Did:* gates are frozen for the rest of the slice; only full runs (all cases, 3 repeats) are judged against them;
  misses are reported as misses.

## Slice 7: CI/CD

**Lint had never run.** There was no ruff or mypy config, so ruff used its defaults and found 74 issues, mypy 30, and
the code carried `noqa: ANN…` comments for rules nobody enabled. eslint wasn't installed (Next 16 dropped `next lint`).
- *Did:* pinned the rules in pyproject.toml (ruff defaults at 120 columns, mypy on the apps), fixed every finding with
  typing-only changes (integration tests pass, generated corpus and golden set byte-identical), added eslint 10 with
  eslint-config-next; its one real finding was TriagePanel resetting state in an effect (now a `key`).

**The triage recordings were made against a stale database.** CI imports the committed corpus fresh, and the first
eval-offline run missed a recording. Slice 4b's seed change had reshuffled the action-item owners in 6 postmortems;
my local database was never re-imported, so every slice 6 eval and recording used the old text of those 6.
- *Did:* a replay miss now prints a diff against the nearest recording (that's how it was found); re-imported, and
  re-recorded only the changed calls with `--fill` (which now covers triage and each repeat); the eval refuses to run
  when the database's documents differ from `data/`.

**rpk says a schema is compatible or not, and exits 0 either way.**
- *Did:* `scripts/breaking_changes.sh` reads its JSON verdict; tested with a breaking and a compatible change.

**main already misses four triage gates, so a gate-checking CI job would be red forever.**
- *Did:* asked; with `--baseline`, misses the baseline shares are reported, not failed (ADR 0011). No threshold moved.

**The runner ran out of disk building the consumer image** (slice 8's first release; a rerun passed). A models image
is built three times on one runner: for the scan, then for both platforms, each on the 0.6 GB models base.
- *Did:* the images job deletes preinstalled toolchains it doesn't use (.NET, Android, GHC, CodeQL) for models
  images, and removes the scan image after trivy.

## Slice 8: Instrumentation

**The aiokafka instrumentation exists, but its consumer spans end at the fetch.** Its `receive` spans close when
`getmany` returns, and the consumer processes records later, in partition batches. Its producer *appends*
`traceparent`, so a republished alert would carry two, and the next hop would read the stale one first.
- *Did:* used it for publish spans (asked), and added our own per-message `process` span: its parent is the creation
  context, and it links to the batch span. `route_failure` now drops incoming trace headers (ADR 0012).

**A retried alert gets ~30 fetch spans.** Messages on a retry partition are re-fetched every time an earlier one
becomes due: the consumer seeks back to the first not-yet-due message rather than holding it in memory. That's slice
3's design (cheap re-reads, no memory), but the instrumentation makes each re-read a span.
- *Did:* left as is; `scripts/trace.py` counts them and doesn't print them.

**Tail sampling as planned dropped most triage traces.** A normal 40 s triage has no error and no degraded source,
so only the 10% rule could keep it. The first done-when triage wasn't in Jaeger.
- *Did:* added an `every-triage` policy (on `pagerwise.triage_id`). Triages are one per new incident, so the volume
  is negligible. It's a deviation from the plan's list, called out in the PR.

**The Ollama request wasn't under the chat span.** The ollama client sends the request on the first iteration of the
stream, not when `chat()` returns, so the `trace.use_span` around `chat()` didn't cover it.
- *Did:* the first chunk is awaited inside it too (`llm.chat_stream`).

**Telemetry showed full-text search finding nothing for triage.** Every triage trace so far has `fts`
`result_count=0` for both runbooks and postmortems. The triage query is long (title, services, alert summaries), and
`websearch_to_tsquery` ANDs every term, so vector search carries triage alone.
- *Not done:* changing retrieval belongs with an eval run (ADR 0009); noted for the next retrieval change.

**Small things:** the collector renamed its `otlp`/`otlphttp` exporters to `otlp_grpc`/`otlp_http` (old names
warn). Prometheus 3 writes histogram `le` labels as `5`, not `5.0`; the rules match either. Unit `"1"` on a gauge
becomes a `_ratio` suffix, so `pagerwise.ollama.up` has no unit.
