"""The eval: retrieval and clustering quality over the golden set (evals/golden/), with gates.

  retrieval   Recall@8 and MRR@10 of the gold runbook chunks, per stage (full-text only, vector only, hybrid,
              hybrid + rerank: the ablation), from one hybrid search per answerable case, plus p50/p95 latency
              over --latency-queries synthetic queries.
  clustering  Every alert of the split replayed through the consumer's clustering (store_alerts) in-process, in
              consumer-sized batches, against a separate database (pagerwise_eval); pairwise precision, recall
              and F1 against the gold grouping.

Writes evals/results/<run>.json (every run is kept) and evals/REPORT.md (the previous one moves to evals/archive/).
Exits 1 if a gate is missed, or with --baseline if a quality metric drops more than 1.5 points.

uv run python evals/run.py [--split dev|test] [--only retrieval,clustering] [--embedding v1|v2|dual]
                           [--baseline evals/baseline.json] [--write-baseline]
"""

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from metrics import mrr_at_k, pairwise_prf, percentile, recall_at_k
from pagerwise_api import retrieval, triage
from pagerwise_api.db import AlertEvent, Chunk, Document, Service, ServiceEdge
from pagerwise_api.embedding import embed_passages
from pagerwise_api.settings import settings
from pagerwise_consumer import clustering
from pagerwise_simulator import load_graph

EVALS = Path(__file__).resolve().parent
ROOT = EVALS.parent
GOLDEN = EVALS / "golden"
GATES = {  # metric -> (comparison, threshold), from the plan
    "retrieval.recall_at_8": (">=", 0.90),
    "retrieval.mrr_at_10": (">=", 0.70),
    "retrieval.latency_p95_ms": ("<=", 250),
    "clustering.f1": (">=", 0.84),  # recalibrated from 0.90 after the first baseline (docs/adr/0009)
}
QUALITY = {"retrieval.recall_at_8", "retrieval.mrr_at_10", "retrieval.mrr_at_10_before_rerank",
           "clustering.precision", "clustering.recall", "clustering.f1"}  # what --baseline guards (higher is better)
STAGES = ("fts", "vector", "rrf", "rerank", "final")
STAGE_NAMES = {"fts": "full-text only", "vector": "vector only", "rrf": "hybrid (RRF)", "rerank": "hybrid + rerank",
               "final": "final (+ sibling chunks)"}


def load_cases(kind: str, split: str) -> list[dict]:
    return [c for c in json.loads((GOLDEN / f"{kind}.json").read_text())["cases"] if c["split"] == split]


def case_query(case: dict, graph) -> str:  # noqa: ANN001
    """The same query triage would build for this incident (triage.build_query)."""
    service = graph[case["service"]]
    neighbours = sorted(set(service.depends_on) | {s.name for s in graph.values() if case["service"] in s.depends_on})
    summaries = list(dict.fromkeys(a["summary"] for a in case["alerts"]))[:1]  # one alert rule: its top summary
    return triage.build_query(case["title"], case["service"], neighbours, summaries)


