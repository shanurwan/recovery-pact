"""Recovery Auditor: the third agent. Runs after the outcome is known.

It reads the whole negotiation, the authority decision and the independent
verification, then produces two things:

- a post-incident report a human can read in thirty seconds
- lessons for Meterless H-MEM, so the next pact starts smarter

It writes memory but cannot act, and its lessons are stored as procedural
memories with lower confidence than verified outcomes. Verified facts are still
written deterministically by the orchestrator; the auditor adds judgement on top.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.integrations.nemotron.client import get_inference_client

logger = logging.getLogger(__name__)

RECOVERY_AUDITOR = "recovery_auditor"

AUDITOR_SYSTEM = """You are the Recovery Auditor in RecoveryPact.

Two guardians negotiated a database recovery: the Database Guardian (restore the database)
and the Continuity Guardian (protect the business). An independent authority decided what
could run and an independent verifier judged whether the business recovered.

Your job, after the fact:
1. Write a short post-incident report for the owning team: what broke, what was decided and
   why, what happened, and whether the business is back. Plain language, numbers from the
   trace, no speculation beyond the evidence.
2. Extract at most 3 lessons that would make the NEXT negotiation on the same workload
   faster or safer. A good lesson is specific (names the workload), actionable (what to do
   or check first) and grounded in what happened. Do not repeat generic policy.
3. Judge the negotiation itself: did either guardian waste a round, miss evidence, or get
   overridden by an invariant?

Respond with ONLY a JSON object, no prose."""

AUDITOR_SCHEMA = """{
  "report": "<4-6 sentences for the owning team>",
  "root_cause": "<one sentence>",
  "lessons": ["<specific, actionable lesson naming the workload>", "..."],
  "negotiation_critique": "<one or two sentences on how the guardians reasoned>",
  "follow_ups": ["<concrete follow-up for a human>", "..."]
}"""


class AuditReport(BaseModel):
    report: str
    root_cause: str = ""
    lessons: list[str] = Field(default_factory=list, max_length=5)
    negotiation_critique: str = ""
    follow_ups: list[str] = Field(default_factory=list)


def audit(trace: str, workload_names: list[str], call_key: str) -> tuple[AuditReport | None, list[dict[str, Any]]]:
    client = get_inference_client()
    metrics: list[dict[str, Any]] = []
    user = f"TRACE:\n{trace}\n\nRespond with ONLY JSON matching:\n{AUDITOR_SCHEMA}"
    for attempt in (1, 2):
        try:
            raw, m = client.complete_json(system=AUDITOR_SYSTEM, user=user, call_key=f"{call_key}-a{attempt}")
            metrics.append(m)
            rep = AuditReport.model_validate(raw)
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            user += f"\n\nYour previous answer was invalid ({str(exc)[:200]}). Answer again with ONLY the JSON."
            continue
        except Exception as exc:  # noqa: BLE001 — auditor is best effort; never blocks recovery
            logger.warning("auditor unavailable: %s", exc)
            return None, metrics
        # Grounding: keep lessons that name a workload seen in this incident.
        rep.lessons = [
            lesson for lesson in rep.lessons[:3] if any(w and w in lesson for w in workload_names)
        ]
        return rep, metrics
    return None, metrics
