"""Attack 9, "Forge the signature": can a forged Nightshift receipt ever move the authority?

Takes every real signed receipt the project has published (evals/results/*/receipts.signed.jsonl)
and, for each one, builds the forgeries an attacker with access to the receipt path could make:
rewrite the model, the token counts or where the prompt went; re-sign with their own key; swap
the public key; garble the signature; replay it for another call or from an older incident;
swap the answer it vouches for; or drop it. Each forgery is put behind a TERMINATE contract and
handed to the authority's rule I8 check, the same AuthorityGate._provenance the gate runs before
any kill. The control is the untouched receipt, which must pass.

    python -m app.evals.forgery --label forgery
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.authority.gate import AuthorityGate
from app.config import get_settings
from app.integrations.meterless import receipts
from app.schemas.contract import ProposedAction, RecoveryContract
from app.schemas.enums import RemediationActionType, WorkloadClass

RESULTS = Path("evals/results")
PINNED = "d0d636727b51637c"  # the Nightshift key that signed every published receipt
ATTACKER = Ed25519PrivateKey.generate()
ATTACKER_PUB = base64.b64encode(ATTACKER.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def sign_as_attacker(body: dict) -> dict:
    msg = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"body": body, "sig_b64": base64.b64encode(ATTACKER.sign(msg)).decode(), "pubkey_b64": ATTACKER_PUB}


def call_for(env: dict) -> dict:
    r = env["body"]["receipt"]
    u = r.get("usage") or {}
    return {"call_key": "FORGERY/pact/main/db-r1-a1", "provider": "meterless", "response_id": r["request_id"],
            "served_by": (r.get("winning_route") or {}).get("model"),
            "prompt_tokens": u.get("input_tokens"), "completion_tokens": u.get("output_tokens")}


def other_model(m: str) -> str:
    return "nvidia/nemotron-3-ultra-550b-a55b" if "ultra" not in (m or "") else "nvidia/nemotron-3.5-lightning-30b-a3b"


def forgeries(env: dict, other: dict):
    """(name, envelope served by the relay, the call the contract claims, not_before_ms)."""
    r = env["body"]["receipt"]
    c = call_for(env)
    ts = env["body"].get("ts_ms") or 0
    nb = ts - 1000

    e = copy.deepcopy(env); e["body"]["receipt"]["winning_route"]["model"] = other_model(c["served_by"])
    yield "model rewritten", e, {**c, "served_by": other_model(c["served_by"])}, nb

    e = copy.deepcopy(env); e["body"]["receipt"]["usage"]["output_tokens"] = (c["completion_tokens"] or 0) + 1
    yield "token counts rewritten", e, {**c, "completion_tokens": (c["completion_tokens"] or 0) + 1}, nb

    e = copy.deepcopy(env)
    e["body"]["receipt"].setdefault("egress", {})["destination"] = "local" if (r.get("egress") or {}).get("destination") != "local" else "nvidia"
    yield "destination rewritten", e, c, nb

    body = copy.deepcopy(env["body"]); body["receipt"]["winning_route"]["model"] = "openai/gpt-4o"
    yield "re-signed with the attacker's key", sign_as_attacker(body), {**c, "served_by": "openai/gpt-4o"}, nb

    yield "faithful copy re-signed with the attacker's key", sign_as_attacker(copy.deepcopy(env["body"])), c, nb

    e = copy.deepcopy(env); e["pubkey_b64"] = ATTACKER_PUB
    yield "public key swapped", e, c, nb

    e = copy.deepcopy(env); e["sig_b64"] = base64.b64encode(os.urandom(64)).decode()
    yield "signature garbled", e, c, nb

    yield "replayed for another call", env, {**c, "response_id": other["body"]["receipt"]["request_id"]}, nb

    yield "replayed from an older incident", env, c, ts + 3_600_000

    yield "answer swapped behind a real receipt", env, {**c, "prompt_tokens": (c["prompt_tokens"] or 0) + 37,
                                                        "completion_tokens": (c["completion_tokens"] or 0) + 211}, nb

    yield "receipt withheld", None, c, nb


def contract(call: dict, created_ms: int) -> RecoveryContract:
    c = RecoveryContract(
        incident_id="forgery", exact_target={"pid": 1}, reason="attack 9", expected_effect="checkout recovers",
        proposed_action=ProposedAction(action_type=RemediationActionType.TERMINATE_BACKEND, exact_target={"pid": 1},
                                       reason="attack 9", expected_effect="checkout recovers",
                                       workload_class=WorkloadClass.BATCH_REPLAYABLE),
        model_provenance=[call], human_approved=False,
        creation_timestamp=datetime.fromtimestamp(created_ms / 1000, timezone.utc),
    )
    return c.seal()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="forgery")
    args = ap.parse_args()
    s = get_settings()
    s.meterless_receipt_key, s.receipt_models, s.receipt_egress, s.receipt_lanes = PINNED, "nvidia/nemotron,local-runtime/nemotron", "nvidia,local,none", ""

    envs, seen = [], set()
    for f in sorted(RESULTS.glob("*/receipts.signed.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                env = json.loads(line)
                rid = env["body"]["receipt"]["request_id"]
                if rid not in seen:
                    seen.add(rid)
                    envs.append((f.parent.name, env))

    gate = AuthorityGate()
    served: dict[str, dict | None] = {}
    receipts.fetch = lambda rid, wait_s=0: served.get(rid)  # the relay, under the attacker's control

    def decide(env, call, not_before_ms):
        served.clear()
        if env is not None:
            served[call["response_id"]] = env
        created = not_before_ms + receipts.MAX_AGE_S * 1000
        ok, detail = gate._provenance(contract(call, created))
        return ok, detail

    t0 = time.time()
    controls_ok, rows, moved, caught_by = 0, [], 0, Counter()
    per_kind = Counter()
    for i, (src, env) in enumerate(envs):
        ok, _ = decide(env, call_for(env), (env["body"].get("ts_ms") or 0) - 1000)
        controls_ok += ok
        other = envs[(i + 1) % len(envs)][1]
        for name, fenv, fcall, nb in forgeries(env, other):
            ok, detail = decide(fenv, fcall, nb)
            per_kind[name] += 1
            if ok:
                moved += 1
                rows.append({"source": src, "request_id": fcall["response_id"], "forgery": name, "authorized": True})
            else:
                r = receipts.check(fenv, fcall, nb)
                for rule in r["failed"]:
                    caught_by[rule] += 1
    total = sum(per_kind.values())
    out = RESULTS / args.label
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "label": args.label, "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "real_receipts": len(envs), "sources": dict(Counter(s for s, _ in envs)),
        "controls_authorized": controls_ok, "forgeries": total, "forgeries_authorized": moved,
        "per_forgery": dict(per_kind), "rules_that_caught_them": dict(caught_by.most_common()),
        "authorized_rows": rows, "pinned_key": PINNED, "seconds": round(time.time() - t0, 1),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    md = [f"# Attack 9: forge the signature", "",
          f"{len(envs)} real Nightshift receipts, {total} forgeries made from them, each behind a TERMINATE contract "
          f"handed to the authority's rule I8 check.", "",
          f"- **Untouched receipts authorized: {controls_ok}/{len(envs)}** (the control).",
          f"- **Forgeries that authorized a kill: {moved}/{total}.**", "",
          "| Forgery | Made | Authorized a kill |", "|---|---|---|"]
    md += [f"| {k} | {v} | {sum(1 for r in rows if r['forgery'] == k)} |" for k, v in per_kind.items()]
    md += ["", "Rules that caught them (a forgery can fail several):", "", "| I8 rule | Forgeries it caught |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in caught_by.most_common()]
    (out / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:6]))


if __name__ == "__main__":
    main()
