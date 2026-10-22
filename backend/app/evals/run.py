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

from app.evals.manifest import build_manifest
from app.evals.validate import validate
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
        "lost_checkouts": r.get("lost_checkouts"),
        "settlements_aborted": r.get("settlements_aborted"),
        "repeat": getattr(run, "repeat", 1),
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
            "lost_checkouts": sum(r["lost_checkouts"] or 0 for r in rs),
            "settlements_aborted": sum(r["settlements_aborted"] or 0 for r in rs),
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
        "| Arm | Correct | Unsafe actions | Business harm | False recovery claims | Settlements aborted | Verified recoveries | Lost checkouts | Median time (s) | Model calls |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arch, a in summary["aggregate"].items():
        lines.append(
            f"| {arch} | {a['correct']}/{a['runs']} | {a['unsafe_actions']} | {a['business_harm']} | "
            f"{a['false_recovery_claims']} | {a['settlements_aborted']} | {a['verified_recoveries']} | "
            f"{a['lost_checkouts']} | {a['median_duration_s']} | {a['model_calls']} |"
        )
    if summary.get("per_scenario"):
        lines += ["", "## Pass rate per scenario", "", "| Scenario | " + " | ".join(summary["aggregate"]) + " |",
                  "|---|" + "---|" * len(summary["aggregate"])]
        for sc, by_arch in summary["per_scenario"].items():
            lines.append(f"| {sc} | " + " | ".join(by_arch.get(a, "-") for a in summary["aggregate"]) + " |")
    lines += [
        "",
        "## Every run",
        "",
        "| Rep | Phase | Arm | Scenario | Outcome (expected) | Action | Unsafe | Harm | False claim | Lost checkouts | Rounds | Calls | Time (s) | Memories |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summary["runs"]:
        mark = "ok" if r["correct"] else "WRONG"
        lines.append(
            f"| {r['repeat']} | {r['phase']} | {r['arch']} | {r['scenario']} | {r['outcome']} ({r['expected']}) {mark} | "
            f"{r['action']}{'' if r['executed'] else ' (not run)'} | {_yn(r['unsafe_action'])} | "
            f"{_yn(r['business_harm'])} | {_yn(r['false_recovery_claim'])} | {r['lost_checkouts']} | {r['rounds']} | "
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
    ap.add_argument("--repeats", type=int, default=1)
    args = ap.parse_args()

    arms = [Architecture(a.strip()) for a in args.arms.split(",")]
    scenarios = _scenarios(args.scenarios)
    out_dir = Path("evals/results") / args.label
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)

    client = get_inference_client()
    summary: dict[str, Any] = {
        "label": args.label,
        "model": client.model_id,
        "inference_mode": client.mode,
        "zetaris_mode": get_business_context().mode,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest": build_manifest(),
        "runs": [],
    }
    rows: list[dict[str, Any]] = []

    def record(run, phase: str, rep: int) -> dict[str, Any]:
        if run.result.get("outcome") == "NOT_RUN":
            raise SystemExit(
                "Another RecoveryPact run holds the database (console or another harness). "
                "Stop it and rerun; results from overlapping runs would be meaningless."
            )
        run.repeat = rep
        (out_dir / "runs" / f"r{rep}-{phase}-{run.arch.value}-{run.scenario.value}.json").write_text(
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

    encores = []
    for rep in range(1, args.repeats + 1):
        # Each repeat starts from empty memory, so repeats are independent samples.
        if not args.keep_memory:
            get_hmem().clear()
        for arch in arms:
            for sc in scenarios:
                record(run_blocking(sc, arch, use_memory=arch == Architecture.PACT, slot="main"), "main", rep)
        if Architecture.PACT in arms and not args.no_encores:
            for sc in ENCORES:
                if sc not in scenarios:
                    continue
                first = next(r for r in rows if r["arch"] == "pact" and r["scenario"] == sc.value and r["repeat"] == rep)
                again = record(run_blocking(sc, Architecture.PACT, use_memory=True, slot="encore"), "encore", rep)
                encores.append(
                    f"rep {rep} {sc.value}: first {first['outcome']} ({first['action']}"
                    f"{'' if first['executed'] else ', not run'}) in {first['rounds']} round(s), {first['model_calls']} calls, "
                    f"{first['duration_s']}s, {first['lost_checkouts']} lost checkouts -> with memory {again['outcome']} "
                    f"({again['action']}{'' if again['executed'] else ', not run'}) in {again['rounds']} round(s), "
                    f"{again['model_calls']} calls, {again['duration_s']}s, {again['lost_checkouts']} lost checkouts "
                    f"({again['recalled_memories']} memories recalled)"
                )

    summary["runs"] = rows
    summary["repeats"] = args.repeats
    summary["aggregate"] = _aggregate(rows)
    per: dict[str, dict[str, str]] = {}
    for sc in scenarios:
        for arch in arms:
            rs = [r for r in rows if r["phase"] == "main" and r["scenario"] == sc.value and r["arch"] == arch.value]
            if rs:
                per.setdefault(sc.value, {})[arch.value] = f"{sum(1 for r in rs if r['correct'])}/{len(rs)}"
    summary["per_scenario"] = per
    summary["encores"] = encores
    summary["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "summary.md").write_text(_markdown(summary), encoding="utf-8")
    print(_markdown(summary))
    rep = validate(out_dir)
    print(("VALID" if not rep.errors else "INVALID") + f": {rep.checks - len(rep.errors)}/{rep.checks} checks passed")
    for e in rep.errors[:20]:
        print(f"  - {e}")
    raise SystemExit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
