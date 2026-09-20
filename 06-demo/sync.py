"""One-way sync: finished assessments leave the field device for base.

THE SHAPE OF THE PROBLEM. A health worker triages in a village with no signal.
The assessments pile up on the device. Later they walk back into range and the
caseload has to arrive at base complete: every citation, every guard action,
every rule that fired. Nothing is edited at base and nothing is ever pushed
back down, so there is no conflict to resolve and none is implemented.

WHY IT IS ONE WAY, AND WHY THAT IS NOT LAZINESS. The assessment is the
clinical record of what a worker saw and what the app told them. A base that
can rewrite it is a base that can rewrite history, and a field device that
accepts edits has to merge them into a conversation the model has cached. One
direction removes both problems. If base needs to change something, that is a
conversation between people, not a write.

INTEGRITY IS THE DISTRIBUTION NODE'S, NOT A SECOND INVENTION. 07-distribute
already settled how this project moves bytes it cares about: a manifest that
names a sha256 for the content, the receiver recomputing it from what actually
arrived, and verify-before-accept. `packlib.sha256_bytes` and the canonical
JSON below are that same approach pointed the other way. A bundle whose digest
does not match what arrived is REFUSED, not stored and flagged.

WHAT A BUNDLE CARRIES.
  assessment   the saved conversation file, verbatim, not a summary. That is
               what makes the citations and the guard removals survive the
               trip: base renders what the field device rendered, from the
               same bytes, without needing the registry or the guards.
  caseload     a snapshot of the device's waiting and seen counts, so base can
               answer "how many are still outstanding out there" without the
               field device having to send a second kind of message.
  device       a stable id generated once per device, and a human label.

IDEMPOTENCE. The digest is the identity. Sending the same assessment twice is
a no-op at base, which is what makes the outbox safe to retry on a flaky link.
"""

import hashlib
import json
import secrets
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path

from store import DATA, _write_json, now_iso, side_state

BUNDLE_VERSION = "1"
DEFAULT_BASE = "http://127.0.0.1:8781"
TIMEOUT = 4.0


