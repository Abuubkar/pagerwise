"""Ask the running API a question and print the answer with each citation resolved to its chunk text.

uv run python scripts/ask.py "Why is payments p99 high?" [--api http://localhost:8001]
"""

import argparse
import json
import textwrap
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("question")
parser.add_argument("--api", default="http://localhost:8001")
args = parser.parse_args()

request = urllib.request.Request(
    f"{args.api}/v1/ask",
    data=json.dumps({"question": args.question}).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=300) as response:
    body = json.load(response)

usage = body["usage"]
print(f"Q: {args.question}")
print(f"verdict: {body['verdict']}   ({usage['model']}, {usage['prompt_version']}, "
      f"{usage['prompt_tokens']} prompt + {usage['output_tokens']} output tokens, {usage['total_ms']} ms)")
if body["problems"]:
    print(f"problems: {body['problems']}")
print("\n" + textwrap.fill(body["answer"], 110) + "\n")
for c in body["citations"]:
    print(f"[{c['tag']}] {c['document_path']} :: {c['heading_path']}  (chunk {c['chunk_id']})")
    print(textwrap.indent(c["text"], "    | ", lambda _: True))
    print()
