# Nightshift receipts for `nightshift-gated`

- **109** Meterless model calls joined to a Nightshift receipt on `response_id = receipt.request_id`; **0** without one.
- Ed25519 signatures verified offline: **109/109**, 1 signing key (d0d636727b51637c).
- Tamper control: the same receipt with `receipt.winning_route.model` rewritten verifies: **False**.
- Calls where Nightshift injected its own memory: **0/109** (RecoveryPact isolates each call's scope, so its governed H-MEM is the only memory in the loop).
- Receipt status ok: **109/109**; single answer phase: **109/109**.
- Latency per call: median 45.4 s, p90 51.4 s.

| Winning model (from the receipt) | Calls |
|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b` | 77 |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 21 |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | 11 |

| Scn | Agent | Call | Winner | Egress | Raced | Nightshift memory | Signature | Latency (s) |
|---|---|---|---|---|---|---|---|---|
| A | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 49.6 |
| A | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 38.2 |
| A | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 35.0 |
| A | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.6 |
| B | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.1 |
| B | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.4 |
| B | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.5 |
| B | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 41.0 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 47.9 |
| C | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 26.0 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 33.9 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 43.5 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 28.3 |
| C | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.4 |
| D | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.4 |
| D | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 33.5 |
| D | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 68.0 |
| D | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 2 | 0 | verified | 45.5 |
| E | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 33.8 |
| E | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 23.0 |
| E | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 40.1 |
| E | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 79.0 |
| F | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 48.6 |
| F | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.4 |
| F | grounding_check | cg-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 45.5 |
| F | grounding_check | cg-r1-a2 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 79.1 |
| F | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 28.6 |
| G | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| G | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 45.5 |
| G | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 50.4 |
| G | database_guardian | db-r2-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 49.9 |
| G | database_guardian | db-r2i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 51.4 |
| G | continuity_guardian | cg-r2-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.1 |
| G | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.4 |
| H | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.7 |
| H | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 44.4 |
| H | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 54.1 |
| H | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| A | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.4 |
| A | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 44.2 |
| A | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 37.0 |
| A | database_guardian | db-r2-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.8 |
| A | continuity_guardian | cg-r2-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 52.0 |
| A | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.5 |
| B | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.3 |
| B | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.7 |
| B | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.3 |
| B | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.4 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 29.5 |
| C | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 25.4 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.4 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 40.2 |
| C | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 43.5 |
| D | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.4 |
| D | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 35.7 |
| D | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 45.4 |
| D | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.5 |
| E | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 29.5 |
| E | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 31.8 |
| E | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 52.8 |
| E | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 43.7 |
| F | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 30.4 |
| F | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 40.8 |
| F | grounding_check | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.4 |
| F | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 45.4 |
| G | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 34.2 |
| G | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.4 |
| G | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 50.7 |
| G | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.8 |
| H | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 32.5 |
| H | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.4 |
| H | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.5 |
| H | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 40.2 |
| A | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| A | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 47.8 |
| A | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 6 | 0 | verified | 45.2 |
| A | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.4 |
| B | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 27.6 |
| B | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.5 |
| B | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.3 |
| B | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 33.9 |
| C | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 35.3 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.6 |
| C | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 49.4 |
| C | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 30.5 |
| C | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.7 |
| D | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.4 |
| D | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.7 |
| D | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.4 |
| D | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| E | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.4 |
| E | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 52.2 |
| E | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.2 |
| E | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.4 |
| F | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.9 |
| F | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.4 |
| F | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.5 |
| F | continuity_guardian | cg-r1-a2 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.4 |
| F | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.4 |
| G | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 48.0 |
| G | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.2 |
| G | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.3 |
| G | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 51.7 |
| H | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 50.1 |
| H | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.4 |
| H | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 49.9 |
| H | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.8 |
