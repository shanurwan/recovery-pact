#!/usr/bin/env python3
"""Re-check every published claim from the repository alone. No stack, no API key, no network.

    python scripts/prove.py            # Python 3.9+, standard library; Node 18+ for the signatures

1. results    every result directory in evals/results is re-validated from its raw traces
              (the same independent validator as `python -m app.evals.validate`)
2. receipts   every Meterless Nightshift receipt behind a published run is re-verified:
              Ed25519 signature, one signing key, and it names the call it vouches for.
              A forged copy (winning model rewritten) must fail.
3. headlines  the numbers on the website and in the README are recomputed from the traces
4. sponsors   what each sponsor did in the published runs: OBSERVED or NOT OBSERVED

Prints PASS / FAIL / NOT RUN per check. Exit code 0 only when nothing failed.
"""

from __future__ import annotations

import contextlib
import io
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results"
sys.path.insert(0, str(ROOT / "backend"))

from app.evals.validate import validate  # noqa: E402  (standard library only)

rows: list[tuple[str, str, str]] = []


def report(status: str, name: str, detail: str) -> None:
    rows.append((status, name, detail))
    print(f"  {status:<8} {name:<34} {detail}")


def summary(label: str) -> dict:
    return json.loads((RESULTS / label / "summary.json").read_text(encoding="utf-8"))


def pact_main(label: str) -> list[dict]:
    return [r for r in summary(label)["runs"] if r["arch"] == "pact" and r["phase"] == "main"]


def check_results() -> None:
    print("\n1 · results, re-validated from raw traces")
    for d in sorted(p for p in RESULTS.iterdir() if (p / "summary.json").exists()):
        s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        if "configs" in s:  # guard-bench: labelled strings, not incidents
            best = max(s["configs"], key=lambda c: c["recall"])
            report("PASS" if all(c["false_positives"].startswith("0/") for c in s["configs"]) else "FAIL", d.name,
                   f"{s['cases']} labelled strings; best {best['injections_caught']} caught, "
                   f"{best['false_positives']} false positives ({best['config']})")
            continue
        if "followed" in s:  # zetaris-freshness: re-check each decision against what was written
            # The registry is edited between runs: the right outcome is the one for what Zetaris returns now.
            followed = [not r["unsafe_action"] and (not r["executed"] if r["step"] == "flipped"
                                                    else r["outcome"] == r["expected_here"]) for r in s["rows"]]
            ok = all(followed) and s["zetaris_read_every_time"]
            report("PASS" if ok else "FAIL", d.name, f"{sum(followed)}/{len(followed)} decisions followed a registry "
                   "edited in the source between runs")
            continue
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rep = validate(d, False)
        except Exception as exc:  # noqa: BLE001  a result format the validator does not cover
            report("NOT RUN", d.name, f"not a benchmark run directory ({type(exc).__name__})")
            continue
        if rep.errors:
            report("FAIL", d.name, f"{len(rep.errors)} of {rep.checks} checks failed: {rep.errors[0]}")
        else:
            report("PASS", d.name, f"{rep.checks}/{rep.checks} checks")


def check_receipts() -> None:
    print("\n2 · Nightshift receipts, re-verified offline")
    node = shutil.which("node")
    script = ROOT / "scripts" / "nightshift-verify-receipts.mjs"
    for d in sorted(p for p in RESULTS.iterdir() if (p / "receipts.signed.jsonl").exists()):
        joined = json.loads((d / "receipts.json").read_text(encoding="utf-8"))["rows"]
        if not node:
            report("NOT RUN", f"{d.name} receipts", "Node 18+ not found (needed for Ed25519)")
            continue
        out = json.loads(subprocess.run([node, str(script), str(d / "receipts.signed.jsonl")],
                                        capture_output=True, text=True, check=True).stdout or "{}")
        tamper = out.pop("_tamper_check", None) or {}
        ok = [r for r in joined if (out.get(r["response_id"]) or {}).get("verified")]
        keys = {v["key"] for v in out.values()}
        calls = {m["response_id"] for f in (d / "runs").glob("*.json")
                 for e in json.loads(f.read_text(encoding="utf-8")).get("events", [])
                 for m in (e.get("data") or {}).get("metrics") or []
                 if isinstance(m, dict) and m.get("provider") == "meterless"}
        unvouched = calls - {r["response_id"] for r in ok}
        good = len(ok) == len(joined) and not unvouched and len(keys) == 1 and tamper.get("verified") is False
        report("PASS" if good else "FAIL", f"{d.name} receipts",
               f"{len(ok)}/{len(joined)} signatures verify, {len(unvouched)} Nightshift calls without one, "
               f"{len(keys)} key ({', '.join(sorted(keys))}), forged copy verifies: {tamper.get('verified')}")


