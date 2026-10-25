#!/usr/bin/env python3
"""Show, side by side, a Nemotron answer signed in the cloud and one signed on our own machine.

    python scripts/show-receipts.py

Reads the signed Nightshift receipts committed next to the runs, re-verifies each Ed25519
signature with Python alone (scripts/ed25519_verify.py) and prints which Nemotron model
answered, where it ran and whether the prompt could leave the machine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from ed25519_verify import check_file  # noqa: E402

SOURCES = [("cloud", ROOT / "evals/results/meterless-nightshift/receipts.signed.jsonl"),
           ("local", ROOT / "evals/results/guard-local-lane/receipts.signed.jsonl")]


def main() -> int:
    for label, path in SOURCES:
        if not path.exists():
            print(f"{label}: {path.relative_to(ROOT)} not found")
            continue
        checks = check_file(str(path))
        env = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        r = env["body"]["receipt"]
        win = r.get("winning_route") or {}
        rid = r["request_id"]
        print(f"\n{label.upper()} answer   ({path.parent.name})")
        print(f"  Nemotron model : {win.get('model')}")
        print(f"  ran            : {win.get('kind')} ({win.get('provider')})")
        print(f"  privacy        : {(r.get('privacy') or {}).get('path')}")
        print(f"  signed by      : {env['body'].get('signer')}, key {checks[rid]['key']}")
        print(f"  signature      : {'VERIFIED' if checks[rid]['verified'] else 'FAILED'}")
        print(f"  all receipts   : {sum(v['verified'] for k, v in checks.items() if k != '_tamper_check')}"
              f"/{len(checks) - 1} verified; forged copy verifies: {checks['_tamper_check']['verified']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
