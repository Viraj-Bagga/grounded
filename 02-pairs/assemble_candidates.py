#!/usr/bin/env python3
"""Assemble a candidates file from a base file plus authored content modules.

    python 02-pairs/assemble_candidates.py \
        --base review/candidates-60.jsonl \
        --out  review/candidates-120.jsonl \
        review/content-p1-contrast-2026-09-19.py review/content-p2-newchunks-2026-09-19.py

Why this exists. `generate_pairs.py scaffold` builds slots at random from the
registry, which is right when the plan is "300 pairs across the corpus" and
wrong when the plan is a named list of axes and chunks. These content modules
carry the slot and the clinical content together: one dict per pair, with a
`slot` key for the mechanics and profile / symptoms / timeline / answer for the
content.

It writes the base rows through unchanged, byte for byte where nothing needed
re-encoding, then appends one unfilled row per new pair. `fill_pairs.py` then
applies the content, which is what enforces citations being a subset of the
slot's keys and a red carrying no follow-up questions. Refuses to overwrite an
existing --out without --force, and refuses to reuse an id from the base.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_module(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("content", nargs="+")
    ap.add_argument("--base", default="review/candidates-60.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    base = Path(args.base) if Path(args.base).is_absolute() else HERE / args.base
    out = Path(args.out) if Path(args.out).is_absolute() else HERE / args.out
    if out.exists() and not args.force:
        sys.exit(f"{out} exists. Pass --force to rebuild it.")

    rows = [json.loads(l) for l in base.read_text(encoding="utf-8").splitlines() if l.strip()]
    seen = {r["id"] for r in rows}
    added = 0
    for c in args.content:
        path = Path(c) if Path(c).is_absolute() else HERE / c
        mod = load_module(path)
        for pid, spec in mod.PAIRS.items():
            if pid in seen:
                sys.exit(f"{pid} in {path.name} is already an id in {base.name}")
            seen.add(pid)
            rows.append({"id": pid, **spec["slot"], "filled": False})
            added += 1

    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")
    print(f"{out}: {len(rows)} rows ({len(rows) - added} from {base.name}, {added} new slots)")
    print("now run fill_pairs.py for each content module with --file", out)


if __name__ == "__main__":
    main()