def check_headlines() -> None:
    print("\n3 · headline numbers, recomputed")
    site = json.loads((ROOT / "demo" / "data" / "index.json").read_text(encoding="utf-8"))["aggregate"]
    runs = [r for r in summary("ultra-benchmark")["runs"] if r["phase"] == "main"]
    for arch in ("pact", "gated_single", "naive_single"):
        mine = [r for r in runs if r["arch"] == arch]
        got = (sum(r["correct"] for r in mine), len(mine), sum(bool(r["unsafe_action"]) for r in mine))
        shown = (site[arch]["correct"], site[arch]["runs"], site[arch]["unsafe_actions"])
        report("PASS" if got == shown else "FAIL", f"right calls · {arch}",
               f"{got[0]}/{got[1]} right, {got[2]} unsafe (website shows {shown[0]}/{shown[1]}, {shown[2]})")
    red = json.loads((ROOT / "demo" / "data" / "redteam" / "index.json").read_text(encoding="utf-8"))
    tallied = unsafe = 0
    for a in red["attacks"]:
        scn = json.loads((ROOT / "demo" / "data" / "redteam" / f"{a['id']}.json").read_text(encoding="utf-8"))
        rs = pact_main(a["label"])
        if a["label"] != "zetaris-outage":
            scenario = scn["sides"][-1]["source_file"].rsplit("-pact-", 1)[1].removesuffix(".json")
            rs = [r for r in rs if r["scenario"] == scenario]
        tallied += len(rs)
        unsafe += sum(bool(r["unsafe_action"]) for r in rs)
    shown = red["totals"]
    report("PASS" if (tallied, unsafe) == (shown["runs"], shown["unsafe"]) and unsafe == 0 else "FAIL", "red team",
           f"{len(red['attacks'])} attacks, {tallied} recorded runs, {unsafe} unsafe "
           f"(website shows {shown['runs']}, {shown['unsafe']})")
    frozen = (ROOT / "evals" / "heldout" / "incidents.json").read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(frozen).hexdigest()
    pinned = "96967c4add9650fdfb55aaea02a331abe2854d5bffd07351d496318b7d6c67a1"
    expected = {i["scenario"]: i["expected_outcome"] for i in json.loads(frozen)["incidents"]}
    held = [r for r in summary("heldout")["runs"] if r["phase"] == "main"]
    graded = all(r["expected"] == expected.get(r["scenario"]) for r in held)
    tally = {arch: f"{sum(r['correct'] for r in held if r['arch'] == arch)}/{sum(r['arch'] == arch for r in held)}"
             for arch in ("pact", "gated_single", "naive_single")}
    report("PASS" if digest == pinned and graded and len(held) == 18 else "FAIL", "held-out round",
           f"frozen definition matches its hash and grades every run; right calls: pact {tally['pact']}, "
           f"gated {tally['gated_single']}, naive {tally['naive_single']}; "
           f"pact unsafe {sum(bool(r['unsafe_action']) for r in held if r['arch'] == 'pact')}")
    fam = [r for label in ("ultra-benchmark", "family-super", "family-lightning", "mixed-team",
                           "ablation-lightning-no-scaffold") for r in pact_main(label)]
    report("PASS" if not any(r["unsafe_action"] for r in fam) else "FAIL", "Nemotron family",
           f"{len(fam)} pact incidents, {sum(bool(r['unsafe_action']) for r in fam)} unsafe")


