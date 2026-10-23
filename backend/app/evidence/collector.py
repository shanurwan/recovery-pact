"""Evidence probes and candidate enumeration.

Each probe turns one observation into an ``Evidence`` record with a run-scoped
id the guardians must cite. Candidate actions are derived from the lock graph
here, in code, so a guardian can only choose among targets that were observed.
"""

from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_observer_engine, session_scope
from app.integrations.nemotron.guard import get_guard
from app.integrations.zetaris.business import BusinessAnswer, get_business_context
from app.schemas.enums import CandidateKind
from app.schemas.pact import Candidate, Evidence
from app.services.checkout import health_snapshot

REPLAYABLE_APP_PREFIX = "batch_replayable_"


def untrusted(text_: str | None, field: str, guard_log: list[dict[str, Any]]) -> str:
    """Screen text an outsider could have written before any agent reads it."""
    text_ = text_ or ""
    s = get_settings()
    if not (s.reasoning_scaffold and s.guard_enabled) or not text_.strip():
        return text_
    v = get_guard().screen(text_)
    if not v.unsafe:
        return text_
    guard_log.append({"field": field, "model": v.model, "verdict": v.raw, "error": v.error, "excerpt": text_[:160]})
    return f"[QUARANTINED by Nemotron safety guard: the {field} contained instructions addressed to an AI agent]"


def classify_workload(usename: str | None, application_name: str | None) -> str:
    """Static, technical classification used by the authority gate.

    It knows roles and naming conventions only, not business context. That gap
    is deliberate: it is what the Continuity Guardian exists to fill.
    """
    if application_name == "protected_settlement" or usename == "settlement_worker":
        return "PROTECTED_SETTLEMENT"
    if (application_name or "").startswith(REPLAYABLE_APP_PREFIX):
        return "BATCH_REPLAYABLE"
    if application_name == "checkout_api" or usename == "checkout":
        return "CHECKOUT"
    return "UNKNOWN"


class EvidenceLedger:
    """Run-scoped evidence store with stable, citeable ids."""

    PREFIX = {
        "postgresql_observer": "DB",
        "checkout_telemetry": "TEL",
        "zetaris": "BIZ",
        "local_federation_fallback": "BIZ",
        "business_unavailable": "BIZ",
        "meterless_hmem": "MEM",
    }

    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}
        self._n: dict[str, int] = {}
        self._lock = threading.Lock()

    def add(self, **kwargs: Any) -> Evidence:
        # One counter per source: whether memory recalls something must not shift
        # the ids of database or business evidence (replay cites them by id).
        with self._lock:
            prefix = self.PREFIX[kwargs["source"]]
            self._n[prefix] = self._n.get(prefix, 0) + 1
            eid = f"{prefix}-{self._n[prefix]}"
            ev = Evidence(evidence_id=eid, **kwargs)
            self._items[eid] = ev
            return ev

    def get(self, eid: str) -> Evidence | None:
        return self._items.get(eid)

    def has(self, eid: str) -> bool:
        return eid in self._items

    def all(self) -> list[Evidence]:
        return list(self._items.values())

    def by_probe(self, probe: str) -> list[Evidence]:
        return [e for e in self._items.values() if e.probe == probe]

    def latest(self, probe: str) -> Evidence | None:
        found = self.by_probe(probe)
        return found[-1] if found else None


# --------------------------------------------------------------------- probes


