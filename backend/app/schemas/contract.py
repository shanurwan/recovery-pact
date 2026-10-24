"""Versioned Recovery Contract — negotiated intent, not authority."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.schemas.enums import (
    ChallengeDecision,
    ContractState,
    NegotiationStatus,
    RemediationActionType,
    VALID_TRANSITIONS,
    WorkloadClass,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceRef(BaseModel):
    evidence_id: str
    source: str
    summary: str
    collected_at: datetime = Field(default_factory=utcnow)


class ProposedAction(BaseModel):
    action_type: RemediationActionType
    exact_target: dict[str, Any]
    reason: str
    expected_effect: str
    workload_class: WorkloadClass = WorkloadClass.UNKNOWN


class BusinessConstraint(BaseModel):
    name: str
    description: str
    invariant: str


class ChallengeRecord(BaseModel):
    challenge_id: str = Field(default_factory=lambda: str(uuid4()))
    round: int
    author: str = "continuity_guardian"
    decision: ChallengeDecision
    objection: str
    missing_facts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    violated_invariants: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utcnow)


class RevisionRecord(BaseModel):
    revision_id: str = Field(default_factory=lambda: str(uuid4()))
    round: int
    author: str = "database_guardian"
    responds_to_challenge_id: str
    changes: list[str]
    revised_action: ProposedAction
    additional_evidence_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utcnow)


class AgreementRecord(BaseModel):
    agreement_id: str = Field(default_factory=lambda: str(uuid4()))
    database_guardian: bool
    continuity_guardian: bool
    conditions: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utcnow)


class RecoveryContract(BaseModel):
    """Strongly typed Recovery Contract.

    Agent agreement records negotiated intent only.
    Execution authority is granted solely by the independent Authority Gate.
    """

    schema_version: str = "1.0"
    contract_id: str = Field(default_factory=lambda: str(uuid4()))
    incident_id: str
    version: int = 1
    proposal_author: str = "database_guardian"
    challenge_history: list[ChallengeRecord] = Field(default_factory=list)
    revision_history: list[RevisionRecord] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    proposed_action: ProposedAction
    exact_target: dict[str, Any]
    reason: str
    expected_effect: str
    business_constraints: list[BusinessConstraint] = Field(default_factory=list)
    required_preconditions: list[str] = Field(default_factory=list)
    permitted_scope: list[str] = Field(default_factory=list)
    authority_expiration: datetime | None = None
    maximum_execution_count: int = 1
    recovery_acceptance_criteria: list[str] = Field(default_factory=list)
    negotiation_status: NegotiationStatus = NegotiationStatus.PROPOSING
    contract_state: ContractState = ContractState.DRAFT
    agreement_records: list[AgreementRecord] = Field(default_factory=list)
    creation_timestamp: datetime = Field(default_factory=utcnow)
    content_digest: str = ""
    denial_reason: str | None = None
    escalation_reason: str | None = None
    # The model calls whose answers this contract rests on (the final proposal and the
    # accepting review): response id, served model, token counts. Sealed into the digest,
    # checked against Nightshift's signed receipts by authority rule I8.
    model_provenance: list[dict[str, Any]] = Field(default_factory=list)
    human_approved: bool = False

    @field_validator("maximum_execution_count")
    @classmethod
    def _positive_executions(cls, v: int) -> int:
        if v < 1:
            raise ValueError("maximum_execution_count must be >= 1")
        return v

    def compute_digest(self) -> str:
        payload = self.model_dump(
            mode="json",
            exclude={"content_digest"},
        )
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def seal(self) -> "RecoveryContract":
        self.content_digest = self.compute_digest()
        return self

    def verify_digest(self) -> bool:
        if not self.content_digest:
            return False
        return self.content_digest == self.compute_digest()

    def transition_to(self, new_state: ContractState) -> None:
        allowed = VALID_TRANSITIONS.get(self.contract_state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Illegal transition {self.contract_state.value} → {new_state.value}"
            )
        self.contract_state = new_state

    def bump_version(self) -> None:
        self.version += 1
        self.seal()
