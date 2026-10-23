"""Meterless provider contract, the JSON entry point and the per-run trace log, without network or database."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from app.config import get_settings
from app.entrypoint import execute, resolve_scenario
from app.integrations.meterless import runtime
from app.observability import trace_log
from app.schemas.enums import IncidentScenario
from app.schemas.pact import RunEvent


@pytest.mark.parametrize("pasted", [
    "127.0.0.1:8088",
    "http://127.0.0.1:8088",
    "http://127.0.0.1:8088/",
    "http://127.0.0.1:8088/v1",
    "http://127.0.0.1:8088/v1/",
    "http://127.0.0.1:8088/v1/chat/completions",
    "http://127.0.0.1:8088/v1/models",
    "http://127.0.0.1:8088/healthz",
    "http://127.0.0.1:8088/v1/v1",
])
def test_meterless_url_normalisation(pasted):
    assert runtime.normalize_base_url(pasted) == "http://127.0.0.1:8088/v1"


def test_meterless_headers_carry_app_and_scope():
    h = runtime.headers("tok", chat=True)
    assert h["Authorization"] == "Bearer tok"
    assert h["meterless-app"] == "recovery-pact"
    assert h["meterless-scope"] == "user"
    assert "meterless-scope" not in runtime.headers("tok")


def _fake_get(status_code, body=None, exc=None):
    def get(url, headers=None, timeout=None):
        if exc:
            raise exc
        return httpx.Response(status_code, json=body if body is not None else {}, request=httpx.Request("GET", url))
    return get


def test_status_unauthorized_not_offline(monkeypatch):
    monkeypatch.setattr(runtime.httpx, "get", _fake_get(401))
    assert runtime.status("http://x:8088", "wrong").state == "unauthorized"


def test_status_placeholder_token_is_unauthorized():
    assert runtime.status("http://x:8088", "rt-local").state == "unauthorized"
    assert runtime.status("http://x:8088", "").state == "unauthorized"


def test_status_online_needs_meterless_routes(monkeypatch):
    monkeypatch.setattr(runtime.httpx, "get", _fake_get(200, {"data": [{"id": "meterless/auto"}, {"id": "meterless/zz.new"}]}))
    st = runtime.status("http://x:8088", "tok")
    assert st.state == "online" and "meterless/zz.new" in st.models  # unknown meterless/* ids are kept
    monkeypatch.setattr(runtime.httpx, "get", _fake_get(200, {"data": [{"id": "gpt-x"}]}))
    assert runtime.status("http://x:8088", "tok").state == "offline"


def test_status_offline_on_connection_error(monkeypatch):
    monkeypatch.setattr(runtime.httpx, "get", _fake_get(0, exc=httpx.ConnectError("refused")))
    assert runtime.status("http://x:8088", "tok").state == "offline"


def test_route_map(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "meterless_routes", "nvidia/a=meterless/fast, nvidia/b=meterless/deep")
    monkeypatch.setattr(s, "meterless_model", "meterless/auto")
    assert s.meterless_route("nvidia/a") == "meterless/fast"
    assert s.meterless_route("nvidia/b") == "meterless/deep"
    assert s.meterless_route("nvidia/other") == "meterless/auto"


def test_resolve_scenario_accepts_letters_ids_and_titles():
    assert resolve_scenario("g") == IncidentScenario.BUSINESS_FREEZE
    assert resolve_scenario("B_PROTECTED_TRANSACTION") == IncidentScenario.PROTECTED_TRANSACTION
    with pytest.raises(ValueError):
        resolve_scenario("Z")


def test_entrypoint_returns_structured_error_on_bad_input():
    out = execute({"run_id": "t-1", "input": {"scenario": "nope"}})
    assert out["status"] == "error"
    assert out["error"]["type"] == "InvalidInput" and out["error"]["recoverable"] is False
    assert out["run_id"] == "t-1"


def test_trace_log_writes_jsonl_and_redacts(tmp_path):
    ev = RunEvent(seq=1, ts=datetime(2026, 10, 22, tzinfo=timezone.utc), kind="proposal", actor="database_guardian",
                  title="R1 proposes C1 with key nvapi-ABCDEFGHIJKLMNOP",
                  data={"proposal": {"cited_evidence": ["DB-1"], "requested_probes": [], "confidence": 0.8},
                        "attempts": 2, "metrics": [{"model": "nvidia/x", "mode": "nemotron", "latency_ms": 10,
                                                     "prompt_tokens": 5, "completion_tokens": 3}]})
    trace_log.append("run-test", ev, logs_dir=str(tmp_path))
    row = json.loads((tmp_path / "trace-run-test.jsonl").read_text(encoding="utf-8").strip())
    assert row["agent_name"] == "Database Guardian"
    assert row["target_agent"] == "Continuity Guardian"
    assert row["retry_count"] == 1 and row["confidence"] == 0.8 and row["tokens"] == 8
    assert "nvapi-ABCDEFGH" not in row["output_summary"] and "redacted" in row["output_summary"]
