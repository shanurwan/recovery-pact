"""Check that a replay reproduces the published run, decision by decision.

    python -m app.evals.compare evals/results/ci-replay evals/results/ultra-benchmark --repeat 3

The shipped recordings come from the last repeat of the published benchmark, so a
replay must land on the same outcome, action and safety flags for every
(phase, arm, scenario) of that repeat. Timing and lost-checkout counts depend on
the machine and are reported, not compared.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KEYS = ("outcome", "action", "executed", "unsafe_action", "business_harm", "false_recovery_claim", "correct")


def rows(path: Path, repeat: int | None) -> dict[tuple[str, str, str], dict]:
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    out = {}
    for r in summary["runs"]:
        if repeat is not None and r.get("repeat") != repeat:
            continue
        out[(r["phase"], r["arch"], r["scenario"])] = r
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("published")
    ap.add_argument("--repeat", type=int, required=True, help="repeat of the published run the recordings came from")
    args = ap.parse_args()
    got = rows(Path(args.replay), None)
    want = rows(Path(args.published), args.repeat)
    diffs = []
    for key, w in sorted(want.items()):
        g = got.get(key)
        if g is None:
            continue  # the replay may run a subset
        for k in KEYS:
            if g.get(k) != w.get(k):
                diffs.append(f"{'/'.join(key)}: {k} replay={g.get(k)} published={w.get(k)}")
    compared = len([k for k in want if k in got])
    if not compared:
        print("nothing to compare: no overlapping runs")
        return 1
    if diffs:
        print(f"DIVERGED on {len(diffs)} field(s) across {compared} runs:")
        print("\n".join(f"  - {d}" for d in diffs))
        return 1
    print(f"REPRODUCED: {compared} runs match the published repeat {args.repeat} on {', '.join(KEYS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
