"""The eval-offline job's PR comment: this run's metrics next to main's baseline, with deltas and gate status.

uv run python evals/pr_comment.py RESULTS_JSON BASELINE_JSON > comment.md
"""

import json
import sys
from pathlib import Path

from run import GATES, check_gates

MARKER = "<!-- pagerwise-eval -->"  # how the workflow finds its previous comment to update


def main() -> None:
    run = json.loads(Path(sys.argv[1]).read_text())
    baseline = json.loads(Path(sys.argv[2]).read_text())["metrics"]
    rows = []
    for name, value in run["metrics"].items():
        if not isinstance(value, int | float) or name not in GATES and name not in baseline:
            continue
        base = baseline.get(name)
        delta = f"{value - base:+.3f}" if isinstance(base, int | float) else "new"
        gate = ""
        if name in GATES:
            op, threshold = GATES[name]
            missed, missed_on_main = check_gates({name: value}), base is not None and check_gates({name: base})
            gate = f"{op} {threshold} " + ("pass" if not missed else "MISS (also on main)" if missed_on_main
                                           else "**MISS**")
        rows.append(f"| {name} | {fmt(base)} | {fmt(value)} | {delta} | {gate} |")
    print(f"""{MARKER}
### Offline eval (dev split, model calls replayed)

Run `{run['run']}` against main's `evals/baseline.json`. A gate main already misses is reported, not failed
(docs/adr/0011).

| metric | main | this PR | delta | gate |
|---|---|---|---|---|
""" + "\n".join(rows))


def fmt(value: object) -> str:
    return "—" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)


if __name__ == "__main__":
    main()
