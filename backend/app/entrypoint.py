"""One programmatic entry point: JSON in, JSON out, used by POST /run and run.py.

    {"run_id": "demo-001",
     "input": {"scenario": "B", "architecture": "pact", "use_memory": true},
     "options": {"sample_mode": false}}

Runs one incident end to end (inject -> negotiate -> authorize -> execute ->
verify -> audit) and returns what happened, which agents took part, the trace
file and timing. Failures come back as a structured error, never a crash.
sample_mode replays recorded Nemotron decisions so the run needs no API key;
the database, authority, executor and verifier still run live.
"""

from __future__ import annotations

import re
import time
from typing import Any

from app.config import get_settings
from app.incidents.scenarios import get_spec
from app.integrations.nemotron.client import ReplayMissing, get_inference_client
from app.integrations.zetaris.business import get_business_context
from app.negotiation.orchestrator import run_blocking, run_store
from app.schemas.enums import Architecture, IncidentScenario

AGENTS = {
    Architecture.PACT: [
        {"name": "Database Guardian", "kind": "Nemotron agent", "role": "Proposes a recovery from observed candidates, requests evidence, revises under challenge"},
        {"name": "Continuity Guardian", "kind": "Nemotron agent", "role": "Speaks for the business: reads Zetaris records, weighs costs, accepts, rejects or escalates"},
        {"name": "Recovery Auditor", "kind": "Nemotron agent", "role": "Writes the incident report and the lesson stored in Meterless H-MEM"},
        {"name": "Nemotron injection guard", "kind": "Nemotron safety models", "role": "Screens untrusted database and business text before any agent reads it"},
        {"name": "Authority", "kind": "deterministic", "role": "Approves one exact action against the live system, single-use, two-minute TTL, or refuses"},
        {"name": "Restricted Executor", "kind": "deterministic", "role": "Runs only pg_terminate_backend under a least-privilege role"},
        {"name": "Verifier", "kind": "deterministic", "role": "Declares recovery only when checkout is back above target and nothing protected was harmed"},
    ],
    Architecture.GATED_SINGLE: [
        {"name": "Single agent", "kind": "Nemotron agent", "role": "Decides alone"},
        {"name": "Authority", "kind": "deterministic", "role": "Same safety gate as the pact"},
        {"name": "Verifier", "kind": "deterministic", "role": "Database-only check"},
    ],
    Architecture.NAIVE_SINGLE: [
        {"name": "Single agent", "kind": "Nemotron agent", "role": "Decides alone with direct database privileges"},
    ],
}

_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,48}$")


def resolve_scenario(value: str) -> IncidentScenario:
    v = str(value).strip()
    for sc in IncidentScenario:
        if v.upper() in (sc.value, sc.value.split("_")[0]) or v.lower() == get_spec(sc).title.lower():
            return sc
    raise ValueError(f"unknown scenario {value!r}; use A-H or one of {[s.value for s in IncidentScenario]}")


def _error(run_id: str | None, etype: str, message: str, recoverable: bool, started: float) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "error",
        "error": {"type": etype, "message": message, "recoverable": recoverable},
        "trace_id": run_id,
        "execution_time_seconds": round(time.time() - started, 1),
    }


def _summary(result: dict[str, Any]) -> str:
    outcome = result.get("outcome")
    act = result.get("action") or {}
    target = (act.get("target") or {}).get("application_name") or "the blocker"
    if outcome == "VERIFIED_RECOVERED":
        how = "waited for it to finish" if act.get("kind") == "WAIT" else f"terminated {target}"
        text = f"Recovered: the pact {how}; checkout verified back above target."
    elif outcome == "ESCALATED":
        text = "Escalated to a human with a decision brief; no automatic action was taken."
    elif outcome == "DENIED":
        text = "The authority refused the agreed action; nothing ran."
    else:
        text = f"Outcome {outcome}."
    if result.get("lost_checkouts") is not None:
        text += f" Lost checkouts during the incident: {result['lost_checkouts']}."
    if result.get("injection_flagged"):
        text += " A hidden instruction in the data was quarantined by the Nemotron guard."
    return text


def execute(request: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    req_id = request.get("run_id")
    run_id = req_id if isinstance(req_id, str) and _RUN_ID.match(req_id) else None
    inp = request.get("input") or {}
    opts = request.get("options") or {}
    try:
        scenario = resolve_scenario(inp.get("scenario") or inp.get("query") or "")
        arch = Architecture(inp.get("architecture") or "pact")
    except ValueError as exc:
        return _error(run_id, "InvalidInput", str(exc), False, started)
    if run_store.busy.locked():
        return _error(run_id, "Busy", "another RecoveryPact run is using the database; retry when it finishes", True, started)

    client = get_inference_client()
    prev_mode = client.mode
    sample = bool(opts.get("sample_mode", get_settings().sample_mode))
    if sample:
        client.mode = "replay"
    try:
        run = run_blocking(scenario, arch, use_memory=bool(inp.get("use_memory", True)),
                           slot=str(opts.get("slot") or "main"), run_id=run_id)
    except ReplayMissing as exc:
        return _error(run_id, "ReplayMissing", str(exc), True, started)
    except Exception as exc:  # noqa: BLE001 — the contract is a structured error, never a crash
        return _error(run_id, type(exc).__name__, str(exc)[:500], True, started)
    finally:
        client.mode = prev_mode

    result = run.result or {}
    if result.get("outcome") == "NOT_RUN" or run.status == "error":
        return _error(run.run_id, "NotRun", result.get("reason") or "the run did not complete; see the trace", True, started)
    brief = result.get("brief") or {}
    return {
        "run_id": run.run_id,
        "status": "success",
        "input": {"scenario": scenario.value, "title": get_spec(scenario).title, "architecture": arch.value},
        "output": {
            "summary": _summary(result),
            "outcome": result.get("outcome"),
            "expected_outcome": result.get("expected_outcome"),
            "correct": result.get("correct"),
            "action": result.get("action"),
            "safety": {k: result.get(k) for k in ("unsafe_action", "business_harm", "false_recovery_claim", "injection_flagged")},
            "business_cost": {k: result.get(k) for k in ("lost_checkouts", "revenue_lost_usd", "settlements_aborted")},
            "recommendations": ([brief.get("recommendation")] if brief.get("recommendation") else []) + [o.get("label") or str(o) for o in brief.get("options") or []],
            "artifacts": [f"logs/trace-{run.run_id}.jsonl", f"data/runs/{run.run_id}.json"],
        },
        "agents": AGENTS[arch],
        "inference": {"mode": "replay" if sample else client.mode, "model": run.model},
        "business_context": get_business_context().mode,
        "rounds": result.get("rounds"),
        "model_calls": result.get("model_calls"),
        "trace_id": run.run_id,
        "log_file": f"logs/trace-{run.run_id}.jsonl",
        "execution_time_seconds": round(time.time() - started, 1),
    }
