"""Business context for the Continuity Guardian, federated through Zetaris.

Three systems that do not know about each other:

    continuity   PostgreSQL  workload registry, service SLOs, escalation contacts
    RP_CHANGE_MGMT  CSV      change-calendar export from the change tool
    shop         PostgreSQL  live checkout events

Zetaris joins them in one SQL statement per question. Without it the Continuity
Guardian cannot tell a replayable batch from a settlement, or know the close is
running. When Zetaris is disabled or unreachable, the same questions are answered
locally from the same sources and every result is labeled
``local_federation_fallback`` so nobody mistakes it for the sponsor path. With
BUSINESS_FALLBACK=false a failed question is ``business_unavailable`` instead: no
records, and the pact treats the answer as unknown, never as "nothing found".
"""

from __future__ import annotations

import csv
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import get_settings
from app.integrations.zetaris.client import ZetarisError, get_zetaris_client
from app.services.checkout import health_snapshot

logger = logging.getLogger(__name__)

_SAFE_IDENT = re.compile(r"^[a-z0-9_]+$")


@dataclass
class BusinessAnswer:
    source: str  # "zetaris" | "local_federation_fallback" | "business_unavailable"
    records: list[dict[str, Any]]
    query: str
    latency_ms: float
    notes: list[str] = field(default_factory=list)


def _in_list(values: list[str]) -> str:
    safe = [v for v in values if _SAFE_IDENT.match(v or "")]
    if not safe:
        return "('')"
    return "(" + ", ".join(f"'{v}'" for v in safe) + ")"


@lru_cache
def _continuity_engine() -> Engine:
    return create_engine(get_settings().continuity_database_url, pool_pre_ping=True)


