"""Inject reproducible PostgreSQL lock-contention incidents.

All injections run inside the dedicated simulation environment against
local demo roles only — never against arbitrary external databases.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text

from app.config import get_settings
from app.schemas.enums import IncidentScenario

logger = logging.getLogger(__name__)


@dataclass
class ActiveIncident:
    incident_id: str
    scenario: IncidentScenario
    injected_at: datetime
    blocker_pid: int | None = None
    blocker_role: str | None = None
    blocker_application_name: str | None = None
    sku: str = "SKU-WIDGET-01"
    metadata: dict[str, Any] = field(default_factory=dict)
    hold_thread: threading.Thread | None = None
    stop_event: threading.Event | None = None
    status: str = "ACTIVE"


class IncidentInjector:
    """Manages long-running lock holders for demo scenarios."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: ActiveIncident | None = None

    @property
    def active(self) -> ActiveIncident | None:
        with self._lock:
            return self._active

    def reset(self) -> dict[str, Any]:
        with self._lock:
            if self._active and self._active.stop_event:
                self._active.stop_event.set()
            prev = self._active
            self._active = None
        if prev and prev.hold_thread:
            prev.hold_thread.join(timeout=5)
        self._cancel_demo_backends()
        return {"ok": True, "message": "incidents reset"}

    def inject(self, scenario: IncidentScenario) -> ActiveIncident:
        self.reset()
        incident_id = f"inc-{uuid.uuid4().hex[:12]}"
        if scenario in {
            IncidentScenario.SAFE_AUTONOMOUS,
            IncidentScenario.STALE_CONTRACT,
            IncidentScenario.VERIFICATION_FAILS,
        }:
            return self._inject_batch_lock(
                incident_id,
                scenario,
                protected=False,
                keep_holding=scenario == IncidentScenario.VERIFICATION_FAILS,
            )
        if scenario == IncidentScenario.PROTECTED_TRANSACTION:
            return self._inject_batch_lock(incident_id, scenario, protected=True)
        if scenario == IncidentScenario.BOTH_AGENTS_WRONG:
            inc = ActiveIncident(
                incident_id=incident_id,
                scenario=scenario,
                injected_at=datetime.now(timezone.utc),
                metadata={"force_prohibited_proposal": True},
            )
            with self._lock:
                self._active = inc
            return inc
        if scenario == IncidentScenario.NEGOTIATION_TIMEOUT:
            # Inject a lock but mark evidence as contradictory for the orchestrator
            inc = self._inject_batch_lock(incident_id, scenario, protected=False)
            inc.metadata["contradictory_evidence"] = True
            return inc
        raise ValueError(f"Unsupported scenario: {scenario}")

    def _batch_url(self, role: str, password: str) -> str:
        base = get_settings().database_url
        after = base.split("@", 1)[1]
        return f"postgresql+psycopg://{role}:{password}@{after}"

    def _inject_batch_lock(
        self,
        incident_id: str,
        scenario: IncidentScenario,
        *,
        protected: bool,
        keep_holding: bool = False,
    ) -> ActiveIncident:
        role = "settlement_worker" if protected else "batch_worker"
        app_name = "protected_settlement" if protected else "batch_replayable_inventory"
        stop_event = threading.Event()
        ready = threading.Event()
        pid_box: dict[str, int] = {}
        error_box: dict[str, str] = {}

        def holder() -> None:
            engine = create_engine(
                self._batch_url(role, password=role),
                connect_args={"options": f"-c application_name={app_name}"},
            )
            try:
                with engine.connect() as conn:
                    trans = conn.begin()
                    try:
                        pid = int(conn.execute(text("SELECT pg_backend_pid()")).scalar_one())
                        pid_box["pid"] = pid
                        conn.execute(
                            text(
                                "INSERT INTO batch_jobs (job_name, workload_class, status, started_at) "
                                "VALUES (:name, :cls, 'RUNNING', now())"
                            ),
                            {
                                "name": (
                                    "settlement_hold" if protected else "inventory_reconcile"
                                ),
                                "cls": (
                                    "PROTECTED_SETTLEMENT" if protected else "BATCH_REPLAYABLE"
                                ),
                            },
                        )
                        if protected:
                            conn.execute(
                                text(
                                    "INSERT INTO settlement_ledger "
                                    "(settlement_id, amount_cents, status, protected) "
                                    "VALUES (:sid, :amt, 'IN_PROGRESS', TRUE)"
                                ),
                                {"sid": str(uuid.uuid4()), "amt": 100000},
                            )
                        conn.execute(
                            text(
                                "SELECT reserved FROM inventory_locks "
                                "WHERE sku = :sku FOR UPDATE"
                            ),
                            {"sku": "SKU-WIDGET-01"},
                        )
                        ready.set()
                        deadline = time.time() + 600
                        while not stop_event.is_set() and time.time() < deadline:
                            time.sleep(0.25)
                        trans.rollback()
                    except Exception as exc:
                        error_box["error"] = str(exc)
                        logger.exception("lock holder failed")
                        ready.set()
                        try:
                            trans.rollback()
                        except Exception:
                            pass
            finally:
                engine.dispose()

        t = threading.Thread(target=holder, name=f"lock-holder-{incident_id}", daemon=True)
        t.start()
        if not ready.wait(timeout=15):
            raise RuntimeError("Failed to acquire demo lock within timeout")
        if "error" in error_box and "pid" not in pid_box:
            raise RuntimeError(f"Lock holder error: {error_box['error']}")

        inc = ActiveIncident(
            incident_id=incident_id,
            scenario=scenario,
            injected_at=datetime.now(timezone.utc),
            blocker_pid=pid_box.get("pid"),
            blocker_role=role,
            blocker_application_name=app_name,
            stop_event=stop_event,
            hold_thread=t,
            metadata={
                "protected": protected,
                "keep_holding": keep_holding,
                "sku": "SKU-WIDGET-01",
            },
        )
        with self._lock:
            self._active = inc
        logger.info(
            "Injected %s incident %s blocker_pid=%s role=%s",
            scenario.value,
            incident_id,
            inc.blocker_pid,
            role,
        )
        return inc

    def invalidate_blocker_identity(self) -> dict[str, Any]:
        """Scenario C: rotate the blocker session so the contract target PID is stale."""
        with self._lock:
            inc = self._active
            if not inc:
                raise RuntimeError("No active incident")
            old_pid = inc.blocker_pid
            incident_id = inc.incident_id
            if inc.stop_event:
                inc.stop_event.set()
            thread = inc.hold_thread
        if thread:
            thread.join(timeout=5)
        self._cancel_demo_backends()
        new_inc = self._inject_batch_lock(
            incident_id,
            IncidentScenario.STALE_CONTRACT,
            protected=False,
        )
        new_inc.metadata["stale_pid"] = old_pid
        new_inc.metadata["identity_rotated"] = True
        return {"old_pid": old_pid, "new_pid": new_inc.blocker_pid}

    def _cancel_demo_backends(self) -> None:
        from app.db.session import get_executor_engine

        try:
            engine = get_executor_engine()
            with engine.connect() as conn:
                conn.execute(
                    text(
                        """
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                          AND pid <> pg_backend_pid()
                          AND usename IN ('batch_worker', 'settlement_worker')
                          AND application_name IN (
                            'batch_replayable_inventory', 'protected_settlement'
                          )
                        """
                    )
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("cancel demo backends: %s", exc)


injector = IncidentInjector()
