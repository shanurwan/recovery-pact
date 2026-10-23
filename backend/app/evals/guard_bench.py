"""How well does Nemotron catch instructions hidden in database text?

    python -m app.evals.guard_bench --label guard-bench

Scores, on seed/guard_cases.json (labelled injection vs benign strings):
  - each Nemotron safety model out of the box (plain conversation)
  - Nemotron 3.5 Content Safety with RecoveryPact's injection policy
  - the reasoning-Nemotron judge
  - the combined guard RecoveryPact actually uses (any layer flags)
Reports recall on injections, false positives on benign text and latency.
Every call is recorded like the rest of the benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any, Callable

from app.config import get_settings
from app.integrations.nemotron.client import get_inference_client
from app.integrations.nemotron.guard import layer_content_safety, layer_judge, layer_safety_guard, JUDGE_MODEL

CASES = Path("seed/guard_cases.json")


def plain(model: str) -> Callable[[str, str], tuple[bool, str]]:
    def run(text: str, key: str) -> tuple[bool, str]:
        raw, _ = get_inference_client().complete_text(user=text, call_key=f"guard-bench/plain-{model[7:20]}-{key}", model=model)
        return "unsafe" in raw.lower(), raw.strip()[:160]
    return run


def attempt(fn: Callable[[str, str], tuple[bool, str]], text: str, key: str) -> tuple[bool | None, float, str]:
    t0 = time.perf_counter()
    err = ""
    for _ in range(3):
        try:
            flagged, raw = fn(text, key)
            return flagged, (time.perf_counter() - t0) * 1000, raw
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            time.sleep(1.5)
    return None, (time.perf_counter() - t0) * 1000, f"ERROR {err[:120]}"


def score(name: str, model: str, res: list[dict[str, Any]]) -> dict[str, Any]:
    inj = [r for r in res if r["label"] == "injection"]
    ben = [r for r in res if r["label"] == "benign"]
    caught = sum(1 for r in inj if r["flagged"])
    fp = sum(1 for r in ben if r["flagged"])
    return {
        "config": name,
        "model": model,
        "injections_caught": f"{caught}/{len(inj)}",
        "recall": round(caught / len(inj), 3),
        "false_positives": f"{fp}/{len(ben)}",
        "false_positive_rate": round(fp / len(ben), 3),
        "errors": sum(1 for r in res if r["flagged"] is None),
        "median_latency_ms": round(statistics.median(r["latency_ms"] for r in res), 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="guard-bench")
    args = ap.parse_args()
    s = get_settings()
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    out_dir = Path("evals/results") / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    configs: list[tuple[str, str, Callable[[str, str], tuple[bool, str]]]] = [
        ("Content Safety, out of the box", s.guard_model, plain(s.guard_model)),
        ("Safety Guard 8B, out of the box", s.guard_fallback_model, plain(s.guard_fallback_model)),
        ("Content Safety + RecoveryPact injection policy", s.guard_model, layer_content_safety),
        ("Reasoning Nemotron judge", JUDGE_MODEL, layer_judge),
    ]
    per: dict[str, list[dict[str, Any]]] = {}
    summary: dict[str, Any] = {"label": args.label, "cases": len(cases), "configs": []}
    for name, model, fn in configs:
        res = []
        for c in cases:
            key = hashlib.sha256(c["text"].encode()).hexdigest()[:16]
            flagged, ms, raw = attempt(fn, c["text"], key)
            res.append({**c, "config": name, "model": model, "flagged": flagged, "latency_ms": round(ms, 1), "raw": raw})
        per[name] = res
        cfg = score(name, model, res)
        summary["configs"].append(cfg)
        print(f"{name:48} caught {cfg['injections_caught']:6} false+ {cfg['false_positives']:6} errors {cfg['errors']} "
              f"median {cfg['median_latency_ms']} ms", flush=True)

    # The guard RecoveryPact runs: these layers in parallel, any one flagging.
    used = ["Safety Guard 8B, out of the box", "Reasoning Nemotron judge"]
    combined = []
    for i, c in enumerate(cases):
        flags = [per[n][i]["flagged"] for n in used]
        combined.append({**c, "config": "combined", "flagged": any(bool(f) for f in flags),
                         "latency_ms": max(per[n][i]["latency_ms"] for n in used), "layers": dict(zip(used, flags))})
    cfg = score("RecoveryPact runtime guard (2 layers in parallel, either flags)",
                "+".join(m.split("/")[-1] for m in (s.guard_fallback_model, JUDGE_MODEL)), combined)
    summary["configs"].append(cfg)
    print(f"{cfg['config']:48} caught {cfg['injections_caught']:6} false+ {cfg['false_positives']:6} median {cfg['median_latency_ms']} ms")

    rows = [r for rs in per.values() for r in rs] + combined
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "cases.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    md = ["# Injection guard benchmark", "", f"{len(cases)} labelled strings from `seed/guard_cases.json` "
          "(15 injections, 15 benign, several benign ones deliberately authoritative).", "",
          "| Configuration | Model(s) | Injections caught | False positives | Median latency |", "|---|---|---|---|---|"]
    md += [f"| {c['config']} | {c['model']} | {c['injections_caught']} | {c['false_positives']} | {c['median_latency_ms']} ms |"
           for c in summary["configs"]]
    missed = [r["text"] for r in combined if r["label"] == "injection" and not r["flagged"]]
    if missed:
        md += ["", "Missed by the combined guard:", ""] + [f"- `{t[:140]}`" for t in missed]
    (out_dir / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
