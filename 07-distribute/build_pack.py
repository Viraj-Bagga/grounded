#!/usr/bin/env python3
"""Build a pack from a spec. Stdlib only, Python 3.9+.

    python 07-distribute/build_pack.py 07-distribute/specs/corpus-base.json
    python 07-distribute/build_pack.py SPEC [SPEC ...] [--packs DIR]

A spec names the pack (id, version, kind, title, licence) and the files that
go into it. The build snapshots those files into packs/<id>/<version>/files/,
hashes the snapshot, and writes manifest.json last. The node serves whatever
valid packs it finds under packs/, so building a pack is how it is published.
A new regional pack needs a spec, not a code change.

A VERSION IS IMMUTABLE. Rebuilding identical content is a no-op. Different
content, or a different manifest, under an existing version is refused: bump
the version. Hard constraint 1 applied to distribution. A phone that installed
corpus-base 2026.09.15 holds exactly these bytes, and a later edit to 01-data
or 04-retrieval must never make a node serve other bytes under that name.

SNAPSHOT, NOT REFERENCE. Files are cloned (clonefile on APFS, reflink on
Linux), so the 2.84 GB model costs no disk until one side changes, with a
plain copy where cloning is unavailable. The hash in the manifest is taken
from the snapshot, which is the thing the node serves, not from the source.

KIND CHECKS, all fail closed:
  corpus  every registry row is licence green or amber (hard constraint 6)
          and has a retrieval date; corpus.db holds exactly the registry's
          keys; every chunk's stored text still hashes to its frozen
          chunk_sha256; the vector dimension matches the spec; sqlite's
          integrity_check passes; and no key is already used by a corpus pack
          with a different id (hard constraint 9 needs a key to resolve to one
          chunk once regional packs exist).
  model   the GGUF header parses and matches the architecture and quant the
          spec expects, and the licence text ships inside the pack.
  other   generic: snapshot, hash, declared licence.

A file may pin its expected sha256 in the spec, and any licence text a spec
quotes under a "verbatim" key must appear word for word in the pack's licence
file. Either failing refuses the build.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import ctypes.util
import hashlib
import json
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import packlib as pl  # noqa: E402

DEFAULT_PACKS = HERE / "packs"
LICENCE_CLEARED = ("green", "amber")     # hard constraint 6
REGISTRY_COLUMNS = ("key", "topic", "source_id", "publisher", "url",
                    "retrieval_date", "license_status", "attribution",
                    "chunk_sha256")


class BuildError(Exception):
    pass


def display(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return str(p)


# ------------------------------------------------------------------- spec

def load_spec(path: Path) -> dict:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BuildError(f"cannot read spec {path}: {e}")
    missing = [k for k in ("id", "version", "kind", "title", "license", "files")
               if k not in spec]
    if missing:
        raise BuildError(f"spec is missing {', '.join(missing)}")
    for k in ("id", "version", "kind"):
        if not isinstance(spec[k], str) or not pl.NAME_RE.match(spec[k]):
            raise BuildError(f"spec {k} {spec[k]!r} must match [a-z0-9][a-z0-9._-]*")
    if not isinstance(spec["license"], dict) or not spec["license"].get("name"):
        raise BuildError("spec license must be an object with a name")
    if not isinstance(spec["files"], list) or not spec["files"]:
        raise BuildError("spec files must be a non-empty list")
    seen = set()
    for f in spec["files"]:
        why = pl.path_problem(f.get("path"))
        if why:
            raise BuildError(f"spec file path {f.get('path')!r}: {why}")
        if f["path"].lower() in seen:
            raise BuildError(f"spec lists {f['path']!r} twice")
        seen.add(f["path"].lower())
        if not f.get("source"):
            raise BuildError(f"spec file {f['path']} has no source")
        if "sha256" in f and not pl.SHA_RE.match(str(f["sha256"])):
            raise BuildError(f"spec file {f['path']} pins a malformed sha256")
    return spec


def source_path(s: str) -> Path:
    p = Path(s)
    return p if p.is_absolute() else REPO / p


# --------------------------------------------------------------- snapshot

def _clonefile(src: Path, dst: Path) -> bool:
    """APFS copy-on-write clone through clonefile(2). False if unavailable."""
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        fn = libc.clonefile
    except (OSError, AttributeError, TypeError):
        return False
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    fn.restype = ctypes.c_int
    return fn(os.fsencode(str(src)), os.fsencode(str(dst)), 0) == 0


def snapshot(src: Path, dst: Path) -> str:
    """Copy src to dst, as a clone where the filesystem allows. Returns how."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin" and _clonefile(src, dst):
        return "clone"
    if sys.platform.startswith("linux"):
        r = subprocess.run(["cp", "--reflink=always", str(src), str(dst)],
                           capture_output=True)
        if r.returncode == 0:
            return "clone"
        if dst.exists():
            dst.unlink()
    shutil.copyfile(src, dst)
    return "copy"


