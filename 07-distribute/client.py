#!/usr/bin/env python3
"""Pull packs from a distribution node and verify them. Stdlib only, Python 3.9+.

    python 07-distribute/client.py list   [--node URL]
    python 07-distribute/client.py pull   ID --dest DIR [--version V] [--expect PACK_SHA256]
    python 07-distribute/client.py verify DIR/<id>/<version>

The reference client. A phone port has to do the same four things in the same
order, and nothing here depends on anything a phone lacks.

PULL
  1. Fetch the node's index and the pack's manifest. Refuse a manifest that is
     invalid, disagrees with the index, or names a path that could land outside
     --dest: a hostile node must not be able to write anywhere else.
  2. Download each file to <path>.part. A dropped connection resumes with Range
     and If-Range, up to --retries times. If-Range makes the node send the whole
     file again if it has changed, so two versions are never spliced together.
  3. Hash the file FROM DISK and compare its size and sha256 with the manifest.
     Match: rename it into place. Mismatch: delete it and exit 2.
  4. Write manifest.json last. Its presence means every file verified. There is
     no other definition of installed.

--expect PACK_SHA256 pins a pack out of band. The manifest comes from the same
node as the files, so its hashes prove integrity, not authenticity: a hostile
node can rewrite a file and its manifest together. A digest the app ships with,
generated at build time the way registry.ts is generated from citations.csv, is
out of the node's reach.

Exit codes: 0 ok. 1 usage or network failure; partial downloads are kept, and
running the same command again resumes them. 2 integrity failure; nothing is
installed.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import packlib as pl  # noqa: E402

DEFAULT_NODE = "http://127.0.0.1:8790"
UA = "steel26-distribute-client/1"
READ_BLOCK = 1024 * 1024
QUIET_BELOW = 50_000_000        # no progress lines for files smaller than this
# URLError, ConnectionError and timeouts are all OSError; IncompleteRead is an
# HTTPException.
NET_ERRORS = (OSError, http.client.HTTPException)


class Integrity(Exception):
    """The bytes or the manifest are wrong. Exit 2, nothing installed."""


class Failure(Exception):
    """Could not finish. Exit 1."""


def fetch(url: str, wait: float = 0.0) -> bytes:
    deadline = time.time() + wait
    while True:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise Failure(f"GET {url}: HTTP {e.code}")
        except NET_ERRORS as e:
            if time.time() < deadline:
                time.sleep(0.25)
                continue
            raise Failure(f"GET {url}: {e}")


def get_index(node: str, wait: float) -> dict:
    raw = fetch(node + "/packs", wait)
    try:
        idx = json.loads(raw.decode("utf-8"))
    except ValueError as e:
        raise Failure(f"{node}/packs is not JSON: {e}")
    if not isinstance(idx, dict) or not isinstance(idx.get("packs"), list):
        raise Failure(f"{node}/packs is not a pack index")
    return idx


class Meter:
    """Progress. Redraws on a terminal; prints every 10% into a log."""

    def __init__(self, total: int, start: int):
        self.total, self.start = total, start
        self.t0 = self.last = time.time()
        self.tty = sys.stdout.isatty()
        self.quiet = total < QUIET_BELOW
        self.next = (start * 10 // total + 1) * 10 if total else 100

    def rate(self, have: int) -> float:
        return (have - self.start) / max(time.time() - self.t0, 1e-6) / 1e6

    def update(self, have: int):
        if self.quiet:
            return
        pct = have * 100 // self.total
        if self.tty:
            now = time.time()
            if now - self.last >= 0.2:
                self.last = now
                sys.stdout.write(f"\r    {pct:3d}%  {pl.human(have)} of "
                                 f"{pl.human(self.total)}  {self.rate(have):.0f} MB/s ")
                sys.stdout.flush()
            return
        while pct >= self.next and self.next <= 100:
            print(f"    {self.next:3d}%  {pl.human(have):>10}  {self.rate(have):6.0f} MB/s")
            self.next += 10

    def finish(self, have: int):
        if self.tty and not self.quiet:
            sys.stdout.write("\r" + " " * 64 + "\r")
        dt = max(time.time() - self.t0, 1e-6)
        moved = have - self.start
        rate = f", {self.rate(have):.0f} MB/s" if moved >= 1_000_000 else ""
        print(f"    transferred {pl.human(moved)} in {dt:.2f} s{rate}")


def download(url: str, part: Path, size: int, sha: str, retries: int) -> int:
    """Bring part up to size bytes, resuming across drops. Returns bytes moved."""
    moved, failures = 0, 0
    while True:
        have = part.stat().st_size if part.exists() else 0
        if have > size:
            part.unlink()
            have = 0
        if have == size:
            return moved
        headers = {"User-Agent": UA}
        if have:
            headers["Range"] = f"bytes={have}-"
            headers["If-Range"] = f'"{sha}"'
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status == 206:
                    cr = (r.headers.get("Content-Range") or "").strip()
                    m = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", cr)
                    if not m or int(m.group(1)) != have or int(m.group(3)) != size:
                        raise Integrity(f"the node answered a resume from byte {have} "
                                        f"with Content-Range {cr!r}")
                    mode = "ab"
                    print(f"    resuming at {pl.human(have)}: the node answered "
                          f"206 Partial Content, bytes {m.group(1)}-{m.group(2)}")
                elif r.status == 200:
                    if have:
                        print("    the node sent the whole file (200); starting again from 0")
                    have, mode = 0, "wb"
                else:
                    raise Failure(f"GET {url}: HTTP {r.status}")
                meter = Meter(size, have)
                with open(part, mode) as out:
                    while True:
                        block = r.read(READ_BLOCK)
                        if not block:
                            break
                        if have + len(block) > size:
                            raise Integrity(f"the node sent more than the {size} bytes "
                                            f"the manifest lists")
                        out.write(block)
                        have += len(block)
                        moved += len(block)
                        meter.update(have)
                meter.finish(have)
            if have < size:
                # http.client's read(n) returns b"" at an early close rather
                # than raising, so a short body is detected here.
                raise ConnectionError(f"connection closed after {pl.human(have)} "
                                      f"of {pl.human(size)}")
        except Integrity:
            if part.exists():
                part.unlink()
            raise
        except urllib.error.HTTPError as e:
            if e.code != 416:
                raise Failure(f"GET {url}: HTTP {e.code}")
            part.unlink()       # the node says our partial file is past its end
            failures += 1
            if failures > retries:
                raise Failure(f"GET {url}: repeated 416 responses")
        except NET_ERRORS as e:
            failures += 1
            at = part.stat().st_size if part.exists() else 0
            if failures > retries:
                raise Failure(f"transfer failed {failures} times, last: {e}. "
                              f"{part.name} keeps {pl.human(at)}; run the same "
                              f"command again to resume.")
            print(f"    interrupted at {pl.human(at)}: {e.__class__.__name__}: {e}. "
                  f"Retry {failures} of {retries}.")
            time.sleep(min(0.5 * failures, 3.0))


def fetch_file(url: str, target: Path, f: dict, retries: int):
    size, want = f["size"], f["sha256"]
    part = target.with_name(target.name + pl.PART_SUFFIX)
    print(f"  {f['path']}  {pl.human(size)}")
    if target.exists():
        # left by an earlier pull of this pack that stopped on a later file
        if target.stat().st_size == size and pl.sha256_file(target) == want:
            print("    already here from an earlier pull, and it re-hashes correctly")
            return 0, want
        target.unlink()
    moved = download(url, part, size, want, retries)
    arrived = part.stat().st_size
    if arrived != size:
        part.unlink()
        raise Integrity(f"{f['path']}: {arrived} bytes arrived, the manifest says "
                        f"{size}. Deleted the download. Nothing installed.")
    t = time.time()
    got = pl.sha256_file(part)
    dt = time.time() - t
    if got != want:
        part.unlink()
        raise Integrity(f"{f['path']}: the sha256 of the bytes on disk does not match "
                        f"the manifest\n    expected {want}\n    got      {got}\n"
                        f"  Deleted the download. Nothing installed.")
    os.replace(part, target)
    print(f"    sha256 {got}\n"
          f"      hashed from disk in {dt:.1f} s: matches the manifest")
    return moved, got


def cmd_list(args) -> int:
    idx = get_index(args.node.rstrip("/"), args.wait)
    packs = idx["packs"]
    print(f"node {args.node}: {len(packs)} pack(s)")
    if not packs:
        return 0
    rows = [("id", "version", "kind", "size", "files", "licence", "pack_sha256")]
    for p in packs:
        lic = p.get("license") or {}
        rows.append((str(p.get("id")), str(p.get("version")), str(p.get("kind")),
                     pl.human(p.get("size") or 0), str(len(p.get("files") or [])),
                     f"{lic.get('name')} [{lic.get('status', '?')}]",
                     str(p.get("pack_sha256"))[:16] + "..."))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    print()
    for r in rows:
        print("  " + "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
    return 0


def cmd_pull(args) -> int:
    node = args.node.rstrip("/")
    if args.expect and not pl.SHA_RE.match(args.expect.lower()):
        raise Failure("--expect must be a 64-character sha256")
    idx = get_index(node, args.wait)
    matches = [p for p in idx["packs"] if p.get("id") == args.id]
    if not matches:
        have = sorted(f"{p.get('id')}@{p.get('version')}" for p in idx["packs"])
        raise Failure(f"{args.id} is not on {node}. It has: {', '.join(have) or 'nothing'}")
    if args.version:
        matches = [p for p in matches if p.get("version") == args.version]
        if not matches:
            raise Failure(f"{args.id}@{args.version} is not on {node}")
    elif len(matches) > 1:
        raise Failure(f"{args.id} has several versions on {node}: "
                      f"{', '.join(str(p.get('version')) for p in matches)}. "
                      f"Name one with --version.")
    entry = matches[0]

    raw = fetch(urllib.parse.urljoin(node + "/", str(entry.get("manifest_url", ""))))
    try:
        m = json.loads(raw.decode("utf-8"))
    except ValueError as e:
        raise Integrity(f"the manifest is not JSON: {e}")
    errs = pl.manifest_problems(m)
    if errs:
        raise Integrity("manifest refused:\n  - " + "\n  - ".join(errs))
    if (m["id"], m["version"]) != (entry.get("id"), entry.get("version")):
        raise Integrity(f"asked for {entry.get('id')}@{entry.get('version')}, the "
                        f"node's manifest is for {m['id']}@{m['version']}")
    if m["pack_sha256"] != entry.get("pack_sha256"):
        raise Integrity("the node's index and its manifest disagree about pack_sha256")
    lic = m["license"]
    print(f"pull {m['id']}@{m['version']} ({m['kind']}) from {node}")
    print(f"  {len(m['files'])} files, {pl.human(m['size'])} ({m['size']:,} bytes), "
          f"licence {lic['name']} [{lic.get('status', '?')}]")
    print(f"  pack_sha256 {m['pack_sha256']}")
    if args.expect:
        if m["pack_sha256"] != args.expect.lower():
            raise Integrity(f"pack_sha256 is not the expected {args.expect.lower()}. "
                            f"Refused before downloading anything.")
        print("  pack_sha256 matches --expect")

    dest = Path(args.dest) / m["id"] / m["version"]
    installed = dest / pl.MANIFEST
    if installed.exists():
        try:
            old = json.loads(installed.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
        if old.get("pack_sha256") == m["pack_sha256"]:
            print(f"already installed at {dest}. Run verify to re-hash it.")
            return 0
        raise Integrity(f"{dest} already holds a different {m['id']}@{m['version']} "
                        f"(pack_sha256 {old.get('pack_sha256')}). A version never "
                        f"changes, so one of the two is wrong. Not overwriting it.")

    root = dest / pl.FILES_DIR
    root.mkdir(parents=True, exist_ok=True)
    real_root = root.resolve()
    t0, moved, verified = time.time(), 0, []
    for f in sorted(m["files"], key=lambda f: f["path"]):
        target = root / f["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        parent = target.parent.resolve()
        if parent != real_root and real_root not in parent.parents:
            raise Integrity(f"{f['path']} would be written outside {root}")
        url = urllib.parse.urljoin(
            node + "/", f"packs/{m['id']}/{m['version']}/{pl.FILES_DIR}/"
                        f"{urllib.parse.quote(f['path'])}")
        n, sha = fetch_file(url, target, f, args.retries)
        moved += n
        verified.append({"path": f["path"], "sha256": sha})

    digest = pl.pack_digest(verified)
    if digest != m["pack_sha256"]:
        raise Integrity("the files on disk do not add up to the manifest's pack_sha256")
    tmp = dest / ".manifest.json.tmp"
    tmp.write_bytes(raw)
    os.replace(tmp, installed)
    dt = time.time() - t0
    print(f"INSTALLED {m['id']}@{m['version']} at {dest}")
    print(f"  transferred {pl.human(moved)} in {dt:.1f} s including hashing")
    print(f"  every file hashed from disk and matched its manifest entry")
    print(f"  pack_sha256 recomputed from the files on disk: {digest}")
    return 0


def cmd_verify(args) -> int:
    d = Path(args.dir)
    try:
        m = json.loads((d / pl.MANIFEST).read_bytes().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise Integrity(f"{d} has no readable manifest.json, so it is not an "
                        f"installed pack: {e}")
    errs = pl.manifest_problems(m)
    if errs:
        raise Integrity("the installed manifest is invalid: " + "; ".join(errs))
    print(f"verify {m['id']}@{m['version']} at {d}")
    bad, verified = [], []
    for f in sorted(m["files"], key=lambda f: f["path"]):
        p = d / pl.FILES_DIR / f["path"]
        if not p.is_file():
            bad.append(f"{f['path']} missing")
            print(f"  {f['path']:<14} MISSING")
            continue
        size = p.stat().st_size
        if size != f["size"]:
            bad.append(f"{f['path']} is {size} bytes, not {f['size']}")
            print(f"  {f['path']:<14} WRONG SIZE {size}")
            continue
        t = time.time()
        got = pl.sha256_file(p)
        ok = got == f["sha256"]
        print(f"  {f['path']:<14} {pl.human(size):>10}  sha256 {got}  "
              f"{time.time() - t:.1f} s  {'ok' if ok else 'MISMATCH'}")
        if ok:
            verified.append({"path": f["path"], "sha256": got})
        else:
            bad.append(f"{f['path']} sha256 mismatch")
    root = d / pl.FILES_DIR
    known = {f["path"] for f in m["files"]}
    for p in sorted(root.rglob("*")) if root.is_dir() else []:
        if p.is_file() and p.relative_to(root).as_posix() not in known:
            print(f"  (not part of the pack, ignored: {p.relative_to(root).as_posix()})")
    if bad:
        raise Integrity(f"{len(bad)} file(s) failed: " + "; ".join(bad))
    print(f"VERIFIED {m['id']}@{m['version']}: every file matches, "
          f"pack_sha256 {pl.pack_digest(verified)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pull and verify packs from a distribution node.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="show what a node offers")
    p.add_argument("--node", default=DEFAULT_NODE)
    p.add_argument("--wait", type=float, default=0.0,
                   help="seconds to keep trying while the node starts up")
    p = sub.add_parser("pull", help="download a pack and verify every file")
    p.add_argument("id")
    p.add_argument("--dest", type=Path, required=True,
                   help="installs into DEST/<id>/<version>")
    p.add_argument("--version")
    p.add_argument("--node", default=DEFAULT_NODE)
    p.add_argument("--expect", metavar="PACK_SHA256",
                   help="refuse unless the pack's digest is exactly this")
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--wait", type=float, default=0.0,
                   help="seconds to keep trying while the node starts up")
    p = sub.add_parser("verify", help="re-hash an installed pack")
    p.add_argument("dir", type=Path)
    args = ap.parse_args(argv)
    try:
        # Line by line even into a pipe or a log, so a transcript interleaves
        # with the node's log in the order things happened.
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    try:
        return {"list": cmd_list, "pull": cmd_pull, "verify": cmd_verify}[args.cmd](args)
    except Integrity as e:
        print(f"INTEGRITY FAILURE: {e}")
        return 2
    except Failure as e:
        print(f"FAILED: {e}")
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted. Partial downloads are kept as .part files; run the "
              "same command again to resume.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
