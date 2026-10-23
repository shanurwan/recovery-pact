"""Pact protocol messages: evidence, candidate actions, guardian turns, run events.

The guardians never name a raw PID or write SQL. They pick a candidate id that
the orchestrator enumerated from observed evidence, and cite evidence ids that
the grounding check verifies. That is what keeps their autonomy bounded.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.enums import CandidateKind, ChallengeDecision


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


EvidenceSource = Literal[
    "postgresql_observer",
    "zetaris",
    "local_federation_fallback",
    "business_unavailable",
    "meterless_hmem",
    "checkout_telemetry",
]


class Evidence(BaseModel):
    evidence_id: str
    probe: str
    source: EvidenceSource
    summary: str
    facts: dict[str, Any] = Field(default_factory=dict)
    # Exact query text for federated evidence, so a judge can rerun it.
    query: str | None = None
    latency_ms: float | None = None
    requested_by: str = "orchestrator"
    collected_at: datetime = Field(default_factory=utcnow)

    def brief(self) -> str:
        return f"[{self.evidence_id}] ({self.source}, probe={self.probe}) {self.summary}"


class Candidate(BaseModel):
    candidate_id: str
    kind: CandidateKind
    description: str
    target: dict[str, Any] = Field(default_factory=dict)
    evidence_id: str | None = None


# Probes a guardian may ask the orchestrator to run. A fixed menu: the agents
# choose what to investigate, never how to query.
PROBES: dict[str, str] = {
    "db.lock_graph": "Who blocks whom right now (pg_locks x pg_stat_activity).",
    "db.protected_settlements": "Card settlements currently in flight.",
    "biz.workload_registry": "Owner, replayability, replay cost and interrupt policy of the blocking workload (Zetaris).",
    "biz.change_calendar": "Active change-calendar windows covering the blocking workload (Zetaris, CSV source).",
    "biz.impact": "Live checkout failure rate and revenue at risk versus the SLO (Zetaris, federated).",
    "biz.tradeoff": "Cost of waiting vs cost of interrupting, computed in code from registry + impact.",
}

# Derived automatically once registry + impact evidence exist; citeable, not requestable.
DERIVED_PROBES = {"biz.tradeoff"}


def _none_to_list(v: Any) -> Any:
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    return v


class Proposal(BaseModel):
    """Database Guardian turn."""

    round: int
    candidate_id: str
    rationale: str
    cited_evidence: list[str] = Field(default_factory=list)
    expected_effect: str = ""
    risk_assessment: str = ""
    requested_probes: list[str] = Field(default_factory=list)
    responds_to: str | None = None
    changes: list[str] = Field(default_factory=list)
    confidence: float = 0.5

    _lists = field_validator("cited_evidence", "requested_probes", "changes", mode="before")(_none_to_list)


class AcceptanceCriteria(BaseModel):
    checkout_success_rate_min: float = 0.95
    window_seconds: int = 10
    protected_operations_intact: bool = True


class Review(BaseModel):
    """Continuity Guardian turn."""

    round: int
    review_id: str
    decision: ChallengeDecision
    objection: str = ""
    violated_invariants: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    cited_evidence: list[str] = Field(default_factory=list)
    acceptance_criteria: AcceptanceCriteria = Field(default_factory=AcceptanceCriteria)
    business_rationale: str = ""
    confidence: float = 0.5

    _lists = field_validator(
        "violated_invariants", "required_evidence", "conditions", "cited_evidence", mode="before"
    )(_none_to_list)

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def _criteria(cls, v: Any) -> Any:
        return v if isinstance(v, (dict, AcceptanceCriteria)) else {}


class GroundingResult(BaseModel):
    ok: bool
    problems: list[str] = Field(default_factory=list)
    # A review downgraded by a deterministic invariant (e.g. accepting a
    # termination without registry evidence) records why here.
    overridden: str | None = None


class RunEvent(BaseModel):
    seq: int
    ts: datetime = Field(default_factory=utcnow)
    kind: str
    actor: str
    title: str
    data: dict[str, Any] = Field(default_factory=dict)


class HumanBrief(BaseModel):
    """What a human needs to decide in one screen."""

    headline: str
    what_broke: str
    who_is_affected: str
    options: list[dict[str, Any]] = Field(default_factory=list)
    recommendation: str = ""
    owner_team: str | None = None
    channel: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
