#!/usr/bin/env python3
"""End-to-end tests for 07-distribute. Stdlib only, loopback only.

    python 07-distribute/selftest.py            # exit 0 only if every check passes
    python 07-distribute/selftest.py --keep     # leave the temp directory behind

Runs in a fresh temp directory: a node on an ephemeral loopback port, a
fault-injecting proxy in front of it, and the real builder and client run as
subprocesses, so exit codes are tested the way a user meets them. Payloads are
synthetic and not medical. The real packs/ directory is never touched. The
corpus tests read the real 01-data/citations.csv and 04-retrieval/corpus.db and
modify only copies of them.

One test per claim the README makes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import json
import os
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import packlib as pl  # noqa: E402
import server as node_mod  # noqa: E402

BUILD, CLIENT, PY = HERE / "build_pack.py", HERE / "client.py", sys.executable
REAL_REGISTRY = REPO / "01-data" / "citations.csv"
REAL_DB = REPO / "04-retrieval" / "corpus.db"
REAL_OVERLAY = HERE / "regional" / "india"

RESULTS = []
NODE_LOG = []
TMP = Path()


def show(s: str) -> str:
    return s.replace(str(TMP), "$TMP")


def check(name: str, ok, detail: str = ""):
    node_says()
    RESULTS.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if detail and not ok:
        print(f"        {show(detail)}")


def section(title: str):
    print(f"\n{title}")


def run(*args):
    """Run a tool the way a user does. Returns (exit code, combined output)."""
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True)
    out = (r.stdout + r.stderr).rstrip()
    shown = [Path(a).name if str(a).startswith(str(HERE)) else str(a) for a in args]
    print("    $ " + show(" ".join(shown)))
    for line in out.splitlines():
        print("    | " + show(line))
    print(f"    exit {r.returncode}")
    return r.returncode, out


MARK = [0]


def node_says():
    """Print what the node logged since the last call."""
    for line in NODE_LOG[MARK[0]:]:
        print("    node| " + show(line))
    MARK[0] = len(NODE_LOG)


def get(port: int, path: str, headers=None, method="GET"):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request(method, path, headers=headers or {})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, dict(r.getheaders()), body


def listed(port: int) -> set:
    _, _, body = get(port, "/packs")
    return {f"{p['id']}@{p['version']}" for p in json.loads(body)["packs"]}


def write_spec(path: Path, **spec) -> Path:
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return path


def tiny_gguf(path: Path, arch: str = "testarch", ftype: int = 15):
    """A header-only GGUF: enough for the builder's checks, no weights."""
    def s(x: str) -> bytes:
        b = x.encode()
        return struct.pack("<Q", len(b)) + b
    kv = [s("general.architecture") + struct.pack("<I", 8) + s(arch),
          s("general.file_type") + struct.pack("<II", 4, ftype),
          s("tokenizer.ggml.tokens") + struct.pack("<IIQ", 9, 8, 2) + s("a") + s("b")]
    path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, len(kv)) + b"".join(kv) + bytes(64))


# ------------------------------------------------------------ fault proxy

class Proxy(ThreadingHTTPServer):
    """Forwards to the node, optionally damaging what comes back.

    pass      forward unchanged
    flip      flip one bit in the middle of payload.bin
    cut-once  send payload.bin's full Content-Length, then half the body, then
              close; later requests pass through
    evil      rewrite the index and manifest so the first file's path is
              ../escaped.bin, with pack_sha256 recomputed to stay consistent
    """
    daemon_threads = True

    def __init__(self, upstream: int):
        self.upstream, self.mode, self.cut_done, self.seen = upstream, "pass", False, []
        super().__init__(("127.0.0.1", 0), ProxyHandler)


