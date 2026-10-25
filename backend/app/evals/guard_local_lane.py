"""Nemotron on our own machine, through Meterless Nightshift's local lane, with a signed receipt per call.

    GUARD_LOCAL="nvidia/nemotron-3.5-content-safety=nightshift" \
        python -m app.evals.guard_local_lane --label guard-local-lane

Runs Nemotron 3.5 Content Safety (a Q4_K_M GGUF on the laptop's CPU, served by Nightshift's
own llama.cpp lane) on the tuning and held-out guard sets, out of the box and with
RecoveryPact's injection policy in the prompt. Nightshift does not forward
chat_template_kwargs, so the native custom_policy configuration cannot run this way.

For every call it keeps the completion id, the route Nightshift reports (kind local or
cloud, the routed model), and the signed receipt fetched from the read-only relay
(METERLESS_RECEIPTS_URL). receipts.signed.jsonl holds those envelopes unmodified, so
scripts/prove.py re-verifies every signature offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.integrations.meterless import receipts as nightshift
from app.integrations.nemotron.client import get_inference_client
from app.integrations.nemotron.guard import POLICY

SETS = {"tuning": Path("seed/guard_cases.json"), "held-out": Path("seed/guard_cases_heldout.json")}
CONFIGS = {
    "Content Safety, out of the box": lambda t: t,
    "Content Safety + RecoveryPact injection policy (in the prompt)": lambda t: POLICY.format(text=t[:2000]),
}


def call(prompt: str, key: str) -> tuple[bool | None, str, dict[str, Any], float]:
    s = get_settings()
    t0 = time.perf_counter()
    for _ in range(3):
        try:
            raw, m = get_inference_client().complete_text(user=prompt, call_key=key, model=s.guard_model, max_tokens=40)
            return "unsafe" in raw.lower(), raw.strip()[:160], m, (time.perf_counter() - t0) * 1000
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            time.sleep(1.5)
    return None, f"ERROR {err[:120]}", {}, (time.perf_counter() - t0) * 1000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="guard-local-lane")
    args = ap.parse_args()
    s = get_settings()
    assert s.guard_local_map.get(s.guard_model) == "nightshift", "set GUARD_LOCAL=<guard model>=nightshift"
    out_dir = Path("evals/results") / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, envelopes, configs = [], [], []
    for set_name, path in SETS.items():
        cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        for name, build in CONFIGS.items():
            res = []
            for c in cases:
                key = f"guard/local-{set_name[:4]}-{hashlib.sha256((name + c['text']).encode()).hexdigest()[:12]}"
                flagged, raw, m, ms = call(build(c["text"]), key)
                env = nightshift.fetch(m["response_id"]) if m.get("response_id") else None
                if env:
                    envelopes.append(env)
                res.append({**c, "set": set_name, "config": name, "flagged": flagged, "raw": raw, "latency_ms": round(ms, 1),
                            "response_id": m.get("response_id"), "route_kind": m.get("route_kind"),
                            "routed_model": m.get("routed_model"), "receipt": bool(env)})
            inj = [r for r in res if r["label"] == "injection"]
            ben = [r for r in res if r["label"] == "benign"]
            cfg = {
                "set": set_name, "config": name,
                "injections_caught": f"{sum(1 for r in inj if r['flagged'])}/{len(inj)}",
                "recall": round(sum(1 for r in inj if r["flagged"]) / len(inj), 3),
                "false_positives": f"{sum(1 for r in ben if r['flagged'])}/{len(ben)}",
                "errors": sum(1 for r in res if r["flagged"] is None),
                "served_local": f"{sum(1 for r in res if r['route_kind'] == 'local')}/{len(res)}",
                "signed_receipts": f"{sum(1 for r in res if r['receipt'])}/{len(res)}",
                "median_latency_ms": round(statistics.median(r["latency_ms"] for r in res), 1),
            }
            configs.append(cfg)
            rows += res
            print(f"{set_name:8} {name:62} caught {cfg['injections_caught']:6} false+ {cfg['false_positives']:6} "
                  f"local {cfg['served_local']} receipts {cfg['signed_receipts']} median {cfg['median_latency_ms']} ms",
                  flush=True)
    routed = sorted({r["routed_model"] for r in rows if r["routed_model"]})
    n_cases = sum(len(json.loads(p.read_text(encoding="utf-8"))["cases"]) for p in SETS.values())
    summary = {"label": args.label, "cases": n_cases, "calls": len(rows), "routed_models": routed, "configs": configs}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "cases.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (out_dir / "receipts.signed.jsonl").write_text("".join(json.dumps(e) + "\n" for e in envelopes),
                                                   encoding="utf-8", newline="\n")
    md = ["# Nemotron on our own machine, through Nightshift's local lane", "",
          f"{len(rows)} calls. Nightshift routed them to: {', '.join(f'`{m}`' for m in routed) or 'nothing'}. "
          "Each call's signed receipt is in `receipts.signed.jsonl`.", "",
          "| Set | Configuration | Injections caught | False positives | Served locally | Signed receipts | Median latency |",
          "|---|---|---|---|---|---|---|"]
    md += [f"| {c['set']} | {c['config']} | {c['injections_caught']} | {c['false_positives']} | {c['served_local']} | "
           f"{c['signed_receipts']} | {c['median_latency_ms']} ms |" for c in configs]
    (out_dir / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
