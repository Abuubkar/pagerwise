---
status: accepted; reranker default superseded by ADR 0009 (off: no gain with v2 + sibling chunks)
date: 2026-11-02
---

# Seeded corpus, a paginated docs import, and hybrid retrieval with a small reranker

**Corpus.** `scripts/seed.py corpus` renders 120 runbooks (12 services x 10 failure modes) and 60 postmortems from
Jinja templates (`data/templates/`) into `data/corpus/`, deterministically (`--seed`, dates relative to a fixed
`--anchor`), and writes `evals/planted_facts.json`: 420 facts, each with the document and section it was planted in,
a question, and strings the answer must contain. Every runbook plants a threshold, an error code and a config
value; every postmortem plants a root cause (category + component), and the recent ones point at a seeded deploy.
The generated files are committed so reviewers can read them; they are regenerated, never edited. The 12 services
and their dependencies live in `data/service_graph.yaml`, which the simulator and the seeds both read.
`scripts/seed.py deploys` fills the `deploys` table with 30 days of deploys.

**Import.** `apps/docs_mock` imitates a docs API: 20 documents per page, oldest change first, `Link: rel="next"`,
per-page ETags, cursors that go stale (404) when the corpus changes, and test hooks to inject 5xx or edit a
document. `apps/indexer` is the only way documents reach the store (it replaces `scripts/load_docs.py`). It saves
its place after every page, in the same transaction as that page's documents; sends If-None-Match for pages it has
seen and keeps each page's next link next to its ETag, so a 304 still knows where to go; retries 5xx with backoff;
and on a stale cursor restarts from page 1 with `since` = the newest change already stored. A document whose hash
is unchanged is skipped; a changed one has its chunk set replaced in one transaction.

**Retrieval.** `retrieval.hybrid_search` replaces slice 1's vector-only search everywhere (ask, triage, and the new
`GET /v1/search`). Full-text search (a generated `tsvector` column with a GIN index, `websearch_to_tsquery`,
`ts_rank_cd`) and pgvector cosine search (HNSW, m=16, ef_construction=64) each take their top 40 on separate
connections at the same time; Reciprocal Rank Fusion (k=60) merges them; a cross-encoder reranks the top fused
candidates. Every stage's rank is kept on each hit.

**Reranker: ms-marco-MiniLM-L-6-v2 on the top 10, not bge-reranker-base on the top 40.** Measured by
`evals/rerank_choice.py` on 80 planted-fact questions (60 runbook facts, 20 postmortem root causes), M-series
laptop CPU, warm models:

| setup | hit@1 | hit@8 | MRR@10 | search p50 / p95 |
|---|---|---|---|---|
| full-text only | 0.68 | 0.71 | 0.69 | - |
| vector only | 0.85 | 1.00 | 0.93 | - |
| RRF, no reranker | 0.94 | 1.00 | 0.97 | 16 / 24 ms |
| MiniLM-L-6, top 10 | 0.96 | 1.00 | 0.98 | 562 / 595 ms |
| MiniLM-L-6, top 20 | 0.96 | 1.00 | 0.98 | 1,116 / 1,272 ms |
| MiniLM-L-6, top 40 | 0.96 | 1.00 | 0.98 | 2,402 / 5,064 ms |
| bge-reranker-base, top 40 | 0.95 | 1.00 | 0.97 | 14,972 / 22,824 ms |

A cross-encoder reads every candidate in full, so its cost is candidates x tokens; on CPU, 40 chunks of ~420 tokens
is about 17k tokens per query. bge-reranker-base was 6x slower than MiniLM-L-6 and no better here. MiniLM on the top
10 keeps the measured gain (2 of 80 questions moved to rank 1) at about half a second, which is small next to a
20-second triage. **It misses the plan's 250 ms retrieval p95**; `RERANK_CANDIDATES=0` meets it (24 ms) with hit@1
0.94. Hybrid fusion is clearly worth it: vector alone gets hit@1 0.85, and full-text alone finds exact tokens that
vector search ranks low (an error code: full-text 1st, vector 18th).

**Alternatives considered.**
- *bge-reranker-base* (the plan's choice): measured above; too slow on CPU for no gain on this corpus.
- *No reranker*: meets the latency target with almost the same quality on these questions. Kept as a setting.
- *Sending only part of each chunk to the reranker* (e.g. the first 128 tokens): cheaper, but the planted facts sit
  deep in Diagnosis and Mitigation sections. Not measured yet.
- *A separate search engine* (OpenSearch, as Shelfsense uses): Postgres already does both searches over a few
  hundred chunks in under 30 ms.

**Assumptions.**
- The planted-fact questions are easy: each names the service and the failure mode, which also appear in the
  document's title. Slice 6's golden set has paraphrased and unanswerable questions; rerun this measurement there
  before trusting the reranker's gain (or its absence).
- `websearch_to_tsquery` ANDs every word, so full-text search returns little for long natural questions and is mainly
  useful for exact tokens (codes, metric names). Fusion covers for it. An OR query was not tried.
- The docs API lists documents oldest change first; the `since` restart depends on that order.
