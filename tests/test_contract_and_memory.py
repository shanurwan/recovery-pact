"""Recovery Contract integrity, authority policy, and Meterless H-MEM behaviour."""

from __future__ import annotations

import sqlite3

import pytest

from app.authority.gate import AuthorityGate
from app.memory.hmem import HMEM, HashEmbedder
from app.schemas.contract import ProposedAction, RecoveryContract
from app.schemas.enums import ContractState, RemediationActionType, WorkloadClass


def contract(target: dict, wl: WorkloadClass = WorkloadClass.BATCH_REPLAYABLE) -> RecoveryContract:
    c = RecoveryContract(
        incident_id="inc-1",
        proposed_action=ProposedAction(
            action_type=RemediationActionType.TERMINATE_BACKEND,
            exact_target=target,
            reason="r",
            expected_effect="e",
            workload_class=wl,
        ),
        exact_target=target,
        reason="r",
        expected_effect="e",
        required_preconditions=["no_protected_settlement"],
    )
    c.transition_to(ContractState.AGREED)
    c.transition_to(ContractState.SUBMITTED_FOR_AUTHORIZATION)
    return c.seal()


BATCH = {"pid": 101, "usename": "batch_worker", "application_name": "batch_replayable_inventory"}


def test_tampering_after_sealing_breaks_the_digest():
    c = contract(BATCH)
    assert c.verify_digest()
    c.exact_target["pid"] = 999
    assert not c.verify_digest()


def test_illegal_state_transition_is_refused():
    c = contract(BATCH)
    with pytest.raises(ValueError):
        c.transition_to(ContractState.VERIFIED)


class FakeGate(AuthorityGate):
    """Authority with the live database lookups replaced by a fixed view."""

    def __init__(self, live: dict | None, settlements: bool = False) -> None:
        super().__init__()
        self.live = live
        self.settlements = settlements

    def _live_backend(self, pid):
        return self.live if self.live and self.live["pid"] == pid else None

    def _any_protected_settlement(self) -> bool:
        return self.settlements


def test_authority_authorizes_an_allowlisted_live_target_once():
    gate = FakeGate(BATCH | {"state": "idle in transaction"})
    d = gate.evaluate(contract(BATCH))
    assert d.authorized, d.reason
    assert gate.consume(d.authorization_id, 101).authorized
    assert not gate.consume(d.authorization_id, 101).authorized  # single use: replay refused


def test_agreement_is_not_permission_for_a_checkout_session():
    target = {"pid": 202, "usename": "checkout", "application_name": "checkout_api"}
    gate = FakeGate(target | {"state": "active"})
    d = gate.evaluate(contract(target, WorkloadClass.CHECKOUT))
    assert not d.authorized
    failed = {c["name"] for c in d.checks if not c["passed"]}
    assert {"role_allowlist", "app_allowlist"} <= failed


def test_stale_pid_fails_only_live_identity():
    gate = FakeGate(None)  # the session reconnected under another pid
    d = gate.evaluate(contract(BATCH))
    assert not d.authorized
    assert {c["name"] for c in d.checks if not c["passed"]} == {"live_identity"}


def test_tampered_contract_is_denied():
    c = contract(BATCH)
    c.reason = "edited after sealing"
    d = FakeGate(BATCH | {"state": "idle"}).evaluate(c)
    assert not d.authorized
    assert any(ch["name"] == "content_digest" and not ch["passed"] for ch in d.checks)


# ------------------------------------------------------------------- H-MEM


@pytest.fixture
def hmem(tmp_path):
    return HMEM(tmp_path / "h.sqlite3", HashEmbedder(), threshold=0.05)


def test_recall_ranks_the_matching_workload_first(hmem):
    hmem.add("Verified pact: terminating batch_replayable_inventory restored checkout.",
             entities=["batch_replayable_inventory"], conflict_key="terminate:batch_replayable_inventory", verdict="effective")
    hmem.add("Waiting for protected_settlement was correct.", entities=["protected_settlement"])
    res = hmem.query("root blocker batch_replayable_inventory blocks checkout", entities=["batch_replayable_inventory"])
    assert res.memories
    assert "batch_replayable_inventory" in res.memories[0].memory["content"]
    assert "[MEMORY CONTEXT]" in res.context and set(res.memories[0].terms) >= {"semantic", "entity", "recency"}


def test_newer_contradicting_verdict_supersedes_never_deletes(hmem):
    old = hmem.add("terminating price_sync is effective", conflict_key="terminate:price_sync", verdict="effective")
    new = hmem.add("terminating price_sync was INEFFECTIVE", conflict_key="terminate:price_sync", verdict="ineffective")
    assert new["supersedes"] == old["id"]
    assert hmem.get(old["id"])["superseded_by"] == new["id"]
    assert len(hmem.list()) == 2


def test_feedback_moves_confidence_and_promotes_after_two_helpful(hmem):
    m = hmem.add("lesson about batch_replayable_inventory", confidence=0.7)
    hmem.feedback(m["id"], "helpful")
    hmem.feedback(m["id"], "helpful")
    got = hmem.get(m["id"])
    assert got["layer"] == "long_term"
    assert got["confidence"] == pytest.approx(0.8)
    hmem.feedback(m["id"], "wrong")
    got = hmem.get(m["id"])
    assert got["confidence"] == pytest.approx(0.6)
    assert "review" in got["tags"]


def test_trust_ledger_is_append_only(hmem):
    hmem.add("anything")
    with sqlite3.connect(hmem.path) as c:
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("DELETE FROM ledger")
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("UPDATE ledger SET action='x'")
