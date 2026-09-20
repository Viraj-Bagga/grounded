#!/usr/bin/env python3
"""The laptop demo: the triage app against llama-server, with the guards wired in.

    # terminal 1
    llama-server -m 03-model/base/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf \
      --jinja -np 2 -ngl 0 -c 8192 --port 8080
    # -np 2: two slots. A compare assessment decodes both sides together (86 s
    # against 112 at -np 1, 06-demo/results/2026-09-19-compare-timing.txt), and
    # each assessment side is pinned to a slot so follow-ups hit the prefix
    # cache. -c 8192 keeps 4096 tokens per slot.
    # terminal 2
    python 06-demo/server.py          # then open http://127.0.0.1:8770

WHY THIS AND NOT THE SIMULATOR. Decided 2026-09-17: one completion in the iOS
simulator is 3 min 56 s in Release, against about 40 s here, and a judge visit is
about 5 minutes. The phone gets a screenshot as evidence that it runs on-device.
This is the surface that can answer inside a visit.

THE APP
  /                        a new assessment for the selected person
  /c/<id>                  an assessment: a conversation of turns, saved to disk
  /people, /people/<id>    the household, managed through a form, never through chat

THE API
  GET    /api/health                      llama-server, slots, sources
  GET    /api/people                      the household, and what each profile turns on
  POST   /api/people                      add a person
  POST   /api/people/preview              what a draft profile would turn on
  PUT    /api/people/<id>                 edit a person
  DELETE /api/people/<id>                 remove a person; their assessments stay
  GET    /api/conversations               history, newest first
  POST   /api/conversations               start an assessment for one person or two
  GET    /api/conversations/<id>          one assessment, every turn
  POST   /api/conversations/<id>/turn     one turn for one side, streamed
  GET    /api/chunk/<key>                 the real chunk text and its source
  POST   /api/transcribe                  speech to text, on this machine

VOICE IS INPUT, NOT A SHORTCUT. /api/transcribe returns text and nothing else.
It never starts an assessment. The transcript lands in the composer for the
person to read and fix before they send it, because a misheard symptom is a
wrong verdict. See voice.py.

STREAMING IS NOT DECORATION. Generation runs at 9.5 to 10 tok/s on CPU, so a
200-token answer is about 20 s and a whole first turn is 40 s or more. Forty
seconds of frozen screen reads as a crash at a desk. Tokens are streamed so the
thing is visibly working, and the guarded result is rendered only when the JSON
is complete, because a half-parsed verdict must never reach the screen.

THE SERVER NOW HOLDS STATE. Until 2026-09-19 every request stood alone. Now an
assessment lives on disk and a turn builds on the ones before it, so two
assessments can be open at once in two tabs, and a turn keeps running and is
saved even if its tab closes. See pipeline.py and store.py.
"""

import argparse
import base64
import binascii
import json
import os
import socket
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pipeline  # noqa: E402
import soap  # noqa: E402  (puts 02-pairs, 04-retrieval on the path)
import voice  # noqa: E402
from guards import is_child_profile, load_registry  # noqa: E402
from escalation import verify_grounding  # noqa: E402
from store import (SEED_PEOPLE, ConversationStore, PeopleStore,  # noqa: E402
                   clean_person, profile_text)

PORT = 8770
STATIC = HERE / "static"
# 60 s of 16 kHz mono 16-bit is 1.92 MB, and base64 adds a third on top. Every
# other request is small, so the cap is per route rather than one global limit.
MAX_BODY = 200_000
MAX_AUDIO_BODY = 4_000_000
APP_ROUTES = re.compile(r"^/(?:c/[\w-]+|people(?:/[\w-]+)?|regions)?/?$")

# The regional add-on packs, read only, for the region selector. They are NOT
# wired into retrieval (Viraj's call 2026-09-19): selecting a region changes
# what the page SAYS, never what the retriever reads. Everything here comes
# from the frozen pack directory, which is what a distributed pack carries.
REGIONAL_ROOT = Path(os.environ.get("REGIONAL_ROOT")
                     or HERE.parent / "07-distribute" / "regional")


