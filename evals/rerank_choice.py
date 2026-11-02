"""Which reranker? Runs planted-fact questions (evals/planted_facts.json) through hybrid search and reports, for
each stage and each candidate reranker, how often the planted document is found, and how long reranking takes.

A hit means the chunk's document is the one the fact was planted in. Hit@1 and hit@8 are shares of questions;
MRR@10 is the mean of 1/rank of the first hit within 10 (0 if none). Latency is the rerank stage only, warm.

Needs the corpus imported (uv run python -m pagerwise_indexer). Downloads each reranker model on first use.

uv run python evals/rerank_choice.py [--questions 80] [--models BAAI/bge-reranker-base Xenova/ms-marco-MiniLM-L-6-v2]
"""

import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path

from pagerwise_api import embedding, retrieval
from pagerwise_api.db import SessionLocal, engine
from pagerwise_api.settings import settings

FACTS = Path(__file__).resolve().parent / "planted_facts.json"


def scores(ranked_docs: list[list[str]], gold: list[str]) -> dict[str, float]:
    def rank_of(docs: list[str], doc: str) -> int | None:
        return next((i for i, d in enumerate(docs, start=1) if d == doc), None)

    ranks = [rank_of(docs, g) for docs, g in zip(ranked_docs, gold, strict=True)]
    n = len(gold)
    return {
        "hit@1": sum(r == 1 for r in ranks) / n,
        "hit@8": sum(r is not None and r <= 8 for r in ranks) / n,
        "mrr@10": sum(1 / r for r in ranks if r is not None and r <= 10) / n,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=int, default=80)
    parser.add_argument("--models", nargs="+", default=["BAAI/bge-reranker-base", "Xenova/ms-marco-MiniLM-L-6-v2"])
    parser.add_argument("--candidates", nargs="+", type=int, default=[40], help="fused chunks the reranker reads")
    args = parser.parse_args()
    facts = json.loads(FACTS.read_text())["facts"]
    rng = random.Random(0)
    runbook = [f for f in facts if f["id"].startswith("rb/")]
    postmortem = [f for f in facts if f["id"].startswith("pm/")]
    n_pm = min(len(postmortem), args.questions // 4)
    sample = rng.sample(runbook, args.questions - n_pm) + rng.sample(postmortem, n_pm)
    gold = [f["doc"] for f in sample]
    print(f"{len(sample)} questions ({len(sample) - n_pm} runbook facts, {n_pm} postmortem root causes)\n")

    rows = []
    for model, candidates in [(m, c) for m in args.models for c in args.candidates]:
        settings.reranker_model = model
        settings.rerank_candidates = candidates
        embedding._reranker.cache_clear()
        embedding.rerank("warm up", ["load the model before timing"])
        stages: dict[str, list[list[str]]] = {"fts": [], "vector": [], "rrf": [], "rerank": []}
        rerank_ms, total_ms = [], []
        async with SessionLocal() as session:
            for fact in sample:
                result = await retrieval.hybrid_search(session, fact["question"], k=retrieval.CANDIDATES)
                hits = result.hits
                stages["rerank"].append([h.document_path for h in hits])
                stages["rrf"].append([h.document_path for h in sorted(hits, key=lambda h: h.rrf_rank)])
                stages["fts"].append([h.document_path for h in sorted((h for h in hits if h.fts_rank),
                                                                        key=lambda h: h.fts_rank)])
                stages["vector"].append([h.document_path for h in sorted((h for h in hits if h.vector_rank),
                                                                           key=lambda h: h.vector_rank)])
                rerank_ms.append(result.timings_ms["rerank"])
                total_ms.append(result.timings_ms["total"])
        if not rows:  # the stages before reranking don't depend on the model
            for stage in ("fts", "vector", "rrf"):
                rows.append((stage, "-", scores(stages[stage], gold), None, None))
        q = statistics.quantiles
        rows.append((f"rerank{candidates}", model, scores(stages["rerank"], gold),
                     (statistics.median(rerank_ms), q(rerank_ms, n=20)[18]),
                     (statistics.median(total_ms), q(total_ms, n=20)[18])))

    print(f"{'stage':8} {'reranker':32} {'hit@1':>6} {'hit@8':>6} {'mrr@10':>7}   {'rerank ms p50/p95':>18}   "
          f"{'total ms p50/p95':>17}")
    for stage, model, s, rr, tot in rows:
        lat = f"{rr[0]:.0f} / {rr[1]:.0f}" if rr else "-"
        total = f"{tot[0]:.0f} / {tot[1]:.0f}" if tot else "-"
        print(f"{stage:8} {model:32} {s['hit@1']:>6.2f} {s['hit@8']:>6.2f} {s['mrr@10']:>7.2f}   {lat:>18}   {total:>17}")
    await engine.dispose()


if __name__ == "__main__":
    started = time.time()
    asyncio.run(main())
    print(f"\n{time.time() - started:.0f}s")
