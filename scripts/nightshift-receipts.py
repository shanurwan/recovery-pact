#!/usr/bin/env python3
"""Join every Nemotron call of a run set to its Meterless Nightshift receipt.

Each model call RecoveryPact makes through Nightshift records the completion id
(`response_id` in the call's metrics). Nightshift writes a signed receipt per
request with the same id (`receipt.request_id`), naming the model that actually
won the race, the routing reason, where the prompt went and whether Nightshift
added memories of its own. With Node available, every joined receipt's Ed25519
signature is also verified offline (scripts/nightshift-verify-receipts.mjs).

    python scripts/nightshift-receipts.py evals/results/nightshift-verify \
        "%LOCALAPPDATA%/ai.meterless.runtime/receipts.jsonl" > evals/results/nightshift-verify/receipts.md

Also writes receipts.json (the joined rows) and receipts.signed.jsonl (the signed
envelopes of exactly those calls, unmodified) next to the runs, so anyone can
re-verify every signature from the repository alone: python scripts/prove.py
"""

from __future__ import annotations

import collections
import json
import shutil
import statistics
import subprocess
import sys
from pathlib import Path


def calls(result_dir: Path):
    for f in sorted((result_dir / "runs").glob("*.json")):
        run = json.loads(f.read_text(encoding="utf-8"))
        seen = set()
        for e in run.get("events", []):
            for m in (e.get("data") or {}).get("metrics") or []:
                if isinstance(m, dict) and m.get("call_key") and m.get("response_id") not in seen:
                    seen.add(m.get("response_id"))
                    yield run["run_id"], run["scenario"], e.get("actor"), m


def receipts(path: Path) -> dict[str, dict]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        r = d.get("body", {}).get("receipt", {})
        if r.get("request_id"):
            out[r["request_id"]] = {**r, "_signed": bool(d.get("sig_b64") and d.get("pubkey_b64")), "_line": line}
    return out


def verify(path: Path) -> dict[str, dict]:
    node = shutil.which("node")
    script = Path(__file__).with_name("nightshift-verify-receipts.mjs")
    if not node:
        return {}
    res = subprocess.run([node, str(script), str(path)], capture_output=True, text=True, check=True)
    return json.loads(res.stdout or "{}")


def main() -> int:
    result_dir, rpath = Path(sys.argv[1]), Path(sys.argv[2])
    recs, sigs = receipts(rpath), verify(rpath)
    tamper = sigs.pop("_tamper_check", None)
    rows, missing = [], []
    for run_id, scenario, actor, m in calls(result_dir):
        if m.get("provider") not in ("meterless", "nightshift-local"):
            continue  # e.g. the safety classifier, which the runtime catalog does not serve
        r = recs.get(m.get("response_id") or "")
        if r is None:
            missing.append(m.get("call_key"))
            continue
        win = (r.get("winning_route") or {}).get("model") or (r.get("routing") or {}).get("winner")
        rows.append({
            "run_id": run_id, "scenario": "_".join(scenario.split("_")[:2]) if scenario.startswith("B2_") else scenario[:1], "actor": actor, "call_key": m["call_key"],
            "response_id": m.get("response_id"), "route": m.get("route"), "winner": win,
            "egress": (r.get("egress") or {}).get("destination"), "hmem": (r.get("hmem") or {}).get("injected") or 0,
            "raced": (r.get("routing") or {}).get("width"), "status": r.get("status"),
            "phases": "+".join(p.get("phase", "?") for p in (r.get("phases") or [])),
            "signed": r["_signed"], "verified": (sigs.get(m.get("response_id")) or {}).get("verified"),
            "key": (sigs.get(m.get("response_id")) or {}).get("key"), "latency_ms": m.get("latency_ms"),
        })
    (result_dir / "receipts.json").write_text(json.dumps({"rows": rows, "missing": missing, "tamper_check": tamper}, indent=2))
    (result_dir / "receipts.signed.jsonl").write_text(
        "".join(recs[r["response_id"]]["_line"] + "\n" for r in rows), encoding="utf-8", newline="\n")
    n = len(rows)
    winners = collections.Counter(r["winner"] for r in rows)
    keys = {r["key"] for r in rows if r["key"]}
    lat = [r["latency_ms"] for r in rows if r["latency_ms"]]
    print(f"# Nightshift receipts for `{result_dir.name}`\n")
    print(f"- **{n}** Meterless model calls joined to a Nightshift receipt on `response_id = receipt.request_id`; "
          f"**{len(missing)}** without one.")
    if sigs:
        print(f"- Ed25519 signatures verified offline: **{sum(1 for r in rows if r['verified'])}/{n}**, "
              f"{len(keys)} signing key{'s' if len(keys) != 1 else ''} ({', '.join(sorted(keys))}).")
    if tamper:
        print(f"- Tamper control: the same receipt with `{tamper['forged_field']}` rewritten verifies: "
              f"**{tamper['verified']}**.")
    print(f"- Calls where Nightshift injected its own memory: **{sum(1 for r in rows if r['hmem'])}/{n}** "
          "(RecoveryPact isolates each call's scope, so its governed H-MEM is the only memory in the loop).")
    print(f"- Receipt status ok: **{sum(1 for r in rows if r['status'] == 'ok')}/{n}**; "
          f"single answer phase: **{sum(1 for r in rows if r['phases'] == 'final_synthesis')}/{n}**.")
    if lat:
        lat.sort()
        print(f"- Latency per call: median {statistics.median(lat) / 1000:.1f} s, "
              f"p90 {lat[int(0.9 * (len(lat) - 1))] / 1000:.1f} s.\n")
    print("| Winning model (from the receipt) | Calls |\n|---|---|")
    for w, c in winners.most_common():
        print(f"| `{w}` | {c} |")
    print("\n| Scn | Agent | Call | Winner | Egress | Raced | Nightshift memory | Signature | Latency (s) |\n"
          "|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        sig = "verified" if r["verified"] else ("signed" if r["signed"] else "unsigned")
        print(f"| {r['scenario']} | {r['actor']} | {r['call_key'].split('/')[-1]} | `{r['winner']}` | {r['egress']} | "
              f"{r['raced']} | {r['hmem']} | {sig} | {(r['latency_ms'] or 0) / 1000:.1f} |")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
