#!/usr/bin/env python3
"""The distribution node. Stdlib only, Python 3.9+.

    python 07-distribute/server.py                  # 127.0.0.1:8790, serves 07-distribute/packs
    python 07-distribute/server.py --host 0.0.0.0   # serve the local network
    python 07-distribute/server.py --packs DIR --port N

How packs reach a phone that has no internet: the node runs on any machine with
Python 3 on the same network, a laptop or a Raspberry Pi at a clinic, and needs
no internet itself.

  GET  /packs                                 every valid pack, manifest inline, with URLs
  GET  /packs/<id>/<version>/manifest.json    the manifest, byte for byte as built
  GET  /packs/<id>/<version>/files/<path>     a file. HEAD, a single Range and If-Range
                                              are supported; the ETag is the file's sha256
  anything else                               404

DISCOVERY. Packs are found by scanning packs/<id>/<version>/manifest.json on
every request. No pack is named in this file, and a pack dropped into the
directory is listed on the next request without a restart.

VERIFIED BEFORE ADVERTISED. Every file is hashed against its manifest before
its pack is listed, and again whenever the file's inode, size or mtime changes.
A pack with a missing, resized or altered file is withdrawn from /packs, its
files return 404, and the log says why. This catches a file that has gone bad
on the node's own disk, a failing SD card for example, before a phone spends
2.84 GB downloading it only to fail the hash check.

ONLY LISTED PATHS. A file is served only if its path appears exactly in a valid
manifest and resolves inside its pack. There is no directory listing, and
nothing else on disk is reachable.

INTEGRITY, NOT AUTHENTICITY. The hashes let a client detect corruption in
transit or on disk. They do not prove who built a pack: whoever controls a node
can rewrite a file and its manifest together. See --expect in client.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import stat
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import packlib as pl  # noqa: E402

DEFAULT_PACKS = HERE / "packs"
DEFAULT_PORT = 8790
NODE_NAME = "steel26-distribute"
SEND_BLOCK = 1024 * 1024


def log(msg: str):
    print(f"[node {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


class Pack:
    def __init__(self, pid, version, manifest, raw, files):
        self.id, self.version = pid, version
        self.manifest = manifest      # parsed
        self.raw = raw                # the bytes on disk, served as is
        self.files = files            # path -> (resolved Path, manifest entry)


class Catalog:
    """The packs directory, rescanned on every request.

    Hashes are cached per file state, (inode, size, mtime_ns), so a file is
    hashed once when it first appears and again only after it changes.
    """

    def __init__(self, root: Path, logger=log):
        self.root = root
        self.log = logger
        self.lock = threading.Lock()
        self.hashes = {}      # str(resolved path) -> (state, sha256)
        self.listed = {}      # "id@version" -> pack_sha256, as last logged
        self.rejected = {}    # "id/version" -> reason, as last logged

    @staticmethod
    def state(st) -> tuple:
        return (st.st_ino, st.st_size, st.st_mtime_ns)

    def verified_state(self, path: Path):
        entry = self.hashes.get(str(path))
        return entry[0] if entry else None

    def scan(self) -> dict:
        with self.lock:
            packs, rejected = {}, {}
            if self.root.is_dir():
                for id_dir in sorted(self.root.iterdir()):
                    if not (id_dir.is_dir() and pl.NAME_RE.match(id_dir.name)):
                        continue
                    for ver_dir in sorted(id_dir.iterdir()):
                        if not (ver_dir.is_dir() and pl.NAME_RE.match(ver_dir.name)):
                            continue
                        pack, why = self._load(id_dir.name, ver_dir.name, ver_dir)
                        if why:
                            rejected[f"{id_dir.name}/{ver_dir.name}"] = why
                        else:
                            packs[(pack.id, pack.version)] = pack
            self._report(packs, rejected)
            return packs

    def _load(self, pid: str, ver: str, d: Path):
        try:
            raw = (d / pl.MANIFEST).read_bytes()
        except FileNotFoundError:
            return None, "no manifest.json"
        except OSError as e:
            return None, f"manifest unreadable: {e}"
        try:
            m = json.loads(raw.decode("utf-8"))
        except ValueError as e:
            return None, f"manifest is not valid JSON: {e}"
        errs = pl.manifest_problems(m)
        if errs:
            return None, "invalid manifest: " + "; ".join(errs[:3])
        if (m["id"], m["version"]) != (pid, ver):
            return None, (f"manifest says {m['id']}@{m['version']}, "
                          f"the directory says {pid}@{ver}")
        root = (d / pl.FILES_DIR).resolve()
        files = {}
        for f in m["files"]:
            try:
                p = (d / pl.FILES_DIR / f["path"]).resolve(strict=True)
            except (OSError, RuntimeError):
                return None, f"{f['path']}: missing"
            if root not in p.parents:
                return None, f"{f['path']}: resolves outside the pack"
            st = p.stat()
            if not stat.S_ISREG(st.st_mode):
                return None, f"{f['path']}: not a regular file"
            if st.st_size != f["size"]:
                return None, (f"{f['path']}: {st.st_size} bytes on disk, "
                              f"the manifest says {f['size']}")
            cached = self.hashes.get(str(p))
            if not cached or cached[0] != self.state(st):
                t = time.time()
                sha = pl.sha256_file(p)
                self.hashes[str(p)] = cached = (self.state(st), sha)
                self.log(f"hashed {pid}@{ver}/{f['path']}, {pl.human(st.st_size)} "
                         f"in {time.time() - t:.1f} s: "
                         + ("matches the manifest" if sha == f["sha256"]
                            else "DOES NOT MATCH the manifest"))
            if cached[1] != f["sha256"]:
                return None, f"{f['path']}: sha256 on disk does not match the manifest"
            files[f["path"]] = (p, f)
        return Pack(pid, ver, m, raw, files), None

    def _report(self, packs: dict, rejected: dict):
        listed = {}
        for p in packs.values():
            name = f"{p.id}@{p.version}"
            listed[name] = p.manifest["pack_sha256"]
            if self.listed.get(name) != listed[name]:
                self.log(f"serving {name}: {len(p.files)} files, "
                         f"{pl.human(p.manifest['size'])}, "
                         f"pack_sha256 {listed[name][:16]}...")
        for name in self.listed:
            if name not in listed:
                self.log(f"withdrawn {name}")
        for name, why in rejected.items():
            if self.rejected.get(name) != why:
                self.log(f"NOT SERVING {name}: {why}")
        self.listed, self.rejected = listed, rejected


def parse_range(header: str, size: int):
    """One byte range -> (start, end) inclusive, "unsatisfiable", or None.

    None means ignore the header and send the whole file, which HTTP allows for
    anything malformed and is what this node does for multiple ranges.
    """
    m = re.fullmatch(r"\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*", header)
    if not m or m.group(1) == m.group(2) == "":
        return None
    first, last = m.groups()
    if first == "":
        n = int(last)
        return (max(0, size - n), size - 1) if n else "unsatisfiable"
    start = int(first)
    if start >= size:
        return "unsatisfiable"
    end = size - 1 if last == "" else min(int(last), size - 1)
    return (start, end) if end >= start else None


class Handler(BaseHTTPRequestHandler):
    server_version = f"{NODE_NAME}/1"
    protocol_version = "HTTP/1.1"
    timeout = 60

    def log_request(self, code="-", size="-"):
        pass    # _done writes one line per response instead

    def log_message(self, fmt, *args):
        self.server.log(f"{self.client_address[0]} {fmt % args}")

    def do_GET(self):
        self._route(send_body=True)

    def do_HEAD(self):
        self._route(send_body=False)

    def _route(self, send_body: bool):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path in ("/packs", "/packs/"):
            return self._index(send_body)
        parts = path.split("/")
        if len(parts) >= 5 and parts[:2] == ["", "packs"] \
                and pl.NAME_RE.match(parts[2]) and pl.NAME_RE.match(parts[3]):
            pid, ver = parts[2], parts[3]
            if len(parts) == 5 and parts[4] == pl.MANIFEST:
                return self._manifest(pid, ver, send_body)
            if len(parts) >= 6 and parts[4] == pl.FILES_DIR:
                return self._file(pid, ver, "/".join(parts[5:]), send_body)
        self._error(404, "not found")

    def _done(self, code, detail=""):
        self.server.log(f"{self.client_address[0]} {self.command} {self.path} "
                        f"{code} {detail}".rstrip())

    def _send(self, code: int, data: bytes, ctype: str, send_body: bool, detail=""):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)
        self._done(code, detail or f"{len(data)} bytes")

    def _error(self, code: int, msg: str):
        data = (json.dumps({"error": msg}) + "\n").encode("utf-8")
        self._send(code, data, "application/json", self.command != "HEAD", msg)

    def _index(self, send_body: bool):
        packs = self.server.catalog.scan()
        out = []
        for (pid, ver), p in sorted(packs.items()):
            base = f"/packs/{pid}/{ver}"
            entry = dict(p.manifest)
            entry["manifest_url"] = f"{base}/{pl.MANIFEST}"
            entry["files"] = [dict(f, url=f"{base}/{pl.FILES_DIR}/{urllib.parse.quote(f['path'])}")
                              for f in p.manifest["files"]]
            out.append(entry)
        body = {"node": NODE_NAME, "format": pl.FORMAT, "generated": pl.utc_now(),
                "packs": out}
        data = (json.dumps(body, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        self._send(200, data, "application/json; charset=utf-8", send_body,
                   f"{len(out)} packs, {len(data)} bytes")

    def _manifest(self, pid: str, ver: str, send_body: bool):
        p = self.server.catalog.scan().get((pid, ver))
        if not p:
            return self._error(404, "no such pack")
        self._send(200, p.raw, "application/json; charset=utf-8", send_body)

    def _file(self, pid: str, ver: str, rel: str, send_body: bool):
        catalog = self.server.catalog
        p = catalog.scan().get((pid, ver))
        if not p or rel not in p.files:
            return self._error(404, "not found")
        path, f = p.files[rel]
        size, etag = f["size"], f'"{f["sha256"]}"'
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng is not None and size > 0:
            cond = self.headers.get("If-Range")
            if cond is None or cond.strip() == etag:
                r = parse_range(rng, size)
                if r == "unsatisfiable":
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return self._done(416, f"range {rng!r} is past {size} bytes")
                if r:
                    (start, end), code = r, 206
        try:
            fh = open(path, "rb")
        except OSError:
            return self._error(404, "not found")
        with fh:
            # The scan verified this file a moment ago. Refuse if what was
            # just opened is not the file that was verified.
            if catalog.state(os.fstat(fh.fileno())) != catalog.verified_state(path):
                return self._error(503, "file changed since it was verified; retry")
            length = end - start + 1
            self.send_response(code)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", etag)
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            what = f"{pl.human(length)}" + (f", bytes {start}-{end} of {size}" if code == 206 else "")
            if not send_body:
                return self._done(code, what)
            fh.seek(start)
            sent, t = 0, time.time()
            try:
                while sent < length:
                    block = fh.read(min(SEND_BLOCK, length - sent))
                    if not block:
                        break
                    self.wfile.write(block)
                    sent += len(block)
            except (BrokenPipeError, ConnectionResetError, socket.timeout, TimeoutError) as e:
                self.close_connection = True
                return self._done(code, f"{what}: client went away after "
                                        f"{pl.human(sent)} ({e.__class__.__name__})")
            if sent < length:
                self.close_connection = True
            dt = max(time.time() - t, 1e-6)
            rate = f", {sent / dt / 1e6:.0f} MB/s" if sent >= 1_000_000 else ""
            self._done(code, f"{what}: sent {pl.human(sent)} in {dt:.2f} s{rate}")


class Node(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, catalog: Catalog, logger=log):
        self.catalog = catalog
        self.log = logger
        super().__init__(addr, Handler)


def make_node(packs: Path, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
              logger=log) -> Node:
    """Hash every pack, then bind. Port 0 picks a free port (the self-test)."""
    catalog = Catalog(packs, logger)
    catalog.scan()
    return Node((host, port), catalog, logger)


def _stop(signum, frame):
    raise KeyboardInterrupt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Serve packs on this network.")
    ap.add_argument("--packs", type=Path, default=DEFAULT_PACKS)
    ap.add_argument("--host", default="127.0.0.1",
                    help="address to bind; 0.0.0.0 serves the local network")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)
    log(f"packs directory {args.packs}")
    node = make_node(args.packs, args.host, args.port)
    host, port = node.server_address[:2]
    if args.host == "0.0.0.0":
        log("bound to every interface: anyone on this network can list and "
            "download these packs")
    log(f"listening on http://{host}:{port}/packs")
    signal.signal(signal.SIGTERM, _stop)
    try:
        node.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        node.server_close()
        log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
