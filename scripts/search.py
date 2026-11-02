"""Run a hybrid search on the running API and print each result's rank at every stage, plus stage timings.

uv run python scripts/search.py "ledger running out of database connections" [--k 8] [--api http://localhost:8001]
"""

import argparse
import json
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("query")
parser.add_argument("--k", type=int, default=8)
parser.add_argument("--api", default="http://localhost:8001")
args = parser.parse_args()

url = f"{args.api}/v1/search?{urllib.parse.urlencode({'q': args.query, 'k': args.k})}"
with urllib.request.urlopen(url, timeout=60) as response:
    body = json.load(response)


def rank(value: int | None) -> str:
    return "-" if value is None else str(value)


print(f'Q: {body["query"]}   ({body["candidates"]} fused candidates)')
print(f"  {'final':>5} {'rerank':>6} {'rrf':>4} {'fts':>4} {'vec':>4}  {'type':10} {'document > section'}")
for i, hit in enumerate(body["results"], start=1):
    doc = hit["document_path"].rsplit("/", 1)[-1].removesuffix(".md")
    section = hit["heading_path"].split(" > ", 1)[-1]
    print(f"  {i:>5} {rank(hit['rerank_rank']):>6} {hit['rrf_rank']:>4} {rank(hit['fts_rank']):>4} "
          f"{rank(hit['vector_rank']):>4}  {hit['source_type']:10} {doc} > {section}")
t = body["timings_ms"]
print(f"  ms: embed {t['embed']:.0f}, fts {t['fts']:.0f} | vector {t['vector']:.0f} (concurrent: {t['searches']:.0f}), "
      f"fuse {t['fuse']:.0f}, rerank {t['rerank']:.0f}, total {t['total']:.0f}")
