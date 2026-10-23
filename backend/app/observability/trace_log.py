"""Per-run agent trace: logs/trace-<run_id>.jsonl plus one readable stdout line per step.

Every RunEvent the orchestrator emits is mirrored here, so the file shows which
agent acted, what it was asked, who it handed off to, grounding retries,
fallbacks, Zetaris and Meterless calls, the authority's decision and the final
outcome. Secrets never reach events; the redaction below is a second line of
defence for anything that looks like a key.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
from pathlib import Path
from typing import Any

from app.config import get_settings

AGENT_NAMES = {
    "database_guardian": "Database Guardian",
    "continuity_guardian": "Continuity Guardian",
    "recovery_auditor": "Recovery Auditor",
    "solo_agent": "Single agent",
    "authority": "Authority",
    "executor": "Restricted Executor",
    "verifier": "Verifier",
    "zetaris": "Zetaris",
    "meterless_hmem": "Meterless H-MEM",
    "observer": "Observer",
    "business_calculator": "Trade-off calculator",
    "grounding_check": "Grounding check",
    "injection_guard": "Nemotron injection guard",
    "detector": "Detector",
    "simulator": "Incident simulator",
    "eval_judge": "Eval judge",
    "human": "Human",
    "pact": "Pact",
    "orchestrator": "Orchestrator",
}

# Who acts next after each kind of step (the handoff a reader follows).
NEXT = {
    "proposal": "continuity_guardian",
    "contract": "authority",
    "authority": "executor",
    "execution": "verifier",
    "agreement": "authority",
    "escalation": "human",
}

_SECRET = re.compile(r"(nvapi-|sk-|Bearer\s+)[A-Za-z0-9._\-]{8,}")
_lock = threading.Lock()


def _stdout_logger() -> logging.Logger:
    log = logging.getLogger("recoverypact.trace")
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        log.addHandler(h)
        log.propagate = False
        log.setLevel(get_settings().log_level)
    return log


def redact(text: str) -> str:
    return _SECRET.sub(lambda m: m.group(1) + "...redacted", text)


def _metrics(data: dict[str, Any]) -> list[dict[str, Any]]:
    m = data.get("metrics")
    if isinstance(m, dict):
        return [m]
    return [x for x in m if isinstance(x, dict)] if isinstance(m, list) else []


def _input_summary(kind: str, data: dict[str, Any]) -> str:
    p, r = data.get("proposal") or {}, data.get("review") or {}
    if kind == "proposal" and p:
        return f"cited {', '.join(p.get('cited_evidence') or []) or 'no evidence'}; requested {', '.join(p.get('requested_probes') or []) or 'no probes'}"
    if kind == "review" and r:
        return f"required evidence {', '.join(r.get('required_evidence') or []) or 'none'}"
    for k in ("probe", "source", "query", "sql"):
        if data.get(k):
            return f"{k}={str(data[k])[:200]}"
    return ""


def append(run_id: str, ev: Any, logs_dir: str | None = None) -> None:
    data = ev.data or {}
    metrics = _metrics(data)
    attempts = data.get("attempts") or 1
    proposal = data.get("proposal") or {}
    status = "error" if ev.kind == "error" else "warning" if ev.kind in ("override", "grounding") else "success"
    row = {
        "timestamp": ev.ts.isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "seq": ev.seq,
        "agent_name": AGENT_NAMES.get(ev.actor, ev.actor),
        "action": ev.kind,
        "input_summary": redact(_input_summary(ev.kind, data)),
        "output_summary": redact(ev.title),
        "target_agent": AGENT_NAMES.get(NEXT.get(ev.kind, ""), None),
        "confidence": proposal.get("confidence"),
        "retry_count": max(0, int(attempts) - 1) if isinstance(attempts, int) else 0,
        "status": status,
        "models": sorted({m.get("model") for m in metrics if m.get("model")}),
        "inference": sorted({m.get("mode") for m in metrics if m.get("mode")}),
        "latency_ms": round(sum(m.get("latency_ms") or 0 for m in metrics), 1) or None,
        "tokens": sum((m.get("prompt_tokens") or 0) + (m.get("completion_tokens") or 0) for m in metrics) or None,
    }
    path = Path(logs_dir or get_settings().logs_dir) / f"trace-{run_id}.jsonl"
    try:
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass
    level = logging.WARNING if status != "success" else logging.INFO
    _stdout_logger().log(level, "run_id=%s %s %s: %s", run_id, row["agent_name"], ev.kind, row["output_summary"])
