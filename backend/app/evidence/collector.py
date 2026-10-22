"""Collect PostgreSQL lock / activity evidence via observer role."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db.session import get_observer_engine, session_scope
from app.services.checkout import health_snapshot


def collect_lock_evidence(incident_id: str) -> dict[str, Any]:
    evidence_id = f"ev-lock-{uuid.uuid4().hex[:10]}"
    with session_scope(get_observer_engine()) as session:
        blockers = session.execute(
            text(
                """
                SELECT
                  blocked.pid AS blocked_pid,
                  blocked.usename AS blocked_user,
                  blocked.application_name AS blocked_app,
                  blocked.query AS blocked_query,
                  blocking.pid AS blocking_pid,
                  blocking.usename AS blocking_user,
                  blocking.application_name AS blocking_app,
                  blocking.state AS blocking_state,
                  blocking.query AS blocking_query,
                  EXTRACT(EPOCH FROM (now() - blocking.xact_start)) AS blocking_xact_age_s
                FROM pg_stat_activity blocked
                JOIN pg_locks bl ON bl.pid = blocked.pid AND NOT bl.granted
                JOIN pg_locks bk ON bk.locktype = bl.locktype
                  AND bk.database IS NOT DISTINCT FROM bl.database
                  AND bk.relation IS NOT DISTINCT FROM bl.relation
                  AND bk.page IS NOT DISTINCT FROM bl.page
                  AND bk.tuple IS NOT DISTINCT FROM bl.tuple
                  AND bk.virtualxid IS NOT DISTINCT FROM bl.virtualxid
                  AND bk.transactionid IS NOT DISTINCT FROM bl.transactionid
                  AND bk.classid IS NOT DISTINCT FROM bl.classid
                  AND bk.objid IS NOT DISTINCT FROM bl.objid
                  AND bk.objsubid IS NOT DISTINCT FROM bl.objsubid
                  AND bk.pid <> bl.pid
                  AND bk.granted
                JOIN pg_stat_activity blocking ON blocking.pid = bk.pid
                WHERE blocked.datname = current_database()
                """
            )
        ).mappings().all()

        activity = session.execute(
            text(
                """
                SELECT pid, usename, application_name, state, wait_event_type, wait_event,
                       LEFT(query, 200) AS query, xact_start, query_start
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                ORDER BY xact_start NULLS LAST
                """
            )
        ).mappings().all()

        settlement = session.execute(
            text(
                """
                SELECT settlement_id::text, amount_cents, status, protected, started_at
                FROM settlement_ledger
                WHERE status = 'IN_PROGRESS' AND protected = TRUE
                """
            )
        ).mappings().all()

        batch = session.execute(
            text(
                """
                SELECT job_id, job_name, workload_class, status, started_at
                FROM batch_jobs
                WHERE status = 'RUNNING'
                ORDER BY started_at DESC
                LIMIT 5
                """
            )
        ).mappings().all()

    health = health_snapshot(30)
    return {
        "evidence_id": evidence_id,
        "incident_id": incident_id,
        "source": "postgresql_observer",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "blocking_relationships": [dict(r) for r in blockers],
        "activity": [dict(r) for r in activity],
        "protected_settlements": [dict(r) for r in settlement],
        "running_batch_jobs": [dict(r) for r in batch],
        "checkout_health": health,
    }


def classify_workload(usename: str | None, application_name: str | None) -> str:
    if application_name == "protected_settlement" or usename == "settlement_worker":
        return "PROTECTED_SETTLEMENT"
    if application_name == "batch_replayable_inventory" or usename == "batch_worker":
        return "BATCH_REPLAYABLE"
    if application_name == "checkout_api" or usename == "checkout":
        return "CHECKOUT"
    return "UNKNOWN"
