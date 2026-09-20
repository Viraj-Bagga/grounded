#!/usr/bin/env python3
"""Region packs: what the distribution node offers, and what is installed here.

THE DOWNLOAD IS THE POINT. Until now "Use this region" was instant and nothing
showed, so the distribution node existed only in a terminal transcript. A pack
now arrives over HTTP from the node, every file is hashed from disk against the
manifest, and the page shows it happening and keeps the evidence afterwards.

THE VERIFICATION IS NOT REIMPLEMENTED HERE. `install` calls
07-distribute/client.py's own `cmd_pull`, in process, with its stdout captured
line by line. That is the reference client running exactly as it ships: index,
manifest, per-file download, hash FROM DISK, recompute pack_sha256 from the
files, write manifest.json last. Nothing in this file decides whether a pack is
good. If the client raises Integrity, nothing is installed and the page says so.

INSTALLED MEANS manifest.json EXISTS. That is the client's definition and it is
the only one. It is written last, after every file has verified, so its presence
is the proof. This module never writes it.

RETRIEVAL IS UNCHANGED BY ANY OF THIS. Installing a pack puts files on disk and
changes what the page says about emergency numbers. The model still reads the
base corpus alone. Viraj's call 2026-09-19; rewiring retrieval days before
judging would put the scope floor and the refusal wording at risk.
"""

import contextlib
import io
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DISTRIBUTE = ROOT / "07-distribute"
sys.path.insert(0, str(DISTRIBUTE))

NODE = os.environ.get("PACK_NODE", "http://127.0.0.1:8790").rstrip("/")
# Starts EMPTY, and is gitignored with the rest of 06-demo/data. A pack that is
# in 07-distribute/packs is on the NODE, not on this device: the whole demo is
# that the two are different places.
INSTALL_ROOT = Path(os.environ.get("PACK_INSTALL_ROOT") or HERE / "data" / "packs")

# The page calls it "india"; the node calls it "regional-india". One convention,
# in one place, rather than sprinkled through the server.
def node_id(region_id):
    return f"regional-{region_id}"


REGION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
SHA_LINE = re.compile(r"^ {4}sha256 ([0-9a-f]{64})$")

# One install at a time. cmd_pull writes to a shared stdout, and two pulls of
# the same pack would race on the same directory.
_lock = threading.Lock()


class Refused(Exception):
    """The request is wrong. The message reaches the page."""


# ------------------------------------------------------------------ the node

