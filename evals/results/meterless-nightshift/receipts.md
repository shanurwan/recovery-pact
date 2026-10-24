# Nightshift receipts for `meterless-nightshift`

- **95** Meterless model calls joined to a Nightshift receipt on `response_id = receipt.request_id`; **0** without one.
- Ed25519 signatures verified offline: **95/95**, 1 signing key (d0d636727b51637c).
- Tamper control: the same receipt with `receipt.winning_route.model` rewritten verifies: **False**.
- Calls where Nightshift injected its own memory: **0/95** (RecoveryPact isolates each call's scope, so its governed H-MEM is the only memory in the loop).
- Receipt status ok: **95/95**; single answer phase: **94/95**.
- Latency per call: median 45.3 s, p90 51.3 s.

| Winning model (from the receipt) | Calls |
|---|---|
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 84 |
| `nvidia/nemotron-3-ultra-550b-a55b` | 8 |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | 3 |

| Scn | Agent | Call | Winner | Egress | Raced | Nightshift memory | Signature | Latency (s) |
|---|---|---|---|---|---|---|---|---|
| A | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.3 |
| A | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 57.0 |
| A | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.3 |
| A | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| B | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.3 |
| B | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| B | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 51.3 |
| B | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| C | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 54.6 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| C | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| C | database_guardian | db-r1i-a2 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| C | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.3 |
| D | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| D | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 36.5 |
| D | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 82.1 |
| D | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| E | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| E | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| E | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 80.2 |
| E | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.2 |
| F | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| F | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| F | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 86.8 |
| G | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.3 |
| G | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 49.6 |
| G | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.2 |
| G | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| H | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 52.8 |
| H | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.3 |
| H | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| H | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| A | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.0 |
| A | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 43.9 |
| A | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 49.6 |
| B | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| B | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| B | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.5 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.8 |
| C | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 33.2 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| C | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.3 |
| D | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| D | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 36.1 |
| D | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 67.7 |
| D | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| E | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| E | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 43.4 |
| E | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 2 | 0 | verified | 88.5 |
| F | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| F | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| F | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| G | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| G | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| G | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 44.8 |
| H | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| H | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| H | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| A | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| A | database_guardian | db-r1-a2 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 47.5 |
| A | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| A | database_guardian | db-r1i-a2 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| A | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.6 |
| A | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| B | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 47.1 |
| B | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| B | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 24.9 |
| C | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.3 |
| C | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 42.0 |
| D | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| D | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| D | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| D | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| E | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.2 |
| E | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 39.1 |
| E | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.9 |
| E | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| F | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 50.1 |
| F | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| F | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 79.0 |
| G | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| G | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| G | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| G | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 2 | 0 | verified | 78.6 |
| H | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 44.3 |
| H | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 43.7 |
| H | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
| H | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.3 |
