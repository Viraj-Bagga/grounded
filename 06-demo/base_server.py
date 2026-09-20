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
and no route that changes an assessment. Mark reviewed is the one write, and
it records that a person LOOKED: it touches no verdict, no guard and no SOAP
note, and it never syncs back to the device. Base reads what the field device
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
from datetime import datetime, timezone
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


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


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
            # synced_at is BASE's clock, not the device's: it is when this
            # arrived here, which is the only thing base can vouch for. A
            # review already recorded survives a resend, because it is a fact
            # about this device and not about the bundle.
            b["synced_at"] = now_iso()
            if old and old.get("reviewed"):
                b["reviewed"] = old["reviewed"]
            _write(path, b)
        devices = _read(DEVICES, {})
        # The latest caseload snapshot wins: base wants what is outstanding
        # NOW, not what was outstanding when an older assessment was made.
        devices[dev] = {"id": dev, "label": b["device"].get("label") or dev,
                        "last_seen": b.get("created"),
                        "caseload": b.get("caseload") or {}}
        _write(DEVICES, devices)
    return b, already


def review(aid, by=None):
    """Record that a person looked at this. It changes NOTHING about the
    assessment: not the verdict, not the guards, not the SOAP note. It is a
    fact about base, which is why it lives here and never syncs back."""
    for f in RECEIVED.glob(f"*/{aid}.json"):
        with _lock:
            b = _read(f, None)
            if not b:
                return None
            if not b.get("reviewed"):
                b["reviewed"] = {"at": now_iso(), "by": by or None}
            _write(f, b)
            return b
    return None


def received():
    out = []
    for f in sorted(RECEIVED.glob("*/*.json")):
        b = _read(f, None)
        if b and isinstance(b.get("assessment"), dict):
            out.append(b)
    out.sort(key=lambda b: (b["assessment"].get("updated") or ""), reverse=True)
    return out


def _removed_in(ev):
    return sum(len(v) if isinstance(v, list) else (1 if v else 0)
               for v in (ev.get("dropped") or {}).values())


# Which status wins when the same rule fires on more than one turn. A rule that
# RAISED a verdict once is the fact worth surfacing, even if it only supported
# a later one.
_STATUS_RANK = {"raised": 0, "flag": 1, "at_least": 2, "supports": 3, "noted": 4}


