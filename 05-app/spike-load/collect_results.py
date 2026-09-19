#!/usr/bin/env python3
"""Receive spike results from the simulator app and write them to a file.

    python 05-app/spike-load/collect_results.py            # listens on 8123
    python 05-app/spike-load/collect_results.py --port 9000

WHY A LISTENER AND NOT A FILE WRITE. The app has no filesystem API. React Native
core exposes no documents path, llama.rn only strips a `file://` prefix, and
`xcrun simctl install` rotates the Data container UUID on every install, so even
a hardcoded path goes stale. Measured 2026-09-17: ADEC8507 -> 304E8CF4 ->
E2789BED across three installs.

The simulator shares host networking, so the app POSTs its record here and the
host writes the file. That survives container rotation and works in Release,
where there is no Metro and RN 0.81 sends console.log to React Native DevTools
rather than anywhere a script can read.

This exists because the `dropped_*` fields from the first Release run rendered
below the fold and were lost: a simulator screenshot cannot be scrolled from the
host. Results must not live only on a screen.
"""
import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

OUT = Path(__file__).resolve().parent / "results"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        # Microseconds, not seconds: two results in the same second silently
        # overwrote each other. Found during the 2026-09-17 single-request-
        # assumption scan, same class of bug as the others.
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S_%fZ")
        path = OUT / f"{stamp}-app-result.json"
        try:
            payload = json.loads(body)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except json.JSONDecodeError:
            path = path.with_suffix(".txt")
            path.write_bytes(body)
        print(f"wrote {path}  ({len(body)} bytes)")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass    # the write line above is the only output worth having


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8123)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    print(f"listening on 127.0.0.1:{args.port}, writing to {OUT}")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
