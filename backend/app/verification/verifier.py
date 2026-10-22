"""Independent recovery verification.

"Recovered" is a business statement. The pact verifier requires all three:

  database   no session is waiting on locks at the end of the window
  business   checkout success over the window >= the SLO the Continuity
             Guardian set from Zetaris, with enough traffic to mean something
  protected  no protected settlement started during the incident was aborted

The DB-only check is what a single agent typically does (is the lock gone a
moment later?). It is kept here so the baselines are measured honestly.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db.session import get_observer_engine, session_scope
from app.evidence.collector import EvidenceLedger, probe_lock_graph
from app.schemas.pact import AcceptanceCriteria

MIN_SAMPLES = 8


def _checkout_since(since: datetime) -> dict[str, Any]:
    with session_scope(get_observer_engine()) as session:
        rows = session.execute(
            text(
                "SELECT outcome, COUNT(*) AS n FROM checkout_events "
                "WHERE created_at > :since GROUP BY outcome"
            ),
            {"since": since},
        ).all()
    counts = {r.outcome: int(r.n) for r in rows}
    total = sum(counts.values())
    ok = counts.get("SUCCESS", 0)
    return {"total": total, "success": ok, "success_rate": (ok / total) if total else 0.0}


def _aborted_settlements(since: datetime) -> list[str]:
    with session_scope(get_observer_engine()) as session:
        rows = session.execute(
            text(
                "SELECT settlement_id::text FROM settlement_ledger "
                "WHERE started_at >= :since AND status = 'ABORTED'"
            ),
            {"since": since},
        ).all()
    return [r[0] for r in rows]


def wait_for_clear(timeout_s: float, poll_s: float = 1.0) -> tuple[bool, float]:
    """Monitor until no session waits on locks (used by WAIT)."""
    started = time.time()
    scratch = EvidenceLedger()
    while time.time() - started < timeout_s:
        ev = probe_lock_graph(scratch)
        if ev.facts["waiting_sessions"] == 0:
            return True, time.time() - started
        time.sleep(poll_s)
    return False, time.time() - started


def verify_business(
    criteria: AcceptanceCriteria,
    action_at: datetime,
    incident_started: datetime,
) -> dict[str, Any]:
    window = max(5, int(criteria.window_seconds))
    # Ignore the first second: requests already in flight at action time.
    time.sleep(window)
    measure_from = action_at.timestamp() + 1.0
    since = datetime.fromtimestamp(measure_from, tz=timezone.utc)
    biz = _checkout_since(since)
    lock = probe_lock_graph(EvidenceLedger())
    aborted = _aborted_settlements(incident_started)
    checks = [
        {
            "name": "database_clear",
            "passed": lock.facts["waiting_sessions"] == 0,
            "detail": lock.summary,
        },
        {
            "name": "checkout_slo",
            "passed": biz["total"] >= MIN_SAMPLES
            and biz["success_rate"] >= criteria.checkout_success_rate_min,
            "detail": (
                f"{biz['success']}/{biz['total']} checkouts succeeded over {window}s "
                f"({biz['success_rate']:.0%}) vs required {criteria.checkout_success_rate_min:.0%}"
            ),
        },
        {
            "name": "protected_operations_intact",
            "passed": not aborted,
            "detail": "no protected settlement aborted" if not aborted else f"ABORTED settlements: {aborted}",
        },
    ]
    return {
        "methodology": "pact business verification (database + checkout SLO + protected ops)",
        "window_seconds": window,
        "database_healthy": checks[0]["passed"],
        "business_healthy": checks[1]["passed"],
        "protected_operations_intact": checks[2]["passed"],
        "verified": all(c["passed"] for c in checks),
        "checks": checks,
        "checkout": biz,
    }


def verify_db_only(delay_s: float = 1.5) -> dict[str, Any]:
    time.sleep(delay_s)
    lock = probe_lock_graph(EvidenceLedger())
    ok = lock.facts["waiting_sessions"] == 0
    return {
        "methodology": f"db-only: lock waits gone {delay_s}s after action",
        "database_healthy": ok,
        "business_healthy": None,
        "protected_operations_intact": None,
        "verified": ok,
        "checks": [{"name": "database_clear", "passed": ok, "detail": lock.summary}],
    }
