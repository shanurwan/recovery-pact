"""Restricted executor — typed commands only, remediator role only.

Never accepts arbitrary model-generated SQL for privileged operations.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.authority.gate import ALLOWLISTED_APP_NAMES, ALLOWLISTED_ROLES, AuthzDecision, authority_gate
from app.db.session import get_executor_engine, session_scope
from app.schemas.contract import RecoveryContract
from app.schemas.enums import RemediationActionType

logger = logging.getLogger(__name__)


class RestrictedExecutor:
    def execute(
        self,
        contract: RecoveryContract,
        decision: AuthzDecision,
    ) -> dict[str, Any]:
        started = datetime.now(timezone.utc)
        if not decision.authorized or not decision.authorization_id:
            return {
                "executed": False,
                "error": decision.reason,
                "started_at": started.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }

        target = contract.exact_target or contract.proposed_action.exact_target
        pid = int(target["pid"])

        consumed = authority_gate.consume(decision.authorization_id, pid)
        if not consumed.authorized:
            return {
                "executed": False,
                "error": consumed.reason,
                "started_at": started.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }

        action = contract.proposed_action.action_type
        if action != RemediationActionType.TERMINATE_BACKEND:
            return {
                "executed": False,
                "error": f"Unsupported action type: {action}",
                "started_at": started.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }

        return self._terminate_backend(pid, contract, started)

    def _terminate_backend(
        self,
        pid: int,
        contract: RecoveryContract,
        started: datetime,
    ) -> dict[str, Any]:
        # Final identity check under remediator connection
        with session_scope(get_executor_engine()) as session:
            live = session.execute(
                text(
                    """
                    SELECT pid, usename, application_name
                    FROM pg_stat_activity
                    WHERE pid = :pid AND datname = current_database()
                    """
                ),
                {"pid": pid},
            ).mappings().first()
            if not live:
                return {
                    "executed": False,
                    "error": "Target backend disappeared before execution",
                    "started_at": started.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            if live["usename"] not in ALLOWLISTED_ROLES:
                return {
                    "executed": False,
                    "error": f"Refusing to terminate usename={live['usename']}",
                    "started_at": started.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            if live["application_name"] not in ALLOWLISTED_APP_NAMES:
                return {
                    "executed": False,
                    "error": f"Refusing to terminate app={live['application_name']}",
                    "started_at": started.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }

            ok = session.execute(
                text("SELECT pg_terminate_backend(:pid)"),
                {"pid": pid},
            ).scalar_one()

            session.execute(
                text(
                    """
                    INSERT INTO audit_log (actor, action, details)
                    VALUES ('restricted_executor', 'TERMINATE_BACKEND', CAST(:details AS jsonb))
                    """
                ),
                {
                    "details": json.dumps(
                        {"pid": pid, "contract_id": contract.contract_id, "result": bool(ok)}
                    )
                },
            )

        finished = datetime.now(timezone.utc)
        logger.info("terminated backend pid=%s result=%s", pid, ok)
        return {
            "executed": bool(ok),
            "action": "TERMINATE_BACKEND",
            "target": {"pid": pid},
            "result": "terminated" if ok else "pg_terminate_backend returned false",
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "error": None if ok else "terminate returned false",
        }


restricted_executor = RestrictedExecutor()
