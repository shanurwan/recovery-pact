# Spec: `recoverypact-mcp`, post-incident review inside Cursor

## Why

An SRE reviewing a RecoveryPact incident should be able to ask Cursor *"why did the
pact refuse to kill the card settlement in run X?"* and get an answer built from the
real evidence, not a guess. This MCP server exposes RecoveryPact's run records, the
correlated trace, the independent validator, keyless replay and the Meterless
receipt verifier as tools. With Cursor's model pointed at Meterless Nightshift
(OpenAI-compatible, Nemotron behind it), the loop is Cursor → Nightshift → RecoveryPact
evidence (Zetaris queries, authority checks, signed receipts).

**Read-only by design.** No tool can start a live incident, call the executor, touch
`.env`, or reach a model provider. Replay uses recorded Nemotron responses only. This
is the product's rule applied to the IDE: agreement is not permission, and an
assistant is not an operator.

## Where

```
tools/recoverypact-mcp/
  server.py          # the MCP server (stdio), FastMCP from the official `mcp` SDK
  requirements.txt   # mcp>=1.2 only; everything else is the standard library
  README.md          # setup for Cursor, the five tools, example questions, screenshots
  test_server.py     # pytest: every tool against evals/results/ultra-benchmark
.cursor/mcp.json     # already present: registers the server for this workspace
docs/cursor.md       # how Cursor was used to build this (prompts, sessions, demo GIF)
```

Python 3.10+, stdio transport, no network access, paths resolved from the repo root
(the parent of `tools/`), so it works from any working directory.

## Data it reads (already in the repo)

- `evals/results/<label>/summary.json`: `label`, `model`, `inference_mode`,
  `zetaris_mode`, `aggregate`, `per_scenario`, `runs` (one row per run: `phase`,
  `run_id`, `arch`, `scenario`, `outcome`, `expected`, `correct`, `action`,
  `executed`, `unsafe_action`, `business_harm`, `false_recovery_claim`, `rounds`,
  `model_calls`, `duration_s`, `lost_checkouts`, `repeat`).
- `evals/results/<label>/runs/*.json`: one full run record each. Keys: `run_id`,
  `scenario`, `title`, `arch`, `slot`, `model`, `zetaris_mode`, `result`, `events`,
  `evidence`.
  - `events[]`: `{seq, ts, kind, actor, title, data}`. Kinds in order of a run:
    `incident`, `detect`, `evidence`, `candidates`, `memory`, `proposal`, `probe`,
    `review`, `grounding`, `agreement`, `contract`, `authority`, `execution`,
    `verification`, `escalation`, `audit`, `memory_write`, `outcome`.
    `data.metrics[]` on model turns holds `{model, provider, route, served_by,
    response_id, latency_ms, call_key, attempt}`.
  - `evidence[]`: `{evidence_id, probe, source, summary, facts, query, latency_ms,
    requested_by, collected_at}`. `source` is `postgresql_observer`, `zetaris`,
    `local_federation_fallback`, `business_unavailable`, `meterless_hmem` or
    `checkout_telemetry`; `query` is the exact SQL Zetaris ran.
  - `result`: `outcome`, `expected_outcome`, `correct`, `action {kind, executed,
    target}`, `unsafe_action`, `business_harm`, `false_recovery_claim`,
    `verification`, `audit`, `duration_s`, `model_calls`.
- `evals/results/<label>/receipts.json` (when present): Nightshift receipts joined to
  calls by `scripts/nightshift-receipts.py`.
- `logs/trace-*.jsonl`: one JSON line per step, joined on `run_id`.

## The five tools

Each returns compact markdown (a judge reads it in the Cursor chat), never raw dumps
over ~12 KB. Unknown labels or run ids return a helpful error listing valid ones.

1. **`list_runs(label: str = "ultra-benchmark", scenario: str = "", arch: str = "", only_wrong: bool = False)`**
   Table of runs from `summary.json`: run_id, phase, arch, scenario, outcome
   (expected), correct, unsafe, duration. With no label match, list available labels
   (directories under `evals/results` that contain `summary.json`).

2. **`explain_run(run_id: str, label: str = "")`**
   Find the run record (search all labels if none given). Return the decision story
   in order:
   - header: scenario + title, arch, model, outcome vs expected, correct, unsafe;
   - evidence table: id, source, probe, one-line summary, latency; for Zetaris
     evidence include the SQL in a collapsed code block;
   - negotiation: each proposal (candidate, cited evidence ids) and review
     (decision, objection, any `[invariant override]`), in round order;
   - grounding failures (and their `reason`: provider_error vs ungrounded);
   - the sealed contract digest, every authority check (name, passed, detail),
     executor result, verifier checks;
   - escalation brief if any, and the auditor's root cause + lessons;
   - the model calls: agent, served_by, latency, response_id (the key into
     Nightshift's signed receipt).

3. **`compare_arms(scenario: str, label: str = "ultra-benchmark")`**
   For one scenario, the pact vs `gated_single` vs `naive_single` side by side:
   outcome, action, unsafe, harm, false claim, lost checkouts, duration, plus the one
   evidence item each arm cited that decided it. This is the "why two guardians"
   answer.

4. **`validate_results(label: str)`**
   Run the independent validator and return VALID/INVALID, check counts and the first
   20 errors/findings. Prefer
   `docker compose exec -T api python -m app.evals.validate evals/results/<label>`
   from the repo root; if the stack is not running, run
   `python -m app.evals.validate evals/results/<label>` with `PYTHONPATH=backend`
   and report clearly if dependencies are missing. 300 s timeout.

5. **`verify_receipts(label: str, receipts_path: str = "")`**
   Run `python scripts/nightshift-receipts.py evals/results/<label> <receipts>` and
   return its markdown (signed/verified counts, tamper control, winners, Nightshift
   memory injected). Default receipts path:
   `%LOCALAPPDATA%/ai.meterless.runtime/receipts.jsonl` on Windows,
   `~/.local/share/ai.meterless.runtime/receipts.jsonl` elsewhere. If the result has
   no Meterless calls, say so plainly.

Optional sixth, only if time allows: **`replay_incident(scenario: str)`**, running
`docker compose exec -T -e INFERENCE_MODE=replay api python -m app.evals.run --label mcp-replay --arms pact --scenarios <letter> --no-encores`
and returning the outcome line. Refuse if `INFERENCE_MODE` would be anything but
`replay`.

## Tests (`tools/recoverypact-mcp/test_server.py`)

Call the tool functions directly (no MCP transport) against
`evals/results/ultra-benchmark`:
- `list_runs()` has 78 rows; `only_wrong=True` on the pact arm returns none;
- `explain_run` on the pact B run mentions `PROTECTED_SETTLEMENT` or
  `never_interrupt` and shows the authority/verification sections;
- `compare_arms("B")` shows the naive arm with an unsafe action and the pact without;
- an unknown run id returns the helpful error, not an exception.

## Done means

- `pip install -r tools/recoverypact-mcp/requirements.txt` then
  `pytest tools/recoverypact-mcp -q` passes.
- Cursor (CLI or editor) lists the five tools from `.cursor/mcp.json`, and answers
  "Explain why the pact did not terminate in incident B of the ultra benchmark" using
  `explain_run`.
- `docs/cursor.md` records the prompts used and one real transcript of that question.