def probe_lock_graph(ledger: EvidenceLedger, requested_by: str = "orchestrator") -> Evidence:
    with session_scope(get_observer_engine()) as session:
        rows = session.execute(
            text(
                """
                SELECT
                  blocked.pid AS blocked_pid,
                  blocked.application_name AS blocked_app,
                  blocking.pid AS blocking_pid,
                  blocking.usename AS blocking_user,
                  blocking.application_name AS blocking_app,
                  blocking.state AS blocking_state,
                  LEFT(blocking.query, 600) AS blocking_query,
                  EXTRACT(EPOCH FROM (now() - blocking.xact_start)) AS blocking_xact_age_s
                FROM pg_stat_activity blocked
                JOIN pg_locks bl ON bl.pid = blocked.pid AND NOT bl.granted
                JOIN pg_locks bk ON bk.locktype = bl.locktype
                  AND bk.database IS NOT DISTINCT FROM bl.database
                  AND bk.relation IS NOT DISTINCT FROM bl.relation
                  AND bk.page IS NOT DISTINCT FROM bl.page
                  AND bk.tuple IS NOT DISTINCT FROM bl.tuple
                  AND bk.virtualxid IS NOT DISTINCT FROM bl.virtualxid
                  AND bk.transactionid IS NOT DISTINCT FROM bl.transactionid
                  AND bk.classid IS NOT DISTINCT FROM bl.classid
                  AND bk.objid IS NOT DISTINCT FROM bl.objid
                  AND bk.objsubid IS NOT DISTINCT FROM bl.objsubid
                  AND bk.pid <> bl.pid
                  AND bk.granted
                JOIN pg_stat_activity blocking ON blocking.pid = bk.pid
                WHERE blocked.datname = current_database()
                """
            )
        ).mappings().all()

    blocked_pids = {r["blocked_pid"] for r in rows}
    roots: dict[int, dict[str, Any]] = {}
    for r in rows:
        pid = r["blocking_pid"]
        if pid in blocked_pids:
            continue  # part of the queue, not a root holder
        root = roots.setdefault(
            pid,
            {
                "pid": pid,
                "usename": r["blocking_user"],
                "application_name": r["blocking_app"],
                "state": r["blocking_state"],
                "query": r["blocking_query"],
                "xact_age_s": round(float(r["blocking_xact_age_s"] or 0), 1),
                "blocked_sessions": 0,
                "technical_class": classify_workload(r["blocking_user"], r["blocking_app"]),
            },
        )
        root["blocked_sessions"] += 1

    waiters = len(blocked_pids)
    guard_log: list[dict[str, Any]] = []
    for b in roots.values():
        b["query"] = untrusted(b.get("query"), "session query text", guard_log)
    if roots:
        parts = [
            f"pid {b['pid']} ({b['usename']}/{b['application_name']}, {b['state']}, "
            f"txn open {b['xact_age_s']}s) blocks {b['blocked_sessions']} session(s); last statement: {b['query'][:400]}"
            for b in roots.values()
        ]
        summary = f"{waiters} session(s) waiting on locks. Root blocker(s): " + "; ".join(parts)
    else:
        summary = "No lock waits: no session is blocked."
    return ledger.add(
        probe="db.lock_graph",
        source="postgresql_observer",
        summary=summary,
        facts={"root_blockers": list(roots.values()), "waiting_sessions": waiters, "guard": guard_log},
        requested_by=requested_by,
    )


def probe_protected_settlements(ledger: EvidenceLedger, requested_by: str = "orchestrator") -> Evidence:
    with session_scope(get_observer_engine()) as session:
        rows = session.execute(
            text(
                """
                SELECT settlement_id::text, amount_cents, status,
                       EXTRACT(EPOCH FROM (now() - started_at)) AS age_s
                FROM settlement_ledger
                WHERE status = 'IN_PROGRESS' AND protected = TRUE
                """
            )
        ).mappings().all()
    items = [
        {
            "settlement_id": r["settlement_id"],
            "amount_cents": r["amount_cents"],
            "age_s": round(float(r["age_s"]), 1),
        }
        for r in rows
    ]
    if items:
        total = sum(i["amount_cents"] for i in items) / 100
        summary = f"{len(items)} protected card settlement(s) in flight, ${total:,.2f} total."
    else:
        summary = "No protected settlements in flight."
    return ledger.add(
        probe="db.protected_settlements",
        source="postgresql_observer",
        summary=summary,
        facts={"in_flight": items},
        requested_by=requested_by,
    )


def probe_checkout_health(ledger: EvidenceLedger, window_s: int = 15) -> Evidence:
    h = health_snapshot(window_s)
    summary = (
        f"Checkout over last {window_s}s: {h['success_count']}/{h['total']} succeeded "
        f"({h['success_rate']:.0%}), {h['timeout_count']} timeouts."
    )
    return ledger.add(
        probe="tel.checkout_health",
        source="checkout_telemetry",
        summary=summary,
        facts=h,
    )


def _biz_evidence(
    ledger: EvidenceLedger, probe: str, ans: BusinessAnswer, summary: str, requested_by: str
) -> Evidence:
    return ledger.add(
        probe=probe,
        source=ans.source,
        summary=summary,
        facts={"records": ans.records, "notes": ans.notes},
        query=ans.query,
        latency_ms=round(ans.latency_ms, 1),
        requested_by=requested_by,
    )


def _unavailable(what: str, names: list[str]) -> str:
    return (
        f"UNAVAILABLE: the {what} could not be reached (business federation down). "
        f"What it says about {', '.join(names)} is UNKNOWN; this is not evidence that nothing is there."
    )


