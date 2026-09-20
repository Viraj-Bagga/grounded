#!/usr/bin/env python3
"""BASE: where the caseload lands when a field device comes back into range.

    python 06-demo/base_server.py              # then open http://127.0.0.1:8781
    python 06-demo/base_server.py --lan        # so a field device on the wifi can reach it

THIS IS A SEPARATE SURFACE AND THAT IS THE POINT. It runs in its own process,
on its own port, out of its own data directory, and it imports nothing from
the triage path: no llama-server, no retriever, no encoder, no guards, no
registry. It cannot slow the field app down and it cannot break it. If base is
broken, the field app still triages, which is the only thing that must never
stop working.

IT ALSO MEANS BASE CAN RUN ON A PHONE. There is no model here, nothing to
load, and the whole process is a JSON store and a page.

RECEIVE IS VERIFY-BEFORE-ACCEPT. A bundle is checked for shape and then its
assessment is re-hashed from the bytes that actually arrived. A mismatch is
REFUSED with the two digests, not stored with a warning. That is the
distribution node's rule pointed the other way: see sync.py.

NOTHING IS EDITED HERE AND NOTHING IS SENT BACK. There is no PUT, no DELETE
and no route that changes an assessment. Base reads what the field device
rendered, from the same bytes, which is why the citations and the guard
removals survive the trip without base owning a corpus.
"""

import argparse
import json
import os
import re
import socket
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sync  # noqa: E402

PORT = 8781
STATIC = HERE / "base-static"
BASE_DATA = Path(os.environ.get("BASE_DATA") or HERE / "base-data")
RECEIVED = BASE_DATA / "received"
DEVICES = BASE_DATA / "devices.json"
MAX_BODY = 2_000_000          # one assessment with its turns, generously
ID_RE = re.compile(r"^[\w-]{1,64}$")

_lock = threading.Lock()


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def store_bundle(b):
    """Write a verified bundle. Returns (record, already_had_it).

    Keyed by device and assessment id, so the same assessment arriving twice
    overwrites its own file rather than making a second row. The digest is the
    identity: an identical resend is reported as `already` and changes nothing.
    """
    dev = b["device"]["id"]
    aid = b["assessment"]["id"]
    if not ID_RE.match(dev) or not ID_RE.match(aid):
        return None, False
    path = RECEIVED / dev / f"{aid}.json"
    with _lock:
        old = _read(path, None)
        already = bool(old and old.get("sha256") == b["sha256"])
        if not already:
            _write(path, b)
        devices = _read(DEVICES, {})
        # The latest caseload snapshot wins: base wants what is outstanding
        # NOW, not what was outstanding when an older assessment was made.
        devices[dev] = {"id": dev, "label": b["device"].get("label") or dev,
                        "last_seen": b.get("created"),
                        "caseload": b.get("caseload") or {}}
        _write(DEVICES, devices)
    return b, already


def received():
    out = []
    for f in sorted(RECEIVED.glob("*/*.json")):
        b = _read(f, None)
        if b and isinstance(b.get("assessment"), dict):
            out.append(b)
    out.sort(key=lambda b: (b["assessment"].get("updated") or ""), reverse=True)
    return out


def row(b):
    """One assessment as the dashboard lists it. Everything here comes out of
    the assessment the field device saved; nothing is recomputed."""
    a = b["assessment"]
    sides = []
    for s in a.get("sides", []):
        turns = s.get("turns", [])
        last = next((t for t in reversed(turns) if t.get("kind") in ("result", "refused", "error")), None)
        ev = (last or {}).get("event") or {}
        res = ev.get("result") or {}
        dropped = ev.get("dropped") or {}
        removed = sum(len(v) if isinstance(v, list) else (1 if v else 0)
                      for v in dropped.values())
        esc = ev.get("escalation") or {}
        sides.append({
            "label": (s.get("profile") or {}).get("label") or "?",
            "state": sync.side_state(s).get("state"),
            "ungrounded": bool(ev.get("ungrounded")),
            "citations": res.get("citations") or [],
            "removed": removed,
            "rules": [f"{f['rule']}:{f['status']}" for f in (esc.get("fired") or [])],
            "raised": bool(esc.get("changed")),
            "said": (turns[0].get("text") if turns else "") or "",
        })
    return {"id": a["id"], "created": a.get("created"), "updated": a.get("updated"),
            "mode": a.get("mode"), "title": a.get("title") or "",
            "device": b["device"]["id"], "device_label": b["device"].get("label") or "",
            "sha256": b["sha256"], "sides": sides}


