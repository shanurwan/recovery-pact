#!/usr/bin/env python3
"""Attack 9, live: a hostile receipt relay that forges every receipt it serves.

Sits where RecoveryPact fetches Nightshift receipts (METERLESS_RECEIPTS_URL). It fetches the real
receipt from the real relay and rewrites one field before handing it over, the way an attacker
who controls the receipt path would launder an answer:

    model   the winning model becomes Nemotron Ultra (claim a bigger, trusted model answered)
    tokens  the output token count is changed (vouch for a different answer)

Nothing is re-signed: the attacker does not hold Nightshift's key. Standard library only.

    python scripts/forging-relay.py <listen_host> <listen_port> <real_relay_url> [model|tokens]
"""

from __future__ import annotations

import json
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT, REAL = sys.argv[1], int(sys.argv[2]), sys.argv[3].rstrip("/")
MODE = sys.argv[4] if len(sys.argv) > 4 else "model"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        try:
            with urllib.request.urlopen(REAL + self.path, timeout=10) as r:
                env = json.loads(r.read())
        except Exception:  # noqa: BLE001  pass the real relay's miss through
            self.send_response(404)
            self.end_headers()
            return
        rec = env.get("body", {}).get("receipt", {})
        if MODE == "tokens":
            rec.setdefault("usage", {})["output_tokens"] = (rec.get("usage", {}).get("output_tokens") or 0) + 128
        else:
            rec.setdefault("winning_route", {})["model"] = "nvidia/nemotron-3-ultra-550b-a55b"
        data = json.dumps(env).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # one line per forged receipt
        sys.stderr.write("forged %s (%s)\n" % (self.path.rsplit("/", 1)[-1], MODE))


ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
