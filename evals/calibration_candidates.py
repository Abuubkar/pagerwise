"""Candidate rows for the judge's calibration set, from real generated briefs (an eval results file).

Every (sentence, cited source) pair of the first repeat's briefs is a candidate. To get enough "no" rows (the plan
asks for at least 15 of 40), candidates are ordered by how little of the claim's specific content (numbers,
identifiers, longer words) appears in the source: low overlap is where unsupported claims hide. A person then
labels each row yes/no; the labels, not this ordering, are what the judge is measured against.

uv run python evals/calibration_candidates.py evals/results/<run>.json [--count 60]
    [--exclude evals/golden/calibration.csv --first-id 61 --out evals/golden/calibration_candidates_holdout.csv]

--exclude skips every (case, sentence) already in a labelled file: that's how the held-out rows were drawn.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from triage_eval import claims

TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{5,}|\d[\d.,%]*")


def overlap(claim: str, source: str) -> float:
    words = {t.lower() for t in TOKEN.findall(claim)}
    return len([w for w in words if w in source.lower()]) / len(words) if words else 1.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--exclude", type=Path, help="a labelled CSV whose (case, claim) pairs to skip")
    parser.add_argument("--first-id", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "golden" / "calibration_candidates.csv")
    args = parser.parse_args()
    run = json.loads(args.results.read_text())
    rows = []
    for brief in (b for b in run["briefs"] if b["repeat"] == 0 and b["status"] == "done"):
        for claim in claims(brief["raw"], brief["evidence"]):
            for source in claim["sources"]:
                rows.append({"case": brief["case"], "section": claim["section"], "claim": claim["claim"],
                             "cites": len(claim["sources"]), "all_tags": " ".join(x["tag"] for x in claim["sources"]),
                             "source_tag": source["tag"], "source_type": source["type"], "source": source["text"],
                             "overlap": round(overlap(claim["claim"], source["text"]), 2)})
    # Half the lowest-overlap pairs, half spread over the rest, one pair per (case, claim) at most.
    rows.sort(key=lambda r: r["overlap"])
    seen = {(r["case"], r["claim"]) for r in csv.DictReader(args.exclude.open())} if args.exclude else set()
    picked = []
    low = [r for r in rows if r["overlap"] < 0.6]
    rest = [r for r in rows if r["overlap"] >= 0.6]
    for pool, n in ((low, args.count // 2), (rest[:: max(1, len(rest) // max(1, args.count // 2))], args.count)):
        for r in pool:
            key = (r["case"], r["claim"])
            if key not in seen and len(picked) < n + (args.count // 2 if pool is rest else 0):
                seen.add(key)
                picked.append(r)
    out = args.out.resolve()
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", *picked[0].keys()])
        writer.writeheader()
        for i, r in enumerate(picked[: args.count], start=args.first_id):
            writer.writerow({"id": f"cal-{i:02}", **r})
    print(f"{len(rows)} (claim, source) pairs in {args.results.name}; wrote {min(len(picked), args.count)} "
          f"candidates to {out.relative_to(out.parents[2])} ({sum(r['overlap'] < 0.6 for r in picked)} low-overlap)")


main()
