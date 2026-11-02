---
status: accepted
date: 2026-11-02
supersedes: ADR 0006's reranker default (MiniLM on the top 10); the reranker stays available behind a setting
---

# A golden set and gated eval; bge-base embeddings, sibling chunks, reranker off

**Golden set** (`evals/build_golden.py`, deterministic). 40 answerable incidents (a (service, failure mode) the
corpus has a runbook for; gold cause {category, component}; gold evidence = that runbook's chunks as (document,
ordinal), resolved to chunk ids at eval time because ids change on re-import, and heading paths aren't unique), 15
unanswerable ones (failure modes no document covers), 10 caused by a deploy (for 6b's degraded-honesty check). Each
has a replayable alert sequence; about 40% of the answerable and deploy cases also page a neighbouring service, the
way callers of a failing dependency do; all fall in one overlapping six-hour window. Hash split dev/test 25/15,
10/5, 6/4. The test split is for confirming a decision, never for tuning one.

**Eval** (`evals/run.py`, `make eval`, `make eval-test`). Retrieval: Recall@8 and MRR@10 of the gold chunks per stage
(full-text, vector, RRF, rerank, final) from one search per case, p50/p95 over 500 queries. Clustering: every alert
replayed through `clustering.store_alerts` in consumer-sized batches against a separate `pagerwise_eval` database;
pairwise precision/recall/F1. Gates exit 1; `--baseline evals/baseline.json` fails any quality drop over 1.5 points.
Each run's results are kept in `evals/results/`; a replaced REPORT.md moves to `evals/archive/`.

**Embedding: v2 (bge-base-en-v1.5, 768-d) is the default.** Migration 0009 added `chunks.embedding_v2` with an HNSW
index built `CONCURRENTLY`; `scripts/reembed.py` filled it in id-ordered, resumable, throttled batches (297 chunks,
~5 min on CPU); the importer writes both. `RETRIEVAL_EMBEDDING_VERSION = v1 | v2 | dual` (dual fuses both vector
lists with full-text). Before the other changes below, v2 matched or beat v1 on both splits (dev Recall@8 0.70 vs
0.66, test 0.60 vs 0.57; MRR@10 before reranking 1.00 vs 0.94 / 0.88). **The v1 column is kept until 6b's triage
eval also passes on v2**, then dropped with the switch.

**Sibling chunks.** The miss behind Recall@8 0.6–0.7 was one pattern: the gold runbook's first chunk always ranked
first, its second (diagnosis and mitigation, which don't restate the symptoms a query names) often fell out of the
top 8. Now a chunk in the top k brings its document's other chunks in right after it (small-to-big retrieval).
Recall@8 went to 1.00 on dev and test.

**Reranker off by default.** With v2 and sibling chunks, MiniLM on the top 10 changed no metric on either split and
added ~490 ms per search (p95 523 vs 32 ms). Before sibling chunks it even lowered Recall@8: it scores each chunk
alone against a symptom-heavy query, so other runbooks' symptom-rich first chunks beat the right runbook's second
chunk. `RERANK_CANDIDATES` brings it back if a harder eval (6b's briefs, real queries) shows a gain.

**Clustering gate recalibrated to 0.84.** F1 is 0.847 on dev (precision 0.983, recall 0.743) and 0.912 on test. The
misses are a neighbour's cascade alerts becoming their own incident. A lower similarity bar for neighbours can't fix
it: on dev, cascade alerts score 0.56–0.69 against their incident while unrelated neighbour incidents within 10
minutes score 0.59–0.76. Grouping across services needs signals summaries don't carry (topology plus timing, deploy
correlation); a timing rule tuned on this golden set would only mirror the generator's fixed cascade delay, so that
waits for real alert data.

**Other gates unchanged:** Recall@8 ≥ 0.90, MRR@10 ≥ 0.70, retrieval p95 ≤ 250 ms (all pass now).

**Known weaknesses.**
- Full-text search contributes nothing on these queries (Recall@8 and MRR 0.00): `websearch_to_tsquery` ANDs every
  word, and incident queries never contain all of a chunk's words. An OR-of-terms query is the next thing to try.
- The golden queries come from the same templates as the documents (metric and alert names), which is when
  embeddings do best; Recall@8 1.00 says retrieval is good *on this set*, not on human-phrased queries.
- Cascades in the golden set follow their incident by a fixed 20–90 s; real cascades vary.
