#!/usr/bin/env python3
"""Epic 4 smoke test: does retrieval return the right chunks for the five
discrimination cases?

    python 04-retrieval/smoke_test.py
    python 04-retrieval/smoke_test.py --k 5 --query-mode symptom+timeline

WHAT THIS DOES AND DOES NOT MEASURE. It compares what the index returns against
the chunk list each case was hand-assigned in discrimination_test.py. Those
hand-assigned lists are the "matched" condition every eval run so far has used,
so this answers a question those runs could not: would real retrieval have
supplied them, or has every measurement so far been running on chunks a human
picked?

It says nothing about whether the verdict improves. Retrieval quality and
triage quality are separate, and the base model's red bias is settled as not
being a retrieval problem (see build-log 2026-09-17, no-chunk probe).

probe-costo-unmatched is expected to MISS, and that is the point of it: no
chunk in the corpus describes costochondritis, CP-COSTO is a documented gap in
sources.yaml. Its hand-assigned list is what a similarity search was guessed to
surface. This test finally checks that guess.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "01-data" / "eval"))
from discrimination_test import CASES            # noqa: E402
from retrieve import PROMPT_EVAL_TOK_PER_S, Retriever   # noqa: E402


def build_query(case, mode):
    if mode == "symptom":
        return case["symptom"]
    if mode == "symptom+timeline":
        return case["symptom"] + "\n" + case["timeline"]
    if mode == "symptom+profile":
        return case["profile"] + "\n" + case["symptom"]
    raise ValueError(mode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--query-mode", default="symptom",
                    choices=["symptom", "symptom+timeline", "symptom+profile"])
    args = ap.parse_args()

    r = Retriever()
    print(f"RETRIEVAL SMOKE TEST, top-{args.k}, query = {args.query_mode}")
    print("expected = the chunks the case was hand-assigned in "
          "discrimination_test.py\n")

    grand_total = 0
    exact = partial = miss = 0
    for case in CASES:
        q = build_query(case, args.query_mode)
        hits = r.search(q, args.k)
        got = [h[0] for h in hits]
        want = case["chunks"]
        overlap = [k for k in got if k in want]
        missing = [k for k in want if k not in got]
        total = sum(h[2] for h in hits)
        grand_total += total

        if set(want) <= set(got):
            verdict, sym = "ALL EXPECTED RETURNED", "++"
            exact += 1
        elif overlap:
            verdict, sym = f"PARTIAL, {len(overlap)}/{len(want)}", "+-"
            partial += 1
        else:
            verdict, sym = "NONE OF THE EXPECTED", "--"
            miss += 1

        probe = "  (PROBE, expected to miss)" if case.get("probe") else ""
        print(f"{sym} {case['id']:<22} {verdict}{probe}")
        print(f"     expected : {want}")
        print(f"     returned : {got}")
        if missing:
            print(f"     not returned: {missing}")
        for key, dist, toks, _text, cat in hits:
            mark = "*" if key in want else " "
            print(f"       {mark} {key:<16} d={dist:.4f}  {toks:>4} tok  "
                  f"[{cat or 'uncategorised'}]")
        print(f"     retrieved {total} tokens, about "
              f"{total / PROMPT_EVAL_TOK_PER_S:.1f} s of prompt eval\n")

    scored = [c for c in CASES if not c.get("probe")]
    print(f"{'=' * 62}")
    print(f"scored cases: {len(scored)}   all-expected {exact}  "
          f"partial {partial}  none {miss}   (includes the probe in the counts "
          f"only if it landed)")
    print(f"total retrieved across all {len(CASES)} cases: {grand_total} tokens, "
          f"mean {grand_total / len(CASES):.0f} per case")
    print(f"mean prompt-eval cost per case: "
          f"{grand_total / len(CASES) / PROMPT_EVAL_TOK_PER_S:.1f} s at "
          f"{PROMPT_EVAL_TOK_PER_S:.0f} tok/s, retrieved context only, "
          f"before the system prompt and the case text")


if __name__ == "__main__":
    main()
