#!/usr/bin/env python3
"""Fetch, chunk and freeze the regional add-on packs.

    python 07-distribute/regional/build_regional.py fetch
    python 07-distribute/regional/build_regional.py chunk
    python 07-distribute/regional/build_regional.py freeze [--pack ID] [--dry-run] [--out DIR]

A BUILD TOOL, not part of the node. server.py and client.py are stdlib only
and stay that way; this reuses 01-data's extractor and word-piece counter so
the packs are chunked by the same code as the base corpus, and it only reads
from 01-data, never writes there. The base registry stays public domain and
frozen (hard constraint 1).

WHAT IS FROZEN WHERE. Each pack owns its chunks and its registry, under
07-distribute/regional/<pack>/. Nothing is appended to 01-data/citations.csv:
a pack that contains WHO text is CC BY-NC-SA, and mixing it into the base
registry would put that licence on the base pack.

THE CUTS ARE DATA, in sources.yaml, as `from` and `to` text anchors. A chunk
boundary is a clinical decision and belongs in a file a human can read and
argue with, not in a heuristic. The RHD cut, splitting acute rheumatic fever
from valve damage, is Viraj's call of 2026-09-19 and is written there.

KEYS ARE IMMUTABLE ONCE FROZEN, per pack, the same rule as the base corpus.
freeze refuses to rewrite a key whose text has changed and says so; delete the
pack directory deliberately if a re-chunk is really what you want. The shared
TB chunks are byte-identical in both packs and carry the same keys: a key must
resolve to one chunk even when two packs are installed.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "01-data"))

from build_corpus import TokenCounter, extract_main   # noqa: E402

RAW = HERE / "raw"
REVIEW = HERE / "review"
FETCH_LOG = HERE / "fetch_log.json"
CEILING = 256          # hard constraint 2, all-MiniLM-L6-v2 truncates here
UA = "steel26-corpus/1.0 (hackathon prototype; offline triage; contact virajboj@gmail.com)"
COLUMNS = ["key", "topic", "subtopic", "expected_category", "source_id", "publisher",
           "url", "retrieval_date", "license_status", "attribution", "token_count",
           "chunk_sha256"]


def load_manifest():
    import yaml
    with open(HERE / "sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def chunk_sha(text):
    """Matches 01-data: first 16 hex of the sha256 of the chunk text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- fetch

def cmd_fetch(args, man):
    RAW.mkdir(parents=True, exist_ok=True)
    log = json.loads(FETCH_LOG.read_text()) if FETCH_LOG.exists() else {}
    for sid, src in man["sources"].items():
        if args.source and sid != args.source:
            continue
        t = time.time()
        req = Request(src["url"], headers={"User-Agent": UA})
        with urlopen(req, timeout=60) as r:
            body = r.read()
        path = RAW / f"{sid}.html"
        path.write_bytes(body)
        log[sid] = {"url": src["url"], "retrieved": date.today().isoformat(),
                    "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()[:16],
                    "publisher": src["publisher"]}
        print(f"  {sid:<12} {len(body):>8} bytes  sha256 {log[sid]['sha256']}  "
              f"{time.time() - t:.1f} s  -> {path.relative_to(REPO)}")
    FETCH_LOG.write_text(json.dumps(log, indent=2, sort_keys=True) + "\n")
    print(f"fetch log: {FETCH_LOG.relative_to(REPO)}")
    return 0


# ---------------------------------------------------------------- chunk

def section_blocks(html, selectors, section):
    for head, items in extract_main(html, selectors):
        if head.strip() == section:
            return items
    raise SystemExit(f"section {section!r} not found. The page changed: re-check before chunking.")


def cut(items, frm, to):
    """The blocks from the one starting with `frm` up to, not including, the
    one starting with `to`. Anchors are the source's own sentences."""
    start = next((i for i, (_, t) in enumerate(items) if t.startswith(frm)), None)
    if start is None:
        raise SystemExit(f"cut anchor {frm!r} is not in the page any more. Re-check before chunking.")
    if to is None:
        return items[start:]
    end = next((i for i, (_, t) in enumerate(items) if i > start and t.startswith(to)), None)
    if end is None:
        raise SystemExit(f"cut anchor {to!r} is not in the page any more. Re-check before chunking.")
    return items[start:end]


