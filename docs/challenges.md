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
