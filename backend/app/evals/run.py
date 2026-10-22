"""Ablation harness: the same incidents through three architectures.

    python -m app.evals.run --label nano                 # all scenarios, all arms
    python -m app.evals.run --arms pact --scenarios A,G  # a subset

Order: memory is cleared, then each arm runs every scenario, then the pact runs
the memory encores (A and E again, now with what it learned). Writes
evals/results/<label>/summary.json, summary.md and one JSON per run in runs/.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.incidents.scenarios import SCENARIOS
from app.integrations.nemotron.client import get_inference_client
from app.integrations.zetaris.business import get_business_context
from app.memory.hmem import get_hmem
from app.negotiation.orchestrator import run_blocking
from app.schemas.enums import Architecture, IncidentScenario

ENCORES = [IncidentScenario.SAFE_AUTONOMOUS, IncidentScenario.VERIFICATION_FAILS]


def _scenarios(arg: str) -> list[IncidentScenario]:
    if arg == "all":
        return list(SCENARIOS)
    wanted = {x.strip().upper() for x in arg.split(",")}
    return [s for s in SCENARIOS if s.value.split("_")[0] in wanted or s.value in wanted]


def _row(run, phase: str) -> dict[str, Any]:
    r = run.result
    return {
        "phase": phase,
        "run_id": run.run_id,
        "arch": run.arch.value,
        "scenario": run.scenario.value,
        "outcome": r.get("outcome"),
        "expected": r.get("expected_outcome"),
        "correct": r.get("correct"),
        "action": (r.get("action") or {}).get("kind"),
        "executed": (r.get("action") or {}).get("executed"),
        "unsafe_action": r.get("unsafe_action"),
        "business_harm": r.get("business_harm"),
        "false_recovery_claim": r.get("false_recovery_claim"),
        "rounds": r.get("rounds"),
        "model_calls": r.get("model_calls"),
        "tokens": r.get("tokens"),
        "duration_s": r.get("duration_s"),
        "recalled_memories": r.get("recalled_memories"),
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arch in dict.fromkeys(r["arch"] for r in rows):
        rs = [r for r in rows if r["arch"] == arch and r["phase"] == "main"]
        if not rs:
            continue
        out[arch] = {
            "runs": len(rs),
            "correct": sum(1 for r in rs if r["correct"]),
            "unsafe_actions": sum(1 for r in rs if r["unsafe_action"]),
            "business_harm": sum(1 for r in rs if r["business_harm"]),
            "false_recovery_claims": sum(1 for r in rs if r["false_recovery_claim"]),
            "verified_recoveries": sum(1 for r in rs if r["outcome"] == "VERIFIED_RECOVERED" and not r["false_recovery_claim"]),
            "median_duration_s": statistics.median(r["duration_s"] or 0 for r in rs),
            "model_calls": sum(r["model_calls"] or 0 for r in rs),
            "tokens": sum(r["tokens"] or 0 for r in rs),
        }
    return out


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# RecoveryPact eval: {summary['label']}",
        "",
        f"Model `{summary['model']}` ({summary['inference_mode']}), business context via "
        f"`{summary['zetaris_mode']}`, {summary['started_at']}.",
        "",
        "## Architectures",
        "",
        "| Arm | Correct | Unsafe actions | Business harm | False recovery claims | Verified recoveries | Median time (s) | Model calls |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for arch, a in summary["aggregate"].items():
        lines.append(
            f"| {arch} | {a['correct']}/{a['runs']} | {a['unsafe_actions']} | {a['business_harm']} | "
            f"{a['false_recovery_claims']} | {a['verified_recoveries']} | {a['median_duration_s']} | {a['model_calls']} |"
        )
    lines += [
        "",
        "## Every run",
        "",
        "| Phase | Arm | Scenario | Outcome (expected) | Action | Unsafe | Harm | False claim | Rounds | Calls | Time (s) | Memories |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summary["runs"]:
        mark = "ok" if r["correct"] else "WRONG"
        lines.append(
            f"| {r['phase']} | {r['arch']} | {r['scenario']} | {r['outcome']} ({r['expected']}) {mark} | "
            f"{r['action']}{'' if r['executed'] else ' (not run)'} | {_yn(r['unsafe_action'])} | "
            f"{_yn(r['business_harm'])} | {_yn(r['false_recovery_claim'])} | {r['rounds']} | "
            f"{r['model_calls']} | {r['duration_s']} | {r['recalled_memories']} |"
        )
    if summary.get("encores"):
        lines += ["", "## Memory encores (pact, same incident again)", ""]
        for e in summary["encores"]:
            lines.append(f"- {e}")
    return "\n".join(lines) + "\n"


def _yn(v: Any) -> str:
    return "YES" if v else "-"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="latest")
    ap.add_argument("--arms", default="pact,gated_single,naive_single")
    ap.add_argument("--scenarios", default="all")
    ap.add_argument("--no-encores", action="store_true")
    ap.add_argument("--keep-memory", action="store_true")
    args = ap.parse_args()

    arms = [Architecture(a.strip()) for a in args.arms.split(",")]
    scenarios = _scenarios(args.scenarios)
    out_dir = Path("evals/results") / args.label
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)
    if not args.keep_memory:
        get_hmem().clear()

    client = get_inference_client()
    summary: dict[str, Any] = {
        "label": args.label,
        "model": client.model_id,
        "inference_mode": client.mode,
        "zetaris_mode": get_business_context().mode,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runs": [],
    }
    rows: list[dict[str, Any]] = []

    def record(run, phase: str) -> dict[str, Any]:
        (out_dir / "runs" / f"{phase}-{run.arch.value}-{run.scenario.value}.json").write_text(
            json.dumps(run.to_json(), indent=2), encoding="utf-8"
        )
        row = _row(run, phase)
        rows.append(row)
        print(
            f"[{phase}] {row['arch']:<13} {row['scenario']:<26} {row['outcome']:<19} "
            f"expected {row['expected']:<19} {'ok' if row['correct'] else 'WRONG'} "
            f"rounds={row['rounds']} calls={row['model_calls']} {row['duration_s']}s",
            flush=True,
        )
        time.sleep(3)  # let checkout traffic settle between incidents
        return row

    for arch in arms:
        for sc in scenarios:
            record(run_blocking(sc, arch, use_memory=arch == Architecture.PACT), "main")

    encores = []
    if Architecture.PACT in arms and not args.no_encores:
        for sc in ENCORES:
            if sc not in scenarios:
                continue
            first = next(r for r in rows if r["arch"] == "pact" and r["scenario"] == sc.value)
            again = record(run_blocking(sc, Architecture.PACT, use_memory=True), "encore")
            encores.append(
                f"{sc.value}: first {first['outcome']} in {first['rounds']} round(s), {first['model_calls']} calls, "
                f"{first['duration_s']}s -> with memory {again['outcome']} in {again['rounds']} round(s), "
                f"{again['model_calls']} calls, {again['duration_s']}s ({again['recalled_memories']} memories recalled)"
            )

    summary["runs"] = rows
    summary["aggregate"] = _aggregate(rows)
    summary["encores"] = encores
    summary["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "summary.md").write_text(_markdown(summary), encoding="utf-8")
    print(_markdown(summary))


if __name__ == "__main__":
    main()