def build_chunks(man, counter):
    """[(pack_ids, source_id, block, key, text, tokens)], in manifest order."""
    log = json.loads(FETCH_LOG.read_text()) if FETCH_LOG.exists() else {}
    out = []
    for sid, src in man["sources"].items():
        packs = [pid for pid, p in man["packs"].items() if sid in p["sources"]]
        html = (RAW / f"{sid}.html").read_text(encoding="utf-8", errors="replace")
        for b in src["blocks"]:
            items = cut(section_blocks(html, src["selectors"], b["section"]), b["from"], b.get("to"))
            lines = [t for _, t in items]
            if src.get("lead") and not lines[0].startswith(src["lead"][:30]):
                # A list cut across chunks loses the sentence that framed it.
                lines.insert(0, src["lead"])
            text = "\n".join(lines).strip()
            n = counter.count(text)
            if n > CEILING:
                raise SystemExit(f"{src['key_prefix']}-{b['suffix']} is {n} word-pieces, over the "
                                 f"{CEILING} ceiling. Split it; never truncate (hard constraint 2).")
            out.append({"packs": packs, "source_id": sid, "src": src, "block": b,
                        "key": f"{src['key_prefix']}-{b['suffix']}", "text": text,
                        "tokens": n, "retrieved": (log.get(sid) or {}).get("retrieved", "")})
    return out


def cmd_chunk(args, man):
    counter = TokenCounter()
    chunks = build_chunks(man, counter)
    REVIEW.mkdir(parents=True, exist_ok=True)
    lines = [f"Regional pack candidates, {date.today().isoformat()}. NOT FROZEN.",
             "Cuts come from sources.yaml, which records why each one is where it is.",
             "Review the boundaries, then freeze. Keys are immutable after that.", ""]
    for c in chunks:
        lines += ["=" * 92,
                  f"{c['key']}  {c['tokens']} word-pieces  packs: {', '.join(c['packs'])}",
                  f"  source     {c['source_id']}  {c['src']['publisher']}",
                  f"  section    {c['block']['section']}  [{c['block'].get('subtopic', '')}]",
                  f"  category   {c['block'].get('category') or '(none)'}",
                  f"  licence    {c['src']['license_status']}  {c['src']['attribution']}",
                  f"  why here   {c['block'].get('note', '')}", "", c["text"], ""]
    text = "\n".join(lines) + "\n"
    (REVIEW / f"candidates-{date.today().isoformat()}.txt").write_text(text)
    print(text)
    print(f"{len(chunks)} candidate chunks, none over {CEILING} word-pieces.")
    print(f"written to {(REVIEW / f'candidates-{date.today().isoformat()}.txt').relative_to(REPO)}")
    return 0


# ---------------------------------------------------------------- freeze

