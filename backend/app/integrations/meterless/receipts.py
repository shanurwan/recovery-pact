"""Signed provenance: check Nightshift's receipt for every Nemotron answer before acting on it.

Meterless Nightshift writes an Ed25519-signed receipt for every routed call
(schema meterless.compute_receipt.v1). The receipt names the model that won the
route, where the prompt went, the token counts and the status, under the same
id the completion returned (receipt.request_id == response id). The signature
covers the JSON of the receipt body.

The authority uses this as rule I8: the model answers a recovery contract rests
on must each carry a receipt that

- exists, and is signed by the pinned Nightshift key;
- names this exact call (request_id) with status ok;
- says a Nemotron model answered, the same model the client was told served it;
- when the role has a lane (RECEIPT_LANES), names one of that lane's models: a runtime
  that substitutes a smaller model for a guardian's turn is caught here;
- kept the prompt inside the allowed destinations (NVIDIA, or on the machine);
- attests the same input and output token counts the answer arrived with;
- was written during this incident, not replayed from an older one.

A receipt does not sign the answer text itself; the token counts tie the answer
we parsed to the call that was signed. A missing receipt, a relay that is down
or a pinned key that is not configured all fail closed.

Receipts are fetched from a read-only relay that runs next to Nightshift
(scripts/nightshift-receipt-relay.py): GET {METERLESS_RECEIPTS_URL}/v1/receipts/<request_id>
returns the receipt line exactly as Nightshift wrote it.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.config import get_settings

SCHEMA = "meterless.compute_receipt.v1"
MAX_AGE_S = 1800  # a receipt older than the incident window is a replay
FETCH_WAIT_S = 15.0  # Nightshift writes the receipt just after it answers


def key_fingerprint(pubkey_b64: str) -> str:
    """Same fingerprint the published receipts table uses: sha256 of the base64 key, 16 hex chars."""
    return hashlib.sha256((pubkey_b64 or "").encode()).hexdigest()[:16]


_ROLE_PREFIX = {"db": "database_guardian", "cg": "continuity_guardian", "auditor": "auditor"}


def role_of(call_key: str) -> str:
    """The role a call answered for, from its key (".../db-r1-a1" -> database_guardian)."""
    return _ROLE_PREFIX.get(call_key.rsplit("/", 1)[-1].split("-", 1)[0], "")


def signature_valid(envelope: dict[str, Any]) -> bool:
    """Ed25519 over the receipt body serialised the way Nightshift signs it (compact JSON, key order kept)."""
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(envelope["pubkey_b64"]))
        msg = json.dumps(envelope["body"], separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        key.verify(base64.b64decode(envelope["sig_b64"]), msg)
        return True
    except (InvalidSignature, KeyError, ValueError, TypeError):
        return False


def fetch(request_id: str, wait_s: float = FETCH_WAIT_S) -> dict[str, Any] | None:
    s = get_settings()
    base = s.meterless_receipts_url.rstrip("/")
    if not base or not request_id:
        return None
    deadline = time.monotonic() + wait_s
    while True:
        try:
            r = httpx.get(f"{base}/v1/receipts/{request_id}", timeout=5.0)
            if r.status_code == 200:
                return r.json()
        except (httpx.HTTPError, ValueError):
            pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(1.0)


def check(envelope: dict[str, Any] | None, call: dict[str, Any], not_before_ms: int | None = None) -> dict[str, Any]:
    """Every rule for one model call. Returns {ok, failed, winner, key, ...} for the audit trail."""
    s = get_settings()
    rid = call.get("response_id") or ""
    out: dict[str, Any] = {"call_key": call.get("call_key"), "request_id": rid, "ok": False, "failed": []}
    if envelope is None:
        out["failed"].append("no receipt")
        return out
    body = envelope.get("body") or {}
    r = body.get("receipt") or {}
    win = (r.get("winning_route") or {}).get("model") or ""
    usage = r.get("usage") or {}
    dest = (r.get("egress") or {}).get("destination") or ""
    fp = key_fingerprint(envelope.get("pubkey_b64", ""))
    out.update(winner=win, egress=dest, key=fp, receipt_id=r.get("receipt_id"), status=r.get("status"))
    pinned = s.meterless_receipt_key.strip()
    rules = [
        ("pinned key configured", bool(pinned)),
        ("signed by the pinned Nightshift key", pinned in (envelope.get("pubkey_b64"), fp)),
        ("signature verifies", signature_valid(envelope)),
        ("receipt schema", r.get("schema") == SCHEMA),
        ("names this call", bool(rid) and r.get("request_id") == rid),
        ("status ok", r.get("status") == "ok"),
        ("a Nemotron model answered", any(win.startswith(p) for p in s.receipt_model_prefixes)),
        ("same model the client was told", win == call.get("served_by")),
        ("prompt stayed in allowed destinations", dest in s.receipt_egress_allowed),
        ("token counts match the answer", usage.get("input_tokens") == call.get("prompt_tokens")
         and usage.get("output_tokens") == call.get("completion_tokens")),
    ]
    lane = s.receipt_lane_map.get(role_of(call.get("call_key") or ""))
    if lane:
        out["lane"] = sorted(lane)
        rules.append(("served by the role's lane model", win in lane))
    ts = body.get("ts_ms")
    if not_before_ms is not None:
        rules.append(("written during this incident", isinstance(ts, int) and ts >= not_before_ms))
    out["failed"] = [name for name, ok in rules if not ok]
    out["ok"] = not out["failed"]
    return out


def verify_calls(calls: list[dict[str, Any]], not_before_ms: int | None = None) -> list[dict[str, Any]]:
    """Fetch and check the receipt of each model call; calls not served by Nightshift have none."""
    results = []
    for call in calls:
        if call.get("provider") != "meterless":
            results.append({"call_key": call.get("call_key"), "request_id": call.get("response_id"), "ok": False,
                            "failed": ["not served through Nightshift, so nothing signed it"]})
            continue
        results.append(check(fetch(call.get("response_id") or ""), call, not_before_ms))
    return results


def not_before(created_ms: int) -> int:
    return created_ms - MAX_AGE_S * 1000