def poison(m: dict):
    m["files"][0]["path"] = "../escaped.bin"
    m["pack_sha256"] = pl.pack_digest(m["files"])


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        srv = self.server
        fwd = {k: v for k, v in self.headers.items() if k.lower() in ("range", "if-range")}
        c = http.client.HTTPConnection("127.0.0.1", srv.upstream, timeout=30)
        c.request("GET", self.path, headers=fwd)
        r = c.getresponse()
        body = r.read()
        c.close()
        srv.seen.append((self.path, self.headers.get("Range"), r.status))
        target = self.path.endswith("/payload.bin") and r.status in (200, 206)
        if srv.mode == "flip" and target:
            b = bytearray(body)
            b[len(b) // 2] ^= 0x01
            body = bytes(b)
        if srv.mode == "evil" and r.status == 200 and "/files/" not in self.path:
            doc = json.loads(body)
            for m in (doc["packs"] if "packs" in doc else [doc]):
                poison(m)
            body = json.dumps(doc).encode()
        self.send_response(r.status)
        for k, v in r.getheaders():
            if k.lower() in ("content-type", "etag", "accept-ranges", "content-range"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if srv.mode == "cut-once" and target and not srv.cut_done:
            srv.cut_done = True
            self.wfile.write(body[: len(body) // 2])
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            return
        self.wfile.write(body)


def serve(server):
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server.server_address[1]


# ------------------------------------------------------------------ tests

def main() -> int:
    global TMP
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    TMP = Path(tempfile.mkdtemp(prefix="distribute-selftest-")).resolve()
    print(f"07-distribute self-test, {pl.utc_now()}, Python {sys.version.split()[0]}")
    print(f"temp directory $TMP = {TMP}")

    packs, src = TMP / "packs", TMP / "src"
    src.mkdir()
    payload = os.urandom(3 * 1024 * 1024 + 4321)       # not block aligned
    (src / "payload.bin").write_bytes(payload)
    (src / "NOTICE.txt").write_text("Synthetic self-test payload. Not medical content.\n")
    test_licence = {"name": "Self-test payload, no licence", "status": "green"}
    spec_a = write_spec(TMP / "spec-a.json", id="test-alpha", version="1", kind="test",
                        title="Self-test pack", license=test_licence,
                        files=[{"path": "payload.bin", "source": str(src / "payload.bin")},
                               {"path": "NOTICE.txt", "source": str(src / "NOTICE.txt")}])

    section("T01  build a pack from a spec")
    rc, out = run(BUILD, spec_a, "--packs", packs)
    manifest = json.loads((packs / "test-alpha/1/manifest.json").read_text())
    check("builder exits 0 and writes packs/test-alpha/1/manifest.json", rc == 0)
    notice_len = (src / "NOTICE.txt").stat().st_size
    check("manifest carries version, size, sha256 per file, pack_sha256 and licence",
          manifest["version"] == "1" and manifest["size"] == len(payload) + notice_len
          and all(pl.SHA_RE.match(f["sha256"]) for f in manifest["files"])
          and manifest["license"]["name"] and not pl.manifest_problems(manifest))

    node = node_mod.make_node(packs, "127.0.0.1", 0, logger=NODE_LOG.append)
    port = serve(node)
    proxy = Proxy(port)
    pport = serve(proxy)
    url, purl = f"http://127.0.0.1:{port}", f"http://127.0.0.1:{pport}"
    node_says()
    print(f"    node on {url}, fault proxy on {purl}")

    section("T02  GET /packs lists what is available")
    status, _, body = get(port, "/packs")
    idx = json.loads(body)
    entry = next((p for p in idx["packs"] if p["id"] == "test-alpha"), None)
    check("GET /packs is 200 and lists test-alpha@1", status == 200 and entry
          and entry["version"] == "1")
    check("each entry carries the manifest, its URL and a URL per file",
          entry and entry["manifest_url"] == "/packs/test-alpha/1/manifest.json"
          and all("url" in f for f in entry["files"])
          and entry["pack_sha256"] == manifest["pack_sha256"])
    rc, out = run(CLIENT, "list", "--node", url)
    check("client list shows it", rc == 0 and "test-alpha" in out)

    section("T03  pull over loopback, then verify from disk")
    d1 = TMP / "dest1"
    rc, out = run(CLIENT, "pull", "test-alpha", "--node", url, "--dest", d1)
    inst = d1 / "test-alpha/1"
    check("pull exits 0 and says INSTALLED", rc == 0 and "INSTALLED" in out)
    check("installed payload is byte-identical to the source",
          (inst / "files/payload.bin").read_bytes() == payload)
    check("manifest.json written, no .part left", (inst / "manifest.json").exists()
          and not list(inst.rglob("*.part")))
    rc, out = run(CLIENT, "verify", inst)
    check("verify re-hashes it and exits 0", rc == 0 and "VERIFIED" in out)
    rc, out = run(CLIENT, "pull", "test-alpha", "--node", url, "--dest", d1)
    check("pulling again is a no-op", rc == 0 and "already installed" in out)

    section("T04  pack_sha256 reproduces with the system shasum tool, no project code")
    tool = shutil.which("shasum")
    if tool:
        names = sorted(f["path"] for f in manifest["files"])
        listing = subprocess.run([tool, "-a", "256", *names], cwd=inst / "files",
                                 capture_output=True, text=True).stdout
        digest = subprocess.run([tool, "-a", "256"], input=listing, capture_output=True,
                                text=True).stdout.split()[0]
        print(f"    $ cd files && shasum -a 256 {' '.join(names)} | shasum -a 256\n    | {digest}")
        check("equals the manifest's pack_sha256", digest == manifest["pack_sha256"])
    else:
        check("shasum is on PATH", False, "no shasum tool; skipped")

    section("T05  Range semantics on the node")
    fpath = "/packs/test-alpha/1/files/payload.bin"
    etag = f'"{next(f["sha256"] for f in manifest["files"] if f["path"] == "payload.bin")}"'
    n = len(payload)
    st, h, b = get(port, fpath, {"Range": "bytes=10-19"})
    check("bytes=10-19 gives 206 and exactly those bytes",
          st == 206 and b == payload[10:20] and h.get("Content-Range") == f"bytes 10-19/{n}")
    st, h, b = get(port, fpath, {"Range": "bytes=-5"})
    check("a suffix range gives the last 5 bytes", st == 206 and b == payload[-5:])
    st, h, b = get(port, fpath, {"Range": "bytes=10-", "If-Range": '"stale"'})
    check("If-Range with a stale ETag gives 200 and the whole file",
          st == 200 and len(b) == n)
    st, h, b = get(port, fpath, {"Range": "bytes=10-", "If-Range": etag})
    check("If-Range with the current ETag honours the range", st == 206 and b == payload[10:])
    st, h, b = get(port, fpath, {"Range": f"bytes={n}-"})
    check("a range past the end gives 416", st == 416 and h.get("Content-Range") == f"bytes */{n}")
    st, h, b = get(port, fpath, {"Range": "bytes=0-1,5-6"})
    check("multiple ranges are ignored: 200, whole file", st == 200 and len(b) == n)
    st, h, b = get(port, fpath, method="HEAD")
    check("HEAD gives the size and ETag with no body",
          st == 200 and h.get("Content-Length") == str(n) and h.get("ETag") == etag and b == b"")

    section("T06  a bit flipped in transit is refused")
    proxy.mode = "flip"
    d2 = TMP / "dest2"
    rc, out = run(CLIENT, "pull", "test-alpha", "--node", purl, "--dest", d2)
    inst2 = d2 / "test-alpha/1"
    check("client exits 2 with INTEGRITY FAILURE", rc == 2 and "INTEGRITY FAILURE" in out)
    check("no manifest.json, so the pack is not installed", not (inst2 / "manifest.json").exists())
    check("the bad download is deleted: no payload.bin, no .part",
          not (inst2 / "files/payload.bin").exists() and not list(d2.rglob("*.part")))

    section("T07  a transfer cut mid-file resumes with a 206 and verifies")
    proxy.mode, proxy.cut_done, proxy.seen = "cut-once", False, []
    d3 = TMP / "dest3"
    rc, out = run(CLIENT, "pull", "test-alpha", "--node", purl, "--dest", d3)
    resumed = [s for s in proxy.seen if s[0].endswith("payload.bin") and s[1] and s[2] == 206]
    check("client exits 0 after the drop", rc == 0 and "interrupted at" in out)
    check("the retry asked for the rest with Range and got 206", bool(resumed)
          and "resuming at" in out, str(proxy.seen))
    check("the resumed file is byte-identical to the source",
          (d3 / "test-alpha/1/files/payload.bin").read_bytes() == payload)
    proxy.mode = "pass"

    section("T08  --expect pins the pack out of band")
    d4 = TMP / "dest4"
    rc, out = run(CLIENT, "pull", "test-alpha", "--node", url, "--dest", d4, "--expect", "0" * 64)
    check("a wrong digest exits 2 before downloading anything",
          rc == 2 and "before downloading" in out and not (d4 / "test-alpha").exists())
    rc, out = run(CLIENT, "pull", "test-alpha", "--node", url, "--dest", d4,
                  "--expect", manifest["pack_sha256"])
    check("the right digest installs", rc == 0 and "matches --expect" in out)

    section("T09  a manifest path that escapes the destination is refused by the client")
    proxy.mode = "evil"
    d5 = TMP / "dest5"
    rc, out = run(CLIENT, "pull", "test-alpha", "--node", purl, "--dest", d5)
    check("client exits 2 and names the bad path", rc == 2 and "../escaped.bin" in out)
    check("nothing named escaped.bin exists anywhere under $TMP",
          not list(TMP.rglob("escaped.bin")))
    proxy.mode = "pass"

    section("T10  the node serves only paths listed in a valid manifest")
    (packs / "test-alpha/1/files/unlisted.bin").write_bytes(b"on disk, not in the manifest")
    probes = ["/packs/test-alpha/1/files/unlisted.bin",
              "/packs/test-alpha/1/files/../manifest.json",
              "/packs/test-alpha/1/files/%2e%2e/manifest.json",
              "/packs/test-alpha/1/files/NOTICE.txt/../payload.bin",
              "/packs/test-alpha/1/files/",
              "/packs/test-alpha/1",
              "/packs/../../etc/passwd",
              "/packs/test-alpha/../../../etc/passwd",
              "/etc/passwd",
              "/"]
    codes = {p: get(port, p)[0] for p in probes}
    for p, c in codes.items():
        print(f"    GET {p}  ->  {c}")
    check("every probe gets 404", all(c == 404 for c in codes.values()), str(codes))
    check("the listed file still gets 200", get(port, fpath)[0] == 200)

    section("T11  the node refuses packs that point outside themselves")
    evil = {"format": 1, "id": "test-evil", "version": "1", "kind": "test", "title": "x",
            "license": test_licence,
            "files": [{"path": "../../src/NOTICE.txt", "size": 51, "sha256": "0" * 64}]}
    evil["size"], evil["pack_sha256"] = 51, pl.pack_digest(evil["files"])
    (packs / "test-evil/1/files").mkdir(parents=True)
    (packs / "test-evil/1/manifest.json").write_text(json.dumps(evil))
    link_dir = packs / "test-link/1/files"
    link_dir.mkdir(parents=True)
    os.symlink(src / "payload.bin", link_dir / "payload.bin")
    link = {"format": 1, "id": "test-link", "version": "1", "kind": "test", "title": "x",
            "license": test_licence,
            "files": [{"path": "payload.bin", "size": len(payload),
                       "sha256": pl.sha256_file(src / "payload.bin")}]}
    link["size"], link["pack_sha256"] = len(payload), pl.pack_digest(link["files"])
    (packs / "test-link/1/manifest.json").write_text(json.dumps(link))
    now = listed(port)
    node_says()
    check("a manifest with ../ in a path is not listed", "test-evil@1" not in now)
    check("a symlink out of the pack is not listed", "test-link@1" not in now)
    check("the node log says why for both",
          any("test-evil/1" in l and "invalid manifest" in l for l in NODE_LOG)
          and any("test-link/1" in l and "outside the pack" in l for l in NODE_LOG))
    check("their files get 404", get(port, "/packs/test-link/1/files/payload.bin")[0] == 404)

    section("T12  a pack dropped into a running node's directory is listed, no restart")
    elsewhere = TMP / "elsewhere"
    spec_b = write_spec(TMP / "spec-b.json", id="test-regional-zz", version="1", kind="test",
                        title="Synthetic regional pack", region="zz", license=test_licence,
                        files=[{"path": "NOTICE.txt", "source": str(src / "NOTICE.txt")}])
    rc, out = run(BUILD, spec_b, "--packs", elsewhere)
    before = listed(port)
    shutil.copytree(elsewhere / "test-regional-zz", packs / "test-regional-zz")
    after = listed(port)
    node_says()
    check("not listed before the copy, listed after",
          "test-regional-zz@1" not in before and "test-regional-zz@1" in after)
    rc, out = run(CLIENT, "pull", "test-regional-zz", "--node", url, "--dest", TMP / "dest6")
    check("and it pulls and verifies", rc == 0 and "INSTALLED" in out)

    section("T13  a file altered on the node is withdrawn, and restored when it is fixed")
    served = packs / "test-alpha/1/files/payload.bin"
    with open(served, "r+b") as f:
        f.seek(1000)
        orig = f.read(1)
        f.seek(1000)
        f.write(bytes([orig[0] ^ 0xFF]))
    gone = listed(port)
    code = get(port, fpath)[0]
    node_says()
    check("altered in place, same size: withdrawn from /packs", "test-alpha@1" not in gone)
    check("and its file gets 404", code == 404)
    with open(served, "r+b") as f:
        f.seek(1000)
        f.write(orig)
    back = listed(port)
    node_says()
    check("bytes restored: listed again", "test-alpha@1" in back)

    section("T14  a version is immutable")
    rc, out = run(BUILD, spec_a, "--packs", packs)
    check("rebuilding identical content is a no-op", rc == 0 and "identical" in out)
    (src / "payload.bin").write_bytes(payload + b"!")
    rc, out = run(BUILD, spec_a, "--packs", packs)
    check("different content under the same version is refused",
          rc == 1 and "already built with different files" in out)
    (src / "payload.bin").write_bytes(payload)
    retitled = json.loads(spec_a.read_text())
    retitled["title"] = "A different title"
    rc, out = run(BUILD, write_spec(TMP / "spec-a2.json", **retitled), "--packs", packs)
    check("a different manifest under the same version is refused",
          rc == 1 and "different manifest" in out)

    section("T15  model packs: GGUF header, pinned hash, licence file, verbatim quotes")
    tiny_gguf(src / "tiny.gguf")
    (src / "LICENSE.txt").write_text("Test licence.\n\n7. Clause seven says   exactly this.\n")
    base = dict(id="test-model", version="1", kind="model", title="Tiny model",
                model={"file": "model.gguf", "expect_architecture": "testarch",
                       "expect_quant": "Q4_K_M"},
                license={"name": "Test licence", "status": "amber", "file": "LICENSE.txt",
                         "legal_review": {"verbatim": "7. Clause seven says exactly this."}},
                files=[{"path": "model.gguf", "source": str(src / "tiny.gguf"),
                        "sha256": pl.sha256_file(src / "tiny.gguf")},
                       {"path": "LICENSE.txt", "source": str(src / "LICENSE.txt")}])
    mpacks = TMP / "model-packs"
    rc, out = run(BUILD, write_spec(TMP / "m-ok.json", **base), "--packs", mpacks)
    mm = json.loads((mpacks / "test-model/1/manifest.json").read_text()) if rc == 0 else {}
    check("a good spec builds, header read into the manifest",
          rc == 0 and mm.get("model", {}).get("architecture") == "testarch"
          and mm["model"]["quant"] == "Q4_K_M" and "expect_quant" not in mm["model"])

    def variant(name, change, expect):
        spec = json.loads(json.dumps(base))
        change(spec)
        spec["version"] = name
        rc, out = run(BUILD, write_spec(TMP / f"m-{name}.json", **spec), "--packs", mpacks)
        return rc == 1 and expect in out

    check("the wrong architecture is refused",
          variant("arch", lambda s: s["model"].update(expect_architecture="nemotron_h"),
                  "is architecture 'testarch'"))
    check("a hash that is not the pinned one is refused",
          variant("pin", lambda s: s["files"][0].update(sha256="f" * 64), "the spec pins"))
    check("no licence file in the pack is refused",
          variant("nolicence", lambda s: (s["files"].pop(), s["license"].pop("legal_review"),
                                          s["license"].pop("file")),
                  "must ship its licence text"))
    check("a 'verbatim' quote that is not in the licence file is refused",
          variant("quote", lambda s: s["license"]["legal_review"].update(
              verbatim="7. Clause seven says something else."), "quoted as verbatim"))

    section("T16  corpus packs: the real registry and index pass; damaged copies do not")
    corpus = dict(kind="corpus", title="Corpus copy", version="1",
                  license={"name": "Public domain (US federal government works)", "status": "green"},
                  corpus={"embedding_dim": 384},
                  files=[{"path": "citations.csv", "source": str(REAL_REGISTRY)},
                         {"path": "corpus.db", "source": str(REAL_DB)}])
    rc, out = run(BUILD, write_spec(TMP / "c-a.json", id="test-corpus-a", **corpus), "--packs", packs)
    check("the real citations.csv and corpus.db pass every corpus check", rc == 0)
    rc, out = run(BUILD, write_spec(TMP / "c-b.json", id="test-corpus-b", **corpus), "--packs", packs)
    check("a second corpus pack reusing those keys is refused (constraint 9)",
          rc == 1 and "resolve to one chunk" in out)

    cpacks = TMP / "corpus-packs"
    red = TMP / "citations-red.csv"
    lines = REAL_REGISTRY.read_text(encoding="utf-8").splitlines(keepends=True)
    red.write_text(lines[0] + lines[1].replace(",green,", ",red,", 1) + "".join(lines[2:]),
                   encoding="utf-8")
    spec = json.loads(json.dumps(corpus))
    spec["files"][0]["source"] = str(red)
    rc, out = run(BUILD, write_spec(TMP / "c-red.json", id="test-corpus-red", **spec), "--packs", cpacks)
    check("a registry row with licence red is refused (constraint 6)",
          rc == 1 and "not licence-cleared" in out)

    drift = TMP / "corpus-drift.db"
    shutil.copyfile(REAL_DB, drift)
    db = sqlite3.connect(drift)
    db.execute("update chunk_meta set text = text || ' ' where key = 'CP-ACS-001'")
    db.commit()
    db.close()
    spec = json.loads(json.dumps(corpus))
    spec["files"][1]["source"] = str(drift)
    rc, out = run(BUILD, write_spec(TMP / "c-drift.json", id="test-corpus-drift", **spec), "--packs", cpacks)
    check("an index whose chunk text drifted from the freeze is refused (constraint 1)",
          rc == 1 and "CP-ACS-001" in out and "frozen chunk_sha256" in out)

    section("T17  overlay packs: a regional add-on is frozen, and stays frozen")
    # The two checks that make an overlay safe. Both were exercised by hand on
    # 2026-09-19 and belong here instead: an add-on whose text can drift, or
    # whose keys can mean two things, is worse than no add-on, because a
    # citation key has to resolve to one chunk however many packs are on the
    # phone (hard constraint 9) and a frozen chunk must stay frozen (1).
    if not (REAL_OVERLAY / "citations.csv").exists():
        check("the frozen india overlay is on disk to test against", False,
              f"{REAL_OVERLAY} has no citations.csv: run build_regional.py freeze")
    else:
        opacks = TMP / "overlay-packs"
        reg_rows = list(csv.DictReader(
            (REAL_OVERLAY / "citations.csv").read_text(encoding="utf-8").splitlines()))
        keys = [r["key"] for r in reg_rows]

        def overlay_spec(pid, root, version="1"):
            files = [{"path": "citations.csv", "source": str(root / "citations.csv")},
                     {"path": "LICENCE.txt", "source": str(REAL_OVERLAY / "LICENCE.txt")}]
            files += [{"path": f"chunks/{k}.txt", "source": str(root / "chunks" / f"{k}.txt")}
                      for k in keys]
            return dict(id=pid, version=version, kind="overlay", title="Overlay copy",
                        requires="corpus-base",
                        license={"name": "CC BY-NC-SA 3.0 IGO", "status": "amber",
                                 "note": "Contains WHO text: NonCommercial and ShareAlike."},
                        files=files)

        rc, out = run(BUILD, write_spec(TMP / "o-a.json", **overlay_spec("test-overlay-a", REAL_OVERLAY)),
                      "--packs", opacks)
        check("the frozen regional pack passes every overlay check", rc == 0,
              out.strip().splitlines()[-1] if rc else "")
        check("it records the pack it is layered on and that retrieval is untouched",
              rc == 0 and '"requires": "corpus-base"' in
              (opacks / "test-overlay-a" / "1" / "manifest.json").read_text(encoding="utf-8")
              and '"wired_into_retrieval": false' in
              (opacks / "test-overlay-a" / "1" / "manifest.json").read_text(encoding="utf-8"))

        # 1. A chunk edited after it was frozen.
        edited = TMP / "overlay-edited"
        shutil.copytree(REAL_OVERLAY, edited, dirs_exist_ok=True)
        first = edited / "chunks" / f"{keys[0]}.txt"
        first.write_text(first.read_text(encoding="utf-8") + " tampered\n", encoding="utf-8")
        rc, out = run(BUILD, write_spec(TMP / "o-edit.json",
                                        **overlay_spec("test-overlay-edited", edited)),
                      "--packs", opacks)
        check("a chunk edited after freezing is refused (constraint 1)",
              rc == 1 and keys[0] in out and "It changed after it was frozen" in out, out[-200:])

        # 2. Another pack claiming one of those keys for different text.
        claim = TMP / "overlay-claim"
        (claim / "chunks").mkdir(parents=True, exist_ok=True)
        text = "A different chunk that claims a key another pack already uses.\n"
        (claim / "chunks" / f"{keys[0]}.txt").write_text(text, encoding="utf-8")
        row = dict(reg_rows[0], chunk_sha256=hashlib.sha256(text.encode()).hexdigest()[:16],
                   token_count="11")
        with open(claim / "citations.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(reg_rows[0]))
            w.writeheader()
            w.writerow(row)
        spec = overlay_spec("test-overlay-claim", claim)
        spec["files"] = [f for f in spec["files"]
                         if f["path"] in ("citations.csv", "LICENCE.txt", f"chunks/{keys[0]}.txt")]
        rc, out = run(BUILD, write_spec(TMP / "o-claim.json", **spec), "--packs", opacks)
        check("a second pack claiming that key for different text is refused (constraint 9)",
              rc == 1 and "resolve to one chunk" in out and keys[0] in out, out[-200:])

        # 3. An add-on that does not say what it is layered on is not an add-on.
        spec = overlay_spec("test-overlay-noreq", REAL_OVERLAY)
        spec.pop("requires")
        rc, out = run(BUILD, write_spec(TMP / "o-noreq.json", **spec), "--packs", opacks)
        check("an overlay with no `requires` is refused", rc == 1 and "layered on" in out, out[-160:])

    node.shutdown()
    proxy.shutdown()
    node.server_close()
    proxy.server_close()
    passed = sum(ok for _, ok in RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    for name, ok in RESULTS:
        if not ok:
            print(f"  FAILED: {name}")
    if args.keep:
        print(f"kept {TMP}")
    else:
        shutil.rmtree(TMP, ignore_errors=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
