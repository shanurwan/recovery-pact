# Nightshift receipts for `blind3-usl`

- **102** Meterless model calls joined to a Nightshift receipt on `response_id = receipt.request_id`; **0** without one.
- Ed25519 signatures verified offline: **102/102**, 1 signing key (d0d636727b51637c).
- Tamper control: the same receipt with `receipt.winning_route.model` rewritten verifies: **False**.
- Calls where Nightshift injected its own memory: **0/102** (RecoveryPact isolates each call's scope, so its governed H-MEM is the only memory in the loop).
- Receipt status ok: **102/102**; single answer phase: **102/102**.
- Latency per call: median 46.1 s, p90 52.7 s.

| Winning model (from the receipt) | Calls |
|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b` | 77 |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 24 |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | 1 |

| Scn | Agent | Call | Winner | Egress | Raced | Nightshift memory | Signature | Latency (s) |
|---|---|---|---|---|---|---|---|---|
| B3_01 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.1 |
| B3_01 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.6 |
| B3_01 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.4 |
| B3_01 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.9 |
| B3_02 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.3 |
| B3_02 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.2 |
| B3_02 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 48.3 |
| B3_02 | database_guardian | db-r2-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.3 |
| B3_02 | continuity_guardian | cg-r2-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 50.0 |
| B3_02 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.0 |
| B3_03 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.1 |
| B3_03 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 51.9 |
| B3_03 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.1 |
| B3_03 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 43.6 |
| B3_04 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.3 |
| B3_04 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.2 |
| B3_04 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.1 |
| B3_04 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.8 |
| B3_05 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.1 |
| B3_05 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.7 |
| B3_05 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 39.7 |
| B3_05 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 52.7 |
| B3_06 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 50.9 |
| B3_06 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 55.8 |
| B3_06 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 44.0 |
| B3_06 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.9 |
| B3_07 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.7 |
| B3_07 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.0 |
| B3_07 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.7 |
| B3_07 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.0 |
| B3_08 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 52.0 |
| B3_08 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 54.3 |
| B3_08 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_08 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 47.4 |
| B3_09 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 55.6 |
| B3_09 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 36.2 |
| B3_09 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 53.1 |
| B3_09 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.0 |
| B3_10 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.0 |
| B3_10 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 50.7 |
| B3_10 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.8 |
| B3_10 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_11 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_11 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.5 |
| B3_11 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_11 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_12 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.1 |
| B3_12 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 24.1 |
| B3_12 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 58.6 |
| B3_12 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 39.4 |
| B3_13 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 2 | 0 | verified | 73.4 |
| B3_13 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 39.6 |
| B3_13 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.1 |
| B3_13 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_14 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.0 |
| B3_14 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 35.3 |
| B3_14 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 51.7 |
| B3_14 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 52.0 |
| B3_15 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_15 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.1 |
| B3_15 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.2 |
| B3_15 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 52.2 |
| B3_16 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.1 |
| B3_16 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.4 |
| B3_16 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.5 |
| B3_17 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 39.6 |
| B3_17 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_17 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 89.5 |
| B3_17 | continuity_guardian | cg-r1-a2 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 49.2 |
| B3_17 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_18 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_18 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 50.5 |
| B3_18 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 41.7 |
| B3_18 | database_guardian | db-r2-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 43.5 |
| B3_18 | continuity_guardian | cg-r2-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_18 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 34.7 |
| B3_19 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_19 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 40.6 |
| B3_19 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.5 |
| B3_19 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.2 |
| B3_20 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_20 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 42.7 |
| B3_20 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.4 |
| B3_20 | database_guardian | db-r2-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 50.1 |
| B3_20 | continuity_guardian | cg-r2-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_20 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 40.0 |
| B3_21 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_21 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.4 |
| B3_21 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.1 |
| B3_21 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 31.9 |
| B3_22 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 44.6 |
| B3_22 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 50.9 |
| B3_22 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_22 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.7 |
| B3_23 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 34.6 |
| B3_23 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 26.2 |
| B3_23 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 22.1 |
| B3_23 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 43.4 |
| B3_24 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.9 |
| B3_24 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.9 |
| B3_24 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.2 |
| B3_24 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.1 |
