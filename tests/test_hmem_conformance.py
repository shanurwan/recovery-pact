"""Meterless's official H-MEM conformance vectors, run against our implementation."""

from pathlib import Path

import pytest

from app.memory.conformance import run

VECTORS = Path(__file__).parent / "meterless" / "vectors.json"
RESULTS = run(VECTORS)


@pytest.mark.parametrize("case", RESULTS, ids=[r["id"] for r in RESULTS])
def test_meterless_conformance(case):
    assert case["status"] == "PASS", f"{case['id']} {case['description']}: {case.get('detail')}"


def test_every_section_ran():
    assert {r["section"] for r in RESULTS} == {
        "record-validation", "feedback-deltas", "ranking-order", "sleep-guardrails",
        "conflict-gate", "ledger-audit", "dream-boundary",
    }
    assert len(RESULTS) == 13  # every case in Meterless vectors.json v1
