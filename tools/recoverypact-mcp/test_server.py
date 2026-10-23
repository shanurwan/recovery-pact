"""Call recoverypact-mcp tools directly against evals/results/ultra-benchmark."""

from __future__ import annotations

import re

from server import compare_arms, explain_run, list_runs


def test_list_runs_has_78_rows() -> None:
    md = list_runs()
    # Header + separator + 78 data rows, then a "Showing N" line
    data_rows = [ln for ln in md.splitlines() if ln.startswith("| `run-")]
    assert len(data_rows) == 78, f"expected 78 runs, got {len(data_rows)}"


def test_list_runs_only_wrong_pact_is_empty() -> None:
    md = list_runs(arch="pact", only_wrong=True)
    data_rows = [ln for ln in md.splitlines() if ln.startswith("| `run-")]
    assert data_rows == []
    assert "Showing **0**" in md


def test_explain_run_pact_b_protected() -> None:
    # Resolve the pact B main repeat-1 run via list_runs
    table = list_runs(scenario="B", arch="pact")
    m = re.search(r"`(run-[a-f0-9]+)`", table)
    assert m, f"no pact B run_id in:\n{table[:500]}"
    run_id = m.group(1)

    md = explain_run(run_id, label="ultra-benchmark")
    assert "PROTECTED_SETTLEMENT" in md.upper() or "never_interrupt" in md
    assert "## Contract / authority / execution / verification" in md
    assert "**authority**" in md or "authority" in md.lower()
    assert "**verification**" in md or "verification" in md.lower()


def test_compare_arms_b_naive_unsafe_pact_safe() -> None:
    md = compare_arms("B")
    assert "naive_single" in md and "pact" in md
    # Table rows: find unsafe column for each arch
    naive_line = next(ln for ln in md.splitlines() if ln.startswith("| **naive_single**"))
    pact_line = next(ln for ln in md.splitlines() if ln.startswith("| **pact**"))
    # columns: arch | outcome | action | unsafe | ...
    assert naive_line.split("|")[4].strip() == "yes", naive_line
    assert pact_line.split("|")[4].strip() == "no", pact_line


def test_unknown_run_id_helpful_error() -> None:
    md = explain_run("run-does-not-exist")
    assert "Unknown run_id" in md
    assert "run-" in md  # lists example ids
    assert "Exception" not in md
