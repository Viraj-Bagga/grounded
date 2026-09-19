#!/usr/bin/env python3
"""Smoke test the BM25 + vector blend against the five discrimination cases.

    python 04-retrieval/smoke_hybrid.py                 # alpha 0.5, the default
    python 04-retrieval/smoke_hybrid.py --alpha 0.0     # pure BM25, diagnostic
    python 04-retrieval/smoke_hybrid.py --sweep         # every alpha, diagnostic

Query is symptom + timeline, which was the best of the three modes tried on the
dense-only run.

ON THE SWEEP. It is a diagnostic, not a selection procedure. Picking the alpha
that makes the table look best over five cases is fitting the weight to the test
set, and the test set is four scored cases with one green in it. If the blend
does not surface the ACS chunks at the principled default, that is the finding
and no amount of sweeping changes it.

ON THE EXPECTED CHUNKS. `discrimination_test.py` hand-assigned them, and they
have never been checked. They are the target here, but a miss can mean the
retriever is wrong OR the expectation is. CP-ACS-002 is worth reading before
blaming the retriever for skipping it.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "01-data" / "eval"))
from discrimination_test import CASES               # noqa: E402
from hybrid import HybridRetriever                  # noqa: E402
from retrieve import PROMPT_EVAL_TOK_PER_S          # noqa: E402


def run(r, alpha, k, verbose=True):
    rows, all_keys, total_tokens = [], set(), 0
    for case in CASES:
        q = case["symptom"] + "\n" + case["timeline"]
        hits = r.search(q, k, alpha)
        got = [h[0] for h in hits]
        want = case["chunks"]
        all_keys.update(got)
        toks = sum(h[4] for h in hits)
        total_tokens += toks
        hit = [x for x in want if x in got]
        rows.append((case, got, want, hit, toks, hits))
    return rows, all_keys, total_tokens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    r = HybridRetriever()

    if args.sweep:
        print("DIAGNOSTIC SWEEP, not a weight selection. query = symptom+timeline\n")
        print(f"{'alpha':>6}  {'expected found':>14}  {'distinct chunks':>15}  "
              f"{'ACS-001/002 on red-acs':>23}  {'tokens':>7}")
        for a in [0.0, 0.25, 0.5, 0.75, 1.0]:
            rows, keys, toks = run(r, a, args.k)
            found = sum(len(h) for _c, _g, _w, h, _t, _hh in rows)
            want = sum(len(w) for _c, _g, w, _h, _t, _hh in rows)
            acs = [x for x in rows[0][1] if x in ("CP-ACS-001", "CP-ACS-002")]
            print(f"{a:>6.2f}  {found:>6}/{want:<7}  {len(keys):>15}  "
                  f"{str(acs or 'neither'):>23}  {toks:>7}")
        return

    print(f"HYBRID SMOKE TEST, top-{args.k}, alpha={args.alpha} "
          f"({'pure BM25' if args.alpha == 0 else 'pure vector' if args.alpha == 1 else 'blend'}), "
          f"query = symptom+timeline\n")

    rows, all_keys, total_tokens = run(r, args.alpha, args.k)
    exact = partial = miss = 0
    for case, got, want, hit, toks, hits in rows:
        if set(want) <= set(got):
            sym, verdict = "++", "ALL EXPECTED RETURNED"
            exact += 1
        elif hit:
            sym, verdict = "+-", f"PARTIAL, {len(hit)}/{len(want)}"
            partial += 1
        else:
            sym, verdict = "--", "NONE OF THE EXPECTED"
            miss += 1
        probe = "  (PROBE)" if case.get("probe") else ""
        print(f"{sym} {case['id']:<22} {verdict}{probe}")
        print(f"     expected : {want}")
        print(f"     returned : {got}")
        for key, sc, cos, bm, t, cat in hits:
            mark = "*" if key in want else " "
            print(f"       {mark} {key:<16} blend={sc:.3f} cos={cos:.3f} "
                  f"bm25={bm:5.2f}  {t:>4} tok  [{cat or 'uncategorised'}]")
        print(f"     retrieved {toks} tokens, about "
              f"{toks / PROMPT_EVAL_TOK_PER_S:.1f} s of prompt eval\n")

    print("=" * 66)
    print(f"all-expected {exact}   partial {partial}   none {miss}")
    print(f"distinct chunks across the 5 cases: {len(all_keys)} of 22")
    print(f"  {sorted(all_keys)}")
    red = rows[0][1]
    acs = [x for x in red if x in ("CP-ACS-001", "CP-ACS-002")]
    print(f"CP-ACS-001 or CP-ACS-002 on red-acs: "
          f"{acs if acs else 'NEITHER'}")
    print(f"total retrieved {total_tokens} tokens, mean "
          f"{total_tokens / len(rows):.0f} per case, about "
          f"{total_tokens / len(rows) / PROMPT_EVAL_TOK_PER_S:.1f} s of prompt "
          f"eval per case")


if __name__ == "__main__":
    main()
