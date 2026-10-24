#!/usr/bin/env python3
"""Serve Nightshift's signed receipts, read-only, so the authority can check them before acting.

Runs on the machine running Nightshift. Nightshift appends one signed receipt per
routed call to receipts.jsonl; this serves each line exactly as written:

    GET /v1/receipts/<request_id>  -> 200 {body, sig_b64, pubkey_b64} | 404
    GET /healthz                   -> 200 {"receipts": <count>}

It cannot create or change a receipt: the authority verifies each signature
against Nightshift's pinned public key, so a relay that lies is caught. It binds
to loopback; reach it from the server the same way as the runtime:

    python scripts/nightshift-receipt-relay.py            # 127.0.0.1:8099
    ssh -N -R 127.0.0.1:18099:127.0.0.1:8099 user@server
    python3 scripts/nightshift-forward.py 192.168.100.19 18100 18099   # on the server
    # then METERLESS_RECEIPTS_URL=http://192.168.100.19:18100 for the api container
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "ai.meterless.runtime" / "receipts.jsonl"
PATH = Path(os.environ.get("NIGHTSHIFT_RECEIPTS", DEFAULT))
PORT = int(os.environ.get("RELAY_PORT", "8099"))
ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_index: dict[str, str] = {}
_offset = 0
_lock = threading.Lock()


def refresh() -> None:
    """Index new lines since the last read (the file is append-only)."""
    global _offset
    with _lock:
        if not PATH.exists():
            return
        with PATH.open("rb") as f:
            f.seek(_offset)
            for raw in f:
                if not raw.endswith(b"\n"):
                    break  # a line still being written; read it next time
                _offset += len(raw)
                line = raw.decode("utf-8").strip()
                try:
                    rid = json.loads(line)["body"]["receipt"]["request_id"]
                except (ValueError, KeyError, TypeError):
                    continue
                _index[rid] = line


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        refresh()
        if self.path == "/healthz":
            return self._send(200, json.dumps({"receipts": len(_index)}))
        m = re.match(r"^/v1/receipts/([^/?#]+)$", self.path)
        if not m or not ID.match(m.group(1)):
            return self._send(404, '{"error":"not found"}')
        line = _index.get(m.group(1))
        return self._send(200, line) if line else self._send(404, '{"error":"no receipt"}')

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("relay %s\n" % (fmt % args))


if __name__ == "__main__":
    refresh()
    print(f"serving {len(_index)} receipts from {PATH} on 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