def index(timeout=2.5):
    """The node's catalogue, or None if it is not answering."""
    try:
        with urllib.request.urlopen(NODE + "/packs", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def offered(idx=None):
    """{region_id: entry} for the regional packs the node is serving."""
    idx = index() if idx is None else idx
    out = {}
    for p in (idx or {}).get("packs", []):
        pid = str(p.get("id") or "")
        if pid.startswith("regional-"):
            out[pid[len("regional-"):]] = p
    return out


def manifest_of(entry, timeout=2.5):
    """The manifest for a node index entry, or None. Used for the file list and
    the byte count the button shows; the client fetches its own copy again and
    is the one that trusts it."""
    url = str(entry.get("manifest_url") or "")
    if not url:
        return None
    try:
        with urllib.request.urlopen(NODE + "/" + url.lstrip("/"), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


# --------------------------------------------------------------- this device

def installed(region_id):
    """The installed manifest for a region, or None. Newest version wins."""
    base = INSTALL_ROOT / node_id(region_id)
    if not base.is_dir():
        return None
    for d in sorted(base.iterdir(), reverse=True):
        f = d / "manifest.json"
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return None


def state(region_ids):
    """What the page needs per region: installed, and what the node offers.

    Never raises. With the node down every region reports node_ok False and
    whatever is already installed, because an installed pack does not stop
    working when the node goes away. That is the point of a pack.
    """
    idx = index()
    avail = offered(idx)
    out = {"node": NODE, "node_ok": idx is not None, "regions": {}}
    for rid in region_ids:
        inst = installed(rid)
        entry = avail.get(rid)
        man = manifest_of(entry) if entry else None
        out["regions"][rid] = {
            "installed": bool(inst),
            "installed_version": (inst or {}).get("version"),
            "installed_files": len((inst or {}).get("files") or []),
            "installed_size": (inst or {}).get("size"),
            "installed_sha256": (inst or {}).get("pack_sha256"),
            "offered": bool(entry),
            "version": (entry or {}).get("version"),
            "size": (man or {}).get("size"),
            "files": len((man or {}).get("files") or []),
        }
    return out


# ------------------------------------------------------------------- install

class _Sink(io.TextIOBase):
    """Captures cmd_pull's stdout a line at a time and hands each line on.

    RE-ENTRANCY IS NOT OPTIONAL HERE. Anything a handler writes while it is
    being called is NOT the client's output, and feeding it back in is an
    infinite recursion: a handler that prints would hang the server. Measured
    the first time this ran. Handler output goes to the real stdout instead of
    being swallowed, so a caller that logs still logs.
    """

    def __init__(self, on_line, passthrough=None):
        self.on_line = on_line
        self.passthrough = passthrough
        self.buf = ""
        self.busy = False

    def write(self, s):
        if self.busy:
            if self.passthrough:
                self.passthrough.write(s)
            return len(s)
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self._dispatch(line)
        return len(s)

    def _dispatch(self, line):
        self.busy = True
        try:
            self.on_line(line)
        finally:
            self.busy = False

    def flush(self):
        if self.buf and not self.busy:
            line, self.buf = self.buf, ""
            self._dispatch(line)


def install(region_id, emit):
    """Pull a pack from the node and verify it. Emits (event, payload).

    Events: start, file, verified, done, error. Every one also gets `line` for
    the client's own words, because the raw transcript is the evidence and a
    parser that drifts should never be able to hide it.
    """
    if not REGION_ID.match(region_id or ""):
        raise Refused("that is not a region id")
    nid = node_id(region_id)

    if installed(region_id):
        return emit("done", {"already": True,
                             "message": "That pack is already installed."})

    idx = index()
    if idx is None:
        raise Refused(f"the distribution node at {NODE} is not answering. Start it "
                      f"with: python 07-distribute/server.py")
    entry = offered(idx).get(region_id)
    if not entry:
        raise Refused(f"{nid} is not on {NODE}")
    man = manifest_of(entry)
    if not man:
        raise Refused(f"could not read the manifest for {nid} from {NODE}")

    # Known paths and sizes up front, so the progress is matched against the
    # manifest rather than guessed out of the client's prose.
    sizes = {f["path"]: f["size"] for f in man["files"]}
    total = int(man.get("size") or sum(sizes.values()))
    emit("start", {"id": nid, "version": man["version"], "node": NODE,
                   "files": len(sizes), "size": total,
                   "license": (man.get("license") or {}).get("name"),
                   "pack_sha256": man.get("pack_sha256")})

    progress = {"done": 0, "path": None}

    def on_line(line):
        emit("line", {"text": line})
        stripped = line.strip()
        # A file begins: the client prints "  <path>  <human size>".
        if line.startswith("  "):
            head = line[2:].split("  ")[0]
            if head in sizes:
                progress["path"] = head
                emit("file", {"path": head, "size": sizes[head],
                              "done": progress["done"], "total": total})
                return
        m = SHA_LINE.match(line)
        if m and progress["path"]:
            progress["done"] += sizes.get(progress["path"], 0)
            emit("verified", {"path": progress["path"], "sha256": m.group(1),
                              "done": progress["done"], "total": total})
            progress["path"] = None
            return
        # "already here from an earlier pull, and it re-hashes correctly"
        if "re-hashes correctly" in stripped and progress["path"]:
            progress["done"] += sizes.get(progress["path"], 0)
            emit("verified", {"path": progress["path"], "sha256": None,
                              "done": progress["done"], "total": total})
            progress["path"] = None

    import client  # 07-distribute/client.py, the reference client

    args = type("Args", (), {
        "id": nid, "dest": str(INSTALL_ROOT), "version": man["version"],
        "node": NODE, "expect": None, "retries": 3, "wait": 0.0,
    })()

    with _lock:
        INSTALL_ROOT.mkdir(parents=True, exist_ok=True)
        sink = _Sink(on_line, passthrough=sys.stdout)
        t0 = time.time()
        try:
            with contextlib.redirect_stdout(sink):
                client.cmd_pull(args)
            sink.flush()
        except client.Integrity as e:
            sink.flush()
            # Nothing is installed: the client deletes the bad file and never
            # writes manifest.json. Say which, because "download failed" and
            # "the bytes did not match the manifest" are different events.
            return emit("error", {"message": str(e), "integrity": True})
        except client.Failure as e:
            sink.flush()
            return emit("error", {"message": str(e), "integrity": False})
        except Exception as e:                       # a dead node, a full disk
            sink.flush()
            return emit("error", {"message": str(e), "integrity": False})

    inst = installed(region_id)
    if not inst:
        return emit("error", {"message": "the pull finished but no manifest was "
                                         "written, so nothing counts as installed",
                              "integrity": True})
    emit("done", {"id": nid, "version": inst["version"], "files": len(inst["files"]),
                  "size": inst["size"], "pack_sha256": inst["pack_sha256"],
                  "ms": int((time.time() - t0) * 1000),
                  "dest": str(INSTALL_ROOT / nid / inst["version"])})