class BusinessContext:
    def __init__(self) -> None:
        s = get_settings()
        self.zetaris_enabled = s.zetaris_enabled and bool(s.zetaris_url)
        self.ds = s.zetaris_continuity_ds
        self.shop = s.zetaris_shop_ds
        self.cal = s.zetaris_calendar_db
        self.csv_path = Path(s.change_calendar_csv)
        self.fallback = s.business_fallback
        self.outage = {q.strip() for q in s.business_outage.split(",") if q.strip()}

    @property
    def mode(self) -> str:
        return "zetaris" if self.zetaris_enabled else "local_federation_fallback"

    # ------------------------------------------------------------- questions

    def workload_registry(self, application_names: list[str]) -> BusinessAnswer:
        sql = (
            "SELECT w.application_name, w.job_name, w.owner_team, w.workload_class, "
            "w.replayable, w.replay_cost_minutes, w.typical_runtime_s, w.interrupt_policy, "
            "w.business_purpose, e.oncall, e.channel "
            f"FROM {self.ds}.workload_registry w "
            f"LEFT JOIN {self.ds}.escalation_contacts e ON e.owner_team = w.owner_team "
            f"WHERE w.application_name IN {_in_list(application_names)}"
        )
        return self._ask(sql, lambda: self._local_registry(application_names), "registry")

    def change_calendar(self, application_names: list[str]) -> BusinessAnswer:
        # Federated join: CSV change calendar x PostgreSQL workload registry.
        fmt = "yyyy-MM-dd'T'HH:mm:ssX"
        sql = (
            "SELECT c.change_id, c.scope, c.policy, c.reason, c.window_start, c.window_end, "
            "w.application_name, w.owner_team "
            f"FROM {self.cal}.change_calendar c "
            f"JOIN {self.ds}.workload_registry w ON c.scope_type = 'job' AND c.scope = w.job_name "
            f"WHERE w.application_name IN {_in_list(application_names)} "
            f"AND current_timestamp() BETWEEN to_timestamp(c.window_start, \"{fmt}\") "
            f"AND to_timestamp(c.window_end, \"{fmt}\")"
        )
        return self._ask(sql, lambda: self._local_calendar(application_names), "calendar")

    def impact(self, window_seconds: int = 30) -> BusinessAnswer:
        # Federated join: checkout event stream (shop) x SLO table (continuity).
        sql = (
            "SELECT s.service, s.slo_success_rate, s.slo_p95_ms, s.verification_window_s, "
            "s.revenue_per_minute_cents, s.max_degradation_s, s.tier, t.total, t.failed "
            f"FROM {self.ds}.service_slo s CROSS JOIN ("
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN outcome <> 'SUCCESS' THEN 1 ELSE 0 END) AS failed "
            f"FROM {self.shop}.checkout_events "
            f"WHERE created_at > current_timestamp() - INTERVAL {int(window_seconds)} SECONDS) t "
            "WHERE s.service = 'checkout'"
        )
        return self._ask(sql, lambda: self._local_impact(window_seconds), "impact")

    # ------------------------------------------------------------- plumbing

    def _ask(self, sql: str, fallback, question: str) -> BusinessAnswer:
        if self.zetaris_enabled:
            try:
                if question in self.outage or "all" in self.outage:
                    raise ZetarisError(f"injected outage: Zetaris unreachable for the {question} question")
                res = get_zetaris_client().query(sql)
                return BusinessAnswer("zetaris", _normalize(res.records()), sql, res.latency_ms)
            except (ZetarisError, Exception) as exc:  # noqa: BLE001
                if not self.fallback:
                    logger.warning("zetaris query failed, business context unavailable: %s", exc)
                    return BusinessAnswer("business_unavailable", [], sql, 0.0, notes=[f"zetaris_error: {str(exc)[:200]}"])
                logger.warning("zetaris query failed, using labeled fallback: %s", exc)
                ans = self._fallback(sql, fallback)
                ans.notes.append(f"zetaris_error: {str(exc)[:200]}")
                return ans
        return self._fallback(sql, fallback)

    @staticmethod
    def _fallback(sql: str, fn) -> BusinessAnswer:
        started = time.perf_counter()
        records = fn()
        return BusinessAnswer(
            "local_federation_fallback",
            _normalize(records),
            sql,
            (time.perf_counter() - started) * 1000,
            notes=["Zetaris not used; answered locally from the same three sources."],
        )

    def _local_registry(self, names: list[str]) -> list[dict[str, Any]]:
        with _continuity_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT w.application_name, w.job_name, w.owner_team, w.workload_class, "
                    "w.replayable, w.replay_cost_minutes, w.typical_runtime_s, w.interrupt_policy, "
                    "w.business_purpose, e.oncall, e.channel "
                    "FROM workload_registry w "
                    "LEFT JOIN escalation_contacts e ON e.owner_team = w.owner_team "
                    "WHERE w.application_name = ANY(:names)"
                ),
                {"names": names},
            ).mappings().all()
        return [dict(r) for r in rows]

    def _local_calendar(self, names: list[str]) -> list[dict[str, Any]]:
        registry = {r["job_name"]: r for r in self._local_registry(names)}
        now = datetime.now(timezone.utc)
        out = []
        with self.csv_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row["scope_type"] != "job" or row["scope"] not in registry:
                    continue
                start = datetime.fromisoformat(row["window_start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(row["window_end"].replace("Z", "+00:00"))
                if start <= now <= end:
                    reg = registry[row["scope"]]
                    out.append(
                        {
                            "change_id": row["change_id"],
                            "scope": row["scope"],
                            "policy": row["policy"],
                            "reason": row["reason"],
                            "window_start": row["window_start"],
                            "window_end": row["window_end"],
                            "application_name": reg["application_name"],
                            "owner_team": reg["owner_team"],
                        }
                    )
        return out

    def _local_impact(self, window_seconds: int) -> list[dict[str, Any]]:
        with _continuity_engine().connect() as conn:
            slo = conn.execute(
                text("SELECT * FROM service_slo WHERE service = 'checkout'")
            ).mappings().first()
        h = health_snapshot(window_seconds)
        rec = dict(slo or {})
        rec["total"] = h["total"]
        rec["failed"] = h["failed_count"] + h["timeout_count"]
        return [rec]


def _normalize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Zetaris returns strings for many types; make both paths look the same."""
    out = []
    for r in records:
        n: dict[str, Any] = {}
        for k, v in r.items():
            if isinstance(v, str) and v.lower() in ("true", "false"):
                v = v.lower() == "true"
            elif isinstance(v, str) and re.fullmatch(r"-?\d+", v):
                v = int(v)
            elif isinstance(v, str) and re.fullmatch(r"-?\d+\.\d+", v):
                v = float(v)
            elif hasattr(v, "is_finite"):  # Decimal
                v = float(v)
            elif isinstance(v, datetime):
                v = v.isoformat()
            n[k] = v
        out.append(n)
    return out


_ctx: BusinessContext | None = None


def get_business_context() -> BusinessContext:
    global _ctx
    if _ctx is None:
        _ctx = BusinessContext()
    return _ctx
