"""Rule I8: the authority acts only on model answers Nightshift signed.

One fixture is a real receipt Nightshift wrote during the meterless-nightshift
benchmark (incident A, the Database Guardian's first proposal); the rest are
signed here with a throwaway Ed25519 key in the same envelope format.
"""

from __future__ import annotations

import base64
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.authority.gate import AuthorityGate
from app.config import get_settings
from app.integrations.meterless import receipts
from app.schemas.contract import ProposedAction, RecoveryContract
from app.schemas.enums import RemediationActionType, WorkloadClass

REAL = json.loads((Path(__file__).parent / "meterless" / "nightshift-receipt.json").read_text(encoding="utf-8"))
REAL_KEY_FP = "d0d636727b51637c"  # the one key that signed all 95 benchmark receipts
REAL_CALL = {
    "call_key": "A_SAFE_AUTONOMOUS/pact/main/db-r1-a1", "provider": "meterless", "route": "meterless/deep",
    "response_id": "chatcmpl-e02cf3eb-4b58-46fa-a884-6fd8b567601d",
    "served_by": "nvidia/nemotron-3.5-lightning-30b-a3b", "prompt_tokens": 1256, "completion_tokens": 1478,
}

KEY = Ed25519PrivateKey.generate()
PUB = base64.b64encode(KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
NOW_MS = 1_800_000_000_000


def envelope(rid="chatcmpl-1", model="nvidia/nemotron-3-ultra-550b-a55b", dest="nvidia", tokens=(900, 300),
             status="ok", ts=NOW_MS, key=KEY):
    body = {"receipt": {
        "schema": "meterless.compute_receipt.v1", "receipt_id": f"rcpt_{rid}", "request_id": rid, "status": status,
        "winning_route": {"kind": "cloud", "model": model, "provider": "nvidia"},
        "egress": {"destination": dest}, "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
    }, "signer": "meterlessd", "ts_ms": ts}
    msg = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    pub = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    return {"body": body, "sig_b64": base64.b64encode(key.sign(msg)).decode(), "pubkey_b64": pub}


def call(rid="chatcmpl-1", model="nvidia/nemotron-3-ultra-550b-a55b", tokens=(900, 300)):
    return {"call_key": "A/pact/main/db-r1-a1", "provider": "meterless", "response_id": rid, "served_by": model,
            "prompt_tokens": tokens[0], "completion_tokens": tokens[1]}


@pytest.fixture
def pinned(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "meterless_receipt_key", PUB)
    monkeypatch.setattr(s, "receipt_models", "nvidia/nemotron")
    monkeypatch.setattr(s, "receipt_egress", "nvidia,local")
    return s


def test_real_nightshift_receipt_verifies(monkeypatch):
    monkeypatch.setattr(get_settings(), "meterless_receipt_key", REAL_KEY_FP)
    assert receipts.signature_valid(REAL)
    r = receipts.check(REAL, REAL_CALL)
    assert r["ok"], r["failed"]
    assert r["key"] == REAL_KEY_FP and r["winner"] == REAL_CALL["served_by"] and r["egress"] == "nvidia"


def test_real_receipt_with_rewritten_winner_fails(monkeypatch):
    monkeypatch.setattr(get_settings(), "meterless_receipt_key", REAL_KEY_FP)
    forged = copy.deepcopy(REAL)
    forged["body"]["receipt"]["winning_route"]["model"] = "nvidia/nemotron-3-ultra-550b-a55b"
    r = receipts.check(forged, {**REAL_CALL, "served_by": "nvidia/nemotron-3-ultra-550b-a55b"})
    assert not r["ok"] and r["failed"] == ["signature verifies"]


def test_valid_receipt_passes(pinned):
    r = receipts.check(envelope(), call(), not_before_ms=NOW_MS - 1000)
    assert r["ok"], r["failed"]


@pytest.mark.parametrize("env, c, rule", [
    (None, call(), "no receipt"),
    (envelope(key=Ed25519PrivateKey.generate()), call(), "signed by the pinned Nightshift key"),
    (envelope(rid="chatcmpl-other"), call(), "names this call"),
    (envelope(status="error"), call(), "status ok"),
    (envelope(model="openai/gpt-4o"), call(model="openai/gpt-4o"), "a Nemotron model answered"),
    (envelope(model="nvidia/nemotron-3.5-lightning-30b-a3b"), call(), "same model the client was told"),
    (envelope(dest="openai"), call(), "prompt stayed in allowed destinations"),
    (envelope(tokens=(900, 301)), call(), "token counts match the answer"),
    (envelope(ts=NOW_MS - 3_600_000), call(), "written during this incident"),
])
def test_each_rule_fails_closed(pinned, env, c, rule):
    r = receipts.check(env, c, not_before_ms=NOW_MS - 1000)
    assert not r["ok"] and rule in r["failed"]


def test_tampered_body_fails_signature(pinned):
    env = envelope()
    env["body"]["receipt"]["egress"]["destination"] = "nvidia"  # unchanged value: still valid
    assert receipts.signature_valid(env)
    env["body"]["receipt"]["usage"]["output_tokens"] = 999
    r = receipts.check(env, call(tokens=(900, 999)))
    assert r["failed"] == ["signature verifies"]


def test_no_pinned_key_fails_closed(monkeypatch):
    monkeypatch.setattr(get_settings(), "meterless_receipt_key", "")
    assert "pinned key configured" in receipts.check(envelope(), call())["failed"]


def test_answer_not_served_through_nightshift_has_no_receipt(pinned):
    [r] = receipts.verify_calls([{**call(), "provider": "nvidia"}])
    assert not r["ok"] and "not served through Nightshift" in r["failed"][0]


def _contract(provenance, human=False):
    c = RecoveryContract(
        incident_id="i", exact_target={"pid": 1}, reason="r", expected_effect="e",
        proposed_action=ProposedAction(action_type=RemediationActionType.TERMINATE_BACKEND, exact_target={"pid": 1},
                                       reason="r", expected_effect="e", workload_class=WorkloadClass.BATCH_REPLAYABLE),
        model_provenance=provenance, human_approved=human,
        creation_timestamp=datetime.fromtimestamp(NOW_MS / 1000, timezone.utc),
    )
    return c.seal()


def test_gate_accepts_signed_answers(pinned, monkeypatch):
    store = {"chatcmpl-1": envelope(), "chatcmpl-2": envelope(rid="chatcmpl-2", tokens=(1200, 200))}
    monkeypatch.setattr(receipts, "fetch", lambda rid, wait_s=0: store.get(rid))
    ok, detail = AuthorityGate()._provenance(_contract([call(), call("chatcmpl-2", tokens=(1200, 200))]))
    assert ok and detail.count("rcpt_") == 2


def test_gate_refuses_an_impersonated_answer(pinned, monkeypatch):
    monkeypatch.setattr(receipts, "fetch", lambda rid, wait_s=0: {"chatcmpl-1": envelope()}.get(rid))
    ok, detail = AuthorityGate()._provenance(_contract([call(), call("chatcmpl-spoofed")]))
    assert not ok and "no receipt" in detail


def test_gate_refuses_a_contract_with_no_model_answer(pinned):
    assert AuthorityGate()._provenance(_contract([])) == (False, "no model answer on record")


def test_human_approval_needs_no_model_receipt(pinned):
    ok, detail = AuthorityGate()._provenance(_contract([], human=True))
    assert ok and "human-approved" in detail


def test_provenance_is_sealed_into_the_contract_digest():
    c = _contract([call()])
    c.model_provenance[0]["response_id"] = "chatcmpl-swapped"
    assert not c.verify_digest()
