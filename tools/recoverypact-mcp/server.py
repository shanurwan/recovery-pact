"""RecoveryPact MCP server: read-only post-incident review for Cursor.

Exposes eval results, the independent validator and the Nightshift receipt
verifier as tools. Never starts incidents, never calls the executor or a
model provider, never reads .env.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "evals" / "results"
MAX_CHARS = 12_000  # ~12 KB compact markdown for the chat judge

mcp = FastMCP("recoverypact")


# ---------------------------------------------------------------------------
# Path helpers (always from repo root; never touch .env)
# ---------------------------------------------------------------------------


def _labels() -> list[str]:
    if not RESULTS_DIR.is_dir():
        return []
    out = []
    for d in sorted(RESULTS_DIR.iterdir()):
        if d.is_dir() and (d / "summary.json").is_file():
            out.append(d.name)
    return out


def _summary_path(label: str) -> Path:
    return RESULTS_DIR / label / "summary.json"


def _load_summary(label: str) -> dict[str, Any] | str:
    path = _summary_path(label)
    if not path.is_file():
        avail = ", ".join(_labels()) or "(none)"
        return f"Unknown label `{label}`. Available labels with summary.json: {avail}."
    return json.loads(path.read_text(encoding="utf-8"))


def _run_file(label: str, run_id: str) -> Path | None:
    runs = RESULTS_DIR / label / "runs"
    if not runs.is_dir():
        return None
    for f in runs.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("run_id") == run_id:
            return f
    return None


def _load_run(run_id: str, label: str = "") -> tuple[dict[str, Any], str] | str:
    """Return (run, label) or an error string listing valid ids."""
    labels = [label] if label else _labels()
    if label and label not in _labels() and not _summary_path(label).is_file():
        avail = ", ".join(_labels()) or "(none)"
        return f"Unknown label `{label}`. Available labels: {avail}."

    for lab in labels:
        path = _run_file(lab, run_id)
        if path is not None:
            return json.loads(path.read_text(encoding="utf-8")), lab

    # Collect a sample of valid ids for the helpful error
    sample: list[str] = []
    for lab in _labels():
        summary = _load_summary(lab)
        if isinstance(summary, str):
            continue
        for row in summary.get("runs") or []:
            rid = row.get("run_id")
            if rid:
                sample.append(f"{rid} ({lab})")
            if len(sample) >= 12:
                break
        if len(sample) >= 12:
            break
    hint = ", ".join(sample) if sample else "(no runs found)"
    scope = f"label `{label}`" if label else "any label"
    return f"Unknown run_id `{run_id}` under {scope}. Examples: {hint}."


def _match_scenario(value: str, scenario: str) -> bool:
    """Match full id, letter prefix (B), or substring."""
    if not value:
        return True
    s = scenario or ""
    v = value.strip()
    if s == v or s.startswith(v + "_") or v.upper() == s[:1].upper() and len(v) == 1:
        return True
    return v.lower() in s.lower()


def _truncate(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    return text[: MAX_CHARS - 80] + "\n\n... truncated to keep the answer under ~12 KB."


def _one_line(text: str, limit: int = 120) -> str:
    line = " ".join((text or "").split())
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "..."


def _yn(flag: bool | None) -> str:
    if flag is True:
        return "yes"
    if flag is False:
        return "no"
    return "?"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_runs(
    label: str = "ultra-benchmark",
    scenario: str = "",
    arch: str = "",
    only_wrong: bool = False,
) -> str:
    """Table of runs from summary.json (run_id, phase, arch, scenario, outcome, correct, unsafe, duration)."""
    summary = _load_summary(label)
    if isinstance(summary, str):
        return summary

    rows = summary.get("runs") or []
    lines = [
        f"# Runs: `{label}`",
        "",
        f"Model: `{summary.get('model', '?')}` | inference: `{summary.get('inference_mode', '?')}` | "
        f"zetaris: `{summary.get('zetaris_mode', '?')}` | total in summary: {len(rows)}",
        "",
        "| run_id | phase | arch | scenario | outcome (expected) | correct | unsafe | duration_s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    shown = 0
    for r in rows:
        if arch and r.get("arch") != arch:
            continue
        if scenario and not _match_scenario(scenario, r.get("scenario") or ""):
            continue
        if only_wrong and r.get("correct") is not False:
            continue
        outcome = r.get("outcome", "?")
        expected = r.get("expected", "?")
        lines.append(
            f"| `{r.get('run_id', '?')}` | {r.get('phase', '?')} | {r.get('arch', '?')} | "
            f"{r.get('scenario', '?')} | {outcome} ({expected}) | {_yn(r.get('correct'))} | "
            f"{_yn(r.get('unsafe_action'))} | {r.get('duration_s', '?')} |"
        )
        shown += 1

    lines.append("")
    lines.append(f"Showing **{shown}** of {len(rows)} runs.")
    return _truncate("\n".join(lines))


@mcp.tool()
def explain_run(run_id: str, label: str = "") -> str:
    """Decision story for one run: evidence, negotiation, authority, verifier, audit, model calls."""
    loaded = _load_run(run_id, label)
    if isinstance(loaded, str):
        return loaded
    run, lab = loaded
    result = run.get("result") or {}
    action = result.get("action") or {}
    action_kind = action.get("kind") if isinstance(action, dict) else action

    parts: list[str] = []
    parts.append(f"# {run.get('scenario', '?')}: {run.get('title', '')}")
    parts.append("")
    parts.append(
        f"- **label**: `{lab}` | **run_id**: `{run.get('run_id')}` | **arch**: `{run.get('arch')}` | "
        f"**model**: `{run.get('model', '?')}`"
    )
    parts.append(
        f"- **outcome**: {result.get('outcome', '?')} (expected {result.get('expected_outcome', '?')}) | "
        f"**correct**: {_yn(result.get('correct'))} | **unsafe**: {_yn(result.get('unsafe_action'))} | "
        f"**action**: `{action_kind}`"
    )
    parts.append("")

    # Evidence
    parts.append("## Evidence")
    parts.append("")
    parts.append("| id | source | probe | summary | latency_ms |")
    parts.append("|---|---|---|---|---|")
    evidence = run.get("evidence") or []
    zetaris_sql: list[tuple[str, str]] = []
    for e in evidence:
        eid = e.get("evidence_id", "?")
        parts.append(
            f"| {eid} | {e.get('source', '?')} | {e.get('probe', '?')} | "
            f"{_one_line(e.get('summary') or '', 90)} | {e.get('latency_ms', '?')} |"
        )
        if e.get("source") == "zetaris" and e.get("query"):
            zetaris_sql.append((eid, e["query"]))
    if zetaris_sql:
        parts.append("")
        for eid, sql in zetaris_sql:
            parts.append(f"<details><summary>Zetaris SQL ({eid})</summary>")
            parts.append("")
            parts.append("```sql")
            parts.append(sql.strip())
            parts.append("```")
            parts.append("</details>")
            parts.append("")
    parts.append("")

    # Negotiation
    parts.append("## Negotiation")
    parts.append("")
    events = run.get("events") or []
    saw_nego = False
    for e in events:
        kind = e.get("kind")
        data = e.get("data") or {}
        if kind == "proposal":
            saw_nego = True
            prop = data.get("proposal") or {}
            cand = data.get("candidate") or {}
            cited = prop.get("cited_evidence") or []
            parts.append(
                f"- **R{prop.get('round', '?')} proposal** ({e.get('actor')}): "
                f"`{prop.get('candidate_id') or cand.get('candidate_id', '?')}` | "
                f"cited {cited or '-'}"
            )
            if prop.get("rationale"):
                parts.append(f"  - {_one_line(prop['rationale'], 160)}")
        elif kind == "review":
            saw_nego = True
            rev = data.get("review") or {}
            obj = rev.get("objection") or ""
            override = " `[invariant override]`" if "[invariant override]" in obj else ""
            inv = rev.get("violated_invariants") or []
            inv_s = f" | invariants {inv}" if inv else ""
            parts.append(
                f"- **R{rev.get('round', '?')} review** ({e.get('actor')}): "
                f"**{rev.get('decision', '?')}**{override}{inv_s}"
            )
            if obj:
                parts.append(f"  - {_one_line(obj, 160)}")
        elif kind == "agreement":
            saw_nego = True
            cand = data.get("candidate") or {}
            parts.append(
                f"- **agreement**: `{cand.get('candidate_id', '?')}` ({cand.get('kind', '?')})"
            )
    if not saw_nego:
        parts.append("_No proposal/review events._")
    parts.append("")

    # Grounding failures
    grounding = [e for e in events if e.get("kind") == "grounding"]
    parts.append("## Grounding failures")
    parts.append("")
    if not grounding:
        parts.append("_None._")
    else:
        for e in grounding:
            data = e.get("data") or {}
            g = data.get("grounding") or data
            reason = g.get("reason") or data.get("reason") or "?"
            parts.append(f"- {e.get('title', 'grounding')}: reason=`{reason}`")
    parts.append("")

    # Contract + authority + execution + verification
    parts.append("## Contract / authority / execution / verification")
    parts.append("")
    contracts = [e for e in events if e.get("kind") == "contract"]
    if contracts:
        for e in contracts:
            c = (e.get("data") or {}).get("contract") or {}
            parts.append(
                f"- **contract v{c.get('version', '?')}** sealed | digest "
                f"`{(c.get('content_digest') or '')[:16]}...` | state `{c.get('contract_state', '?')}`"
            )
    else:
        parts.append("- **contract**: none sealed (e.g. WAIT / escalate path).")

    authorities = [e for e in events if e.get("kind") == "authority"]
    if authorities:
        for e in authorities:
            data = e.get("data") or {}
            auth = data.get("authorized")
            parts.append(f"- **authority**: {'AUTHORIZED' if auth else 'DENIED'} - {e.get('title', '')}")
            for chk in data.get("checks") or []:
                mark = "pass" if chk.get("passed") else "FAIL"
                parts.append(f"  - `{chk.get('name')}`: {mark} - {_one_line(chk.get('detail') or '', 100)}")
    else:
        parts.append("- **authority**: no gate event (action did not submit a contract).")

    executions = [e for e in events if e.get("kind") == "execution"]
    if executions:
        for e in executions:
            res = (e.get("data") or {}).get("result") or e.get("data") or {}
            parts.append(f"- **executor**: {e.get('title', '')} | `{_one_line(json.dumps(res, default=str), 140)}`")
    else:
        parts.append(f"- **executor**: no execution event (action=`{action_kind}`).")

    verifications = [e for e in events if e.get("kind") == "verification"]
    ver = result.get("verification") or {}
    if verifications:
        for e in verifications:
            v = (e.get("data") or {}).get("verification") or ver
            parts.append(f"- **verification**: {e.get('title', '')}")
            for chk in v.get("checks") or []:
                mark = "pass" if chk.get("passed") else "FAIL"
                parts.append(f"  - `{chk.get('name')}`: {mark} - {_one_line(chk.get('detail') or '', 100)}")
    elif ver:
        parts.append("- **verification** (from result):")
        for chk in ver.get("checks") or []:
            mark = "pass" if chk.get("passed") else "FAIL"
            parts.append(f"  - `{chk.get('name')}`: {mark} - {_one_line(chk.get('detail') or '', 100)}")
    else:
        parts.append("- **verification**: none recorded.")
    parts.append("")

    # Escalation
    parts.append("## Escalation")
    parts.append("")
    escalations = [e for e in events if e.get("kind") == "escalation"]
    brief = result.get("brief")
    if escalations:
        for e in escalations:
            b = (e.get("data") or {}).get("brief") or {}
            parts.append(f"- {e.get('title', 'escalated')}")
            if b.get("headline"):
                parts.append(f"  - {_one_line(b['headline'], 160)}")
    elif brief:
        parts.append(f"- {_one_line((brief or {}).get('headline') or json.dumps(brief), 160)}")
    else:
        parts.append("_None._")
    parts.append("")

    # Audit
    parts.append("## Auditor")
    parts.append("")
    audits = [e for e in events if e.get("kind") == "audit"]
    if audits:
        a = (audits[-1].get("data") or {}).get("audit") or {}
        parts.append(f"- **root cause**: {_one_line(a.get('root_cause') or '', 200)}")
        lessons = a.get("lessons") or []
        if lessons:
            parts.append("- **lessons**:")
            for lesson in lessons[:5]:
                parts.append(f"  - {_one_line(str(lesson), 160)}")
    else:
        parts.append("_No audit event._")
    parts.append("")

    # Model calls
    parts.append("## Model calls")
    parts.append("")
    parts.append("| agent | served_by | latency_ms | response_id |")
    parts.append("|---|---|---|---|")
    seen_ids: set[str] = set()
    for e in events:
        for m in (e.get("data") or {}).get("metrics") or []:
            if not isinstance(m, dict):
                continue
            rid = m.get("response_id") or ""
            key = rid or m.get("call_key") or f"{e.get('actor')}-{m.get('latency_ms')}"
            if key in seen_ids:
                continue
            seen_ids.add(key)
            parts.append(
                f"| {e.get('actor', '?')} | `{m.get('served_by') or m.get('model') or '?'}` | "
                f"{m.get('latency_ms', '?')} | `{rid or '-'}` |"
            )
    if not seen_ids:
        parts.append("| - | - | - | - |")
    parts.append("")

    return _truncate("\n".join(parts))


def _deciding_evidence(run: dict[str, Any]) -> str:
    """One evidence item the arm cited that decided the outcome."""
    events = run.get("events") or []
    cited: list[str] = []
    for e in events:
        data = e.get("data") or {}
        if e.get("kind") == "proposal":
            prop = data.get("proposal") or {}
            cited = list(prop.get("cited_evidence") or [])
        elif e.get("kind") == "agreement":
            cand = data.get("candidate") or {}
            if cand.get("evidence_id"):
                cited = [cand["evidence_id"]]
    evidence = {e.get("evidence_id"): e for e in (run.get("evidence") or [])}
    if not cited:
        # Fall back to first evidence tied to the chosen action
        for e in run.get("evidence") or []:
            return f"{e.get('evidence_id')}: {_one_line(e.get('summary') or '', 100)}"
        return "-"
    eid = cited[0]
    ev = evidence.get(eid) or {}
    return f"{eid}: {_one_line(ev.get('summary') or '(no summary)', 100)}"


@mcp.tool()
def compare_arms(scenario: str, label: str = "ultra-benchmark") -> str:
    """Side-by-side pact vs gated_single vs naive_single for one scenario."""
    summary = _load_summary(label)
    if isinstance(summary, str):
        return summary

    rows = [
        r
        for r in (summary.get("runs") or [])
        if _match_scenario(scenario, r.get("scenario") or "") and r.get("phase") == "main"
    ]
    if not rows:
        scenarios = sorted({r.get("scenario", "") for r in (summary.get("runs") or [])})
        return (
            f"No runs for scenario `{scenario}` in `{label}`. "
            f"Known scenarios: {', '.join(scenarios) or '(none)'}."
        )

    # Prefer repeat 1 when present
    by_arch: dict[str, dict[str, Any]] = {}
    for r in rows:
        arch = r.get("arch") or "?"
        prev = by_arch.get(arch)
        if prev is None or (r.get("repeat") or 99) < (prev.get("repeat") or 99):
            by_arch[arch] = r

    scn = next(iter(by_arch.values())).get("scenario", scenario)
    parts = [
        f"# Compare arms: `{scn}` ({label})",
        "",
        "| arch | outcome | action | unsafe | harm | false claim | lost_checkouts | duration_s | deciding evidence |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arch in ("pact", "gated_single", "naive_single"):
        row = by_arch.get(arch)
        if not row:
            parts.append(f"| {arch} | - | - | - | - | - | - | - | (no run) |")
            continue
        loaded = _load_run(row["run_id"], label)
        deciding = "-"
        if not isinstance(loaded, str):
            deciding = _deciding_evidence(loaded[0])
        parts.append(
            f"| **{arch}** | {row.get('outcome')} | `{row.get('action')}` | "
            f"{_yn(row.get('unsafe_action'))} | {_yn(row.get('business_harm'))} | "
            f"{_yn(row.get('false_recovery_claim'))} | {row.get('lost_checkouts', '?')} | "
            f"{row.get('duration_s', '?')} | {deciding} |"
        )
    parts.append("")
    parts.append(
        "Pact keeps a second guardian (and the authority gate) in the loop; "
        "`naive_single` can execute an unsafe terminate when the solo agent picks it."
    )
    return _truncate("\n".join(parts))


@mcp.tool()
def validate_results(label: str) -> str:
    """Run the independent validator; return VALID/INVALID, check counts, first errors."""
    result_dir = RESULTS_DIR / label
    if not (result_dir / "summary.json").is_file():
        avail = ", ".join(_labels()) or "(none)"
        return f"Unknown label `{label}`. Available: {avail}."

    rel = f"evals/results/{label}"
    docker_cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "api",
        "python",
        "-m",
        "app.evals.validate",
        rel,
    ]
    local_cmd = [sys.executable, "-m", "app.evals.validate", str(result_dir)]
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend")}

    used = "docker compose"
    try:
        proc = subprocess.run(
            docker_cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        # If docker isn't up / service missing, fall back
        if proc.returncode != 0 and (
            "Cannot connect" in (proc.stderr or "")
            or "no configuration file" in (proc.stderr or "").lower()
            or "service" in (proc.stderr or "").lower()
            or proc.returncode == 127
            or "not found" in (proc.stderr or "").lower()
        ):
            raise FileNotFoundError(proc.stderr or "docker unavailable")
        if proc.returncode != 0 and not (proc.stdout or "").strip():
            raise FileNotFoundError(proc.stderr or "docker validate failed")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        used = "local python (PYTHONPATH=backend)"
        try:
            proc = subprocess.run(
                local_cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return f"Validator timed out after 300s for `{label}`."
        except OSError as exc:
            return f"Could not run validator ({used}): {exc}"

    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    if "No module named" in out or "ModuleNotFoundError" in out:
        return (
            f"Validator dependencies missing when running via {used}.\n\n"
            f"```\n{_one_line(out, 500)}\n```\n\n"
            "Start the stack (`docker compose up`) and retry, or install backend deps."
        )

    lines = [ln for ln in out.splitlines() if ln.strip()]
    header = next((ln for ln in lines if ln.startswith("VALID") or ln.startswith("INVALID")), None)
    errors = [ln for ln in lines if ln.strip().startswith("- ")]
    findings = [ln for ln in lines if "FINDINGS" in ln or ln.strip().startswith("- ")]

    parts = [
        f"# Validate `{label}`",
        "",
        f"Runner: {used}",
        "",
        f"**{header or ('INVALID' if proc.returncode else 'VALID (see output)')}**",
        "",
    ]
    # Prefer errors section from INVALID lines
    err_lines = []
    in_err = False
    for ln in lines:
        if ln.startswith("INVALID") or ln.startswith("VALID"):
            in_err = ln.startswith("INVALID")
            continue
        if ln.startswith("FINDINGS"):
            in_err = False
            parts.append(ln)
            continue
        if ln.strip().startswith("- "):
            err_lines.append(ln.strip())

    if err_lines:
        parts.append("First findings/errors (up to 20):")
        for ln in err_lines[:20]:
            parts.append(f"- {ln.lstrip('- ').strip()}")
    elif not header:
        parts.append("```")
        parts.append(_truncate(out.strip() or "(no output)"))
        parts.append("```")

    return _truncate("\n".join(parts))


def _default_receipts_path() -> Path:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "ai.meterless.runtime" / "receipts.jsonl"
    return Path.home() / ".local" / "share" / "ai.meterless.runtime" / "receipts.jsonl"


@mcp.tool()
def verify_receipts(label: str, receipts_path: str = "") -> str:
    """Join Nightshift receipts to model calls; return signed/verified counts and winners."""
    result_dir = RESULTS_DIR / label
    if not (result_dir / "summary.json").is_file():
        avail = ", ".join(_labels()) or "(none)"
        return f"Unknown label `{label}`. Available: {avail}."

    rpath = Path(receipts_path) if receipts_path else _default_receipts_path()
    # Expand %LOCALAPPDATA% style if the caller passed the Windows template literally
    rpath = Path(os.path.expandvars(os.path.expanduser(str(rpath))))

    script = REPO_ROOT / "scripts" / "nightshift-receipts.py"
    if not script.is_file():
        return f"Missing script `{script}`."

    # Quick pre-check: any meterless calls?
    meterless = 0
    nvidiaish = 0
    runs_dir = result_dir / "runs"
    if runs_dir.is_dir():
        for f in runs_dir.glob("*.json"):
            try:
                run = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for e in run.get("events") or []:
                for m in (e.get("data") or {}).get("metrics") or []:
                    if not isinstance(m, dict):
                        continue
                    if m.get("provider") == "meterless":
                        meterless += 1
                    else:
                        nvidiaish += 1

    if meterless == 0:
        return (
            f"# Receipts for `{label}`\n\n"
            "No Meterless calls in this result set "
            f"({nvidiaish} non-Meterless model call metrics found). "
            "`scripts/nightshift-receipts.py` only joins `provider=meterless` "
            "calls to Nightshift receipts, so there is nothing to verify here."
        )

    if not rpath.is_file():
        return (
            f"# Receipts for `{label}`\n\n"
            f"Found {meterless} Meterless call(s), but receipts file not found at `{rpath}`. "
            "Pass `receipts_path` or place Nightshift's `receipts.jsonl` at the default path."
        )

    try:
        proc = subprocess.run(
            [sys.executable, str(script), str(result_dir), str(rpath)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return f"nightshift-receipts.py timed out for `{label}`."

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if not out:
        return f"Receipt script produced no markdown.\n\n```\n{err or '(no stderr)'}\n```"
    return _truncate(out)


if __name__ == "__main__":
    mcp.run(transport="stdio")
