#!/usr/bin/env python3
"""Send one recorded guardian prompt to several Meterless routes and compare.

Picks the Nightshift route the agents should use: it has to answer a real
guardian turn with parseable JSON, quickly, without truncation. Standard library only.

    python3 scripts/nightshift-route-probe.py recordings/<model>/A_SAFE_AUTONOMOUS/pact/main/db-r1-a1.json \
        http://host:18089 meterless/deep meterless/text nvidia/nemotron-3-ultra-550b-a55b
Token from METERLESS_RUNTIME_TOKEN.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request


def main() -> int:
    rec = json.load(open(sys.argv[1], encoding="utf-8"))
    base, routes = sys.argv[2].rstrip("/"), sys.argv[3:]
    token = os.environ["METERLESS_RUNTIME_TOKEN"]
    for route in routes:
        body = {"model": route, "messages": rec["messages"], "max_tokens": 6000, "temperature": 0.2}
        req = urllib.request.Request(
            f"{base}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "X-Meterless-App": "recovery-pact", "meterless-tier-split": os.environ.get("TIER_SPLIT", "on"),
                     "meterless-scope": f"recovery-pact-call-{os.urandom(6).hex()}"},
        )
        t = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read())
            text = d["choices"][0]["message"]["content"] or ""
            if os.environ.get("SHOW"): print(repr(text[:600]), "...", repr(text[-600:]))
            text = text.split("</think>")[-1]
            m = re.search(r"\{.*\}", text, re.S)
            try:
                parsed = json.loads(m.group(0)) if m else None
            except json.JSONDecodeError:
                parsed = None
            print(f"{route:<40} {time.perf_counter() - t:6.1f}s served={d.get('model')} id={d.get('id')} "
                  f"json={'ok' if parsed else 'BAD'} candidate={(parsed or {}).get('candidate_id')} "
                  f"finish={d['choices'][0].get('finish_reason')}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{route:<40} {time.perf_counter() - t:6.1f}s ERROR {str(exc)[:200]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
