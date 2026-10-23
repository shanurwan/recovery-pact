"""Meterless Runtime (Nightshift) as RecoveryPact's primary AI provider.

Implements the official provider contract for Meterless Runtime 0.90.0
(github.com/Meterless/Meterless, docs/agent-ready/add-meterless-provider.md):

- OpenAI-compatible; default base URL http://127.0.0.1:8088/v1. Any pasted URL
  (with or without scheme, /v1, /v1/chat/completions, /v1/models, /healthz) is
  normalised to <host>/v1, never /v1/v1.
- Real auth: Authorization: Bearer <METERLESS_RUNTIME_TOKEN> on every call; the
  placeholder rt-local is rejected.
- meterless-app: recovery-pact on every request, meterless-scope: user on chat.
- Model ids are routing modes (meterless/auto, fast, deep, ...), read from
  GET /v1/models; unknown meterless/* ids are kept.
- GET /v1/models decides status: 401/403 unauthorized, 200 with meterless ids
  online, anything else offline. /healthz only proves the process is up.
- Auto Detect: ports 8088, 8090, 8787, 11434 on 127.0.0.1, localhost, [::1].
- 180 s timeout, because a cold model load can take minutes.

The NVIDIA key lives in Nightshift's Providers tab, not here: Nightshift serves
the Nemotron models configured in its lanes.

    python -m app.integrations.meterless.runtime          # connection, auth, discovery, text checks
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import get_settings

APP_ID = "recovery-pact"
TIMEOUT_S = 180.0
DETECT_PORTS = (8088, 8090, 8787, 11434)
DETECT_HOSTS = ("127.0.0.1", "localhost", "[::1]")
PLACEHOLDER_TOKENS = {"", "rt-local", "your-nightshift-runtime-token-here"}


def normalize_base_url(url: str) -> str:
    """Accept whatever was pasted and return <scheme>://<host>/v1."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return "http://127.0.0.1:8088/v1"
    if not re.match(r"^https?://", u, re.I):
        u = "http://" + u
    u = re.sub(r"(/v1)?(/chat/completions|/models|/healthz)?/?$", "", u, flags=re.I)
    u = re.sub(r"(/v1)+$", "", u, flags=re.I)
    return u + "/v1"


def headers(token: str, chat: bool = False) -> dict[str, str]:
    token = (token or "").strip().lstrip("﻿")  # a token pasted from a BOM-prefixed file
    h = {"Authorization": f"Bearer {token}", "meterless-app": APP_ID, "Content-Type": "application/json"}
    if chat:
        h["meterless-scope"] = "user"
    return h


@dataclass
class Status:
    state: str  # online | unauthorized | offline
    base_url: str
    models: list[str] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"provider": "meterless", "state": self.state, "base_url": self.base_url,
                "models": self.models, "detail": self.detail}


def status(base_url: str | None = None, token: str | None = None, timeout: float = 10.0) -> Status:
    s = get_settings()
    base = normalize_base_url(base_url or s.meterless_base_url)
    tok = s.meterless_runtime_token if token is None else token
    if tok.strip() in PLACEHOLDER_TOKENS:
        return Status("unauthorized", base, detail="no Meterless Runtime token set (copy it from the Nightshift Console)")
    try:
        r = httpx.get(f"{base}/models", headers=headers(tok), timeout=timeout)
    except httpx.HTTPError as exc:
        return Status("offline", base, detail=f"{type(exc).__name__}: {exc}")
    if r.status_code in (401, 403):
        return Status("unauthorized", base, detail=f"HTTP {r.status_code}: the runtime refused this token")
    if r.status_code != 200:
        return Status("offline", base, detail=f"HTTP {r.status_code}")
    try:
        ids = [m.get("id", "") for m in r.json().get("data", [])]
    except ValueError:
        return Status("offline", base, detail="/v1/models did not return JSON")
    ids = [i for i in ids if i]
    if not any(i.startswith("meterless/") for i in ids):
        return Status("offline", base, models=ids, detail="no meterless/* routes listed")
    return Status("online", base, models=ids)


def auto_detect(token: str | None = None) -> Status:
    """First online-or-unauthorized hit on the standard ports, as the contract specifies."""
    last = Status("offline", normalize_base_url(""), detail="nothing answered on 8088/8090/8787/11434")
    for port in DETECT_PORTS:
        for host in DETECT_HOSTS:
            st = status(f"http://{host}:{port}", token, timeout=2.0)
            if st.state in ("online", "unauthorized"):
                return st
    return last


def chat(model: str, messages: list[dict[str, str]], extra: dict[str, Any] | None = None) -> httpx.Response:
    s = get_settings()
    body = {"model": model, "messages": messages, "stream": False, **(extra or {})}
    with httpx.Client(timeout=TIMEOUT_S) as client:
        return client.post(f"{normalize_base_url(s.meterless_base_url)}/chat/completions",
                           headers=headers(s.meterless_runtime_token, chat=True), json=body)


def main() -> int:
    """The contract's checks: connection, authorization, model discovery and a text request."""
    s = get_settings()
    print(f"Meterless Runtime at {normalize_base_url(s.meterless_base_url)} (app id {APP_ID})")
    st = status()
    if st.state == "offline":
        found = auto_detect()
        if found.state != "offline":
            print(f"  auto-detect found the runtime at {found.base_url} ({found.state}); set METERLESS_BASE_URL to it")
        st = found if found.state != "offline" else st
    print(f"  connection + auth: {st.state.upper()} {st.detail}")
    if st.state != "online":
        return 1
    print(f"  discovery: {len(st.models)} routes: {', '.join(st.models)}")
    wrong = status(token="wrong-token-for-check")
    print(f"  wrong token reads as: {wrong.state} (must be unauthorized)")
    routes = sorted({s.meterless_model, *s.meterless_route_map.values()})
    ok = wrong.state == "unauthorized"
    for route in routes:
        t0 = time.perf_counter()
        r = chat(route, [{"role": "user", "content": "Reply with one sentence confirming this connection works."}],
                 {"max_tokens": 60, "temperature": 0})
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            print(f"  text request on {route}: HTTP {r.status_code} {r.text[:200]}")
            ok = False
            continue
        data = r.json()
        text = (data["choices"][0]["message"].get("content") or "").strip()
        print(f"  text request on {route}: served by {data.get('model')!r} in {ms:.0f} ms -> {json.dumps(text[:120])}")
        ok = ok and isinstance(text, str) and bool(text)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