def canonical(obj) -> bytes:
    """The exact bytes a digest is taken over, on both sides.

    Sorted keys and no insignificant whitespace, so the same content hashes the
    same however either side happened to build the dict. This is the only
    serialisation allowed to feed a digest; ordinary writes elsewhere stay
    human-readable.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def digest_of(assessment) -> str:
    return sha256_bytes(canonical(assessment))


def verdicts(conv):
    """Each side's shown outcome, the same call the history rows make, so base
    counts what the field device displayed rather than re-deriving it."""
    return [side_state(s).get("state") for s in conv.get("sides", [])]


class SyncState:
    """data/sync.json: this device's identity, where base is, and what has
    already been accepted there."""

    def __init__(self, path=DATA / "sync.json"):
        self.path = path
        self.lock = threading.Lock()
        self._ensure()

    def _read(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _ensure(self):
        with self.lock:
            d = self._read()
            changed = False
            if not d.get("device_id"):
                # Stable for the life of the device's data directory. Base
                # groups by this, so it must not change on a restart.
                d["device_id"] = "dev-" + secrets.token_hex(4)
                changed = True
            if not d.get("device_label"):
                d["device_label"] = socket.gethostname().split(".")[0] or "field device"
                changed = True
            if "worker" not in d:
                # Who is carrying the handset. Optional, and NULL RENDERS AS
                # NOTHING at base rather than "Unknown": an unnamed worker is
                # missing information, not a person called Unknown.
                d["worker"] = ""
                changed = True
            if not d.get("base_url"):
                d["base_url"] = DEFAULT_BASE
                changed = True
            if "sent" not in d:
                d["sent"] = {}
                changed = True
            if changed:
                _write_json(self.path, d)
            self._d = d

    def get(self):
        with self.lock:
            return dict(self._read() or self._d)

    def set_base(self, url, worker=None):
        url = str(url or "").strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            return None, "Base needs an http:// or https:// address."
        worker = " ".join(str(worker or "").split())[:40]
        with self.lock:
            d = self._read()
            d["base_url"] = url
            d["worker"] = worker
            _write_json(self.path, d)
            return url, None

    def mark_sent(self, cid, digest):
        with self.lock:
            d = self._read()
            d.setdefault("sent", {})[cid] = {"at": now_iso(), "digest": digest}
            _write_json(self.path, d)

    def sent(self):
        return (self.get().get("sent") or {})


def bundle_for(conv, state, caseload_counts):
    """The envelope for one assessment. `sha256` covers the assessment alone,
    so base can verify the clinical content independently of anything the
    envelope says about the device."""
    d = state.get()
    return {
        "bundle": BUNDLE_VERSION,
        "created": now_iso(),
        "device": {"id": d["device_id"], "label": d["device_label"],
                   "worker": d.get("worker") or ""},
        "caseload": dict(caseload_counts or {}),
        "assessment": conv,
        "sha256": digest_of(conv),
    }


def bundle_problems(b) -> list:
    """Everything wrong with a bundle, from the receiver's point of view.

    Shape first, then the digest, so a mangled bundle gets a useful message
    rather than a hash mismatch. This runs at BASE, before anything is stored.
    """
    errs = []
    if not isinstance(b, dict):
        return ["the bundle is not an object"]
    if b.get("bundle") != BUNDLE_VERSION:
        errs.append(f"bundle version {b.get('bundle')!r}, expected {BUNDLE_VERSION!r}")
    dev = b.get("device")
    if not isinstance(dev, dict) or not dev.get("id"):
        errs.append("the bundle names no device")
    a = b.get("assessment")
    if not isinstance(a, dict) or not a.get("id") or not isinstance(a.get("sides"), list):
        errs.append("the bundle carries no assessment")
    claimed = b.get("sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        errs.append("the bundle carries no sha256")
    if errs:
        return errs
    actual = digest_of(a)
    if actual != claimed:
        errs.append(f"sha256 does not match what arrived: bundle says {claimed[:12]}…, "
                    f"the assessment hashes to {actual[:12]}…")
    return errs


def pending(conversations, state):
    """Finished assessments this device has not had accepted at base yet.

    An assessment with no turn that reached the model is not sent: it is an
    empty shell the worker started and abandoned, and base does not want it.
    """
    out = []
    already = state.sent()
    for conv in conversations:
        if not any(t.get("reached_model") for s in conv.get("sides", []) for t in s.get("turns", [])):
            continue
        d = digest_of(conv)
        was = already.get(conv["id"])
        if was and was.get("digest") == d:
            continue          # accepted, and unchanged since
        out.append((conv, d))
    return out


def post(base_url, bundle, timeout=TIMEOUT):
    """POST one bundle. Returns (ok, detail). Never raises: an unreachable
    base is the normal case in the field, not an error to propagate."""
    url = base_url.rstrip("/") + "/api/receive"
    body = canonical(bundle)
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode("utf-8") or "{}")
            return True, out
    except urllib.error.HTTPError as e:
        try:
            out = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            out = {}
        return False, {"error": out.get("error") or f"base refused it: HTTP {e.code}",
                       "problems": out.get("problems") or []}
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        return False, {"error": f"base is not reachable: {e.reason if hasattr(e, 'reason') else e}",
                       "offline": True}


def flush(conversations, state, caseload_counts, emit=None):
    """Send everything pending. Returns a summary dict.

    Stops at the first sign base is unreachable, because the next twenty will
    fail the same way and a worker watching the screen should see one honest
    "not reachable" rather than twenty.
    """
    emit = emit or (lambda *_: None)
    todo = pending(conversations, state)
    sent, failed, offline = [], [], False
    base = state.get()["base_url"]
    emit("start", {"pending": len(todo), "base": base})
    for conv, d in todo:
        b = bundle_for(conv, state, caseload_counts)
        ok, out = post(base, b)
        if ok:
            state.mark_sent(conv["id"], d)
            sent.append(conv["id"])
            emit("sent", {"id": conv["id"], "sha256": d,
                          "already": bool(out.get("already"))})
        elif out.get("offline"):
            offline = True
            emit("offline", {"error": out.get("error")})
            break
        else:
            failed.append({"id": conv["id"], "error": out.get("error"),
                           "problems": out.get("problems") or []})
            emit("refused", failed[-1])
    result = {"sent": sent, "failed": failed, "offline": offline,
              "pending_after": len(pending(conversations, state))}
    emit("done", result)
    return result
