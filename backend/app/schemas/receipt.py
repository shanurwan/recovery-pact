"""Recovery Receipt — permanent, inspectable outcome record."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.contract import ChallengeRecord, ProposedAction, RevisionRecord
from app.schemas.enums import Outcome


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HealthSnapshot(BaseModel):
    captured_at: datetime = Field(default_factory=utcnow)
    checkout_success_rate: float
    checkout_p95_latency_ms: float
    timeout_count: int
    failed_count: int
    success_count: int
    blocking_pid: int | None = None
    lock_waiters: int = 0
    notes: str = ""


class PolicyDecision(BaseModel):
    authorized: bool
    reason: str
    checks: list[dict[str, Any]] = Field(default_factory=list)
    decided_at: datetime = Field(default_factory=utcnow)


class ExecutionRecord(BaseModel):
    executed: bool
    action: ProposedAction | None = None
    target: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: str = ""
    error: str | None = None


class VerificationResult(BaseModel):
    methodology: str
    database_healthy: bool
    business_healthy: bool
    protected_operations_intact: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=utcnow)


class RecoveryReceipt(BaseModel):
    receipt_id: str = Field(default_factory=lambda: str(uuid4()))
    incident_id: str
    contract_ids: list[str] = Field(default_factory=list)
    contract_versions: list[int] = Field(default_factory=list)
    original_proposal: ProposedAction | None = None
    revised_proposals: list[ProposedAction] = Field(default_factory=list)
    challenges: list[ChallengeRecord] = Field(default_factory=list)
    revisions: list[RevisionRecord] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    policy_decision: PolicyDecision | None = None
    execution: ExecutionRecord = Field(default_factory=ExecutionRecord)
    health_before: HealthSnapshot | None = None
    health_after: HealthSnapshot | None = None
    verification: VerificationResult | None = None
    recovery_duration_ms: float | None = None
    protected_operation_integrity: str = "UNKNOWN"
    human_escalation: bool = False
    escalation_reason: str | None = None
    final_outcome: Outcome
    created_at: datetime = Field(default_factory=utcnow)
    inference_mode: str = "fixture"
    model_id: str | None = None
    notes: list[str] = Field(default_factory=list)