def row(b):
    """One assessment as the dashboard lists it.

    A ROW SUMMARISES THE WHOLE ASSESSMENT, NOT ITS LAST TURN. Until the
    rehearsal on 2026-09-20 this read only the last shown turn, so a follow-up
    erased the first turn's escalation and guard removals from the register:
    Aunt Sue's row showed "—" in Attention although her first turn had been
    raised to red by R4 with 5 removals, and because the outstanding rule counts
    removals, an assessment flagged only by a guard removal stopped being
    outstanding as soon as a follow-up landed. The data was always here; the
    summary was throwing it away.

    So: rules are the union across every turn, removals are summed across every
    turn, ungrounded is true if ANY turn was, and citations are the union.

    The MARK is still the last shown verdict, because that is what the
    assessment currently says. Everything else accumulates.

    Nothing here is recomputed. It all comes out of what the field device saved.
    """
    a = b["assessment"]
    sides = []
    for s in a.get("sides", []):
        turns = s.get("turns", [])
        shown = [t for t in turns if t.get("kind") in ("result", "refused", "error")]
        removed = 0
        ungrounded = False
        cites, best = [], {}
        for t in shown:
            ev = t.get("event") or {}
            removed += _removed_in(ev)
            ungrounded = ungrounded or bool(ev.get("ungrounded"))
            for k in ((ev.get("result") or {}).get("citations") or []):
                if k not in cites:
                    cites.append(k)
            for f in ((ev.get("escalation") or {}).get("fired") or []):
                prev = best.get(f["rule"])
                if prev is None or _STATUS_RANK.get(f["status"], 9) < _STATUS_RANK.get(prev, 9):
                    best[f["rule"]] = f["status"]
        # Every verdict this assessment has shown, so the outstanding rule can
        # judge the whole thing rather than only where it ended up.
        every = [sync.side_state({"turns": [t]}).get("state") for t in shown]
        sides.append({
            "label": (s.get("profile") or {}).get("label") or "?",
            "state": sync.side_state(s).get("state"),
            "states": [x for x in every if x],
            "turns": len(shown),
            "ungrounded": ungrounded,
            "citations": cites,
            "removed": removed,
            "rules": [f"{r}:{st}" for r, st in best.items()],
            "raised": any(st == "raised" for st in best.values()),
            "said": (turns[0].get("text") if turns else "") or "",
        })
    # OUTSTANDING, per BASE-DESIGN.md section 2: not yet reviewed AND any of
    # red, yellow, refused, or a guard removed something at any urgency. A
    # green with a clean run is not outstanding. One rule, so the count is
    # never arguable.
    #
    # Judged across EVERY turn, not just the last. An assessment that was red
    # and is now green still needs a person to have looked at it, and that is
    # the safe direction for the one screen a supervisor triages from.
    states = [x for s in sides for x in (s["states"] or [s["state"]])]
    needs = (any(x in ("red", "yellow") for x in states)
             or any(x in ("refused", "child", "error") for x in states)
             or any(s["removed"] for s in sides))
    return {"id": a["id"], "created": a.get("created"), "updated": a.get("updated"),
            "mode": a.get("mode"), "title": a.get("title") or "",
            "device": b["device"]["id"], "device_label": b["device"].get("label") or "",
            "worker": (b["device"].get("worker") or None),
            # Bundles stored before synced_at existed fall back to the
            # device's own created time, which is close enough to be useful
            # and is labelled as the sync either way.
            "synced_at": b.get("synced_at") or b.get("created"),
            "reviewed": b.get("reviewed"),
            "outstanding": bool(needs and not b.get("reviewed")),
            "sha256": b["sha256"], "sides": sides}


def dashboard():
    """What a supervisor wants: how many today, how many red, what is still
    outstanding in the field, and which device each case came from."""
    rows = [row(b) for b in received()]
    devices = _read(DEVICES, {})
    today = sync.now_iso()[:10]
    today_rows = [r for r in rows if (r.get("updated") or "")[:10] == today]

    def count(rs, state):
        """ROWS containing that state, not sides.

        This counted sides, so a compare assessment with two red sides made
        counts.red say 39 while the page's own tally said 38: the same word
        meaning two things depending on where you read it. A supervisor counts
        cases, because a case is what they open, so a row is the unit. A
        compare row with a green beside a yellow is counted in both, which is
        the honest answer to "how many have a yellow in them".
        """
        return sum(1 for r in rs if any(x["state"] == state for x in r["sides"]))

    waiting_out_there = sum((d.get("caseload") or {}).get("waiting", 0) for d in devices.values())
    last_sync = max([r.get("synced_at") or "" for r in rows] or [""])
    return {
        "counts": {
            "assessments": len(rows),
            "today": len(today_rows),
            "red": count(rows, "red"),
            "red_today": count(today_rows, "red"),
            "yellow": count(rows, "yellow"),
            "green": count(rows, "green"),
            "refused": count(rows, "refused") + count(rows, "child"),
            "needs_review": sum(1 for r in rows if r["outstanding"]),
            "needs_review_today": sum(1 for r in today_rows if r["outstanding"]),
            "waiting_in_field": waiting_out_there,
            "devices": len(devices),
            "last_sync": last_sync or None,
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
        m = re.match(r"^/api/assessments/([\w-]+)/review$", self._route())
        if m:
            n = int(self.headers.get("Content-Length") or 0)
            body = {}
            if 0 < n <= MAX_BODY:
                try:
                    body = json.loads(self.rfile.read(n).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    body = {}
            b = review(m.group(1), (body or {}).get("by"))
            return self._json(dashboard()) if b else \
                self._json({"error": "not received here"}, 404)
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