def dashboard():
    """What a supervisor wants: how many today, how many red, what is still
    outstanding in the field, and which device each case came from."""
    rows = [row(b) for b in received()]
    devices = _read(DEVICES, {})
    today = sync.now_iso()[:10]
    today_rows = [r for r in rows if (r.get("updated") or "")[:10] == today]

    def count(rs, state):
        return sum(1 for r in rs for s in r["sides"] if s["state"] == state)

    outstanding = sum((d.get("caseload") or {}).get("waiting", 0) for d in devices.values())
    return {
        "counts": {
            "assessments": len(rows),
            "today": len(today_rows),
            "red": count(rows, "red"),
            "red_today": count(today_rows, "red"),
            "yellow": count(rows, "yellow"),
            "green": count(rows, "green"),
            "refused": count(rows, "refused") + count(rows, "child"),
            "outstanding": outstanding,
            "devices": len(devices),
        },
        "devices": sorted(devices.values(), key=lambda d: d.get("last_seen") or "", reverse=True),
        "assessments": rows,
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.client_address[0], fmt % args))

    def _route(self):
        return urlsplit(self.path).path.rstrip("/") or "/"

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self._route()
        if path == "/api/health":
            return self._json({"ok": True, "role": "base",
                               "received": len(received()),
                               "data": str(BASE_DATA)})
        if path == "/api/dashboard":
            return self._json(dashboard())
        m = re.match(r"^/api/assessments/([\w-]+)$", path)
        if m:
            for b in received():
                if b["assessment"]["id"] == m.group(1):
                    return self._json(b)
            return self._json({"error": "not received here"}, 404)
        if path.startswith("/api/"):
            return self._json({"error": "not found"}, 404)
        if path == "/" or re.match(r"^/a/[\w-]+$", path):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self._route() != "/api/receive":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._json({"error": "that bundle is too large"}, 413)
        try:
            b = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._json({"error": "the bundle is not JSON"}, 400)
        # VERIFY BEFORE ACCEPT. Nothing is written until the assessment
        # re-hashes to what the bundle claims.
        problems = sync.bundle_problems(b)
        if problems:
            return self._json({"error": "the bundle was refused", "problems": problems}, 422)
        rec, already = store_bundle(b)
        if rec is None:
            return self._json({"error": "the bundle names an unusable id"}, 422)
        return self._json({"ok": True, "already": already,
                           "id": b["assessment"]["id"], "sha256": b["sha256"]})


def lan_addresses():
    found = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        found.append(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()
    return [a for a in found if not a.startswith("127.")]


def main():
    ap = argparse.ArgumentParser(description="Base: where field assessments land.")
    ap.add_argument("--lan", action="store_true",
                    help="bind every interface so a field device on this wifi can reach it")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")
    RECEIVED.mkdir(parents=True, exist_ok=True)
    d = dashboard()
    print(f"base on http://127.0.0.1:{args.port}")
    if args.lan:
        for a in lan_addresses():
            print(f"  field devices point at: http://{a}:{args.port}")
        print("  ANYONE ON THIS NETWORK CAN READ EVERY ASSESSMENT AND POST NEW ONES.")
        print("  There is no password. Do not use it on a network you do not trust.")
    print(f"  data: {BASE_DATA}")
    print(f"  holding {d['counts']['assessments']} assessments from {d['counts']['devices']} device(s)")
    print("  no model, no retrieval, no corpus: base only stores and shows what arrives")
    ThreadingHTTPServer((host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
