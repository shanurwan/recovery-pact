"""Deterministic guards around the LLM guardians: grounding, invariants, calculator.

No database or model needed: these are the parts that must hold no matter what
the model says.
"""

from __future__ import annotations

from app.agents.guardians import (
    TurnContext,
    _clean_ids,
    _resolve_candidate,
    enforce_business_invariants,
    ground_proposal,
    ground_review,
)
from app.evidence.collector import EvidenceLedger, derive_tradeoff, enumerate_candidates
from app.schemas.enums import ChallengeDecision
from app.schemas.pact import Proposal, Review

APP = "batch_replayable_inventory"


def lock_graph(ledger: EvidenceLedger, app: str = APP, usename: str = "batch_worker", age: float = 4.0):
    return ledger.add(
        probe="db.lock_graph",
        source="postgresql_observer",
        summary=f"pid 101 ({usename}/{app}) blocks checkout",
        facts={
            "root_blockers": [
                {"pid": 101, "usename": usename, "application_name": app, "state": "idle in transaction",
                 "xact_age_s": age, "blocked_sessions": 1}
            ],
            "waiting_sessions": 12,
        },
    )


def registry(ledger: EvidenceLedger, app: str = APP, **over):
    rec = {
        "application_name": app, "job_name": "inventory_reconcile", "owner_team": "inventory-platform",
        "workload_class": "BATCH_REPLAYABLE", "replayable": True, "replay_cost_minutes": 4,
        "typical_runtime_s": 900, "interrupt_policy": "may_interrupt", "business_purpose": "x",
    } | over
    return ledger.add(probe="biz.workload_registry", source="zetaris", summary=f"{app} = job ...",
                      facts={"records": [rec]})


def calendar(ledger: EvidenceLedger, app: str = APP, policy: str | None = None):
    recs = [{"change_id": "CHG-1", "application_name": app, "policy": policy, "scope": "job"}] if policy else []
    return ledger.add(probe="biz.change_calendar", source="zetaris",
                      summary=f"calendar for {app}", facts={"records": recs})


def impact(ledger: EvidenceLedger, at_risk: float = 2629.0, tolerance: int = 60):
    return ledger.add(probe="biz.impact", source="zetaris", summary="impact",
                      facts={"revenue_at_risk_per_min": at_risk, "max_degradation_s": tolerance,
                             "slo_success_rate": 0.95, "verification_window_s": 10})


def ctx_for(ledger: EvidenceLedger) -> TurnContext:
    lg = ledger.latest("db.lock_graph")
    return TurnContext("checkout timing out", 1, 3, enumerate_candidates(lg), ledger, "", [], "test")


def accept(**kw) -> Review:
    return Review(round=1, review_id="r", decision=ChallengeDecision.ACCEPT, **kw)


def terminate_proposal(cited: list[str]) -> Proposal:
    return Proposal(round=1, candidate_id=f"terminate:{APP}", rationale="free the lock", cited_evidence=cited)


# ----------------------------------------------------------------- grounding


def test_candidates_come_only_from_observed_evidence():
    led = EvidenceLedger()
    lg = lock_graph(led)
    ids = [c.candidate_id for c in enumerate_candidates(lg)]
    assert ids == [f"terminate:{APP}", "wait", "escalate"]


def test_proposal_with_invented_candidate_or_evidence_is_rejected():
    led = EvidenceLedger()
    lock_graph(led)
    ctx = ctx_for(led)
    g = ground_proposal(Proposal(round=1, candidate_id="drop_table", rationale="x", cited_evidence=["DB-9"]), ctx)
    assert not g.ok
    assert any("not in CANDIDATES" in p for p in g.problems)
    assert any("do not exist" in p for p in g.problems)


def test_termination_must_cite_the_lock_graph_that_observed_it():
    led = EvidenceLedger()
    lg = lock_graph(led)
    tel = led.add(probe="tel.checkout_health", source="checkout_telemetry", summary="bad", facts={})
    ctx = ctx_for(led)
    assert not ground_proposal(terminate_proposal([tel.evidence_id]), ctx).ok
    assert ground_proposal(terminate_proposal([lg.evidence_id]), ctx).ok


def test_id_normalization_fixes_format_not_meaning():
    raw = _clean_ids({"cited_evidence": ["EVIDENCE: [DB-1", "MEMORY:MEM-4", "mem-28167f59"]}, "cited_evidence")
    assert raw["cited_evidence"] == ["DB-1", "MEM-4", "mem-28167f59"]


def test_candidate_shorthand_resolves_only_when_unambiguous():
    led = EvidenceLedger()
    lock_graph(led)
    ctx = ctx_for(led)
    assert _resolve_candidate("terminate", ctx) == f"terminate:{APP}"
    assert _resolve_candidate("nonsense", ctx) == "nonsense"


def test_review_cannot_request_evidence_that_is_already_present():
    led = EvidenceLedger()
    lock_graph(led)
    registry(led)
    calendar(led)
    ctx = ctx_for(led)
    r = Review(round=1, review_id="r", decision=ChallengeDecision.REQUEST_REVISION,
               objection="need more", required_evidence=["biz.workload_registry", "biz.change_calendar"])
    assert not ground_review(r, ctx).ok


# ---------------------------------------------------------------- invariants


