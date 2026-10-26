# Nightshift receipts for `blind3`

- **144** Meterless model calls joined to a Nightshift receipt on `response_id = receipt.request_id`; **0** without one.
- Ed25519 signatures verified offline: **144/144**, 1 signing key (d0d636727b51637c).
- Tamper control: the same receipt with `receipt.winning_route.model` rewritten verifies: **False**.
- Calls where Nightshift injected its own memory: **0/144** (RecoveryPact isolates each call's scope, so its governed H-MEM is the only memory in the loop).
- Receipt status ok: **144/144**; single answer phase: **144/144**.
- Latency per call: median 46.1 s, p90 54.3 s.

| Winning model (from the receipt) | Calls |
|---|---|
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 98 |
| `nvidia/nemotron-3-ultra-550b-a55b` | 43 |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | 3 |

| Scn | Agent | Call | Winner | Egress | Raced | Nightshift memory | Signature | Latency (s) |
|---|---|---|---|---|---|---|---|---|
| B3_01 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 43.8 |
| B3_02 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.8 |
| B3_03 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 34.8 |
| B3_04 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 38.5 |
| B3_05 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 34.2 |
| B3_06 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 36.4 |
| B3_07 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.2 |
| B3_08 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 55.6 |
| B3_09 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 36.8 |
| B3_10 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 39.3 |
| B3_11 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 31.5 |
| B3_12 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 40.0 |
| B3_13 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.9 |
| B3_14 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 38.5 |
| B3_15 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 37.9 |
| B3_16 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 42.7 |
| B3_17 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 48.6 |
| B3_18 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.9 |
| B3_19 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 29.5 |
| B3_20 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 38.4 |
| B3_21 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 30.9 |
| B3_22 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 29.0 |
| B3_23 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.9 |
| B3_24 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 32.1 |
| B3_01 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.6 |
| B3_02 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 33.3 |
| B3_03 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 49.8 |
| B3_04 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.0 |
| B3_05 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 31.7 |
| B3_06 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 34.3 |
| B3_07 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 37.5 |
| B3_08 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 44.1 |
| B3_09 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 41.7 |
| B3_10 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 50.9 |
| B3_11 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 47.6 |
| B3_12 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 36.4 |
| B3_13 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 44.8 |
| B3_14 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 50.0 |
| B3_15 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 34.3 |
| B3_16 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_17 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 35.1 |
| B3_18 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_19 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 30.8 |
| B3_20 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.1 |
| B3_21 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.1 |
| B3_22 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.8 |
| B3_23 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 51.4 |
| B3_24 | solo_agent | solo-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 40.1 |
| B3_01 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 53.0 |
| B3_01 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 38.2 |
| B3_01 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 59.0 |
| B3_01 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 66.5 |
| B3_02 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.3 |
| B3_02 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 54.2 |
| B3_02 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.8 |
| B3_02 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 55.3 |
| B3_03 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.9 |
| B3_03 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 53.3 |
| B3_03 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 47.7 |
| B3_03 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 53.3 |
| B3_04 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.3 |
| B3_04 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.1 |
| B3_04 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.3 |
| B3_04 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.2 |
| B3_05 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.3 |
| B3_05 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.9 |
| B3_05 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.9 |
| B3_05 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 51.1 |
| B3_06 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.5 |
| B3_06 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 60.7 |
| B3_06 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 43.2 |
| B3_06 | database_guardian | db-r2-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 56.3 |
| B3_06 | database_guardian | db-r2i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 36.0 |
| B3_06 | continuity_guardian | cg-r2-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 38.5 |
| B3_06 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 56.1 |
| B3_07 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.5 |
| B3_07 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 51.8 |
| B3_07 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.9 |
| B3_07 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.0 |
| B3_08 | database_guardian | db-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.9 |
| B3_08 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.1 |
| B3_08 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 53.0 |
| B3_08 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.8 |
| B3_09 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 55.9 |
| B3_09 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.5 |
| B3_09 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 46.5 |
| B3_09 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.5 |
| B3_10 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 54.3 |
| B3_10 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.5 |
| B3_10 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_10 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 45.9 |
| B3_11 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 53.2 |
| B3_11 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.9 |
| B3_11 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_11 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.0 |
| B3_12 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 51.2 |
| B3_12 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 51.5 |
| B3_12 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 2 | 0 | verified | 61.7 |
| B3_12 | database_guardian | db-r2-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 39.6 |
| B3_12 | continuity_guardian | cg-r2-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 53.8 |
| B3_12 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.5 |
| B3_13 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 54.9 |
| B3_13 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 53.5 |
| B3_13 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_13 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 45.9 |
| B3_14 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.0 |
| B3_14 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.8 |
| B3_14 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 34.1 |
| B3_15 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 46.1 |
| B3_15 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 63.1 |
| B3_15 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 43.3 |
| B3_15 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 6 | 0 | verified | 52.8 |
| B3_16 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 52.2 |
| B3_16 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 42.4 |
| B3_16 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 52.9 |
| B3_17 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 33.1 |
| B3_17 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.7 |
| B3_17 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 2 | 0 | verified | 75.6 |
| B3_17 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 6 | 0 | verified | 43.5 |
| B3_18 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.2 |
| B3_18 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.4 |
| B3_18 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.3 |
| B3_19 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 54.8 |
| B3_19 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.3 |
| B3_19 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 45.8 |
| B3_20 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 31.8 |
| B3_20 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 54.0 |
| B3_20 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 41.5 |
| B3_20 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_21 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 44.9 |
| B3_21 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 53.1 |
| B3_21 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_22 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 33.1 |
| B3_22 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 45.8 |
| B3_22 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | nvidia | 2 | 0 | verified | 73.1 |
| B3_22 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.1 |
| B3_23 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 51.3 |
| B3_23 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 43.8 |
| B3_23 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 74.2 |
| B3_23 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.2 |
| B3_24 | database_guardian | db-r1-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 52.0 |
| B3_24 | database_guardian | db-r1i-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.1 |
| B3_24 | continuity_guardian | cg-r1-a1 | `nvidia/nemotron-3-ultra-550b-a55b` | nvidia | 2 | 0 | verified | 46.0 |
| B3_24 | recovery_auditor | auditor-a1 | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia | 2 | 0 | verified | 46.0 |
