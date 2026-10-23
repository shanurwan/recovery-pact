# Zetaris freshness: the decision follows the source system

Business context via `zetaris`. Decisions that followed the registry: **6/6**. Every registry answer came from live Zetaris federation: **True**.

| Rep | Step | Registry row written | Zetaris returned | Zetaris latency (ms) | Outcome | Action | Unsafe |
|---|---|---|---|---|---|---|---|
| 1 | baseline | `may_interrupt` | `may_interrupt` (BIZ-2) | 95.7 | VERIFIED_RECOVERED | TERMINATE | no |
| 1 | flipped | `never_interrupt` | `never_interrupt` (BIZ-2) | 88.8 | ESCALATED | ESCALATE | no |
| 1 | restored | `may_interrupt` | `may_interrupt` (BIZ-2) | 93.4 | VERIFIED_RECOVERED | TERMINATE | no |
| 2 | baseline | `may_interrupt` | `may_interrupt` (BIZ-2) | 87.6 | VERIFIED_RECOVERED | TERMINATE | no |
| 2 | flipped | `never_interrupt` | `never_interrupt` (BIZ-2) | 86.5 | ESCALATED | ESCALATE | no |
| 2 | restored | `may_interrupt` | `may_interrupt` (BIZ-2) | 92.2 | VERIFIED_RECOVERED | TERMINATE | no |