async def retrieval_eval(split: str, latency_queries: int) -> tuple[dict, list[dict], dict]:
    engine = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    graph = load_graph()
    cases = load_cases("answerable", split)
    async with sessions() as session:
        chunk_ids = {(path, ordinal): cid for cid, path, ordinal in (await session.execute(
            select(Chunk.id, Document.path, Chunk.ordinal).join(Document))).all()}
    per_case, scores = [], {stage: {"recall": [], "mrr": []} for stage in STAGES}
    totals = []
    async with sessions() as session:
        for case in cases:
            gold = {chunk_ids[(g["doc"], g["ordinal"])] for g in case["gold_evidence"]}
            result = await retrieval.hybrid_search(session, case_query(case, graph), k=retrieval.CANDIDATES)
            hits = result.hits
            candidates = set(result.before_siblings)  # the earlier stages see only real candidates, not siblings
            ranked = [h for h in hits if h.chunk_id in candidates]
            orders = {
                "final": [h.chunk_id for h in hits],
                "rerank": result.before_siblings,
                "rrf": [h.chunk_id for h in sorted(ranked, key=lambda h: h.rrf_rank)],
                "fts": [h.chunk_id for h in sorted((h for h in ranked if h.fts_rank), key=lambda h: h.fts_rank)],
                "vector": [h.chunk_id for h in sorted((h for h in ranked if h.vector_rank), key=lambda h: h.vector_rank)],
            }
            row = {"id": case["id"], "query": case_query(case, graph), "gold": sorted({g["doc"] for g in case["gold_evidence"]})}
            for stage, ranked in orders.items():
                scores[stage]["recall"].append(recall_at_k(ranked, gold, 8))
                scores[stage]["mrr"].append(mrr_at_k(ranked, gold, 10))
                row[stage] = {"recall_at_8": scores[stage]["recall"][-1], "mrr_at_10": scores[stage]["mrr"][-1]}
            by_id = {h.chunk_id: h for h in hits}
            row["top8"] = [by_id[c].document_path.rsplit("/", 1)[-1] + (" (gold)" if c in gold else "")
                           for c in orders["final"][:8]]
            row["timings_ms"] = result.timings_ms
            totals.append(result.timings_ms["total"])
            per_case.append(row)

        # Latency over many queries: the planted-fact questions and the golden queries, cycled.
        questions = [f["question"] for f in json.loads((EVALS / "planted_facts.json").read_text())["facts"]]
        questions += [case_query(c, graph) for c in cases]
        latencies, stage_ms = [], defaultdict(list)
        for i in range(latency_queries):
            result = await retrieval.hybrid_search(session, questions[i % len(questions)])
            latencies.append(result.timings_ms["total"])
            for stage, ms in result.timings_ms.items():
                stage_ms[stage].append(ms)
    await engine.dispose()

    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
    metrics = {
        "retrieval.recall_at_8": mean(scores["final"]["recall"]),
        "retrieval.mrr_at_10": mean(scores["final"]["mrr"]),
        "retrieval.mrr_at_10_before_rerank": mean(scores["rrf"]["mrr"]),
        "retrieval.latency_p50_ms": percentile(latencies, 50),
        "retrieval.latency_p95_ms": percentile(latencies, 95),
    }
    ablation = {stage: {"recall_at_8": mean(scores[stage]["recall"]), "mrr_at_10": mean(scores[stage]["mrr"])}
                for stage in STAGES}
    for stage, keys in {"fts": ["fts"], "vector": ["vector"], "rrf": ["embed", "searches", "fuse"],
                        "rerank": ["embed", "searches", "fuse", "rerank"], "final": ["total"]}.items():
        ablation[stage]["p95_ms"] = sum(percentile(stage_ms[k], 95) for k in keys)
    ablation["_queries"] = {"cases": len(cases), "latency_queries": latency_queries}
    return metrics, per_case, ablation


EVAL_DB = "pagerwise_eval"


async def eval_database() -> str:
    """A separate database for writes (clustering replays alerts), created and migrated on first use, so the dev
    database and the UI never see eval incidents."""
    url = settings.database_url.rsplit("/", 1)[0] + f"/{EVAL_DB}"
    admin = await asyncpg.connect(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", EVAL_DB):
            await admin.execute(f"CREATE DATABASE {EVAL_DB}")
    finally:
        await admin.close()
    migrated = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, capture_output=True,
                              text=True, env={**__import__("os").environ, "DATABASE_URL": url})
    if migrated.returncode != 0:
        raise RuntimeError(f"migrating {EVAL_DB} failed:\n{migrated.stderr[-2000:]}")
    return url


