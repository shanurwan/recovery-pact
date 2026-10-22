"""Customer-facing checkout workflow using real PostgreSQL transactions."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.db.session import get_app_engine, session_scope


@dataclass
class CheckoutResult:
    success: bool
    order_id: str | None
    latency_ms: float
    error: str | None = None
    timed_out: bool = False


def checkout(customer_id: str, sku: str = "SKU-WIDGET-01", qty: int = 1) -> CheckoutResult:
    """Atomically reserve inventory and create an order.

    Contends on ``inventory_locks`` row for the SKU — this is where batch
    lock holders cause customer-facing timeouts.
    """
    settings = get_settings()
    timeout_s = settings.checkout_timeout_ms / 1000.0
    order_id = str(uuid.uuid4())
    started = time.perf_counter()

    engine = get_app_engine()
    try:
        with session_scope(engine) as session:
            session.execute(text(f"SET LOCAL statement_timeout = '{int(timeout_s * 1000)}ms'"))
            session.execute(text("SET LOCAL lock_timeout = '{ms}ms'".format(ms=int(timeout_s * 1000))))

            product = session.execute(
                text(
                    "SELECT price_cents, stock FROM products WHERE sku = :sku FOR SHARE"
                ),
                {"sku": sku},
            ).one()
            price_cents, stock = product
            if stock < qty:
                raise ValueError("insufficient stock")

            # Row lock on inventory_locks — blocked when batch holds FOR UPDATE
            session.execute(
                text(
                    "SELECT reserved FROM inventory_locks WHERE sku = :sku FOR UPDATE"
                ),
                {"sku": sku},
            )
            session.execute(
                text(
                    "UPDATE inventory_locks SET reserved = reserved + :qty, updated_at = now() WHERE sku = :sku"
                ),
                {"sku": sku, "qty": qty},
            )
            session.execute(
                text(
                    "UPDATE products SET stock = stock - :qty WHERE sku = :sku AND stock >= :qty"
                ),
                {"sku": sku, "qty": qty},
            )
            total = price_cents * qty
            session.execute(
                text(
                    """
                    INSERT INTO orders (order_id, customer_id, sku, qty, total_cents, status)
                    VALUES (:order_id, :customer_id, :sku, :qty, :total, 'CONFIRMED')
                    """
                ),
                {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "sku": sku,
                    "qty": qty,
                    "total": total,
                },
            )
            latency = (time.perf_counter() - started) * 1000
            session.execute(
                text(
                    """
                    INSERT INTO checkout_events (order_id, customer_id, sku, outcome, latency_ms)
                    VALUES (:order_id, :customer_id, :sku, 'SUCCESS', :latency)
                    """
                ),
                {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "sku": sku,
                    "latency": latency,
                },
            )
            return CheckoutResult(True, order_id, latency)
    except OperationalError as exc:
        latency = (time.perf_counter() - started) * 1000
        msg = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
        timed_out = "timeout" in msg.lower() or "canceling statement" in msg.lower()
        _record_failure(customer_id, sku, order_id, latency, msg, timed_out)
        return CheckoutResult(False, None, latency, error=msg, timed_out=timed_out)
    except Exception as exc:  # noqa: BLE001 — surface as checkout failure
        latency = (time.perf_counter() - started) * 1000
        _record_failure(customer_id, sku, order_id, latency, str(exc), False)
        return CheckoutResult(False, None, latency, error=str(exc))


def _record_failure(
    customer_id: str,
    sku: str,
    order_id: str,
    latency: float,
    error: str,
    timed_out: bool,
) -> None:
    outcome = "TIMEOUT" if timed_out else "FAILED"
    try:
        with session_scope(get_app_engine()) as session:
            session.execute(
                text(
                    """
                    INSERT INTO checkout_events (order_id, customer_id, sku, outcome, latency_ms, error)
                    VALUES (:order_id, :customer_id, :sku, :outcome, :latency, :error)
                    """
                ),
                {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "sku": sku,
                    "outcome": outcome,
                    "latency": latency,
                    "error": error[:500],
                },
            )
    except Exception:  # noqa: BLE001
        pass


def health_snapshot(window_seconds: int = 30) -> dict[str, Any]:
    with session_scope(get_app_engine()) as session:
        rows = session.execute(
            text(
                """
                SELECT outcome, COUNT(*) AS n, COALESCE(AVG(latency_ms), 0) AS avg_lat,
                       COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 0) AS p95
                FROM checkout_events
                WHERE created_at > now() - make_interval(secs => :secs)
                GROUP BY outcome
                """
            ),
            {"secs": window_seconds},
        ).all()
    counts = {r.outcome: int(r.n) for r in rows}
    success = counts.get("SUCCESS", 0)
    failed = counts.get("FAILED", 0)
    timeouts = counts.get("TIMEOUT", 0)
    total = success + failed + timeouts
    p95 = 0.0
    for r in rows:
        if r.outcome == "SUCCESS":
            p95 = float(r.p95)
    return {
        "window_seconds": window_seconds,
        "success_count": success,
        "failed_count": failed,
        "timeout_count": timeouts,
        "total": total,
        "success_rate": (success / total) if total else 1.0,
        "p95_latency_ms": p95,
    }
