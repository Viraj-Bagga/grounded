#!/usr/bin/env python3
"""Score dense and blended retrieval against the reviewed answer keys.

    python 04-retrieval/score_keys.py
    python 04-retrieval/score_keys.py --k 3 --old     # also show the old keys

Scores against `RETRIEVAL_KEYS` in discrimination_test.py, which are PROPOSED
and not yet signed off, and reports the `MUST_NOT_RETRIEVE` violations
separately because "missing a chunk it should have" and "returning a chunk it
must not" are different failures with different consequences.

probe-costo-unmatched is excluded from scoring by design: its key is empty
because no chunk in the corpus describes costochondritis. It is still listed so
what retrieval does for an unmatched case stays visible.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "01-data" / "eval"))
from discrimination_test import (CASES, MUST_NOT_RETRIEVE,  # noqa: E402
                                 RETRIEVAL_KEYS)
from hybrid import HybridRetriever                          # noqa: E402
from retrieve import PROMPT_EVAL_TOK_PER_S                  # noqa: E402


def score(r, alpha, k, keys, label):
    print(f"\n{'=' * 72}\n{label}  (alpha={alpha}, top-{k}, query=symptom+timeline)")
    print("=" * 72)
    found = want_total = 0
    violations = []
    total_tokens = 0
    for case in CASES:
        cid = case["id"]
        q = case["symptom"] + "\n" + case["timeline"]
        hits = r.search(q, k, alpha)
        got = [h[0] for h in hits]
        toks = sum(h[4] for h in hits)
        total_tokens += toks
        want = keys[cid]
        scored = bool(want)
        hit = [x for x in want if x in got]
        if scored:
            found += len(hit)
            want_total += len(want)
        bad = [x for x in MUST_NOT_RETRIEVE.get(cid, []) if x in got]
        violations += [(cid, x) for x in bad]

        if not scored:
            tag = "UNSCORED (empty key by design)"
        elif len(hit) == len(want):
            tag = f"ALL {len(want)}/{len(want)}"
        elif hit:
            tag = f"PARTIAL {len(hit)}/{len(want)}"
        else:
            tag = f"NONE 0/{len(want)}"
        print(f"\n  {cid:<22} {tag}")
        print(f"     key      : {want or '(none)'}")
        print(f"     returned : {got}")
        if bad:
            print(f"     MUST-NOT-RETRIEVE VIOLATION: {bad}")
        print(f"     {toks} tokens, about {toks / PROMPT_EVAL_TOK_PER_S:.1f} s "
              f"of prompt eval")

    pct = 100 * found / want_total if want_total else 0
    print(f"\n  scored recall: {found}/{want_total} = {pct:.0f}%")
    print(f"  must-not-retrieve violations: "
          f"{violations if violations else 'none'}")
    print(f"  total {total_tokens} tokens, mean "
          f"{total_tokens / len(CASES):.0f} per case")
    return found, want_total, len(violations), total_tokens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--old", action="store_true",
                    help="also score against the original unreviewed keys")
    args = ap.parse_args()

    r = HybridRetriever()
    print("SCORED AGAINST THE FROZEN REVIEWED KEYS")
    print("Approved by Viraj 2026-09-17. Changing one is a clinical decision.")

    rows = []
    for alpha, label in [(1.0, "DENSE ONLY, vector"), (0.5, "BLEND, BM25 + vector"),
                         (0.0, "BM25 ONLY")]:
        rows.append((label, *score(r, alpha, args.k, RETRIEVAL_KEYS, label)))

    if args.old:
        old = {c["id"]: c["chunks"] for c in CASES}
        for alpha, label in [(1.0, "OLD KEYS, dense"), (0.5, "OLD KEYS, blend")]:
            score(r, alpha, args.k, old, label)

    print(f"\n{'=' * 72}\nSUMMARY, frozen keys")
    print(f"{'config':<26} {'recall':>10} {'violations':>11} {'tokens':>8}")
    for label, f, w, v, t in rows:
        print(f"{label:<26} {f}/{w} = {100*f/w:>3.0f}%  {v:>11} {t:>8}")


if __name__ == "__main__":
    main()
