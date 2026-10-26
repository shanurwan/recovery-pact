#!/usr/bin/env python3
"""Build the public receipt log (demo/data/receipts.json) from the signed receipts in the repo.

Every Meterless Nightshift receipt behind a published run, one row each: which Nemotron model
answered, whether it ran on our machine or in the cloud, where the prompt went, the signing key,
whether its Ed25519 signature verifies (checked here, with Python alone), and what the run did
with it. Standard library only.

    python scripts/build-receipt-log.py
"""

from __future__ import annotations

import collections
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results"
sys.path.insert(0, str(ROOT / "scripts"))
from ed25519_verify import check_file  # noqa: E402

ACTOR = {"db": "Database Guardian", "cg": "Continuity Guardian", "auditor": "Auditor", "guard": "Injection guard"}


def actor_of(call_key: str) -> str:
    if call_key.startswith("guard"):
        return ACTOR["guard"]
    return ACTOR.get(call_key.rsplit("/", 1)[-1].split("-", 1)[0], "")


def outcomes(label: str) -> dict:
    f = RESULTS / label / "summary.json"
    if not f.exists():
        return {}
    return {r.get("run_id"): r for r in json.loads(f.read_text(encoding="utf-8")).get("runs", []) if r.get("run_id")}


def main() -> None:
    rows, keys = [], collections.Counter()
    for signed in sorted(RESULTS.glob("*/receipts.signed.jsonl")):
        label = signed.parent.name
        checks = check_file(str(signed))
        joined = {}
        jf = signed.parent / "receipts.json"
        if jf.exists():
            joined = {r.get("response_id"): r for r in json.loads(jf.read_text(encoding="utf-8")).get("rows", [])}
        runs = outcomes(label)
        for line in signed.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            env = json.loads(line)
            r = env["body"]["receipt"]
            rid = r["request_id"]
            win = r.get("winning_route") or {}
            j = joined.get(rid, {})
            run = runs.get(j.get("run_id"), {})
            ck = j.get("call_key") or ""
            v = checks.get(rid, {})
            keys[v.get("key")] += 1
            rows.append({
                "set": label,
                "scenario": (ck.split("/", 1)[0] if ck else j.get("scenario", "")),
                "actor": j.get("actor") and j["actor"].replace("_", " ").title() or actor_of(ck),
                "model": win.get("model", ""),
                "where": win.get("kind", ""),
                "egress": (r.get("egress") or {}).get("destination", ""),
                "privacy": (r.get("privacy") or {}).get("path", ""),
                "ts": datetime.fromtimestamp(env["body"].get("ts_ms", 0) / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "request_id": rid,
                "key": v.get("key", ""),
                "verified": bool(v.get("verified")),
                "outcome": run.get("outcome", ""),
                "action": run.get("action", ""),
            })
    forg = RESULTS / "forgery" / "summary.json"
    forgery = json.loads(forg.read_text(encoding="utf-8")) if forg.exists() else None
    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(rows), "verified": sum(r["verified"] for r in rows),
        "local": sum(r["where"] == "local" for r in rows), "cloud": sum(r["where"] != "local" for r in rows),
        "keys": dict(keys), "sets": dict(collections.Counter(r["set"] for r in rows)),
        "models": dict(collections.Counter(r["model"] for r in rows).most_common()),
        "forgery": {k: forgery[k] for k in ("forgeries", "forgeries_authorized", "real_receipts", "controls_authorized")}
        if forgery else None,
        "rows": sorted(rows, key=lambda r: r["ts"], reverse=True),
    }
    (ROOT / "demo" / "data" / "receipts.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"{out['total']} receipts, {out['verified']} verified, {out['local']} local, keys {dict(keys)}")


if __name__ == "__main__":
    main()