async def clustering_eval(split: str) -> tuple[dict, list[dict]]:
    url = await eval_database()
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    graph = load_graph()
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE alert_events, incidents, service_edges, services CASCADE"))
    async with sessions() as session:
        session.add_all(Service(name=s.name, tier=s.tier, team=s.team) for s in graph.values())
        await session.flush()
        session.add_all(ServiceEdge(from_service=s.name, to_service=d) for s in graph.values() for d in s.depends_on)
        await session.commit()
    edges = {(s.name, d) for s in graph.values() for d in s.depends_on}

    cases = [c for kind in ("answerable", "unanswerable", "degraded") for c in load_cases(kind, split)]
    gold, events = {}, []
    for case in cases:
        start = datetime.fromisoformat(case["opened_at"])
        for i, alert in enumerate(case["alerts"]):
            event_id = uuid.uuid5(uuid.NAMESPACE_URL, f"golden/{case['id']}/{i}")
            gold[event_id] = case["id"]
            events.append({"event_id": event_id, "source": "golden", "service": alert["service"],
                           "fingerprint": alert["fingerprint"], "severity": alert["severity"],
                           "occurred_at": start + timedelta(seconds=alert["offset_s"]),
                           "labels": {"alertname": alert["alertname"], "instance": alert["instance"],
                                      "case": case["id"]},
                           "summary": alert["summary"], "attempt": 0})
    events.sort(key=lambda e: e["occurred_at"])

    async def embed(texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(embed_passages, texts) if texts else []

    # Like the consumer: alerts arrive in order, in small batches per partition (alerts are keyed by service).
    batches: dict[tuple[int, str], list[dict]] = defaultdict(list)
    t0 = events[0]["occurred_at"]
    for event in events:
        batches[(int((event["occurred_at"] - t0).total_seconds() // 2), event["service"])].append(event)
    started = time.monotonic()
    for key in sorted(batches):
        async with sessions() as session, session.begin():
            await clustering.store_alerts(session, batches[key], edges, embed)
    seconds = time.monotonic() - started
    async with sessions() as session:
        predicted = {e: i for e, i in (await session.execute(select(AlertEvent.event_id, AlertEvent.incident_id))).all()}
    await engine.dispose()

    precision, recall, f1 = pairwise_prf(predicted, gold)
    per_case = []
    incidents_of = defaultdict(set)
    cases_in = defaultdict(set)
    for event_id, case_id in gold.items():
        incidents_of[case_id].add(predicted[event_id])
        cases_in[predicted[event_id]].add(case_id)
    for case in cases:
        merged_with = sorted({c for i in incidents_of[case["id"]] for c in cases_in[i]} - {case["id"]})
        per_case.append({"id": case["id"], "service": case["service"], "incidents": len(incidents_of[case["id"]]),
                         "merged_with": merged_with})
    metrics = {"clustering.precision": precision, "clustering.recall": recall, "clustering.f1": f1,
               "clustering.alerts": len(events), "clustering.cases": len(cases),
               "clustering.incidents": len(set(predicted.values())), "clustering.seconds": round(seconds, 1)}
    return metrics, per_case


def check_gates(metrics: dict) -> list[str]:
    missed = []
    for name, (op, threshold) in GATES.items():
        if name in metrics:
            value = metrics[name]
            if (op == ">=" and value < threshold) or (op == "<=" and value > threshold):
                missed.append(f"{name} = {value:.3f}, gate {op} {threshold}")
    return missed


def check_baseline(metrics: dict, baseline_path: Path) -> list[str]:
    baseline = json.loads(baseline_path.read_text())["metrics"]
    return [f"{name} dropped from {baseline[name]:.3f} to {value:.3f}"
            for name, value in metrics.items()
            if name in QUALITY and name in baseline
            and baseline[name] - value > 0.015]


def write_report(run: dict, missed: list[str]) -> None:
    report = EVALS / "REPORT.md"
    if report.exists():  # eval results are never deleted: the previous report is archived
        archive = EVALS / "archive"
        archive.mkdir(exist_ok=True)
        shutil.move(report, archive / f"REPORT-{datetime.fromtimestamp(report.stat().st_mtime, UTC):%Y%m%dT%H%M%S}.md")
    m = run["metrics"]
    lines = [f"# Eval report: {run['split']} split, embedding {run['embedding']}", "",
             f"Run {run['run']} at {run['at']}, reranker {run['reranker']} on the top {run['rerank_candidates']}.", ""]
    lines += ["## Gates", "", "| metric | value | gate | |", "|---|---|---|---|"]
    for name, (op, threshold) in GATES.items():
        if name in m:
            ok = not any(x.startswith(name + " ") for x in missed)
            lines.append(f"| {name} | {m[name]:.3f} | {op} {threshold} | {'pass' if ok else '**MISS**'} |")
    if "retrieval" in run:
        lines += ["", "## Retrieval ablation", "", f"{run['ablation']['_queries']['cases']} answerable cases; "
                  f"latency over {run['ablation']['_queries']['latency_queries']} queries.", "",
                  "| stage | Recall@8 | MRR@10 | p95 ms (cumulative) |", "|---|---|---|---|"]
        for stage in STAGES:
            a = run["ablation"][stage]
            lines.append(f"| {STAGE_NAMES[stage]} | {a['recall_at_8']:.3f} | {a['mrr_at_10']:.3f} | {a['p95_ms']:.0f} |")
        misses = [r for r in run["retrieval"] if r["final"]["recall_at_8"] < 1 or r["final"]["mrr_at_10"] < 1]
        lines += ["", f"### Retrieval cases short of perfect ({len(misses)} of {len(run['retrieval'])})", ""]
        for r in misses:
            lines += [f"- **{r['id']}** Recall@8 {r['final']['recall_at_8']:.2f}, MRR@10 {r['final']['mrr_at_10']:.2f}; "
                      f"gold `{', '.join(g.rsplit('/', 1)[-1] for g in r['gold'])}`",
                      f"  - top 8: {', '.join(r['top8'])}", f"  - query: {r['query']}"]
    if "clustering" in run:
        lines += ["", "## Clustering", "",
                  f"{m['clustering.alerts']} alerts from {m['clustering.cases']} cases became {m['clustering.incidents']} "
                  f"incidents (in {m['clustering.seconds']}s). Pairwise precision {m['clustering.precision']:.3f}, "
                  f"recall {m['clustering.recall']:.3f}, F1 {m['clustering.f1']:.3f}.", ""]
        split = [c for c in run["clustering"] if c["incidents"] > 1]
        merged = [c for c in run["clustering"] if c["merged_with"]]
        lines += [f"- Split across several incidents ({len(split)}): "
                  + (", ".join(f"{c['id']} ({c['service']}) into {c['incidents']}" for c in split) or "none"),
                  f"- Merged with another case ({len(merged)}): "
                  + (", ".join(f"{c['id']} ({c['service']}) with {', '.join(c['merged_with'])}" for c in merged) or "none")]
    if missed:
        lines += ["", "## Missed", ""] + [f"- {x}" for x in missed]
    report.write_text("\n".join(lines) + "\n")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--only", default="retrieval,clustering")
    parser.add_argument("--embedding", choices=["v1", "v2", "dual"], default=settings.retrieval_embedding_version)
    parser.add_argument("--latency-queries", type=int, default=500)
    parser.add_argument("--rerank-candidates", type=int, default=settings.rerank_candidates,
                        help="0 turns the reranker off for this run")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--write-baseline", action="store_true", help="save this run's metrics as evals/baseline.json")
    args = parser.parse_args()
    settings.retrieval_embedding_version = args.embedding
    settings.rerank_candidates = args.rerank_candidates
    sections = set(args.only.split(","))
    run = {"run": datetime.now(UTC).strftime("%Y%m%dT%H%M%S"), "at": datetime.now(UTC).isoformat(timespec="seconds"),
           "split": args.split, "embedding": args.embedding, "reranker": settings.reranker_model,
           "rerank_candidates": settings.rerank_candidates, "metrics": {}}
    if "retrieval" in sections:
        metrics, per_case, ablation = await retrieval_eval(args.split, args.latency_queries)
        run["metrics"] |= metrics
        run["retrieval"], run["ablation"] = per_case, ablation
    if "clustering" in sections:
        metrics, per_case = await clustering_eval(args.split)
        run["metrics"] |= metrics
        run["clustering"] = per_case

    missed = check_gates(run["metrics"])
    if args.baseline:
        missed += check_baseline(run["metrics"], args.baseline)
    results = EVALS / "results"
    results.mkdir(exist_ok=True)
    (results / f"{run['run']}-{args.split}-{args.embedding}.json").write_text(json.dumps(run, indent=1, default=str) + "\n")
    if args.write_baseline:
        (EVALS / "baseline.json").write_text(json.dumps({"run": run["run"], "metrics": run["metrics"]}, indent=1) + "\n")
    write_report(run, missed)

    for name, value in run["metrics"].items():
        print(f"{name:42} {value:.3f}" if isinstance(value, float) else f"{name:42} {value}")
    print("\n" + ("\n".join(f"MISSED {x}" for x in missed) if missed else "all gates passed"))
    print(f"report: {(EVALS / 'REPORT.md').relative_to(ROOT)}; results: evals/results/{run['run']}-{args.split}-{args.embedding}.json")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
