"""Pure-Python Ed25519 verification and a receipt checker equal to nightshift-verify-receipts.mjs.

prove.py uses this when Node is not installed, so every Nightshift signature can be re-verified
with Python's standard library alone. The curve arithmetic follows the reference code in
RFC 8032, section 6 (slow, but a few hundred receipts take seconds).

    python scripts/ed25519_verify.py evals/results/lane-check/receipts.signed.jsonl
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import sys

P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
SQRT_M1 = pow(2, (P - 1) // 4, P)
G_Y = 4 * pow(5, P - 2, P) % P


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    A, B = (y1 - x1) * (y2 - x2) % P, (y1 + x1) * (y2 + x2) % P
    C, Dd = t1 * 2 * D * t2 % P, z1 * 2 * z2 % P
    E, F, G, H = B - A, Dd - C, Dd + C, B + A
    return E * F % P, G * H % P, F * G % P, E * H % P


def _mul(s, pt):
    q = (0, 1, 1, 0)
    while s:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _equal(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % P == 0 and (a[1] * b[2] - b[1] * a[2]) % P == 0


def _recover_x(y, sign):
    if y >= P:
        return None
    x2 = (y * y - 1) * pow(D * y * y + 1, P - 2, P)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P:
        x = x * SQRT_M1 % P
    if (x * x - x2) % P:
        return None
    if (x & 1) != sign:
        x = P - x
    return x


def _decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % P)


G = (_recover_x(G_Y, 0), G_Y, 1, _recover_x(G_Y, 0) * G_Y % P)


def verify(public: bytes, msg: bytes, sig: bytes) -> bool:
    if len(public) != 32 or len(sig) != 64:
        return False
    A, R = _decompress(public), _decompress(sig[:32])
    if not A or not R:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= L:
        return False
    h = int.from_bytes(hashlib.sha512(sig[:32] + public + msg).digest(), "little") % L
    return _equal(_mul(s, G), _add(R, _mul(h, A)))


def _body_bytes(body) -> bytes:
    # The same bytes as JSON.stringify(body) in the Node verifier.
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def check_file(path: str) -> dict:
    """{request_id: {verified, signer, key}} plus _tamper_check, as nightshift-verify-receipts.mjs prints."""
    out: dict = {}
    for line in open(path, encoding="utf-8").read().split("\n"):
        if not line.strip():
            continue
        try:
            env = json.loads(line)
        except ValueError:
            continue
        rid = ((env.get("body") or {}).get("receipt") or {}).get("request_id")
        if not rid:
            continue
        try:
            pk, sig = base64.b64decode(env["pubkey_b64"]), base64.b64decode(env["sig_b64"])
            ok = verify(pk, _body_bytes(env["body"]), sig)
        except (KeyError, ValueError, TypeError):
            pk, sig, ok = b"", b"", False
        fp = hashlib.sha256((env.get("pubkey_b64") or "").encode()).hexdigest()[:16]
        out[rid] = {"verified": ok, "signer": env["body"].get("signer"), "key": fp}
        if ok and "_tamper_check" not in out:
            forged = copy.deepcopy(env["body"])
            forged["receipt"]["winning_route"] = {**(forged["receipt"].get("winning_route") or {}), "model": "forged/model"}
            out["_tamper_check"] = {"request_id": rid, "forged_field": "receipt.winning_route.model",
                                    "verified": verify(pk, _body_bytes(forged), sig)}
    return out


if __name__ == "__main__":
    print(json.dumps(check_file(sys.argv[1])))
