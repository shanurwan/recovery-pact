# RecoveryPact Implementation Plan

**Hackathon:** Open Agent Hackathon 2026  
**Track:** Reasoning Architecture  
**Deadline:** October 27, 2026  
**Repo:** https://github.com/shanurwan/recovery-pact.git

## Baseline (Phase 0)

| Item | Status |
|---|---|
| Remote `origin` | `https://github.com/shanurwan/recovery-pact.git` (empty) |
| Local clone | `C:\Users\user\recovery-pact` |
| Python | 3.12.7 |
| Docker | 28.5.1 |
| Cursor Agent CLI | 2026.10.19-6bbf2c4 |
| Existing code | None — greenfield |

## Priority Order

1. **Vertical slice (Incident A)** — checkout lock contention → negotiate → authorize → terminate noncritical backend → verify recovery → receipt
2. **Negative scenarios B–F** — protected txn, stale contract, wrong consensus, failed verification, negotiation timeout
3. **Sponsor adapters** — Zetaris (real REST + labeled fallback), H-MEM (spec-compatible), Nemotron (NIM OpenAI-compatible + fixtures)
4. **Operator UI** — navy/mint dashboard bound to live backend events
5. **Evals** — autonomy vs approval-gated; dual-guardian vs single-agent
6. **Release** — docs, evidence, push

## Architecture Snapshot

```
Traffic Gen → Checkout API → PostgreSQL (locks are real)
                 ↑                ↑
         Observability      Restricted Executor (pg_terminate_backend only)
                 ↓                ↑
         Evidence Store    Authority Gate (deny-by-default, deterministic)
                 ↓                ↑
    Database Guardian ⇄ Continuity Guardian  → Recovery Contract
                 ↓
            H-MEM + Zetaris adapters
                 ↓
           Recovery Receipt + UI
```

## Security Non-Negotiables

- Agents never receive unrestricted DB credentials
- Executor accepts only typed remediation commands
- Authorization is deterministic and outside the LLM
- Agent agreement ≠ execution permission
- VERIFIED_RECOVERED only after independent business + DB checks

## Sponsor Notes

| Sponsor | Approach |
|---|---|
| NVIDIA Nemotron | `https://integrate.api.nvidia.com/v1` + `nvidia/nemotron-3-nano-30b-a3b` (configurable); fixture mode without key |
| Meterless H-MEM | Python port of canonical model + hybrid ranking formula from AGENTS.md |
| Zetaris | REST login + OpenSqlQuery adapter; local federated fallback clearly labeled |

## Acceptance Gates

Gates 1–11 and 13–15 are Phase 1–2 targets. Gate 12 (live sponsor credentials) marked incomplete until keys are present.