def regions():
    """[{id, title, ...}], the packs on disk. Absent packs are not an error:
    the demo runs on the base corpus alone and says so."""
    out = []
    for f in sorted(REGIONAL_ROOT.glob("*/pack.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out

# BUILT EAGERLY AT STARTUP, NOT LAZILY ON FIRST REQUEST.
#
# Lazy init was a crash, not an inefficiency. Measured 2026-09-17: two
# concurrent first requests both entered the `is None` branch, both constructed
# a HybridRetriever, both loaded all-MiniLM-L6-v2, and **the process died**,
# leaving a loky semaphore behind and every in-flight request returning zero
# bytes. A judge double-clicking Assess would have killed the demo server.
#
# The lock below is belt and braces. The real fix is that `warm_up()` runs
# before the socket is listening, so no request can find these unset and there
# is no race to lose. It also moves the 9 s MiniLM load off the first query,
# which was showing up as a slow first answer.
_retriever = None
_registry = None
_topics = []
_indexed = 0
_init_lock = threading.Lock()


def retriever():
    global _retriever
    if _retriever is None:
        with _init_lock:
            if _retriever is None:          # re-check inside the lock
                from hybrid import HybridRetriever
                _retriever = HybridRetriever()
    return _retriever


def registry():
    global _registry
    if _registry is None:
        with _init_lock:
            if _registry is None:
                _registry = load_registry()
    return _registry


# The seeded household is demo data, and the page labels it so.
SAMPLE_IDS = {p["id"] for p in SEED_PEOPLE}
PEOPLE = PeopleStore()
CONVERSATIONS = ConversationStore()
ENGINE = pipeline.Engine(CONVERSATIONS, retriever, registry)


def warm_up():
    """Build everything before serving, so a first request cannot race. Refuses
    to start if any escalation rule's quote is not verbatim in its chunk."""
    global _topics, _indexed
    problems = verify_grounding(registry())
    if problems:
        raise SystemExit("escalation rules are not grounded:\n  " + "\n  ".join(problems))
    r = retriever()
    r.search("warm up the encoder and the index", 1, 0.5)
    # What retrieval can actually see, which is the index, not the registry:
    # the registry can run ahead of the index while new sources are frozen.
    _topics = sorted({row[0] for row in r.query("select distinct topic from chunk_meta", ())})
    _indexed = r.query("select count(*) from chunk_meta", ())[0][0]
    PEOPLE.list()                           # seeds data/people.json on first run
    return ENGINE.configure_from_server()


def describe(p):
    """A person as the page shows them: facts, whether the app assesses them,
    which rules their profile turns on, and the exact text the model reads."""
    return dict(p, child=is_child_profile(p), watching=pipeline.watching(p),
                prompt=profile_text(p), sample=p["id"] in SAMPLE_IDS)


def conversation_view(conv):
    out = dict(conv, busy=ENGINE.busy(conv["id"]))
    out["sides"] = [dict({k: v for k, v in s.items() if k != "llm"},
                         model_turns=len(s["llm"]) // 2,
                         followups_left=ENGINE.followups_left(s)) for s in conv["sides"]]
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"  {self.address_string()} {fmt % args}\n")

    def end_headers(self):
        # The page is edited while the demo runs; never serve a stale script.
        if not self.path.startswith("/fonts/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _text(self, text, filename):
        payload = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, obj, code=200):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return None

    def _route(self):
        return unquote(urlsplit(self.path).path)

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        path = self._route()
        if path == "/api/health":
            ok, detail = True, "llama-server reachable"
            try:
                with urlopen(pipeline.LLAMA + "/health", timeout=3) as r:
                    r.read()
            except Exception as e:
                ok, detail = False, f"llama-server unreachable: {e}"
            # A page opened from another machine is a SCREEN: the model runs
            # here. The page words itself from this.
            remote = not str(self.client_address[0]).startswith(("127.", "::1"))
            v_ok, v_detail = voice.available()
            return self._json({"ok": ok, "detail": detail, "remote": remote,
                               "voice": {"ok": v_ok, "detail": v_detail},
                               "slots": ENGINE.slots.n,
                               "n_ctx": ENGINE.n_ctx, "sources": _indexed,
                               "registry": len(registry()),
                               "topics": _topics,
                               "max_followups": pipeline.MAX_FOLLOWUPS})
        if path == "/api/regions":
            return self._json({"regions": regions(), "retrieval": "base corpus only"})
        if path == "/api/people":
            return self._json({"people": [describe(p) for p in PEOPLE.list()]})
        m = re.match(r"^/api/people/([\w-]+)$", path)
        if m:
            # "No profile" is not a person: it has no page and no form.
            p = None if m.group(1) == "none" else PEOPLE.get(m.group(1))
            return self._json(describe(p)) if p else self._json({"error": "no such person"}, 404)
        if path == "/api/conversations":
            return self._json({"conversations": CONVERSATIONS.summaries()})
        m = re.match(r"^/api/conversations/([\w-]+)$", path)
        if m:
            conv = CONVERSATIONS.get(m.group(1))
            return self._json(conversation_view(conv)) if conv else \
                self._json({"error": "no such assessment"}, 404)
        # The clinical export. Reads a saved assessment and nothing else: no
        # model call, no retrieval, no change to the triage path.
        m = re.match(r"^/api/conversations/([\w-]+)/soap\.txt$", path)
        if m:
            conv = CONVERSATIONS.get(m.group(1))
            if not conv:
                return self._json({"error": "no such assessment"}, 404)
            text = soap.note(conv, ENGINE.chunk_meta, soap.version_info(pipeline.LLAMA))
            return self._text(text, f"soap-{conv['id']}.txt")
        if path.startswith("/api/chunk/"):
            key = path.rsplit("/", 1)[-1]
            # Constraint 9 again, at the expander. A key that does not resolve
            # must never open a panel, even if something upstream let it through.
            if key not in registry():
                return self._json({"error": f"{key} is not in the registry"}, 404)
            return self._json(ENGINE.chunk_meta(key))
        if path.startswith("/api/"):
            return self._json({"error": "not found"}, 404)
        if APP_ROUTES.match(path):
            self.path = "/index.html"       # the app routes its own paths
        return super().do_GET()

    # --------------------------------------------------------------- POST
    def do_POST(self):
        path = self._route()
        limit = MAX_AUDIO_BODY if path == "/api/transcribe" else MAX_BODY
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            # Answer 413, do not just hang up. Closing the socket while the
            # browser is still uploading turns a readable message into a bare
            # network error on the page, so read the body off the wire first
            # and only refuse to swallow something absurd.
            if n <= limit * 2:
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(left, 65536))
                    if not chunk:
                        break
                    left -= len(chunk)
            else:
                self.send_header("Connection", "close")
            return self._json({"error": "that recording is too long to send"}, 413)
        body = self._body()
        if body is None:
            return self._json({"error": "the request body is not JSON"}, 400)

        # SPEECH TO TEXT, AND NOTHING ELSE. No model call, no retrieval, no
        # conversation touched. It returns what it heard plus an id, and the
        # page decides what to do with the words. The id is how the turn later
        # proves the symptoms were spoken: see voice.provenance.
        if path == "/api/transcribe":
            try:
                wav = base64.b64decode(body.get("audio") or "", validate=True)
            except (binascii.Error, ValueError):
                return self._json({"error": "the audio did not decode"}, 400)
            try:
                heard = voice.transcribe(wav)
            except voice.Bad as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:                      # a dead binary, a full disk
                return self._json({"error": f"transcription failed: {e}"}, 500)
            return self._json({**heard, "id": voice.remember(heard)})

        if path == "/api/people":
            person, errors = PEOPLE.create(body)
            return self._json(describe(person), 201) if person else \
                self._json({"errors": errors}, 422)
        if path == "/api/people/preview":
            # The form's live panel. Works on a draft that may not validate yet.
            draft, errors = clean_person(body)
            shown = dict(draft, age="?" if draft["age"] is None else draft["age"],
                         sex=draft["sex"] or "?")
            return self._json({"errors": errors, "child": is_child_profile(draft),
                               "watching": pipeline.watching(draft),
                               "prompt": profile_text(shown)})

        if path == "/api/conversations":
            ids = body.get("person_ids") or []
            people = [PEOPLE.get(i) for i in ids]
            if not 1 <= len(ids) <= 2 or len(set(ids)) != len(ids) or not all(people):
                return self._json({"error": "choose one person, or two different people"}, 400)
            return self._json(conversation_view(CONVERSATIONS.create(people)), 201)

        m = re.match(r"^/api/conversations/([\w-]+)/turn$", path)
        if m:
            return self._turn(m.group(1), body)
        return self._json({"error": "not found"}, 404)

    def _turn(self, cid, body):
        conv = CONVERSATIONS.get(cid)
        if not conv:
            return self._json({"error": "no such assessment"}, 404)
        si = body.get("side", 0)
        text = str(body.get("text") or "").strip()
        timeline = str(body.get("timeline") or "").strip()
        if not isinstance(si, int) or not 0 <= si < len(conv["sides"]):
            return self._json({"error": "no such side"}, 400)
        if not text:
            return self._json({"error": "no symptoms given"}, 400)
        if len(text) > 2000 or len(timeline) > 2000:
            return self._json({"error": "keep it under 2,000 characters"}, 400)
        if si in ENGINE.busy(cid):
            return self._json({"error": "this answer is still being written"}, 409)
        # Whether these symptoms were spoken, and whether the person corrected
        # what was heard. Decided HERE, by comparing the text that arrived with
        # the text this machine produced, rather than reported by the page: the
        # SOAP note states it to a clinician, so it has to be a fact. None when
        # the turn was typed, or when the transcript has aged out of _RECENT.
        heard = voice.provenance(str(body.get("heard_id") or ""), text)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        gone = {"yes": False}

        def send(event, payload):
            # A closed tab must not stop the turn: it finishes and is saved, and
            # the assessment shows it when reopened.
            if gone["yes"]:
                return
            try:
                self.wfile.write(f"data: {json.dumps({'event': event, **payload})}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                gone["yes"] = True

        try:
            ENGINE.run_turn(cid, si, text, timeline, bool(body.get("confirmed_subject")),
                            send, heard=heard)
        except pipeline.Busy:
            send("error", {"message": "This answer is still being written."})
        except Exception as e:  # never leave the page hanging on a dead server
            send("error", {"message": str(e)})

    # ---------------------------------------------------------- PUT, DELETE
    def do_PUT(self):
        m = re.match(r"^/api/people/([\w-]+)$", self._route())
        body = self._body()
        if not m or body is None:
            return self._json({"error": "not found"}, 404)
        person, errors = PEOPLE.update(m.group(1), body)
        return self._json(describe(person)) if person else self._json({"errors": errors}, 422)

    def do_DELETE(self):
        m = re.match(r"^/api/people/([\w-]+)$", self._route())
        if not m:
            return self._json({"error": "not found"}, 404)
        return self._json({"deleted": m.group(1)}) if PEOPLE.delete(m.group(1)) else \
            self._json({"error": "no such person"}, 404)


def lan_addresses():
    """The IPv4 addresses this machine answers on, best effort and offline.

    The UDP socket sends nothing: connect() on a datagram socket only picks
    the route, which is what names the interface a phone on the same wifi
    would reach. It works with no internet as long as there is a route.
    """
    found = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))          # TEST-NET-1, never routed anywhere
        found.append(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    return [a for i, a in enumerate(found)
            if not a.startswith("127.") and a not in found[:i]]


def main(argv=None):
    ap = argparse.ArgumentParser(description="The demo server for 06-demo.")
    ap.add_argument("--lan", action="store_true",
                    help="bind 0.0.0.0 so a phone on the same wifi can open the page. "
                         "The default is loopback only.")
    ap.add_argument("--host", default=None, help="bind this address instead")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)
    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")

    print("warming up: registry, index, encoder, people ...")
    slots, n_ctx = warm_up()
    print(f"demo on http://127.0.0.1:{args.port}")
    if host not in ("127.0.0.1", "localhost"):
        addrs = lan_addresses()
        for a in addrs:
            print(f"  on this wifi: http://{a}:{args.port}")
        if not addrs:
            print("  on this wifi: no non-loopback address found, so nothing to print")
        # Said plainly because it is a real exposure, and because the phone is
        # only ever a screen: the model runs here, on this laptop.
        print(f"  bound to {host}: anyone on this network can open the page, read every")
        print("    assessment and add or delete people. There is no password. The model")
        print("    still runs on this laptop; a phone that opens the page is a screen.")
    print(f"  llama-server expected at {pipeline.LLAMA}, {slots} slots of {n_ctx} tokens")
    print(f"  retrieval: top-{pipeline.TOP_K}, blend alpha={pipeline.ALPHA}")
    print(f"  registry: {len(registry())} citation keys, topics {', '.join(_topics)}")
    # flush: stdout is block-buffered when this is piped to a log, and the
    # address a phone needs is the one line you cannot afford to lose.
    print(f"  data: {CONVERSATIONS.root.parent}", flush=True)
    ThreadingHTTPServer((host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
