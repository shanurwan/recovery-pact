"""Data for the "Built on Nemotron" page, computed from raw benchmark traces.

    python -m app.evals.build_nemotron --out evals/demo-data/nemotron.json

Reads evals/results/<label>/ for the model-family, scaffold-ablation and
mixed-team runs plus the guard benchmark. Every number comes from the pact arm's
per-run traces, not from a hand-written table.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

CONFIGS = [
    # key, result label, display name, what varies
    ("ultra", "ultra-benchmark", "Nemotron 3 Ultra 550B-A55B", "every agent on Ultra"),
    ("super", "family-super", "Nemotron 3.5 Super 120B-A12B", "every agent on Super"),
    ("lightning", "family-lightning", "Nemotron 3.5 Lightning 30B-A3B", "every agent on Lightning (3B active)"),
    ("lightning_no_scaffold", "ablation-lightning-no-scaffold", "Lightning, reasoning scaffold OFF",
     "no grounding retries, no evidence checklist, no trade-off calculator, no code-enforced invariants, no injection guard"),
    ("mixed", "mixed-team", "Mixed team", "Ultra for the Business AI's judgement; Lightning for the Database AI and the Auditor"),
    ("lanes", "nemotron-lanes", "Lanes through Nightshift",
     "guardians pinned to Super VL, auditor on the fast lane, every answer signed and lane-checked (I8)"),
]
LANES = "nemotron-lanes"
TURN_KINDS = {"proposal", "review", "audit"}


def summarize(res_dir: Path) -> dict[str, Any] | None:
    sp = res_dir / "summary.json"
    if not sp.exists():
        return None
    summary = json.loads(sp.read_text(encoding="utf-8"))
    rows = [r for r in summary["runs"] if r["arch"] == "pact" and r["phase"] == "main"]
    if not rows:
        return None
    lat: dict[str, list[float]] = {}
    tokens, calls = [], []
    for r in rows:
        f = next(res_dir.glob(f"runs/r{r['repeat']}-main-pact-{r['scenario']}.json"), None)
        if not f:
            continue
        t = json.loads(f.read_text(encoding="utf-8"))
        tokens.append(t["result"].get("tokens") or 0)
        calls.append(t["result"].get("model_calls") or 0)
        for e in t["events"]:
            if e["kind"] in TURN_KINDS:
                for m in e["data"].get("metrics") or []:
                    if m.get("latency_ms"):
                        lat.setdefault(e["actor"], []).append(m["latency_ms"])
    per: dict[str, str] = {}
    for sc in sorted({r["scenario"] for r in rows}):
        rs = [r for r in rows if r["scenario"] == sc]
        per[sc] = f"{sum(1 for r in rs if r['correct'])}/{len(rs)}"
    h = [r for r in rows if r["scenario"].startswith("H_")]
    m = summary.get("manifest", {})
    return {
        "label": summary["label"],
        "models_by_role": m.get("models_by_role"),
        "reasoning_scaffold": m.get("reasoning_scaffold", True),
        "zetaris_mode": summary.get("zetaris_mode"),
        "repeats": summary.get("repeats"),
        "runs": len(rows),
        "correct": sum(1 for r in rows if r["correct"]),
        "unsafe_actions": sum(1 for r in rows if r["unsafe_action"]),
        "business_harm": sum(1 for r in rows if r["business_harm"]),
        "false_recovery_claims": sum(1 for r in rows if r["false_recovery_claim"]),
        "median_duration_s": round(statistics.median(r["duration_s"] or 0 for r in rows), 1),
        "median_rounds": statistics.median(r["rounds"] or 0 for r in rows),
        "mean_model_calls": round(statistics.mean(calls), 1) if calls else None,
        "mean_tokens_per_incident": round(statistics.mean(tokens)) if tokens else None,
        "median_turn_latency_ms": {k: round(statistics.median(v)) for k, v in lat.items()},
        "per_scenario": per,
        "injection": {"runs": len(h), "correct": sum(1 for r in h if r["correct"]),
                      "flagged": sum(1 for r in h if r.get("injection_flagged")),
                      "harm": sum(1 for r in h if r["business_harm"])} if h else None,
    }


def lane_receipts(res_dir: Path) -> dict[str, Any] | None:
    """Which model Nightshift's signed receipts say answered each role, over every call of the run."""
    f = res_dir / "receipts.json"
    if not f.exists():
        return None
    rows = json.loads(f.read_text(encoding="utf-8"))["rows"]
    roles: dict[str, dict[str, int]] = {}
    for r in rows:
        if r.get("verified"):
            m = roles.setdefault(r["actor"], {})
            m[r["winner"]] = m.get(r["winner"], 0) + 1
    return {"calls": len(rows), "verified": sum(1 for r in rows if r.get("verified")),
            "keys": sorted({r["key"] for r in rows if r.get("key")}), "by_role": roles}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="evals/results")
    ap.add_argument("--out", default="evals/demo-data/nemotron.json")
    args = ap.parse_args()
    base = Path(args.results)
    out: dict[str, Any] = {"configs": []}
    for key, label, name, varies in CONFIGS:
        s = summarize(base / label)
        if s:
            out["configs"].append({"key": key, "name": name, "varies": varies, **s})
            print(f"{key:24} {s['correct']}/{s['runs']} unsafe={s['unsafe_actions']} harm={s['business_harm']} "
                  f"false={s['false_recovery_claims']} median {s['median_duration_s']}s tokens {s['mean_tokens_per_incident']}")
        else:
            print(f"{key:24} (no results in {label})")
    for key, label in (("guard", "guard-bench-v2"), ("guard_heldout", "guard-bench-heldout")):
        g = base / label / "summary.json"
        if g.exists():
            out[key] = json.loads(g.read_text(encoding="utf-8"))
    lanes = lane_receipts(base / LANES)
    if lanes:
        out["lanes"] = lanes
        print(f"lanes: {lanes}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
