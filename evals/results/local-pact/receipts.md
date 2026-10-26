# Nightshift receipts for `local-pact`

- **12** Meterless model calls joined to a Nightshift receipt on `response_id = receipt.request_id`; **0** without one.
- Ed25519 signatures verified offline: **12/12**, 1 signing key (d0d636727b51637c).
- Tamper control: the same receipt with `receipt.winning_route.model` rewritten verifies: **False**.
- Calls where Nightshift injected its own memory: **0/12** (RecoveryPact isolates each call's scope, so its governed H-MEM is the only memory in the loop).
- Receipt status ok: **12/12**; single answer phase: **12/12**.
- Latency per call: median 1010.2 s, p90 1020.5 s.

| Winning model (from the receipt) | Calls |
|---|---|
| `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | 12 |

| Scn | Agent | Call | Winner | Egress | Raced | Nightshift memory | Signature | Latency (s) |
|---|---|---|---|---|---|---|---|---|
| A | database_guardian | db-r1-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 1000.1 |
| A | database_guardian | db-r1i-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 904.2 |
| A | continuity_guardian | cg-r1-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 990.4 |
| A | recovery_auditor | auditor-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 1021.1 |
| B | database_guardian | db-r1-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 842.6 |
| B | database_guardian | db-r1i-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 950.6 |
| B | database_guardian | db-r1i-a2 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 1020.5 |
| B | continuity_guardian | cg-r1-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 1020.4 |
| B | database_guardian | db-r2-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 1020.5 |
| B | database_guardian | db-r2i-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 1020.4 |
| B | continuity_guardian | cg-r2-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 990.4 |
| B | recovery_auditor | auditor-a1 | `local-runtime/nvidia-nemotron3-nano-4b-q4-k-m` | none | 2 | 0 | verified | 1020.4 |
