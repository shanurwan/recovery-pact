# Attack 9: forge the signature

536 real Nightshift receipts, 5896 forgeries made from them, each behind a TERMINATE contract handed to the authority's rule I8 check.

- **Untouched receipts authorized: 536/536** (the control).
- **Forgeries that authorized a kill: 0/5896.**

| Forgery | Made | Authorized a kill |
|---|---|---|
| model rewritten | 536 | 0 |
| token counts rewritten | 536 | 0 |
| destination rewritten | 536 | 0 |
| re-signed with the attacker's key | 536 | 0 |
| faithful copy re-signed with the attacker's key | 536 | 0 |
| public key swapped | 536 | 0 |
| signature garbled | 536 | 0 |
| replayed for another call | 536 | 0 |
| replayed from an older incident | 536 | 0 |
| answer swapped behind a real receipt | 536 | 0 |
| receipt withheld | 536 | 0 |

Rules that caught them (a forgery can fail several):

| I8 rule | Forgeries it caught |
|---|---|
| signature verifies | 2680 |
| signed by the pinned Nightshift key | 1608 |
| a Nemotron model answered | 536 |
| names this call | 536 |
| written during this incident | 536 |
| token counts match the answer | 536 |
| no receipt | 536 |
