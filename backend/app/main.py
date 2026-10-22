"""RecoveryPact API."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_observer_engine, session_scope
from app.incidents.injector import injector
from app.incidents.scenarios import SCENARIOS
from app.integrations.nemotron.client import get_inference_client
from app.integrations.zetaris.business import get_business_context
from app.memory.hmem import get_hmem
from app.negotiation.orchestrator import run_store, start_run, submit_human_decision
from app.schemas.enums import Architecture, IncidentScenario
from app.services.checkout import checkout, health_snapshot

logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="RecoveryPact", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    scenario: IncidentScenario
    arch: Architecture = Architecture.PACT
    use_memory: bool = True


class DecisionRequest(BaseModel):
    approve: bool
    candidate_id: str | None = None
    note: str = ""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/checkout")
def do_checkout(customer_id: str = "web", sku: str = "SKU-WIDGET-01") -> dict[str, Any]:
    r = checkout(customer_id, sku)
    return {"success": r.success, "latency_ms": round(r.latency_ms, 1), "timed_out": r.timed_out}


@app.get("/api/status")
def status() -> dict[str, Any]:
    client = get_inference_client()
    biz = get_business_context()
    inc = injector.active
    try:
        memories = len(get_hmem().list(1000))
    except Exception:  # noqa: BLE001
        memories = -1
    return {
        "inference": {"mode": client.mode, "model": client.model_id},
        "zetaris": {"mode": biz.mode, "url": get_settings().zetaris_url if biz.zetaris_enabled else None},
        "memory": {"enabled": get_settings().hmem_enabled, "count": memories},
        "busy": run_store.busy.locked(),
        "incident": inc.public() if inc else None,
        "checkout": health_snapshot(15),
    }


@app.get("/api/checkout/series")
def checkout_series(seconds: int = 120) -> list[dict[str, Any]]:
    with session_scope(get_observer_engine()) as session:
        rows = session.execute(
            text(
                """
                SELECT extract(epoch FROM date_trunc('second', created_at))::bigint AS t,
                       count(*) FILTER (WHERE outcome = 'SUCCESS') AS ok,
                       count(*) FILTER (WHERE outcome <> 'SUCCESS') AS bad
                FROM checkout_events
                WHERE created_at > now() - make_interval(secs => :s)
                GROUP BY 1 ORDER BY 1
                """
            ),
            {"s": seconds},
        ).all()
    return [{"t": int(r.t), "ok": int(r.ok), "bad": int(r.bad)} for r in rows]


@app.get("/api/scenarios")
def scenarios() -> list[dict[str, Any]]:
    return [
        {
            "id": s.scenario.value,
            "title": s.title,
            "story": s.story,
            "expected_outcome": s.expected_outcome,
            "expected_action": s.expected_action,
        }
        for s in SCENARIOS.values()
    ]


@app.post("/api/runs")
def create_run(req: RunRequest) -> dict[str, Any]:
    try:
        run = start_run(req.scenario, req.arch, req.use_memory, interactive=True)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return run.summary()


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    return [r.summary() for r in run_store.list()]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run = run_store.get(run_id)
    if run:
        return run.to_json()
    path = Path(get_settings().runs_dir) / f"{run_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    raise HTTPException(404, "run not found")


@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: str, after: int = 0) -> StreamingResponse:
    run = run_store.get(run_id)
    if not run:
        raise HTTPException(404, "run not found")

    async def gen():
        sent = after
        while True:
            events = await asyncio.to_thread(run.wait_events, sent, 10.0)
            for ev in events:
                sent = ev.seq
                yield f"id: {ev.seq}\nevent: pact\ndata: {ev.model_dump_json()}\n\n"
            if run.status != "running" and sent >= len(run.events):
                yield f"event: end\ndata: {json.dumps(run.summary(), default=str)}\n\n"
                return
            if not events:
                yield ": keepalive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/runs/{run_id}/decision")
def decision(run_id: str, req: DecisionRequest) -> dict[str, Any]:
    try:
        run = submit_human_decision(run_id, req.approve, req.candidate_id, req.note)
    except KeyError as exc:
        raise HTTPException(404, "run not found") from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return run.summary()


@app.post("/api/reset")
def reset() -> dict[str, Any]:
    if run_store.busy.locked():
        raise HTTPException(409, "a run is in progress")
    return injector.reset()


@app.get("/api/memory")
def memory() -> dict[str, Any]:
    hm = get_hmem()
    return {"memories": hm.list(100), "ledger": hm.ledger(100), "embedder": getattr(hm.embedder, "name", "")}


@app.post("/api/memory/clear")
def memory_clear() -> dict[str, Any]:
    if run_store.busy.locked():
        raise HTTPException(409, "a run is in progress")
    get_hmem().clear()
    return {"ok": True}


@app.get("/api/evals")
def evals() -> dict[str, Any]:
    base = Path("evals/results")
    out: dict[str, Any] = {}
    for f in sorted(base.glob("*/summary.json")):
        out[f.parent.name] = json.loads(f.read_text(encoding="utf-8"))
    return out
