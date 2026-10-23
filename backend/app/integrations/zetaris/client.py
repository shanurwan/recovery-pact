"""Zetaris Lightning SQL over REST.

    POST {ZETARIS_URL}/api/auth/login                       -> idToken
    POST {ZETARIS_URL}/api/proxy/sql-editor/sqls/run-query  (Bearer idToken, X-Org-ID)

Tokens live about 15 minutes. An expired token comes back as 400 ("Not Allowed"
or a bare "Bad Request") rather than 401, so the client refreshes the token
before it gets old and re-logs in exactly once on any 400/401/403. Login
failures are not retried: three bad logins lock the account.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


TOKEN_MAX_AGE_S = 10 * 60


class ZetarisError(RuntimeError):
    pass


@dataclass
class QueryResult:
    headers: list[str]
    rows: list[list[Any]]
    latency_ms: float

    def records(self) -> list[dict[str, Any]]:
        return [dict(zip(self.headers, r)) for r in self.rows]


class ZetarisClient:
    def __init__(self) -> None:
        s = get_settings()
        self.base_url = s.zetaris_url.rstrip("/")
        self.email = s.zetaris_email
        self.password = s.zetaris_password
        self.org_id = s.zetaris_org_id
        self.timeout = s.zetaris_timeout_seconds
        self._token: str | None = None
        self._token_at = 0.0
        self._lock = threading.Lock()

    def _headers(self, token: str | None = None) -> dict[str, str]:
        h = {"Content-Type": "application/json", "X-Org-ID": self.org_id}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def login(self) -> str:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/api/auth/login",
                headers=self._headers(),
                json={"username": self.email, "password": self.password},
            )
        if resp.status_code != 200:
            raise ZetarisError(f"login failed: HTTP {resp.status_code} {resp.text[:200]}")
        body = resp.json()
        token = body.get("idToken") or body.get("token") or body.get("accessToken")
        if not token:
            raise ZetarisError(f"login returned no token (keys={list(body)})")
        self._token = token
        self._token_at = time.monotonic()
        return token

    def query(self, sql: str, limit: int = 200) -> QueryResult:
        with self._lock:
            fresh = self._token and time.monotonic() - self._token_at < TOKEN_MAX_AGE_S
            token = self._token if fresh else self.login()
        started = time.perf_counter()
        resp = self._run(sql, limit, token)
        if resp.status_code in (400, 401, 403):
            with self._lock:
                token = self.login()
            resp = self._run(sql, limit, token)
        latency = (time.perf_counter() - started) * 1000
        if resp.status_code != 200:
            raise ZetarisError(f"query failed: HTTP {resp.status_code} {resp.text[:300]}")
        body = resp.json()
        headers = [h.get("name") if isinstance(h, dict) else h for h in body.get("headers", [])]
        return QueryResult(headers=headers, rows=body.get("data", []), latency_ms=latency)

    def _run(self, sql: str, limit: int, token: str) -> httpx.Response:
        with httpx.Client(timeout=self.timeout) as client:
            return client.post(
                f"{self.base_url}/api/proxy/sql-editor/sqls/run-query",
                headers=self._headers(token),
                json={"sql": sql, "limit": limit},
            )


_client: ZetarisClient | None = None


def get_zetaris_client() -> ZetarisClient:
    global _client
    if _client is None:
        _client = ZetarisClient()
    return _client
