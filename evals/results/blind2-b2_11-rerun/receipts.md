# Nightshift receipts for `blind2-b2_11-rerun`

- **4** Meterless model calls joined to a Nightshift receipt on `response_id = receipt.request_id`; **0** without one.
- Ed25519 signatures verified offline: **4/4**, 1 signing key (d0d636727b51637c).
- Tamper control: the same receipt with `receipt.winning_route.model` rewritten verifies: **False**.
- Calls where Nightshift injected its own memory: **0/4** (RecoveryPact isolates each call's scope, so its governed H-MEM is the only memory in the loop).
- Receipt status ok: **4/4**; single answer phase: **4/4**.
- Latency per call: median 46.1 s, p90 46.1 s.

| Winning model (from the receipt) | Calls |
|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b` | 4 |

| Scn | Agent | Call | Winner | Egress | Raced | Nightshift memory | Signature | Latency (s) |
|---|---|---|---|---|---|---|---|---|
| B2_11 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.1 |
| B2_11 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 53.3 |
| B2_11 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B2_11 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