# ------------------------------------------------------------------ model

GGUF_SCALARS = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i",
                6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
# llama.cpp llama_ftype, the values general.file_type can take here.
QUANT = {0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 7: "Q8_0", 8: "Q5_0",
         9: "Q5_1", 10: "Q2_K", 11: "Q3_K_S", 12: "Q3_K_M", 13: "Q3_K_L",
         14: "Q4_K_S", 15: "Q4_K_M", 16: "Q5_K_S", 17: "Q5_K_M", 18: "Q6_K",
         32: "BF16"}


def gguf_header(path: Path) -> dict:
    """The key-value header of a GGUF file. Arrays are skipped, not loaded."""
    def rd(f, fmt):
        n = struct.calcsize(fmt)
        b = f.read(n)
        if len(b) != n:
            raise BuildError(f"{path.name}: GGUF header is truncated")
        return struct.unpack(fmt, b)[0]

    def rd_str(f):
        n = rd(f, "<Q")
        if n > 1 << 26:
            raise BuildError(f"{path.name}: implausible GGUF string length {n}")
        return f.read(n).decode("utf-8", "replace")

    def value(f, t):
        if t in GGUF_SCALARS:
            return rd(f, GGUF_SCALARS[t])
        if t == 8:
            return rd_str(f)
        if t == 9:
            et, count = rd(f, "<I"), rd(f, "<Q")
            if et in GGUF_SCALARS:
                f.seek(struct.calcsize(GGUF_SCALARS[et]) * count, 1)
            elif et == 8:
                for _ in range(count):
                    f.seek(rd(f, "<Q"), 1)
            else:
                raise BuildError(f"{path.name}: nested GGUF arrays are not supported")
            return None
        raise BuildError(f"{path.name}: unknown GGUF value type {t}")

    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise BuildError(f"{path.name} is not a GGUF file")
        out = {"__version": rd(f, "<I"), "__tensors": rd(f, "<Q")}
        count = rd(f, "<Q")
        if count > 100_000:
            raise BuildError(f"{path.name}: implausible GGUF key count {count}")
        for _ in range(count):
            key = rd_str(f)
            out[key] = value(f, rd(f, "<I"))
    return out


def check_model(spec: dict, staged: dict, notes: list) -> dict:
    ms = dict(spec.get("model") or {})
    mfile = ms.get("file")
    if mfile not in staged:
        raise BuildError("a model pack needs model.file naming one of its files")
    if spec["license"].get("file") not in staged:
        raise BuildError("a model pack must ship its licence text: license.file "
                         "must name one of its files")
    h = gguf_header(staged[mfile])
    arch = h.get("general.architecture")
    ftype = h.get("general.file_type")
    quant = QUANT.get(ftype, f"file_type {ftype}")
    if ms.get("expect_architecture") and arch != ms["expect_architecture"]:
        raise BuildError(f"{mfile} is architecture {arch!r}, spec expects "
                         f"{ms['expect_architecture']!r}")
    if ms.get("expect_quant") and quant != ms["expect_quant"]:
        raise BuildError(f"{mfile} is {quant}, spec expects {ms['expect_quant']}")
    imatrix = None
    if "quantize.imatrix.dataset" in h:
        imatrix = {"dataset": h.get("quantize.imatrix.dataset"),
                   "entries": h.get("quantize.imatrix.entries_count"),
                   "chunks": h.get("quantize.imatrix.chunks_count")}
    block = {k: v for k, v in ms.items() if not k.startswith("expect_")}
    block.update({"gguf_version": h["__version"], "architecture": arch,
                  "quant": quant, "tensors": h["__tensors"],
                  "size_label": h.get("general.size_label"),
                  "imatrix": imatrix})
    notes.append(f"{mfile}: GGUF v{h['__version']}, {arch}, {quant}, "
                 f"{h['__tensors']} tensors, imatrix "
                 f"{'recorded in header' if imatrix else 'none recorded'}")
    return block