def cmd_freeze(args, man):
    counter = TokenCounter()
    chunks = build_chunks(man, counter)
    # --out rehearses the whole freeze somewhere else, so the chain can be
    # tested end to end before a key is frozen in the repo. Viraj freezes.
    root_dir = Path(args.out).resolve() if args.out else HERE
    rc = 0
    for pid, pack in man["packs"].items():
        if args.pack and pid != args.pack:
            continue
        mine = [c for c in chunks if pid in c["packs"]]
        root = root_dir / pid
        cdir = root / "chunks"
        rows, changed, new = [], [], []
        for c in mine:
            path = cdir / f"{c['key']}.txt"
            if path.exists():
                old = path.read_text(encoding="utf-8")
                if old != c["text"]:
                    changed.append(c["key"])
            else:
                new.append(c["key"])
            rows.append({"key": c["key"], "topic": c["src"]["topic"],
                         "subtopic": c["block"].get("subtopic", ""),
                         "expected_category": c["block"].get("category") or "",
                         "source_id": c["source_id"], "publisher": c["src"]["publisher"],
                         "url": c["src"]["url"], "retrieval_date": c["retrieved"],
                         "license_status": c["src"]["license_status"],
                         "attribution": c["src"]["attribution"],
                         "token_count": c["tokens"], "chunk_sha256": chunk_sha(c["text"])})
        print(f"\n{pid}: {len(rows)} chunks, {len(new)} new, {len(changed)} changed")
        for r in rows:
            print(f"  {r['key']:<14} {r['token_count']:>4} wp  {r['license_status']:<6} "
                  f"{r['chunk_sha256']}  {r['subtopic']}")
        if changed:
            print(f"  REFUSED: {', '.join(changed)} are frozen and their text has changed. "
                  f"Keys are immutable (hard constraint 1). Delete {root.relative_to(REPO)} "
                  f"deliberately if a re-chunk is really what you want.")
            rc = 1
            continue
        if args.dry_run:
            print("  dry run, nothing written")
            continue
        cdir.mkdir(parents=True, exist_ok=True)
        for c in mine:
            (cdir / f"{c['key']}.txt").write_text(c["text"], encoding="utf-8")
        with open(root / "citations.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        (root / "PACK.md").write_text(pack_readme(pid, pack, rows), encoding="utf-8")
        # What the demo reads to show the region selector. It never changes
        # retrieval; the page says so.
        (root / "pack.json").write_text(json.dumps({
            "id": pid, "name": pack["name"], "title": pack["title"],
            "description": " ".join(str(pack.get("description", "")).split()),
            "region": pack["region"], "requires": pack["requires"],
            "emergency_number": pack["emergency_number"],
            "emergency_note": " ".join(str(pack["emergency_note"]).split()),
            "license": {"name": pack["license"]["name"], "status": pack["license"]["status"],
                        "commercial": pack["license"]["commercial"],
                        "plain": " ".join(str(pack["license"]["plain"]).split())},
            "wired_into_retrieval": False,
            "chunks": [{"key": r["key"], "topic": r["topic"], "subtopic": r["subtopic"],
                        "publisher": r["publisher"], "url": r["url"],
                        "license_status": r["license_status"], "attribution": r["attribution"],
                        "token_count": r["token_count"]} for r in rows],
        }, indent=2) + "\n", encoding="utf-8")
        (root / "LICENCE.txt").write_text(licence_file(pid, pack, rows, man), encoding="utf-8")
        spec_dir = root_dir if args.out else REPO / "07-distribute" / "specs"
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec_path = spec_dir / f"regional-{pid}.json"
        spec_path.write_text(json.dumps(pack_spec(pid, pack, rows, root), indent=2) + "\n",
                             encoding="utf-8")
        try:
            where = root.relative_to(REPO)
        except ValueError:
            where = root
        print(f"  written to {where}, spec {spec_path.name}")
    return rc


def pack_readme(pid, pack, rows):
    lic = pack["license"]
    sources = sorted({(r["publisher"], r["url"], r["license_status"]) for r in rows})
    lines = [f"# {pack['title']}", "",
             "EXPERIMENTAL add-on pack. An OVERLAY on `corpus-base`, never a swap:",
             f"selecting this region gives the base corpus plus this pack. Requires "
             f"`{pack['requires']}`.", "",
             "**Not wired into retrieval.** The demo shows which pack is active and what it",
             "holds; retrieval still uses the base corpus alone. Viraj's call, 2026-09-19.", "",
             f"## Licence: {lic['name']}", "",
             " ".join(str(lic["plain"]).split()), "",
             f"Commercial use: {'allowed' if lic.get('commercial') else 'NOT ALLOWED'}.", "",
             "## Emergency number", "",
             f"{pack['emergency_number'] or 'none, use local emergency services'}. "
             + " ".join(str(pack["emergency_note"]).split()), "",
             "## Sources", ""]
    for pub, url, status in sources:
        lines.append(f"- {pub}, {url} ({status})")
    lines += ["", "## Chunks", "", "| key | words | licence | attribution |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['key']} | {r['token_count']} | {r['license_status']} | "
                     f"{r['attribution']} |")
    return "\n".join(lines) + "\n"


LICENCE_URL = "https://creativecommons.org/licenses/by-nc-sa/3.0/igo/"


def licence_file(pid, pack, rows, man):
    """Ships inside the pack. CC BY-NC-SA needs the licence identified and the
    attribution carried; the full legal code lives at the URL, as Creative
    Commons intends, and every per-source line is here verbatim."""
    lic = pack["license"]
    out = [f"{pack['title']}", "",
           f"LICENCE: {lic['name']}", f"Legal code: {LICENCE_URL}", "",
           " ".join(str(lic["plain"]).split()), "",
           "COMMERCIAL USE IS NOT PERMITTED under this licence." if not lic.get("commercial")
           else "Commercial use is permitted.", "",
           "ATTRIBUTION, one line per source, as the licensor requires:", ""]
    for pub, url, attribution, status in sorted({(r["publisher"], r["url"], r["attribution"],
                                                  r["license_status"]) for r in rows}):
        out += [f"  {attribution}", f"    {pub}", f"    {url}", f"    licence status: {status}", ""]
    notes = {man["sources"][sid]["license_note"] for sid in pack["sources"]}
    out += ["WHERE THE LICENCE COMES FROM:", ""]
    for n in sorted(notes):
        out.append("  " + " ".join(str(n).split()))
    out += ["", "The base corpus pack this one is layered on is a separate pack, US",
            "government public domain, and is not affected by this licence."]
    return "\n".join(out) + "\n"


def pack_spec(pid, pack, rows, root):
    """The build_pack spec, generated from what was frozen rather than kept by
    hand, so the pack can only contain what the registry lists."""
    src = lambda name: str((root / name).relative_to(REPO)) if str(root).startswith(str(REPO)) \
        else str(root / name)
    files = [{"path": "citations.csv", "source": src("citations.csv")},
             {"path": "PACK.md", "source": src("PACK.md")},
             {"path": "LICENCE.txt", "source": src("LICENCE.txt")},
             {"path": "pack.json", "source": src("pack.json")}]
    for r in rows:
        files.append({"path": f"chunks/{r['key']}.txt",
                      "source": src(f"chunks/{r['key']}.txt"),
                      "sha256": None})
    for f in files:
        f.pop("sha256", None)
    return {"id": f"regional-{pid}", "version": date.today().strftime("%Y.%m.%d"),
            "kind": "overlay", "title": pack["title"],
            "description": " ".join(str(pack.get("description", "")).split())
            + " EXPERIMENTAL. An add-on layered on the base corpus, never a swap."
            " Not wired into retrieval: the demo shows what this pack holds and"
            " keeps retrieving from the base corpus alone.",
            "language": "en", "region": pack["region"], "requires": pack["requires"],
            "license": {"name": pack["license"]["name"], "status": pack["license"]["status"],
                        "note": " ".join(str(pack["license"]["plain"]).split()),
                        "verbatim": [f"LICENCE: {pack['license']['name']}"]},
            "overlay": {"emergency_number": pack["emergency_number"],
                        "emergency_note": " ".join(str(pack["emergency_note"]).split())},
            "files": files}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("--source")
    sub.add_parser("chunk")
    z = sub.add_parser("freeze")
    z.add_argument("--pack")
    z.add_argument("--dry-run", action="store_true")
    z.add_argument("--out", help="freeze into DIR instead of the repo, to rehearse")
    args = ap.parse_args(argv)
    man = load_manifest()
    return {"fetch": cmd_fetch, "chunk": cmd_chunk, "freeze": cmd_freeze}[args.cmd](args, man)


if __name__ == "__main__":
    raise SystemExit(main())