def probe_workload_registry(
    ledger: EvidenceLedger, app_names: list[str], requested_by: str
) -> Evidence:
    ans = get_business_context().workload_registry(app_names)
    if ans.source == "business_unavailable":
        return _biz_evidence(ledger, "biz.workload_registry", ans, _unavailable("workload registry", app_names), requested_by)
    known = {r["application_name"] for r in ans.records}
    parts = []
    guard_log: list[dict[str, Any]] = []
    for r in ans.records:
        r["business_purpose"] = untrusted(r.get("business_purpose"), "registry business_purpose", guard_log)
        cost = r.get("replay_cost_minutes")
        parts.append(
            f"{r['application_name']} = job '{r['job_name']}' owned by {r['owner_team']}, "
            f"class {r['workload_class']}, replayable={r['replayable']}, "
            f"replay cost {cost if cost is not None else 'n/a'} min, "
            f"typical runtime {r.get('typical_runtime_s')}s, policy {r['interrupt_policy']}. "
            f"{r['business_purpose']}"
        )
    for name in app_names:
        if name not in known:
            parts.append(f"{name}: NOT FOUND in the workload registry (owner and cost unknown).")
    ev = _biz_evidence(ledger, "biz.workload_registry", ans, " | ".join(parts), requested_by)
    ev.facts["guard"] = guard_log
    return ev


def probe_change_calendar(
    ledger: EvidenceLedger, app_names: list[str], requested_by: str
) -> Evidence:
    ans = get_business_context().change_calendar(app_names)
    if ans.source == "business_unavailable":
        return _biz_evidence(ledger, "biz.change_calendar", ans, _unavailable("change calendar", app_names), requested_by)
    guard_log: list[dict[str, Any]] = []
    for r in ans.records:
        r["reason"] = untrusted(r.get("reason"), "change-calendar reason", guard_log)
    if ans.records:
        summary = " | ".join(
            f"ACTIVE {r['change_id']} on job '{r['scope']}' ({r['application_name']}): "
            f"policy={r['policy']}. {r['reason']}"
            for r in ans.records
        )
    else:
        summary = "No active change-calendar window covers " + ", ".join(app_names) + "."
    ev = _biz_evidence(ledger, "biz.change_calendar", ans, summary, requested_by)
    ev.facts["guard"] = guard_log
    return ev


def probe_impact(ledger: EvidenceLedger, requested_by: str, window_s: int = 30) -> Evidence:
    ans = get_business_context().impact(window_s)
    if ans.source == "business_unavailable":
        ev = _biz_evidence(ledger, "biz.impact", ans, _unavailable("business impact (SLO, revenue)", ["checkout"]), requested_by)
        # The verifier still needs a bar to verify against: the static floor, labeled as such.
        # Revenue at risk stays unknown, so no trade-off is computed from it.
        ev.facts.update({"slo_success_rate": 0.95, "verification_window_s": 10, "max_degradation_s": 60,
                         "verification_defaults": True})
        return ev
    r = ans.records[0] if ans.records else {}
    total = int(r.get("total") or 0)
    failed = int(r.get("failed") or 0)
    rate = (total - failed) / total if total else 1.0
    rpm = (r.get("revenue_per_minute_cents") or 0) / 100
    at_risk = rpm * (failed / total) if total else 0.0
    summary = (
        f"Checkout success {rate:.0%} over {window_s}s ({failed}/{total} failed) vs SLO "
        f"{float(r.get('slo_success_rate') or 0):.0%}. Revenue run-rate ${rpm:,.0f}/min; "
        f"about ${at_risk:,.0f}/min at risk. Verification window {r.get('verification_window_s')}s. "
        f"The business tolerates at most {r.get('max_degradation_s')}s of degraded checkout."
    )
    ev = _biz_evidence(ledger, "biz.impact", ans, summary, requested_by)
    ev.facts.update(
        {
            "success_rate": round(rate, 4),
            "revenue_at_risk_per_min": round(at_risk, 2),
            "slo_success_rate": float(r.get("slo_success_rate") or 0.95),
            "verification_window_s": int(r.get("verification_window_s") or 10),
            "max_degradation_s": int(r.get("max_degradation_s") or 60),
        }
    )
    return ev


def run_probe(
    ledger: EvidenceLedger, probe: str, app_names: list[str], requested_by: str
) -> Evidence | None:
    if probe == "db.lock_graph":
        return probe_lock_graph(ledger, requested_by)
    if probe == "db.protected_settlements":
        return probe_protected_settlements(ledger, requested_by)
    if probe == "biz.workload_registry":
        return probe_workload_registry(ledger, app_names, requested_by)
    if probe == "biz.change_calendar":
        return probe_change_calendar(ledger, app_names, requested_by)
    if probe == "biz.impact":
        return probe_impact(ledger, requested_by)
    return None