def test_I2_acceptance_without_registry_and_calendar_is_downgraded():
    led = EvidenceLedger()
    lg = lock_graph(led)
    ctx = ctx_for(led)
    out = enforce_business_invariants(accept(), terminate_proposal([lg.evidence_id]), ctx)
    assert out.decision == ChallengeDecision.REQUEST_REVISION
    assert set(out.required_evidence) >= {"biz.workload_registry", "biz.change_calendar"}


def test_acceptance_stands_when_every_invariant_holds():
    led = EvidenceLedger()
    lg = lock_graph(led)
    registry(led)
    calendar(led)
    ctx = ctx_for(led)
    assert enforce_business_invariants(accept(), terminate_proposal([lg.evidence_id]), ctx).decision == ChallengeDecision.ACCEPT


def test_I1_never_interrupt_workload_is_rejected_even_if_model_accepts():
    led = EvidenceLedger()
    lg = lock_graph(led, app="protected_settlement", usename="settlement_worker")
    registry(led, app="protected_settlement", workload_class="PROTECTED_SETTLEMENT",
             interrupt_policy="never_interrupt", replayable=False)
    calendar(led, app="protected_settlement")
    ctx = ctx_for(led)
    p = Proposal(round=1, candidate_id="terminate:protected_settlement", rationale="x", cited_evidence=[lg.evidence_id])
    assert enforce_business_invariants(accept(), p, ctx).decision == ChallengeDecision.REJECT


def test_I3_consult_owner_window_forces_escalation():
    led = EvidenceLedger()
    lg = lock_graph(led)
    registry(led)
    calendar(led, policy="consult_owner")
    ctx = ctx_for(led)
    out = enforce_business_invariants(accept(), terminate_proposal([lg.evidence_id]), ctx)
    assert out.decision == ChallengeDecision.ESCALATE
    assert "I3" in out.violated_invariants


def test_I4_unknown_workload_cannot_be_terminated():
    led = EvidenceLedger()
    lg = lock_graph(led, app="adhoc_reporting")
    led.add(probe="biz.workload_registry", source="zetaris",
            summary="adhoc_reporting: NOT FOUND in the workload registry", facts={"records": []})
    calendar(led, app="adhoc_reporting")
    ctx = ctx_for(led)
    p = Proposal(round=1, candidate_id="terminate:adhoc_reporting", rationale="x", cited_evidence=[lg.evidence_id])
    assert enforce_business_invariants(accept(), p, ctx).decision == ChallengeDecision.REJECT


def test_M1_memory_can_veto_a_repeat_of_an_ineffective_termination():
    led = EvidenceLedger()
    lg = lock_graph(led)
    registry(led)
    calendar(led)
    led.add(probe="mem.recall", source="meterless_hmem", summary="recalled",
            facts={"recalled": [{"id": "mem-1", "tags": [f"ck:terminate:{APP}", "verdict:ineffective"], "superseded": False}]})
    ctx = ctx_for(led)
    out = enforce_business_invariants(accept(), terminate_proposal([lg.evidence_id]), ctx)
    assert out.decision == ChallengeDecision.ESCALATE
    assert "M1" in out.violated_invariants


def test_M1_superseded_memory_does_not_veto():
    led = EvidenceLedger()
    lg = lock_graph(led)
    registry(led)
    calendar(led)
    led.add(probe="mem.recall", source="meterless_hmem", summary="recalled",
            facts={"recalled": [{"id": "mem-1", "tags": [f"ck:terminate:{APP}", "verdict:ineffective"], "superseded": True}]})
    ctx = ctx_for(led)
    assert enforce_business_invariants(accept(), terminate_proposal([lg.evidence_id]), ctx).decision == ChallengeDecision.ACCEPT


def test_I7_waiting_beyond_business_tolerance_is_rejected():
    led = EvidenceLedger()
    lg = lock_graph(led)
    registry(led)
    impact(led)
    derive_tradeoff(led)
    ctx = ctx_for(led)
    wait = Proposal(round=1, candidate_id="wait", rationale="let it finish", cited_evidence=[lg.evidence_id])
    out = enforce_business_invariants(accept(), wait, ctx)
    assert out.decision == ChallengeDecision.REJECT
    assert "I7" in out.violated_invariants


def test_I7_waiting_for_a_short_settlement_is_allowed():
    led = EvidenceLedger()
    lg = lock_graph(led, app="protected_settlement", usename="settlement_worker", age=10)
    registry(led, app="protected_settlement", typical_runtime_s=45, interrupt_policy="never_interrupt")
    impact(led)
    derive_tradeoff(led)
    ctx = ctx_for(led)
    wait = Proposal(round=1, candidate_id="wait", rationale="settlement finishes soon", cited_evidence=[lg.evidence_id])
    assert enforce_business_invariants(accept(), wait, ctx).decision == ChallengeDecision.ACCEPT


# --------------------------------------------------------------- calculator


def test_tradeoff_arithmetic_is_done_in_code():
    led = EvidenceLedger()
    lock_graph(led, age=0)
    registry(led)
    impact(led, at_risk=600.0, tolerance=60)
    t = derive_tradeoff(led)
    row = t.facts["rows"][0]
    assert row["expected_remaining_s"] == 900
    assert row["wait_cost_usd"] == 9000  # 600 $/min * 15 min
    assert row["wait_within_tolerance"] is False
    assert "EXCEEDS" in t.summary
    assert derive_tradeoff(led) is None  # same inputs: nothing new
