#!/usr/bin/env python3
"""Join every Nemotron call of a run set to its Meterless Nightshift receipt.

Each model call RecoveryPact makes through Nightshift records the completion id
(`response_id` in the call's metrics). Nightshift writes a signed receipt per
request with the same id (`receipt.request_id`), naming the model that actually
won the race, the routing reason, where the prompt went and whether Nightshift
added memories of its own. Standard library only.

    python scripts/nightshift-receipts.py evals/results/nightshift-verify \
        "%LOCALAPPDATA%/ai.meterless.runtime/receipts.jsonl" > evals/results/nightshift-verify/receipts.md
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path


def calls(result_dir: Path):
    for f in sorted((result_dir / "runs").glob("*.json")):
        run = json.loads(f.read_text(encoding="utf-8"))
        for e in run.get("events", []):
            for m in (e.get("data") or {}).get("metrics") or []:
                if isinstance(m, dict) and m.get("call_key"):
                    yield run["run_id"], run["scenario"], e.get("actor"), m


def receipts(path: Path) -> dict[str, dict]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        r = d.get("body", {}).get("receipt", {})
        if r.get("request_id"):
            out[r["request_id"]] = {**r, "_signed": bool(d.get("sig_b64") and d.get("pubkey_b64"))}
    return out


def main() -> int:
    result_dir, rpath = Path(sys.argv[1]), Path(sys.argv[2])
    recs = receipts(rpath)
    rows, missing = [], 0
    for run_id, scenario, actor, m in calls(result_dir):
        r = recs.get(m.get("response_id") or "")
        if r is None:
            missing += 1
            continue
        win = (r.get("winning_route") or {}).get("model") or (r.get("routing") or {}).get("winner")
        rows.append({
            "scenario": scenario[:1], "actor": actor, "call_key": m["call_key"].split("/")[-1],
            "route": m.get("route"), "winner": win, "provider": (r.get("winning_route") or {}).get("provider"),
            "egress": (r.get("egress") or {}).get("destination"), "hmem": (r.get("hmem") or {}).get("injected", 0),
            "raced": (r.get("routing") or {}).get("width"), "signed": r["_signed"], "latency_ms": m.get("latency_ms"),
        })
    winners = collections.Counter(r["winner"] for r in rows)
    print(f"# Nightshift receipts for `{result_dir.name}`\n")
    print(f"{len(rows)} model calls joined to a Nightshift receipt on `response_id = receipt.request_id`; "
          f"{missing} calls without a receipt. Signed receipts: {sum(r['signed'] for r in rows)}/{len(rows)}. "
          f"Calls where Nightshift added its own H-MEM context: {sum(1 for r in rows if r['hmem'])}/{len(rows)}.\n")
    print("| Winning model (from the receipt) | Calls |\n|---|---|")
    for w, n in winners.most_common():
        print(f"| `{w}` | {n} |")
    print("\n| Scn | Agent | Call | Route | Winner | Egress | H-MEM added | Raced | Latency (ms) |\n|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['scenario']} | {r['actor']} | {r['call_key']} | `{r['route']}` | `{r['winner']}` | {r['egress']} | "
              f"{r['hmem']} | {r['raced']} | {r['latency_ms']} |")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