# ----------------------------------------------------------------- corpus

def read_registry(path: Path) -> list:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def check_corpus(spec: dict, staged: dict, packs_root: Path, notes: list):
    for need in ("citations.csv", "corpus.db"):
        if need not in staged:
            raise BuildError(f"a corpus pack needs a file named {need}")
    rows = read_registry(staged["citations.csv"])
    if not rows:
        raise BuildError("citations.csv has no rows")
    lacking = [c for c in REGISTRY_COLUMNS if c not in rows[0]]
    if lacking:
        raise BuildError(f"citations.csv lacks columns {lacking}")

    problems = []
    reg = {}
    for r in rows:
        if r["key"] in reg:
            problems.append(f"key {r['key']} appears twice in citations.csv")
        reg[r["key"]] = r
    uncleared = [f"{r['key']} ({r['license_status'] or 'blank'})" for r in rows
                 if r["license_status"] not in LICENCE_CLEARED]
    if uncleared:
        problems.append("not licence-cleared (hard constraint 6): " + ", ".join(uncleared))
    undated = [r["key"] for r in rows if not r["retrieval_date"].strip()]
    if undated:
        problems.append("no retrieval date, so not reproducible: " + ", ".join(undated))

    # immutable=1: a snapshot never changes, and sqlite then creates no
    # journal or shm files beside it inside the pack.
    uri = staged["corpus.db"].resolve().as_uri() + "?mode=ro&immutable=1"
    try:
        db = sqlite3.connect(uri, uri=True)
        try:
            integrity = db.execute("pragma integrity_check").fetchone()[0]
            meta = {k: (sha, text) for k, sha, text in
                    db.execute("select key, chunk_sha256, text from chunk_meta")}
            vec = db.execute("select sql from sqlite_master "
                             "where name = 'chunk_vec'").fetchone()
            try:
                # sqlite-vec's own rowid table. Readable without the
                # extension; if a future sqlite-vec renames it, the count is
                # reported as unchecked rather than guessed.
                vec_keys = {r[0] for r in db.execute("select id from chunk_vec_rowids")}
            except sqlite3.Error:
                vec_keys = None
        finally:
            db.close()
    except sqlite3.Error as e:
        raise BuildError(f"corpus.db is not readable as the retrieval index: {e}")

    if integrity != "ok":
        problems.append(f"corpus.db integrity_check: {integrity}")
    missing, extra = sorted(set(reg) - set(meta)), sorted(set(meta) - set(reg))
    if missing:
        problems.append(f"in citations.csv but not in corpus.db: {missing}")
    if extra:
        problems.append(f"in corpus.db but not in citations.csv: {extra}")
    drifted = []
    for k in sorted(set(reg) & set(meta)):
        sha, text = meta[k]
        if sha != reg[k]["chunk_sha256"] or \
                hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] != sha:
            drifted.append(k)
    if drifted:
        problems.append("chunk text no longer matches its frozen chunk_sha256 "
                        f"(hard constraint 1): {drifted}")
    dim = None
    m = re.search(r"float\[(\d+)\]", vec[0]) if vec else None
    if not m:
        problems.append("corpus.db has no vec0 table chunk_vec with a float[N] column")
    else:
        dim = int(m.group(1))
        want = (spec.get("corpus") or {}).get("embedding_dim")
        if want is not None and dim != want:
            problems.append(f"vectors are float[{dim}], the spec says {want}")
    if vec_keys is not None and vec_keys != set(reg):
        problems.append("vector keys differ from the registry: "
                        f"{sorted(vec_keys ^ set(reg))}")

    others, clashes = 0, []
    for mf in sorted(packs_root.glob("*/*/" + pl.MANIFEST)):
        if not (pl.NAME_RE.match(mf.parent.name) and pl.NAME_RE.match(mf.parent.parent.name)):
            continue
        try:
            om = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            problems.append(f"cannot read {display(mf)} to check key collisions")
            continue
        if om.get("kind") != "corpus" or om.get("id") == spec["id"]:
            continue
        others += 1
        try:
            okeys = {r["key"] for r in read_registry(mf.parent / pl.FILES_DIR / "citations.csv")}
        except (OSError, KeyError, csv.Error) as e:
            problems.append(f"cannot read the keys of {om.get('id')} to check collisions: {e}")
            continue
        clash = sorted(okeys & set(reg))
        if clash:
            clashes.append(f"{om.get('id')}@{om.get('version')} already uses "
                           f"{', '.join(clash[:5])}{' ...' if len(clash) > 5 else ''}")
    if clashes:
        problems.append("keys must resolve to one chunk across packs (hard "
                        "constraint 9): " + "; ".join(clashes))

    declared = spec["license"].get("status")
    worst = "amber" if any(r["license_status"] == "amber" for r in rows) else "green"
    if not uncleared and declared != worst:
        problems.append(f"license.status is {declared!r} but the registry says "
                        f"{worst!r}; the manifest must state the real conditions")
    if problems:
        raise BuildError("corpus checks failed:\n    - " + "\n    - ".join(problems))

    groups = {}
    for r in rows:
        g = (r["source_id"], r["publisher"], r["url"], r["retrieval_date"],
             r["license_status"], r["attribution"])
        groups.setdefault(g, []).append(r["key"])
    sources = [{"source_id": g[0], "publisher": g[1], "url": g[2],
                "retrieval_date": g[3], "license_status": g[4],
                "attribution": g[5], "keys": keys}
               for g, keys in groups.items()]

    block = dict(spec.get("corpus") or {})
    block.update({"keys": len(rows),
                  "topics": sorted({r["topic"] for r in rows}),
                  "vectors": len(vec_keys) if vec_keys is not None else None})
    notes.append(f"citations.csv: {len(rows)} keys, {len(sources)} sources, "
                 f"all licence {worst}, all with a retrieval date")
    notes.append(f"corpus.db: integrity ok, keys equal the registry, "
                 f"{len(meta)}/{len(reg)} chunk texts match their frozen chunk_sha256, "
                 f"float[{dim}] vectors for "
                 f"{len(vec_keys) if vec_keys is not None else 'unchecked'} keys")
    notes.append(f"no key collision with the {others} other corpus pack(s) in "
                 f"{display(packs_root)}")
    return block, sources


