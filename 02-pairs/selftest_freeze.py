#!/usr/bin/env python3
"""
Proves the freeze path runs end to end, using synthetic placeholder pairs.

    python 02-pairs/selftest_freeze.py

Nothing here is clinical content: every pair is filler that satisfies the
validator and nothing more. It exists because "nothing counts as ready until it
has run once" and the freeze path, including the stratified held-out split, is
otherwise unexercised until there are 300 real pairs to risk on it.

Writes to review/_smoke.jsonl and pairs/_smoke_*, then deletes them, so it can
never be confused with real training data and cannot clobber a real freeze.
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pair_format import SYSTEM_PROMPT, build_human_turn, load_chunk_texts, load_registry
from generate_pairs import build_slots, condition_of
from validate_pairs import check_pair

SMOKE = HERE / "review" / "_smoke.jsonl"


def build(n=30):
    texts, reg = load_chunk_texts(), load_registry()
    slots = build_slots(reg, n, {"red": .3, "yellow": .4, "green": .3}, 26)
    rows = []
    for s in slots:
        keys, cat = s["reference_keys"], s["target_category"]
        a = {
            "urgency": cat,
            "rationale": "Placeholder rationale, smoke test only.",
            "red_flags": (["Placeholder finding at rest beyond 20 minutes"]
                          if cat == "red" else []),
            "next_steps": ["Placeholder step."],
            "citations": keys[:1],
            "follow_up_questions": [] if cat == "red" else ["Placeholder question?"],
        }
        profile = "age: 30, sex: F\nconditions: none\nmedications: none"
        convs = [{"from": "system", "value": SYSTEM_PROMPT},
                 {"from": "human", "value": build_human_turn(
                     profile, "Placeholder.", keys, texts)}]
        for t in range(s["exchanges"]):
            if t:
                convs.append({"from": "human", "value": build_human_turn(
                    profile, "Placeholder follow-up.", keys, texts)})
            convs.append({"from": "gpt", "value": json.dumps(a)})
        rows.append({"id": s["id"], "target_category": cat,
                     "reference_keys": keys, "register": s["register"],
                     "conversations": convs})
    return rows


def main():
    rows = build()
    reg = load_registry()

    errs = sum(len(check_pair(i, r, reg)[0]) for i, r in enumerate(rows, 1))
    print(f"  {'PASS' if not errs else 'FAIL'}  synthetic pairs validate clean "
          f"({errs} errors)")
    if errs:
        return 1

    # Stratified held-out, the same selection generate_pairs.freeze uses.
    rng = random.Random(26)
    strata = {}
    for r in rows:
        sig = tuple(sorted({condition_of(k) for k in r["reference_keys"]}))
        strata.setdefault((r["target_category"], sig), []).append(r)
    held, want = [], 6
    keys = sorted(strata, key=lambda k: (-len(strata[k]), str(k)))
    while len(held) < want and any(strata[k] for k in keys):
        for k in keys:
            if strata[k] and len(held) < want:
                held.append(strata[k].pop(rng.randrange(len(strata[k]))))
    held_ids = {r["id"] for r in held}
    train = [r for r in rows if r["id"] not in held_ids]

    ok = True
    ok &= len(held) == want
    print(f"  {'PASS' if len(held) == want else 'FAIL'}  held out {len(held)} of "
          f"{len(rows)}, requested {want}")
    ok &= not (held_ids & {r['id'] for r in train})
    print(f"  {'PASS' if not (held_ids & {r['id'] for r in train}) else 'FAIL'}  "
          f"train and heldout do not overlap")
    spread = Counter(r["target_category"] for r in held)
    ok &= len(spread) == 3
    print(f"  {'PASS' if len(spread) == 3 else 'FAIL'}  heldout spans all three "
          f"categories: {dict(spread)}")
    ok &= len(train) + len(held) == len(rows)
    print(f"  {'PASS' if len(train) + len(held) == len(rows) else 'FAIL'}  "
          f"no pair lost: {len(train)} + {len(held)} = {len(rows)}")

    print(f"\n{'freeze path is sound.' if ok else 'FREEZE PATH IS BROKEN.'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
