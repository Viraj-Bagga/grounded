"""Pack rules shared by the builder, the node and the client. Stdlib only, 3.9+.

One implementation of the things all three depend on, so there is one rule and
not three: what a valid id, version and file path look like, what a valid
manifest contains, and how pack_sha256 is computed.

A PACK is a directory, packs/<id>/<version>/, holding manifest.json and a
files/ tree. The manifest lists every file with its size and sha256.

PACK_SHA256 is the sha256 of the listing `shasum -a 256` prints for the pack's
files in byte order of path, one line "<sha256>  <path>\n" per file. It pins
every file's name and content, and it reproduces with no project code:

    cd packs/corpus-base/2026.09.15/files
    shasum -a 256 citations.csv corpus.db | shasum -a 256

List the files in byte order (LC_ALL=C sort), uppercase before lowercase.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

FORMAT = 1
MANIFEST = "manifest.json"
FILES_DIR = "files"
PART_SUFFIX = ".part"      # the client's name for a download in progress
BLOCK = 4 * 1024 * 1024

# Lowercase only. APFS and phone filesystems are case-insensitive, so
# "Corpus-Base" and "corpus-base" would be two packs on a Linux node and one
# directory on the device. The leading character rules out ".", ".." and
# hidden directories, which is also how the node skips a build in progress.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
# One component of a file path inside a pack. Same idea, case allowed.
PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

REQUIRED = ("format", "id", "version", "kind", "title", "license", "files",
            "size", "pack_sha256")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def human(n: float) -> str:
    """Decimal units, to match how the repo quotes sizes (2.84 GB)."""
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= scale:
            return f"{n / scale:.2f} {unit}"
    return f"{int(n)} B"


def sha256_file(path, progress=None) -> str:
    """Hash a file from disk in blocks. progress(bytes_done) is optional."""
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as f:
        while True:
            block = f.read(BLOCK)
            if not block:
                break
            h.update(block)
            done += len(block)
            if progress:
                progress(done)
    return h.hexdigest()


def pack_digest(files) -> str:
    listing = "".join(f"{f['sha256']}  {f['path']}\n"
                      for f in sorted(files, key=lambda f: f["path"]))
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def path_problem(p) -> str | None:
    """Why a file path is not allowed in a pack, or None if it is.

    This is the whole traversal defence on the client, and half of it on the
    node: a path that passes cannot be absolute, cannot climb out with "..",
    and cannot name a hidden file.
    """
    if not isinstance(p, str) or not p:
        return "empty or not a string"
    if len(p) > 255:
        return "longer than 255 characters"
    if p.startswith("/") or "\\" in p:
        return "absolute, or contains a backslash"
    parts = p.split("/")
    if len(parts) > 8:
        return "nested more than 8 levels"
    for part in parts:
        if not PART_RE.match(part):
            return f"component {part!r} must match [A-Za-z0-9][A-Za-z0-9._-]*"
    if p.endswith(PART_SUFFIX):
        return f"ends in {PART_SUFFIX}, which the client uses for partial downloads"
    return None


def manifest_problems(m) -> list[str]:
    """Everything wrong with a manifest. Empty list means valid."""
    if not isinstance(m, dict):
        return ["manifest is not a JSON object"]
    errs = [f"missing field {k!r}" for k in REQUIRED if k not in m]
    if errs:
        return errs
    if m["format"] != FORMAT:
        errs.append(f"format is {m['format']!r}; this code reads format {FORMAT}")
    for k in ("id", "version", "kind"):
        if not isinstance(m[k], str) or not NAME_RE.match(m[k]):
            errs.append(f"{k} {m[k]!r} must match [a-z0-9][a-z0-9._-]*, "
                        f"64 characters at most")
    lic = m["license"]
    if not isinstance(lic, dict) or not isinstance(lic.get("name"), str) \
            or not lic.get("name"):
        errs.append("license must be an object with a name")
    files = m["files"]
    if not isinstance(files, list) or not files:
        return errs + ["files must be a non-empty list"]

    seen, total = set(), 0
    for i, f in enumerate(files):
        if not isinstance(f, dict):
            errs.append(f"files[{i}] is not an object")
            continue
        p = f.get("path")
        why = path_problem(p)
        if why:
            errs.append(f"files[{i}] path {p!r}: {why}")
            continue
        if p.lower() in seen:
            errs.append(f"files[{i}] path {p!r} repeats another path, ignoring case")
        seen.add(p.lower())
        size = f.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errs.append(f"files[{i}] {p}: size must be a non-negative integer")
        else:
            total += size
        sha = f.get("sha256")
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            errs.append(f"files[{i}] {p}: sha256 must be 64 lowercase hex characters")
    if errs:
        return errs

    lowered = sorted(f["path"].lower() for f in files)
    for p in lowered:
        for q in lowered:
            if q.startswith(p + "/"):
                errs.append(f"{p!r} is listed as a file and as a directory of {q!r}")
    if m["size"] != total:
        errs.append(f"size is {m['size']!r}; the files add up to {total}")
    if m["pack_sha256"] != pack_digest(files):
        errs.append("pack_sha256 does not match the files listed")
    return errs