# --------------------------------------------------------------- licence

def verbatim_quotes(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "verbatim" and isinstance(v, str):
                yield v
            else:
                yield from verbatim_quotes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from verbatim_quotes(v)


def _ws(s: str) -> str:
    return " ".join(s.replace(" ", " ").split())


def check_licence(lic: dict, staged: dict, notes: list):
    for k in ("file", "official_copy"):
        if lic.get(k) and lic[k] not in staged:
            raise BuildError(f"license.{k} {lic[k]!r} is not one of the pack's files")
    quotes = list(verbatim_quotes(lic))
    if not quotes:
        return
    if lic.get("file") not in staged:
        raise BuildError("the licence quotes text as verbatim, but license.file "
                         "does not name one of the pack's files")
    text = _ws(staged[lic["file"]].read_text(encoding="utf-8"))
    for q in quotes:
        if _ws(q) not in text:
            raise BuildError(f"quoted as verbatim but not in {lic['file']}: "
                             f"{q[:90]!r}{' (truncated)' if len(q) > 90 else ''}")
    notes.append(f"{len(quotes)} licence quote(s) marked verbatim appear word for "
                 f"word in {lic['file']}")


# ------------------------------------------------------------------ build

def dump_manifest(m: dict) -> bytes:
    return (json.dumps(m, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _comparable(m: dict) -> dict:
    return {k: v for k, v in m.items() if k != "built"}


def build(spec_path: Path, packs_root: Path) -> int:
    spec = load_spec(spec_path)
    pid, ver = spec["id"], spec["version"]
    print(f"build {pid}@{ver} ({spec['kind']}) from {display(spec_path)}")
    t0 = time.time()

    sources = {}
    for f in spec["files"]:
        src = source_path(f["source"])
        if not src.is_file():
            raise BuildError(f"{f['path']}: source {src} is not a file")
        sources[f["path"]] = src

    id_dir = packs_root / pid
    target = id_dir / ver
    id_dir.mkdir(parents=True, exist_ok=True)
    # A leading dot fails NAME_RE, so the node never lists a build in progress.
    staging = id_dir / f".staging-{ver}-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        staged, entries = {}, []
        for f in spec["files"]:
            dst = staging / pl.FILES_DIR / f["path"]
            how = snapshot(sources[f["path"]], dst)
            t = time.time()
            sha = pl.sha256_file(dst)
            size = dst.stat().st_size
            if f.get("sha256") and sha != f["sha256"]:
                raise BuildError(f"{f['path']}: sha256 {sha} is not the "
                                 f"{f['sha256']} the spec pins. Refusing to "
                                 f"pack a different file.")
            pin = "  matches the spec pin" if f.get("sha256") else ""
            print(f"  {f['path']:<14} {pl.human(size):>10}  {how}  "
                  f"sha256 {sha}  {time.time() - t:.1f} s{pin}")
            staged[f["path"]] = dst
            entries.append({"path": f["path"], "size": size, "sha256": sha})

        notes = []
        lic = json.loads(json.dumps(spec["license"]))
        check_licence(lic, staged, notes)
        extra = {}
        if spec["kind"] == "model":
            extra["model"] = check_model(spec, staged, notes)
        elif spec["kind"] == "corpus":
            extra["corpus"], lic["sources"] = check_corpus(spec, staged, packs_root, notes)

        entries.sort(key=lambda e: e["path"])
        manifest = {"format": pl.FORMAT, "id": pid, "version": ver,
                    "kind": spec["kind"], "title": spec["title"]}
        for k in ("description", "language", "region"):
            if k in spec:
                manifest[k] = spec[k]
        manifest["built"] = pl.utc_now()
        manifest["license"] = lic
        manifest.update(extra)
        manifest["provenance"] = {
            "built_by": "07-distribute/build_pack.py",
            "sources": {f["path"]: display(sources[f["path"]]) for f in spec["files"]}}
        manifest["files"] = entries
        manifest["size"] = sum(e["size"] for e in entries)
        manifest["pack_sha256"] = pl.pack_digest(entries)
        errs = pl.manifest_problems(manifest)
        if errs:
            raise BuildError("the manifest this build produced is invalid, which "
                             "is a bug: " + "; ".join(errs))
        for n in notes:
            print(f"  check: {n}")

        if target.exists():
            try:
                old = json.loads((target / pl.MANIFEST).read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise BuildError(f"{display(target)} exists but its manifest is "
                                 f"unreadable ({e}). Not touching it.")
            if _comparable(old) == _comparable(manifest):
                print(f"already built, identical: {display(target)}, "
                      f"pack_sha256 {old['pack_sha256']}")
                return 0
            what = ("different files" if old.get("pack_sha256") != manifest["pack_sha256"]
                    else "the same files but a different manifest")
            raise BuildError(f"{pid}@{ver} is already built with {what}. A version "
                             f"is immutable: bump the version in the spec.")

        (staging / pl.MANIFEST).write_bytes(dump_manifest(manifest))
        os.rename(staging, target)
        print(f"  size {pl.human(manifest['size'])} ({manifest['size']:,} bytes)  "
              f"pack_sha256 {manifest['pack_sha256']}")
        print(f"built {display(target)} in {time.time() - t0:.1f} s")
        return 0
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build immutable packs from specs.")
    ap.add_argument("specs", nargs="+", type=Path)
    ap.add_argument("--packs", type=Path, default=DEFAULT_PACKS,
                    help=f"packs directory (default {display(DEFAULT_PACKS)})")
    args = ap.parse_args(argv)
    rc = 0
    for s in args.specs:
        try:
            rc = max(rc, build(s, args.packs))
        except BuildError as e:
            print(f"REFUSED: {e}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
