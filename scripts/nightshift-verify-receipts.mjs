#!/usr/bin/env node
// Verify Meterless Nightshift receipts offline: each line of receipts.jsonl is
// { body, sig_b64, pubkey_b64 }, an Ed25519 signature by the meterlessd daemon over
// the JSON of `body`. Prints {request_id: {verified, signer, key}} as JSON. Node 18+,
// no dependencies.
//
//   node scripts/nightshift-verify-receipts.mjs "%LOCALAPPDATA%/ai.meterless.runtime/receipts.jsonl"

import crypto from "node:crypto";
import fs from "node:fs";

const out = {};
for (const line of fs.readFileSync(process.argv[2], "utf8").split("\n")) {
  if (!line.trim()) continue;
  let env;
  try {
    env = JSON.parse(line);
  } catch {
    continue;
  }
  const id = env?.body?.receipt?.request_id;
  if (!id) continue;
  let verified = false;
  try {
    const pk = Buffer.from(env.pubkey_b64, "base64");
    const key = crypto.createPublicKey({ key: { kty: "OKP", crv: "Ed25519", x: pk.toString("base64url") }, format: "jwk" });
    verified = crypto.verify(null, Buffer.from(JSON.stringify(env.body), "utf8"), key, Buffer.from(env.sig_b64, "base64"));
  } catch {
    verified = false;
  }
  const fp = crypto.createHash("sha256").update(env.pubkey_b64 || "").digest("hex").slice(0, 16);
  out[id] = { verified, signer: env.body.signer || null, key: fp };
  if (verified && !out._tamper_check) {
    // Control: the same receipt with the winning model rewritten must fail.
    const forged = structuredClone(env.body);
    forged.receipt.winning_route = { ...(forged.receipt.winning_route || {}), model: "forged/model" };
    const pk = Buffer.from(env.pubkey_b64, "base64");
    const key = crypto.createPublicKey({ key: { kty: "OKP", crv: "Ed25519", x: pk.toString("base64url") }, format: "jwk" });
    out._tamper_check = {
      request_id: id,
      forged_field: "receipt.winning_route.model",
      verified: crypto.verify(null, Buffer.from(JSON.stringify(forged), "utf8"), key, Buffer.from(env.sig_b64, "base64")),
    };
  }
}
process.stdout.write(JSON.stringify(out));
