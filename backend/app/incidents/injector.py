"""Inject reproducible PostgreSQL lock-contention incidents.

All injections run inside the dedicated simulation environment against
local demo roles only — never against arbitrary external databases.

A holder thread opens a session as the scenario's role and application name,
takes ``FOR UPDATE`` on the hottest SKU's inventory row, and keeps it. Checkout
traffic then queues behind it and times out, which is the customer-visible
outage the guardians must resolve.
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
from sqlalchemy.engine import Engine

from app.config import get_settings
from app.db import get_observer_engine
from app.incidents.scenarios import ScenarioSpec, get_spec
from app.schemas.enums import IncidentScenario

logger = logging.getLogger(__name__)

HOT_SKU = "SKU-WIDGET-01"
MAX_RESUBMITS = 3
RESUBMIT_DELAY_S = 2.5


@dataclass
class ActiveIncident:
    incident_id: str
    scenario: IncidentScenario
    spec: ScenarioSpec
    injected_at: datetime
    blocker_pid: int | None = None
    blocker_role: str | None = None
    blocker_application_name: str | None = None
    sku: str = HOT_SKU
    pid_history: list[int] = field(default_factory=list)
    kills_observed: int = 0
    resubmits: int = 0
    settlement_ids: list[str] = field(default_factory=list)
    holder_outcome: str = "HOLDING"
    metadata: dict[str, Any] = field(default_factory=dict)
    hold_thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    rotate_event: threading.Event = field(default_factory=threading.Event)
    pid_changed: threading.Condition = field(default_factory=threading.Condition)

    def public(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "scenario": self.scenario.value,
            "title": self.spec.title,
            "story": self.spec.story,
            "injected_at": self.injected_at.isoformat(),
            "blocker_pid": self.blocker_pid,
            "blocker_role": self.blocker_role,
            "blocker_application_name": self.blocker_application_name,
            "pid_history": list(self.pid_history),
            "kills_observed": self.kills_observed,
            "resubmits": self.resubmits,
            "holder_outcome": self.holder_outcome,
        }


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
            prev = self._active
            self._active = None
        if prev:
            prev.stop_event.set()
            if prev.hold_thread:
                prev.hold_thread.join(timeout=8)
        self._cancel_demo_backends()
        self._close_dangling_settlements()
        return {"ok": True, "message": "incidents reset"}

    def inject(self, scenario: IncidentScenario) -> ActiveIncident:
        self.reset()
        spec = get_spec(scenario)
        inc = ActiveIncident(
            incident_id=f"inc-{uuid.uuid4().hex[:12]}",
            scenario=scenario,
            spec=spec,
            injected_at=datetime.now(timezone.utc),
            blocker_role=spec.role,
            blocker_application_name=spec.application_name,
        )
        ready = threading.Event()
        t = threading.Thread(
            target=self._holder_loop,
            args=(inc, ready),
            name=f"lock-holder-{inc.incident_id}",
            daemon=True,
        )
        inc.hold_thread = t
        t.start()
        if not ready.wait(timeout=15) or inc.blocker_pid is None:
            inc.stop_event.set()
            raise RuntimeError(f"Failed to acquire demo lock: {inc.metadata.get('error')}")
        with self._lock:
            self._active = inc
        logger.info(
            "Injected %s incident %s blocker_pid=%s app=%s",
            scenario.value,
            inc.incident_id,
            inc.blocker_pid,
            spec.application_name,
        )
        return inc

    def invalidate_blocker_identity(self, timeout: float = 10.0) -> dict[str, Any]:
        """Scenario C: the blocker reconnects, so the contract's PID goes stale."""
        inc = self.active
        if not inc:
            raise RuntimeError("No active incident")
        old_pid = inc.blocker_pid
        with inc.pid_changed:
            inc.rotate_event.set()
            inc.pid_changed.wait_for(
                lambda: inc.blocker_pid is not None and inc.blocker_pid != old_pid,
                timeout=timeout,
            )
        inc.metadata["stale_pid"] = old_pid
        inc.metadata["identity_rotated"] = True
        self._wait_until_blocking(inc.blocker_pid, timeout)
        return {"old_pid": old_pid, "new_pid": inc.blocker_pid}

    @staticmethod
    def _wait_until_blocking(pid: int | None, timeout: float) -> None:
        """Return once checkout has queued behind the reconnected blocker again.

        Without this, a fast re-observation can land in the gap between the old
        backend releasing its lock and the waiters re-queueing, and see no incident.
        """
        if pid is None:
            return
        deadline = time.time() + timeout
        with get_observer_engine().connect() as conn:
            while time.time() < deadline:
                if conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE :pid = ANY(pg_blocking_pids(pid))"),
                                {"pid": pid}).scalar_one():
                    return
                time.sleep(0.1)
        logger.warning("reconnected blocker pid %s is not blocking anyone after %.0fs", pid, timeout)

    # ------------------------------------------------------------------ holder

    def _role_url(self, role: str) -> str:
        after = get_settings().database_url.split("@", 1)[1]
        return f"postgresql+psycopg://{role}:{role}@{after}"

    def _holder_loop(self, inc: ActiveIncident, ready: threading.Event) -> None:
        spec = inc.spec
        engine = create_engine(
            self._role_url(spec.role),
            pool_size=1,
            max_overflow=1,
            connect_args={"options": f"-c application_name={spec.application_name}"},
        )
        # A pact deciding on a laptop CPU takes minutes per call: INCIDENT_HOLD_SCALE stretches how long
        # a job that does not finish on its own keeps its lock, so the incident is still live when it acts.
        scale = 1.0 if spec.completes_on_its_own else get_settings().incident_hold_scale
        deadline = time.time() + spec.hold_seconds * scale
        try:
            while not inc.stop_event.is_set():
                result = self._hold_once(engine, inc, ready, deadline)
                if result == "rotated":
                    continue
                if (
                    result == "killed"
                    and spec.resubmits_on_kill
                    and inc.resubmits < MAX_RESUBMITS
                    and not inc.stop_event.wait(RESUBMIT_DELAY_S)
                ):
                    inc.resubmits += 1
                    logger.info("scheduler resubmitted %s (attempt %s)", spec.application_name, inc.resubmits)
                    continue
                break
        finally:
            engine.dispose()
            ready.set()

    def _hold_once(
        self,
        engine: Engine,
        inc: ActiveIncident,
        ready: threading.Event,
        deadline: float,
    ) -> str:
        spec = inc.spec
        settlement_id: str | None = None
        if spec.protected:
            settlement_id = str(uuid.uuid4())
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO settlement_ledger (settlement_id, amount_cents, status, protected) "
                        "VALUES (:sid, :amt, 'IN_PROGRESS', TRUE)"
                    ),
                    {"sid": settlement_id, "amt": 1_250_000},
                )
            inc.settlement_ids.append(settlement_id)
        try:
            with engine.connect() as conn:
                trans = conn.begin()
                pid = int(conn.execute(text("SELECT pg_backend_pid()")).scalar_one())
                tag = f" /* {spec.query_comment} */" if spec.query_comment else ""
                conn.execute(
                    text("SELECT reserved FROM inventory_locks WHERE sku = :sku FOR UPDATE" + tag),
                    {"sku": inc.sku},
                )
                with inc.pid_changed:
                    inc.blocker_pid = pid
                    inc.pid_history.append(pid)
                    inc.holder_outcome = "HOLDING"
                    inc.pid_changed.notify_all()
                ready.set()
                while not inc.stop_event.is_set():
                    if inc.rotate_event.is_set():
                        inc.rotate_event.clear()
                        trans.rollback()
                        # Drop the pooled connection so the job reconnects as a new backend.
                        conn.invalidate()
                        return "rotated"
                    if time.time() >= deadline:
                        break
                    # Touch the session so a terminated backend surfaces promptly. Scenario H
                    # keeps its comment in the touch, so it stays visible in pg_stat_activity.
                    conn.execute(text("SELECT 1" + tag))
                    time.sleep(0.25)
                if spec.completes_on_its_own and not inc.stop_event.is_set():
                    trans.commit()
                    self._mark_settlement(engine, settlement_id, "COMPLETED")
                    inc.holder_outcome = "COMPLETED"
                    return "completed"
                trans.rollback()
                inc.holder_outcome = "STOPPED"
                return "stopped"
        except Exception as exc:  # noqa: BLE001 — a terminated backend lands here
            if inc.stop_event.is_set():
                return "stopped"
            inc.kills_observed += 1
            inc.holder_outcome = "KILLED"
            inc.metadata["error"] = str(exc)[:300]
            logger.warning("lock holder pid=%s ended: %s", inc.blocker_pid, str(exc)[:120])
            self._mark_settlement(engine, settlement_id, "ABORTED")
            ready.set()
            return "killed"

    @staticmethod
    def _mark_settlement(engine: Engine, settlement_id: str | None, status: str) -> None:
        if not settlement_id:
            return
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE settlement_ledger SET status = :st, finished_at = now() "
                        "WHERE settlement_id = :sid"
                    ),
                    {"st": status, "sid": settlement_id},
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not mark settlement %s %s: %s", settlement_id, status, exc)

    def _cancel_demo_backends(self) -> None:
        from app.db.session import get_executor_engine

        try:
            with get_executor_engine().connect() as conn:
                conn.execute(
                    text(
                        """
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                          AND pid <> pg_backend_pid()
                          AND usename IN ('batch_worker', 'settlement_worker')
                        """
                    )
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("cancel demo backends: %s", exc)

    def _close_dangling_settlements(self) -> None:
        try:
            engine = create_engine(self._role_url("settlement_worker"))
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE settlement_ledger SET status = 'RESET', finished_at = now() "
                        "WHERE status = 'IN_PROGRESS'"
                    )
                )
            engine.dispose()
        except Exception as exc:  # noqa: BLE001
            logger.warning("close dangling settlements: %s", exc)


injector = IncidentInjector()
