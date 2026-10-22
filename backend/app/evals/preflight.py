"""Check that a benchmark can produce meaningful numbers before spending time on it.

    python -m app.evals.preflight

Fails (exit 1) on anything that would silently corrupt results: no database,
no checkout traffic (the business verifier would have nothing to measure), no
model access and no recordings, unwritable memory. Zetaris being unavailable is
reported, not fatal: the business questions are then answered by the labeled
local fallback, and the manifest records which path was used.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from app.config import get_settings
from app.db.session import get_observer_engine, ping
from app.integrations.nemotron.client import get_inference_client
from app.integrations.zetaris.business import get_business_context
from app.memory.hmem import get_hmem
from app.services.checkout import health_snapshot


def main() -> int:
    s = get_settings()
    failures: list[str] = []

    def line(ok: bool, what: str, detail: str = "", fatal: bool = True) -> None:
        mark = "ok  " if ok else ("FAIL" if fatal else "warn")
        print(f"[{mark}] {what}{(': ' + detail) if detail else ''}")
        if not ok and fatal:
            failures.append(what)

    try:
        ping(get_observer_engine())
        line(True, "PostgreSQL reachable")
    except Exception as exc:  # noqa: BLE001
        line(False, "PostgreSQL reachable", str(exc)[:160])

    h = {"total": 0}
    for _ in range(10):
        h = health_snapshot(10)
        if h["total"] >= 10:
            break
        time.sleep(1)
    line(h["total"] >= 10, "checkout traffic flowing", f"{h['total']} checkouts in the last 10s (need >= 10)")
    line(h.get("success_rate", 0) >= 0.95, "checkout healthy before injection",
         f"success {h.get('success_rate', 0):.0%}; reset any active incident first")

    client = get_inference_client()
    if client.mode == "nemotron":
        try:
            _, m = client.complete_json(system="Reply with JSON only.", user='Return {"ok": true}', call_key="_preflight/ping")
            line(True, "Nemotron reachable", f"{client.model_id}, {m.get('latency_ms')} ms")
        except Exception as exc:  # noqa: BLE001
            line(False, "Nemotron reachable", str(exc)[:200])
    else:
        rec = Path(s.recordings_dir) / client._slug(client.model_id)
        n = len(list(rec.rglob("*.json"))) if rec.exists() else 0
        line(n > 0, "replay recordings present", f"{n} recorded Nemotron responses for {client.model_id} in {rec}")

    biz = get_business_context()
    try:
        ans = biz.workload_registry(["batch_replayable_inventory"])
        live = ans.source == "zetaris"
        line(bool(ans.records), "business context answers", f"via {ans.source} in {ans.latency_ms:.0f} ms")
        line(live or not biz.zetaris_enabled, "Zetaris live federation",
             "enabled and answering" if live else ("disabled: labeled local fallback will be used"
                                                   if not biz.zetaris_enabled else f"enabled but failing: {ans.notes}"),
             fatal=False)
    except Exception as exc:  # noqa: BLE001
        line(False, "business context answers", str(exc)[:200])

    try:
        get_hmem().list(1)
        line(True, "Meterless H-MEM store writable", s.hmem_persist_dir)
    except Exception as exc:  # noqa: BLE001
        line(False, "Meterless H-MEM store writable", str(exc)[:160])

    if failures:
        print(f"\nPREFLIGHT FAILED: {', '.join(failures)}")
        return 1
    print("\nPREFLIGHT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
