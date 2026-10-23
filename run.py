#!/usr/bin/env python3
"""Run one RecoveryPact incident from a JSON file and print the JSON result.

    docker compose up -d --build                       # starts the stack (API on :8000)
    python run.py input_examples/example_1.json        # one incident, JSON out
    python run.py input_examples/example_1.json --sample   # force keyless replay
    python run.py --scenario G                         # shorthand, no file

Standard library only, so it runs from any Python 3.9+ without installing
anything. It calls POST /run on the API; the agent trace for the run is written
to logs/trace-<run_id>.jsonl and the API prints one readable line per step
(docker compose logs -f api).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", help="JSON request file (see input_examples/)")
    ap.add_argument("--scenario", help="A-H, instead of a file")
    ap.add_argument("--architecture", default="pact", choices=["pact", "gated_single", "naive_single"])
    ap.add_argument("--sample", action="store_true", help="replay recorded Nemotron decisions (no API key)")
    ap.add_argument("--api", default=os.getenv("RECOVERYPACT_API", "http://localhost:8000"))
    ap.add_argument("--timeout", type=float, default=600, help="seconds to wait for the run")
    args = ap.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            req = json.load(f)
    elif args.scenario:
        req = {"input": {"scenario": args.scenario, "architecture": args.architecture}}
    else:
        ap.error("give an input file or --scenario")
    if args.sample:
        req.setdefault("options", {})["sample_mode"] = True

    body = json.dumps(req).encode()
    http = urllib.request.Request(f"{args.api}/run", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(http, timeout=args.timeout) as resp:
            out = json.load(resp)
    except urllib.error.URLError as exc:
        out = {
            "status": "error",
            "error": {
                "type": "ApiUnreachable",
                "message": f"{args.api} did not answer ({exc}). Start the stack with: docker compose up -d --build",
                "recoverable": True,
            },
        }
    print(json.dumps(out, indent=2))
    return 0 if out.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
