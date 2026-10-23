"""Run Meterless's official H-MEM conformance vectors against this implementation.

    python -m app.memory.conformance [path/to/vectors.json]

A Python port of engines/hmem/conformance/runner.ts from github.com/Meterless/Meterless
(Apache-2.0). The vectors file is vendored unchanged in tests/meterless/. Same
cases, same assertions: record validation, exact feedback deltas, ranking order,
sleep guardrails, the conflict gate, ledger reconstruction and the dreaming
approval boundary. Absolute scores depend on the embedder and are not asserted.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from app.memory.hmem import HMEM, HashEmbedder

DEFAULT_VECTORS = Path(__file__).resolve().parents[2] / "tests" / "meterless" / "vectors.json"
DAY = 86400.0


def _approx(a: Any, b: float, eps: float = 1e-9) -> bool:
    return a is not None and abs(float(a) - b) < eps


def run(vectors_path: Path = DEFAULT_VECTORS) -> list[dict[str, Any]]:
    vectors = json.loads(Path(vectors_path).read_text(encoding="utf-8"))
    t0 = vectors["clock"] / 1000.0  # the vectors use milliseconds; this store uses seconds
    secs = vectors["sections"]
    results: list[dict[str, Any]] = []
    tmp = tempfile.TemporaryDirectory()
    counter = [0]

    def fresh(clock: Callable[[], float]) -> HMEM:
        counter[0] += 1
        return HMEM(Path(tmp.name) / f"case-{counter[0]}.sqlite3", HashEmbedder(), threshold=0.35, clock=clock)

    def record(section: str, case: dict[str, Any], fn: Callable[[], None]) -> None:
        try:
            fn()
            results.append({"section": section, "id": case["id"], "description": case["description"], "status": "PASS"})
        except Exception as exc:  # noqa: BLE001 — a failing case is a result, not a crash
            results.append({"section": section, "id": case["id"], "description": case["description"],
                            "status": "FAIL", "detail": str(exc)})

    def check(cond: bool, msg: str) -> None:
        if not cond:
            raise AssertionError(msg)

    for c in secs["record-validation"]:
        def rv(c=c) -> None:
            h = fresh(lambda: t0)
            try:
                h.add(c["input"]["content"], source=c["input"]["source"])
                rejected = False
            except ValueError:
                rejected = True
            check(rejected == (c["expect"] == "reject"), f"expected {c['expect']}")
        record("record-validation", c, rv)

    for c in secs["feedback-deltas"]:
        def fd(c=c) -> None:
            h = fresh(lambda: t0)
            m = h.add("feedback target record", confidence=c["start"], source="conformance")
            h.feedback(m["id"], c["kind"])
            after = h.get(m["id"])
            check(_approx(after["confidence"], c["expectConfidence"]),
                  f"confidence {after['confidence']}, expected {c['expectConfidence']}")
            if "expectAccessDelta" in c:
                delta = after["access_count"] - m["access_count"]
                check(delta == c["expectAccessDelta"], f"accessCount delta {delta}, expected {c['expectAccessDelta']}")
            if c.get("expectTag"):
                check(c["expectTag"] in after["tags"], f"missing tag {c['expectTag']}")
        record("feedback-deltas", c, fd)

    for c in secs["ranking-order"]:
        def ro(c=c) -> None:
            h = fresh(lambda: t0)
            by = {r["key"]: h.add(r["content"], confidence=r["confidence"], layer=r["layer"], source="conformance")
                  for r in c["records"]}
            for r in c["records"]:
                if r.get("supersededByKey"):
                    h.set_superseded(by[r["key"]]["id"], by[r["supersededByKey"]]["id"])
            order = [rc.memory["id"] for rc in h.query(c["query"], threshold=0, top_n=10).memories]
            want = [by[k]["id"] for k in c["expectOrder"]]
            for a, b in zip(want, want[1:]):
                check(order.index(a) < order.index(b), f"expected order {c['expectOrder']}, got {order}")
        record("ranking-order", c, ro)

    for c in secs["sleep-guardrails"]:
        def sg(c=c) -> None:
            now = [t0]
            h = fresh(lambda: now[0])
            by = {r["key"]: h.add(r["content"], source=r["source"], derived_from=r.get("derivedFrom"))
                  for r in c["records"]}
            now[0] = t0 + c["ageDays"] * DAY
            before = sorted(m["id"] for m in h._all())
            preview = h.sleep.preview()
            check(sorted(m["id"] for m in h._all()) == before, "preview mutated the store")
            for k in c["expectArchived"]:
                check(by[k]["id"] in preview["toArchive"], f"{k} should be archivable")
            for k in c["expectProtected"]:
                check(by[k]["id"] not in preview["toArchive"], f"{k} is guardrail-protected and must not archive")
            report = h.sleep.execute(preview)
            for k in c["expectProtected"]:
                check(h.get(by[k]["id"]) is not None, f"{k} was deleted despite guardrails")
            check(isinstance(report.get("backupId"), str) and report["backupId"], "execute must return a backupId")
        record("sleep-guardrails", c, sg)

    for c in secs["conflict-gate"]:
        def cg(c=c) -> None:
            h = fresh(lambda: t0)
            a = h.add(c["a"]["content"], confidence=c["a"]["confidence"], source="conformance")
            b = h.add(c["b"]["content"], confidence=c["b"]["confidence"], source="conformance")
            found = h.conflicts.scan()
            check(len(found) > 0, "opposing always/never pair on similar content must be detected")
            outcome = h.conflicts.auto_resolve(found[0])
            check(outcome in ("resolved", "queued"), f"outcome must be resolved or queued, got {outcome}")
            if outcome == "resolved":
                check(any(h.get(x["id"])["superseded_by"] for x in (a, b)), "resolved conflicts must mark the loser supersededBy")
            check(h.get(a["id"]) is not None and h.get(b["id"]) is not None, "conflict resolution must never delete records")
        record("conflict-gate", c, cg)

    for c in secs["ledger-audit"]:
        def la(c=c) -> None:
            h = fresh(lambda: t0)
            m = h.add("audited record", confidence=c["start"], source="conformance")
            h.feedback(m["id"], c["kind"])
            hist = h.history(m["id"])
            actions = [e["action"] for e in hist]
            check(actions == c["expectActions"], f"actions {actions}, expected {c['expectActions']}")
            fb = hist[-1]
            check(_approx((fb["previousState"] or {}).get("confidence"), c["expectPrev"]), "previousState.confidence")
            check(_approx((fb["newState"] or {}).get("confidence"), c["expectNew"]), "newState.confidence")
        record("ledger-audit", c, la)

    for c in secs["dream-boundary"]:
        def db(c=c) -> None:
            h = fresh(lambda: t0)
            for r in c["records"]:
                h.add(r["content"], type=r["type"], source="conformance")
            before = len(h._all())
            proposals = h.dreaming.dream()
            check(len(proposals) > 0, "two related preferences must produce at least one proposal")
            check(len(h._all()) == before, "dreaming must not materialize anything before approval")
            created = h.dreaming.approve(proposals[0]["id"])
            if created:
                check(created["layer"] == "long_term", "approved proposals materialize as long_term")
                check(len(created["derived_from"]) > 0, "approved proposals carry derivedFrom lineage")
        record("dream-boundary", c, db)

    tmp.cleanup()
    return results


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VECTORS
    results = run(path)
    print(f"H-MEM conformance (Meterless vectors: {path})")
    section = ""
    for r in results:
        if r["section"] != section:
            section = r["section"]
            print(f"\n  {section}")
        print(f"    {r['status']} {r['id']} {r['description']}" + (f"\n         {r['detail']}" if r.get("detail") else ""))
    passed = sum(r["status"] == "PASS" for r in results)
    print(f"\n  {passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