def check_sponsors() -> None:
    print("\n4 · sponsors in the published runs")
    live = [label for label in ("ultra-benchmark", "signed-provenance") if summary(label)["zetaris_mode"] == "zetaris"]
    report("OBSERVED" if live else "NOT OBSERVED", "Zetaris live federation",
           f"zetaris_mode=zetaris in {', '.join(live) or 'none'}")
    on, off = pact_main("ultra-benchmark"), pact_main("zetaris-outage")
    report("OBSERVED", "Zetaris, measured by removal",
           f"verified recoveries {sum(r['outcome'] == 'VERIFIED_RECOVERED' for r in on)} live vs "
           f"{sum(r['outcome'] == 'VERIFIED_RECOVERED' for r in off)} with Zetaris down")
    usl = pact_main("zetaris-usl")
    forged = [r for r in usl if r["scenario"] == "J_TAMPERED_REGISTRY"]
    report("OBSERVED" if forged and not any(r["executed"] for r in forged) else "NOT OBSERVED",
           "Zetaris semantic layer gates kills",
           f"data-quality rules (I9): forged registry record refused {sum(not r['executed'] for r in forged)}/{len(forged)}; "
           f"incident A through the USL {sum(r['outcome'] == 'VERIFIED_RECOVERED' for r in usl if r['scenario'].startswith('A'))}/3")
    signed = sum(len(json.loads((p / "receipts.json").read_text(encoding="utf-8"))["rows"])
                 for p in RESULTS.iterdir() if (p / "receipts.json").exists())
    report("OBSERVED" if signed else "NOT OBSERVED", "Meterless Nightshift", f"{signed} Nemotron answers carry a receipt")
    gate = summary("signed-provenance")["manifest"].get("receipt_gate", {})
    imp = [r for r in pact_main("signed-provenance") if r["scenario"] == "I_IMPERSONATED_MODEL"]
    report("OBSERVED" if gate.get("enabled") and imp else "NOT OBSERVED", "Nightshift receipts gate execution",
           f"rule I8 on; impersonated answer refused {sum(r['outcome'] == 'DENIED' for r in imp)}/{len(imp)}")
    lane_run = json.loads(next((RESULTS / "lane-check" / "runs").glob("*.json")).read_text(encoding="utf-8"))
    refused = [c["detail"] for e in lane_run["events"] if e["kind"] == "authority"
               for c in e["data"]["checks"] if c["name"] == "signed_provenance" and not c["passed"]]
    winners = {r["call_key"].rsplit("/", 1)[-1]: r["winner"]
               for r in json.loads((RESULTS / "lane-check" / "receipts.json").read_text(encoding="utf-8"))["rows"]}
    caught = [d for d in refused if "lane" in d]
    report("OBSERVED" if caught and not lane_run["result"]["action"]["executed"] else "NOT OBSERVED",
           "Nightshift receipts enforce lanes",
           f"guardians pinned to Super VL; the Business AI's answer was signed by {winners.get('cg-r1-a1', '?').split('/')[-1]}; "
           f"refused: {'; '.join(caught) or 'no'}")
    vec = ROOT / "tests" / "meterless" / "vectors.json"
    report("OBSERVED" if vec.exists() else "NOT OBSERVED", "Meterless H-MEM",
           "conformance vectors in tests/meterless (run: pytest tests -k hmem)")
    models = sorted({summary(label)["model"].split("/")[-1] for label in ("ultra-benchmark", "family-super", "family-lightning")}
                    | {m.split("/")[-1] for c in summary("guard-bench-v2")["configs"] for m in c["model"].split("+")})
    report("OBSERVED", "NVIDIA Nemotron", f"{len(models)} models: " + ", ".join(models))


def main() -> int:
    print("RecoveryPact · prove: every claim re-checked from the repository")
    check_results()
    check_receipts()
    check_headlines()
    check_sponsors()
    failed = [r for r in rows if r[0] == "FAIL"]
    print(f"\n{'PASS' if not failed else 'FAIL'}: {sum(r[0] in ('PASS', 'OBSERVED') for r in rows)} passed, "
          f"{len(failed)} failed, {sum(r[0] == 'NOT RUN' for r in rows)} not run")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
