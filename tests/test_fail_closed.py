"""A guardian turn that fails escalates either way; the trace and the summary must say why."""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.evals.run import _business_sources, _fail_closed
from app.negotiation.orchestrator import _fail_reason
from app.schemas.pact import GroundingResult


def _rec(*problems: str) -> SimpleNamespace:
    return SimpleNamespace(grounding=GroundingResult(ok=False, problems=list(problems)))


def test_provider_outage_is_not_a_reasoning_failure():
    assert _fail_reason(_rec("inference unavailable: Inference failed after retries: Server error '500'")) == "provider_error"
    assert _fail_reason(_rec("two ungrounded attempts")) == "ungrounded"
    assert _fail_reason(_rec()) == "ungrounded"


def _trace(tmp_path, name, arch, slot, events, evidence=()):
    (tmp_path / name).write_text(json.dumps({"arch": arch, "slot": slot, "events": events, "evidence": list(evidence)}))


def test_fail_closed_split_by_cause(tmp_path):
    g = {"kind": "grounding", "actor": "grounding_check"}
    _trace(tmp_path, "a.json", "pact", "main", [{**g, "data": {"reason": "provider_error", "metrics": []}}])
    _trace(tmp_path, "b.json", "pact", "main", [{**g, "data": {"metrics": [{"model": "x"}, {"model": "x"}]}}])
    _trace(tmp_path, "c.json", "pact", "main", [{**g, "data": {"metrics": []}}])  # older trace: no answer at all
    _trace(tmp_path, "d.json", "pact", "encore", [{**g, "data": {"reason": "ungrounded"}}])  # encores not counted
    _trace(tmp_path, "e.json", "naive_single", "main", [{"kind": "proposal", "actor": "solo_agent", "data": {}}])
    assert _fail_closed(tmp_path) == {"pact": {"provider_error": 2, "ungrounded": 1}}


def test_business_sources_read_evidence_ids(tmp_path):
    ev = [{"evidence_id": "BIZ-1", "source": "zetaris"}, {"evidence_id": "BIZ-2", "source": "zetaris"},
          {"evidence_id": "DB-1", "source": "postgresql_observer"}]
    _trace(tmp_path, "a.json", "pact", "main", [{"kind": "evidence", "data": {"evidence": ev[0]}}], ev)
    assert _business_sources(tmp_path) == {"zetaris": 2, "local_federation_fallback": 0}


def test_ungrounded_citation_is_an_error_unless_the_scaffold_was_off():
    from app.evals.validate import Report, audit_trace

    def trace(scaffold):
        return {"evidence": [{"evidence_id": "DB-1"}], "result": {"reasoning_scaffold": scaffold},
                "events": [{"seq": 1, "kind": "proposal", "data": {"proposal": {"cited_evidence": ["DB-1", "biz.tradeoff"]}}},
                           {"seq": 2, "kind": "outcome", "data": {}}]}

    on, off = Report(), Report()
    audit_trace(trace(True), on, "t")
    audit_trace(trace(False), off, "t")
    assert on.errors and not on.findings
    assert not off.errors and len(off.findings) == 1
