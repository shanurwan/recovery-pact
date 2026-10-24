"""Invariant I9: Zetaris data quality as a policy input.

With ZETARIS_QUERY_LAYER=usl every registry answer carries the semantic layer's own
data-quality verdict per row. A row that fails a rule, or that could not be checked,
can't vouch for a kill. No Zetaris needed: the client is faked.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agents.guardians import enforce_business_invariants
from app.evidence.collector import EvidenceLedger
from app.integrations.zetaris import business
from app.schemas.enums import ChallengeDecision
from test_reasoning_guards import accept, calendar, ctx_for, lock_graph, registry, terminate_proposal


def _decide(**row) -> ChallengeDecision:
    led = EvidenceLedger()
    lg = lock_graph(led)
    registry(led, **row)
    calendar(led)
    return enforce_business_invariants(accept(), terminate_proposal([lg.evidence_id]), ctx_for(led)).decision


def test_row_that_passes_data_quality_still_accepts():
    assert _decide(dq_valid=True, dq_failed_rules=[]) == ChallengeDecision.ACCEPT


def test_row_that_fails_data_quality_is_rejected_even_if_model_accepts():
    assert _decide(dq_valid=False, dq_failed_rules=["interruptible_is_replayable"]) == ChallengeDecision.REJECT


def test_unchecked_row_fails_closed():
    assert _decide(dq_valid=None, dq_failed_rules=[]) == ChallengeDecision.REJECT


def test_views_layer_rows_carry_no_verdict_and_are_unaffected():
    assert _decide() == ChallengeDecision.ACCEPT


class FakeZetaris:
    def __init__(self, invalid_apps):
        self.invalid = invalid_apps
        self.sql: list[str] = []

    def query(self, sql):
        self.sql.append(sql)
        if sql.startswith("RUN DQ"):
            bad = "1" if self.invalid else "0"
            rows = [["interruptible_is_replayable", "workload", "Custom Data Quality", "5", "4", bad],
                    ["application_name", "workload", "Primary Key Constraint", "5", "5", "0"]]
        else:
            rows = [[json.dumps({"application_name": a})] for a in self.invalid]
        return SimpleNamespace(rows=rows, latency_ms=10.0)


@pytest.mark.parametrize("invalid", [[], ["protected_settlement"]])
def test_attach_quality_marks_each_row_from_zetaris(monkeypatch, invalid):
    fake = FakeZetaris(invalid)
    monkeypatch.setattr(business, "get_zetaris_client", lambda: fake)
    ctx = business.BusinessContext()
    ctx.usl = "lightning.metastore.recoverypact.recovery_business"
    ans = business.BusinessAnswer("zetaris", [{"application_name": "protected_settlement"},
                                              {"application_name": "batch_replayable_inventory"}], "SELECT", 1.0)
    ctx._attach_quality(ans)
    verdicts = {r["application_name"]: (r["dq_valid"], r["dq_failed_rules"]) for r in ans.records}
    assert verdicts["batch_replayable_inventory"] == (True, [])
    assert verdicts["protected_settlement"] == ((False, ["interruptible_is_replayable"]) if invalid else (True, []))
    assert fake.sql[0].startswith("RUN DQ TABLE") and "SHOW DQ ALL INVALID" in fake.sql[1]


def test_attach_quality_fails_closed_when_rules_cannot_run(monkeypatch):
    def boom():
        raise RuntimeError("zetaris down")
    monkeypatch.setattr(business, "get_zetaris_client", boom)
    ctx = business.BusinessContext()
    ctx.usl = "x.y"
    ans = business.BusinessAnswer("zetaris", [{"application_name": "a"}], "SELECT", 1.0)
    ctx._attach_quality(ans)
    assert ans.records[0]["dq_valid"] is None and any("zetaris_dq_error" in n for n in ans.notes)
