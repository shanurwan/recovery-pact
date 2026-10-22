"""Shared enumerations for RecoveryPact."""

from enum import Enum


class ContractState(str, Enum):
    DRAFT = "DRAFT"
    CHALLENGED = "CHALLENGED"
    REVISED = "REVISED"
    AGREED = "AGREED"
    SUBMITTED_FOR_AUTHORIZATION = "SUBMITTED_FOR_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"
    EXECUTED = "EXECUTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


class NegotiationStatus(str, Enum):
    OBSERVING = "OBSERVING"
    PROPOSING = "PROPOSING"
    CHALLENGING = "CHALLENGING"
    INVESTIGATING = "INVESTIGATING"
    REVISING = "REVISING"
    AGREED = "AGREED"
    ESCALATED = "ESCALATED"
    TIMED_OUT = "TIMED_OUT"


class ChallengeDecision(str, Enum):
    ACCEPT = "ACCEPT"
    CONDITIONAL_ACCEPT = "CONDITIONAL_ACCEPT"
    REJECT = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"
    ESCALATE = "ESCALATE"


class RemediationActionType(str, Enum):
    TERMINATE_BACKEND = "TERMINATE_BACKEND"
    # Intentionally narrow — additional types require explicit allowlisting.


class CandidateKind(str, Enum):
    """What a guardian may choose. Only TERMINATE reaches the executor."""

    TERMINATE = "TERMINATE"
    WAIT = "WAIT"
    ESCALATE = "ESCALATE"


class WorkloadClass(str, Enum):
    CHECKOUT = "CHECKOUT"
    BATCH_REPLAYABLE = "BATCH_REPLAYABLE"
    PROTECTED_SETTLEMENT = "PROTECTED_SETTLEMENT"
    UNKNOWN = "UNKNOWN"


class Outcome(str, Enum):
    VERIFIED_RECOVERED = "VERIFIED_RECOVERED"
    FAILED = "FAILED"
    DENIED = "DENIED"
    ESCALATED = "ESCALATED"


class Architecture(str, Enum):
    """Ablation arms. Only PACT is the product; the others are baselines."""

    NAIVE_SINGLE = "naive_single"  # one agent, direct DB privileges, no gate
    GATED_SINGLE = "gated_single"  # one agent + authority gate + DB-only check
    PACT = "pact"  # two guardians + authority + business verification


class IncidentScenario(str, Enum):
    SAFE_AUTONOMOUS = "A_SAFE_AUTONOMOUS"
    PROTECTED_TRANSACTION = "B_PROTECTED_TRANSACTION"
    STALE_CONTRACT = "C_STALE_CONTRACT"
    BOTH_AGENTS_WRONG = "D_BOTH_AGENTS_WRONG"
    VERIFICATION_FAILS = "E_VERIFICATION_FAILS"
    NEGOTIATION_TIMEOUT = "F_NEGOTIATION_TIMEOUT"
    BUSINESS_FREEZE = "G_BUSINESS_FREEZE"


# Valid contract state transitions (deny-by-default outside this map).
VALID_TRANSITIONS: dict[ContractState, set[ContractState]] = {
    ContractState.DRAFT: {
        ContractState.CHALLENGED,
        ContractState.AGREED,
        ContractState.ESCALATED,
    },
    ContractState.CHALLENGED: {
        ContractState.REVISED,
        ContractState.ESCALATED,
        ContractState.DENIED,
    },
    ContractState.REVISED: {
        ContractState.CHALLENGED,
        ContractState.AGREED,
        ContractState.ESCALATED,
    },
    ContractState.AGREED: {
        ContractState.SUBMITTED_FOR_AUTHORIZATION,
        ContractState.ESCALATED,
    },
    ContractState.SUBMITTED_FOR_AUTHORIZATION: {
        ContractState.AUTHORIZED,
        ContractState.DENIED,
    },
    ContractState.AUTHORIZED: {ContractState.EXECUTED, ContractState.DENIED},
    ContractState.EXECUTED: {ContractState.VERIFIED, ContractState.FAILED},
    ContractState.DENIED: set(),
    ContractState.VERIFIED: set(),
    ContractState.FAILED: {ContractState.ESCALATED},
    ContractState.ESCALATED: set(),
}
