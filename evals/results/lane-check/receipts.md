# Nightshift receipts for `lane-check`

- **4** Meterless model calls joined to a Nightshift receipt on `response_id = receipt.request_id`; **0** without one.
- Ed25519 signatures verified offline: **4/4**, 1 signing key (d0d636727b51637c).
- Tamper control: the same receipt with `receipt.winning_route.model` rewritten verifies: **False**.
- Calls where Nightshift injected its own memory: **0/4** (RecoveryPact isolates each call's scope, so its governed H-MEM is the only memory in the loop).
- Receipt status ok: **4/4**; single answer phase: **4/4**.
- Latency per call: median 48.6 s, p90 51.3 s.

| Winning model (from the receipt) | Calls |
|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b` | 2 |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 1 |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | 1 |

| Scn | Agent | Call | Winner | Egress | Raced | Nightshift memory | Signature | Latency (s) |
|---|---|---|---|---|---|---|---|---|
| A | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.3 |
| A | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 53.0 |
| A | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.8 |
| A | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 2 | 0 | verified | 45.9 |
