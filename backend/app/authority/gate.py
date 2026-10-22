"""Independent Authority Gate — deny by default, outside the LLM.

Agent agreement is NOT execution permission. This module is the only path
that can authorize a typed remediation command.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_observer_engine, session_scope
from app.evidence.collector import classify_workload
from app.schemas.contract import RecoveryContract
from app.schemas.enums import ContractState, RemediationActionType, WorkloadClass

logger = logging.getLogger(__name__)

# Explicit allowlist — nothing else may execute.
ALLOWLISTED_ACTIONS = {RemediationActionType.TERMINATE_BACKEND}
ALLOWLISTED_ROLES = {"batch_worker"}
# Static, technical policy: replayable batch jobs by naming convention. It does
# not know about change calendars or financial close; that is business context.
ALLOWLISTED_APP_NAMES = {
    "batch_replayable_inventory",
    "batch_replayable_price_sync",
    "batch_replayable_month_end_close",
}
PROHIBITED_ROLES = {"settlement_worker", "checkout", "postgres", "observer", "remediator"}
PROHIBITED_APP_NAMES = {"protected_settlement", "checkout_api"}


@dataclass
class AuthzDecision:
    authorized: bool
    authorization_id: str | None
    reason: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    consumed: bool = False
    digest: str = ""


class AuthorityGate:
    """Deterministic policy engine with single-use authorization tokens."""

    def __init__(self) -> None:
        self._issued: dict[str, AuthzDecision] = {}
        self._audit: list[dict[str, Any]] = []

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit)

    def evaluate(self, contract: RecoveryContract) -> AuthzDecision:
        checks: list[dict[str, Any]] = []
        settings = get_settings()

        def check(name: str, ok: bool, detail: str) -> None:
            checks.append({"name": name, "passed": ok, "detail": detail})

        # 1. Contract must be AGREED or SUBMITTED
        state_ok = contract.contract_state in {
            ContractState.AGREED,
            ContractState.SUBMITTED_FOR_AUTHORIZATION,
        }
        check(
            "contract_state",
            state_ok,
            f"state={contract.contract_state.value}",
        )

        # 2. Digest integrity
        digest_ok = contract.verify_digest()
        check("content_digest", digest_ok, "tamper-evident digest")

        # 3. Action allowlist
        action = contract.proposed_action.action_type
        action_ok = action in ALLOWLISTED_ACTIONS
        check("action_allowlist", action_ok, f"action={action.value}")

        # 4. Exact target present
        target = contract.exact_target or contract.proposed_action.exact_target
        pid = target.get("pid")
        usename = target.get("usename")
        app_name = target.get("application_name")
        target_ok = isinstance(pid, int) and pid > 0
        check("exact_target_pid", target_ok, f"pid={pid}")

        # 5. Role / app allowlist (static policy — not from LLM)
        role_ok = usename in ALLOWLISTED_ROLES and usename not in PROHIBITED_ROLES
        check("role_allowlist", role_ok, f"usename={usename}")
        app_ok = app_name in ALLOWLISTED_APP_NAMES and app_name not in PROHIBITED_APP_NAMES
        check("app_allowlist", app_ok, f"application_name={app_name}")

        # 6. Workload class
        wl = contract.proposed_action.workload_class
        wl_ok = wl == WorkloadClass.BATCH_REPLAYABLE
        check("workload_class", wl_ok, f"workload_class={wl.value}")

        # 7. Live state revalidation (TOCTOU mitigation)
        live = self._live_backend(pid) if target_ok else None
        live_ok = False
        if live:
            live_role = live.get("usename")
            live_app = live.get("application_name")
            live_ok = (
                live_role == usename
                and live_app == app_name
                and classify_workload(live_role, live_app) == "BATCH_REPLAYABLE"
            )
            check(
                "live_identity",
                live_ok,
                f"live_usename={live_role} live_app={live_app} state={live.get('state')}",
            )
            # Protected settlement must never pass
            protected_present = self._protected_settlement_on_pid(pid)
            check(
                "no_protected_settlement",
                not protected_present,
                f"protected_on_pid={protected_present}",
            )
            if protected_present:
                live_ok = False
        else:
            check("live_identity", False, "backend not found or pid invalid")

        # 8. Preconditions from contract
        pre_ok = True
        for pre in contract.required_preconditions:
            # Known precondition keys we can validate
            if pre.startswith("blocking_checkout:"):
                pre_ok = pre_ok and bool(live and live.get("state"))
            if pre == "no_protected_settlement":
                pre_ok = pre_ok and not self._any_protected_settlement()
        check("preconditions", pre_ok, ",".join(contract.required_preconditions) or "none")

        # 9. Execution budget
        count_ok = contract.maximum_execution_count >= 1
        check("execution_budget", count_ok, f"max={contract.maximum_execution_count}")

        # 10. TTL will be stamped on authorization
        all_ok = all(c["passed"] for c in checks)
        if not all_ok:
            failed = [c["name"] for c in checks if not c["passed"]]
            decision = AuthzDecision(
                authorized=False,
                authorization_id=None,
                reason=f"DENIED: failed checks {failed}",
                checks=checks,
            )
            self._record(contract, decision)
            return decision

        auth_id = f"authz-{uuid4().hex[:16]}"
        expires = datetime.now(timezone.utc).timestamp() + settings.authority_ttl_seconds
        decision = AuthzDecision(
            authorized=True,
            authorization_id=auth_id,
            reason="AUTHORIZED: all deterministic checks passed",
            checks=checks,
        )
        decision.digest = hashlib.sha256(
            json.dumps(
                {
                    "auth_id": auth_id,
                    "contract_id": contract.contract_id,
                    "pid": pid,
                    "expires": expires,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        # Store with expiry metadata
        decision_meta = decision
        setattr(decision_meta, "expires_at", expires)
        setattr(decision_meta, "pid", pid)
        setattr(decision_meta, "contract_id", contract.contract_id)
        setattr(decision_meta, "contract_version", contract.version)
        self._issued[auth_id] = decision_meta
        self._record(contract, decision)
        return decision

    def consume(self, authorization_id: str, expected_pid: int) -> AuthzDecision:
        """Single-use consumption with expiry and PID re-check."""
        decision = self._issued.get(authorization_id)
        if not decision:
            return AuthzDecision(
                authorized=False,
                authorization_id=authorization_id,
                reason="DENIED: unknown authorization_id",
            )
        if decision.consumed:
            return AuthzDecision(
                authorized=False,
                authorization_id=authorization_id,
                reason="DENIED: authorization already consumed (replay)",
            )
        expires_at = getattr(decision, "expires_at", 0)
        if datetime.now(timezone.utc).timestamp() > expires_at:
            return AuthzDecision(
                authorized=False,
                authorization_id=authorization_id,
                reason="DENIED: authority expired",
            )
        if getattr(decision, "pid", None) != expected_pid:
            return AuthzDecision(
                authorized=False,
                authorization_id=authorization_id,
                reason="DENIED: target PID mismatch",
            )
        # Fresh live check
        live = self._live_backend(expected_pid)
        if not live or live.get("usename") not in ALLOWLISTED_ROLES:
            return AuthzDecision(
                authorized=False,
                authorization_id=authorization_id,
                reason="DENIED: live target no longer eligible",
            )
        decision.consumed = True
        return decision

    def force_deny(self, reason: str) -> AuthzDecision:
        return AuthzDecision(authorized=False, authorization_id=None, reason=reason)

    def _live_backend(self, pid: int | None) -> dict[str, Any] | None:
        if not pid:
            return None
        with session_scope(get_observer_engine()) as session:
            row = session.execute(
                text(
                    """
                    SELECT pid, usename, application_name, state, LEFT(query, 200) AS query
                    FROM pg_stat_activity
                    WHERE pid = :pid AND datname = current_database()
                    """
                ),
                {"pid": pid},
            ).mappings().first()
        return dict(row) if row else None

    def _protected_settlement_on_pid(self, pid: int) -> bool:
        live = self._live_backend(pid)
        if not live:
            return False
        return (
            live.get("usename") in PROHIBITED_ROLES
            or live.get("application_name") in PROHIBITED_APP_NAMES
            or classify_workload(live.get("usename"), live.get("application_name"))
            == "PROTECTED_SETTLEMENT"
        )

    def _any_protected_settlement(self) -> bool:
        with session_scope(get_observer_engine()) as session:
            n = session.execute(
                text(
                    "SELECT COUNT(*) FROM settlement_ledger "
                    "WHERE status = 'IN_PROGRESS' AND protected = TRUE"
                )
            ).scalar_one()
        return int(n) > 0

    def _record(self, contract: RecoveryContract, decision: AuthzDecision) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "contract_id": contract.contract_id,
            "version": contract.version,
            "authorized": decision.authorized,
            "reason": decision.reason,
            "authorization_id": decision.authorization_id,
            "checks": decision.checks,
        }
        self._audit.append(entry)
        logger.info("authority_decision %s", json.dumps(entry))


authority_gate = AuthorityGate()
