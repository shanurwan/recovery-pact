# Demo video script (target 3:30, hard limit 4:00)

Record the console at http://localhost:8080 with live Nemotron and live Zetaris (all three chips green). Clear memory before take one.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:20 | Console idle, checkout pulse green | "At 3 a.m. a database lock takes checkout down. The fix that's right for the database is often wrong for the business. RecoveryPact makes two AI guardians negotiate it, and an independent authority decides what may run." |
| 0:20–0:35 | Point at the chips | "Nemotron runs every agent. Zetaris federates the business context. Meterless H-MEM remembers what worked." |
| 0:35–1:30 | Run **A**. Pulse goes red. Timeline streams | "A batch job holds the lock. The Database Guardian's instinct is to wait. The Continuity Guardian pulls the registry and the change calendar through Zetaris." Click a BIZ chip to show the federated SQL. "The trade-off calculator says waiting costs about $39,000 while a replay costs four minutes. The business rejects waiting, the guardians agree on a termination, and the authority runs ten deterministic checks." Pulse back to green. "Verified on the business SLO, not just because the lock is gone." |
| 1:30–2:00 | Run **B** | "Same symptoms, but the blocker is a card settlement. Killing it double-charges customers. The guardians choose to wait: it finishes inside the 60 seconds the business tolerates, and checkout recovers with the settlement intact. Doing nothing was the right move, and the agents worked that out from the data." |
| 2:00–2:30 | Run **G**, show the decision brief | "Here policy would allow the kill, but Zetaris shows the quarter-end close is running. That trade-off belongs to finance, so the pact escalates with a one-screen brief: what broke, who is affected, the options with their costs. A human approves or declines." |
| 2:30–2:55 | Run **D** | "What if both guardians are compromised and agree on a checkout session? Agreement is not permission. The authority denies the contract." |
| 2:55–3:20 | Run **A** again, then the Memory tab | "Same incident, now with memory. The Database Guardian remembers what the Continuity Guardian needed last time and brings it up front: one round instead of two or three." Show the memories and the append-only ledger. |
| 3:20–3:30 | Evals tab | "Across seven scenarios, the pact is the only architecture with zero unsafe actions and zero false recovery claims. Recovery isn't real until the business is back." |

## Take-two fallbacks
- If the live model answers slowly, cut the waiting in the edit. Never speed up the pulse chart.
- If Zetaris is down, the chip turns amber (local fallback). Re-record: the sponsor score depends on showing it live.