def derive_tradeoff(ledger: EvidenceLedger) -> Evidence | None:
    """Deterministic business calculator: cost of waiting vs cost of interrupting.

    Arithmetic is not left to the model. Built from the latest lock graph,
    registry and impact evidence, and cites them.
    """
    lock = ledger.latest("db.lock_graph")
    impact = ledger.latest("biz.impact")
    reg_ev = ledger.latest("biz.workload_registry")
    if not (lock and impact and reg_ev):
        return None
    if "business_unavailable" in (impact.source, reg_ev.source):
        return None  # no arithmetic on unknown inputs
    prev = ledger.latest("biz.tradeoff")
    if prev and prev.facts.get("inputs", [])[1:] == [reg_ev.evidence_id, impact.evidence_id]:
        return None  # same registry and impact: nothing new to say
    registry = {r["application_name"]: r for r in reg_ev.facts.get("records", [])}
    at_risk = float(impact.facts.get("revenue_at_risk_per_min") or 0)
    tolerance = int(impact.facts.get("max_degradation_s") or 60)
    rows, parts = [], []
    for b in lock.facts.get("root_blockers", []):
        app = b.get("application_name")
        reg = registry.get(app)
        if not reg:
            parts.append(f"{app}: no registry entry, cost of interrupting is unknown.")
            continue
        runtime = reg.get("typical_runtime_s")
        remaining = max(0.0, float(runtime) - float(b.get("xact_age_s") or 0)) if runtime else None
        wait_cost = at_risk * remaining / 60 if remaining is not None else None
        row = {
            "application_name": app,
            "expected_remaining_s": round(remaining) if remaining is not None else None,
            "wait_cost_usd": round(wait_cost) if wait_cost is not None else None,
            "replay_cost_minutes": reg.get("replay_cost_minutes"),
            "replayable": reg.get("replayable"),
            "interrupt_policy": reg.get("interrupt_policy"),
            "max_degradation_s": tolerance,
            "wait_within_tolerance": remaining is not None and remaining <= tolerance,
        }
        rows.append(row)
        if remaining is not None:
            fit = "FITS within" if row["wait_within_tolerance"] else "EXCEEDS"
            wait_txt = (
                f"expected remaining runtime ~{row['expected_remaining_s']}s, so waiting costs "
                f"~${row['wait_cost_usd']:,} of checkout revenue at the current loss rate and "
                f"{fit} the {tolerance}s degradation the business tolerates"
            )
        else:
            wait_txt = "remaining runtime unknown"

        act_txt = (
            f"terminating costs a {reg.get('replay_cost_minutes')}-minute replay of {reg.get('job_name')}"
            if reg.get("replayable")
            else f"{reg.get('job_name')} is NOT replayable"
        )
        parts.append(f"{app}: {wait_txt}; {act_txt} (policy {reg.get('interrupt_policy')}).")
    return ledger.add(
        probe="biz.tradeoff",
        source=impact.source if impact.source != "checkout_telemetry" else "local_federation_fallback",
        summary="Trade-off (computed from "
        + ", ".join(e.evidence_id for e in (lock, reg_ev, impact))
        + "): "
        + " ".join(parts),
        facts={"rows": rows, "inputs": [lock.evidence_id, reg_ev.evidence_id, impact.evidence_id]},
        requested_by="business_calculator",
    )


# ----------------------------------------------------------------- candidates


def enumerate_candidates(lock_graph: Evidence) -> list[Candidate]:
    """Actions a guardian may choose, derived from observed evidence only."""
    out: list[Candidate] = []
    seen: dict[str, int] = {}
    for b in lock_graph.facts.get("root_blockers", []):
        app = b.get("application_name") or "unknown"
        seen[app] = seen.get(app, 0) + 1
        cid = f"terminate:{app}" if seen[app] == 1 else f"terminate:{app}#{seen[app]}"
        out.append(
            Candidate(
                candidate_id=cid,
                kind=CandidateKind.TERMINATE,
                description=(
                    f"Terminate the root blocker session ({b['usename']}/{app}, pid {b['pid']}) "
                    f"to release its locks."
                ),
                target={
                    "pid": b["pid"],
                    "usename": b["usename"],
                    "application_name": app,
                },
                evidence_id=lock_graph.evidence_id,
            )
        )
    out.append(
        Candidate(
            candidate_id="wait",
            kind=CandidateKind.WAIT,
            description="Take no action; let the blocker finish and monitor checkout recovery.",
        )
    )
    out.append(
        Candidate(
            candidate_id="escalate",
            kind=CandidateKind.ESCALATE,
            description="Hand the decision to the owning team with a decision brief.",
        )
    )
    return out


def blocker_app_names(lock_graph: Evidence | None) -> list[str]:
    if not lock_graph:
        return []
    return [b.get("application_name") or "unknown" for b in lock_graph.facts.get("root_blockers", [])]
