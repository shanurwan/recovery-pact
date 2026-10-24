"""Provenance for a benchmark run: enough to tell whether two runs are comparable.

Records the model and settings, a fingerprint of the code and prompts, and a
content hash of the business seed data actually in the database (not the files,
which may differ from what was loaded).
"""

from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from app.config import get_settings
from app.incidents.scenarios import SCENARIOS
from app.integrations.meterless import receipts
from app.integrations.nemotron.client import get_inference_client
from app.integrations.zetaris.business import get_business_context
from app.memory.hmem import get_hmem

APP_DIR = Path(__file__).resolve().parents[1]
HARNESS_VERSION = "1.0"


def code_fingerprint() -> str:
    """sha256 over every Python file of the app, in a stable order."""
    h = hashlib.sha256()
    for p in sorted(APP_DIR.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(str(p.relative_to(APP_DIR)).replace("\\", "/").encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def file_sha256(path: str | Path) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def seed_data_fingerprint() -> dict[str, str]:
    """Content hashes of the business tables as loaded in PostgreSQL."""
    s = get_settings()
    out: dict[str, str] = {}
    queries = {
        "continuity.workload_registry": (s.continuity_database_url, "SELECT * FROM workload_registry ORDER BY 1"),
        "continuity.service_slo": (s.continuity_database_url, "SELECT * FROM service_slo ORDER BY 1"),
        "continuity.escalation_contacts": (s.continuity_database_url, "SELECT * FROM escalation_contacts ORDER BY 1"),
        "checkout.products": (s.observer_database_url, "SELECT sku, name, price_cents FROM products ORDER BY 1"),
    }
    for name, (url, sql) in queries.items():
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(sql)).all()
            out[name] = hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest()
        finally:
            engine.dispose()
    return out


def build_manifest() -> dict[str, Any]:
    s = get_settings()
    client = get_inference_client()
    return {
        "harness_version": HARNESS_VERSION,
        "git_commit": os.environ.get("BENCH_GIT_SHA", "unknown"),
        "code_fingerprint": code_fingerprint(),
        "prompts_fingerprint": file_sha256(APP_DIR / "agents" / "prompts.py"),
        "change_calendar_sha256": file_sha256(s.change_calendar_csv),
        "seed_data": seed_data_fingerprint(),
        "scenarios": {sc.value: {"expected_outcome": spec.expected_outcome, "expected_action": spec.expected_action}
                      for sc, spec in SCENARIOS.items()},
        "model": client.model_id,
        "models_by_role": {r: s.model_for(r) for r in ("database_guardian", "continuity_guardian", "auditor", "solo_agent")},
        "reasoning_scaffold": s.reasoning_scaffold,
        "guard": {"enabled": s.guard_enabled and s.reasoning_scaffold, "model": s.guard_model, "fallback": s.guard_fallback_model},
        "inference_mode": client.mode,
        "thinking": s.nemotron_thinking,
        "temperature": s.inference_temperature,
        "max_rounds": s.negotiation_max_rounds,
        "negotiation_timeout_s": s.negotiation_timeout_seconds,
        "zetaris_mode": get_business_context().mode,
        "zetaris_query_layer": s.zetaris_query_layer,
        "embedder": getattr(get_hmem().embedder, "name", ""),
        "recall_threshold": s.hmem_recall_threshold,
        "traffic_rps": s.traffic_rps,
        "ai_provider": s.ai_provider,
        "meterless_routes": {"default": s.meterless_model, **s.meterless_route_map} if s.ai_provider == "meterless" else None,
        "receipt_gate": {"enabled": s.receipt_gate, "key": receipts.key_fingerprint(s.meterless_receipt_key)
                         if len(s.meterless_receipt_key) > 16 else s.meterless_receipt_key,
                         "models": s.receipt_model_prefixes, "egress": sorted(s.receipt_egress_allowed)},
        "python": platform.python_version(),
    }
