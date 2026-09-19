#!/usr/bin/env python3
"""Re-measure the scope floor, with colloquial phrasing in the sample.

    python 04-retrieval/calibrate_scope.py
    python 04-retrieval/calibrate_scope.py --floor 0.33

WHY THIS EXISTS. The 2026-09-17 calibration used 8 in-scope queries, and every
one of them was written the way a chunk is written. It reported worst in-scope
0.482 and concluded a 0.40 floor was safe with 0.082 of margin.

That sample could not see the failure. On 2026-09-18 a live demo query, "Chest
got tight walking up the hill to my car, same as it does most weeks. Sat on the
wall. It has not shifted, it has been half an hour now", was REFUSED AS OUT OF
SCOPE at 0.394. A man describing an evolving myocardial infarction in ordinary
English was told the system does not cover it.

Two separate causes, both fixed 2026-09-18:
  1. Scope was scored on symptoms PLUS timeline while the floor was calibrated
     on symptoms alone. server.py now scores symptoms only.
  2. The floor was too high for colloquial phrasing, which is the phrasing the
     product exists to serve.

THE IN-SCOPE SET IS DELIBERATELY WRITTEN BADLY. Contractions, hedges, vague
openers, body-part words a clinician would not use. That is the point. A
calibration sample written in corpus language measures how well the corpus
matches itself.

Scores are max cosine over all chunks, the same number `scope_check` sees.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# In scope: chest pain and its neighbours, as a frightened non-clinician types
# it at 2am. Several deliberately omit the word "chest".
IN_SCOPE = [
    ("original worst, kept for continuity",
     "Burning behind my breastbone at night"),
    ("the live refusal that started this",
     "Chest got tight walking up the hill to my car, same as it does most "
     "weeks. Sat on the wall. It has not shifted, it has been half an hour now."),
    ("the classic idiom", "Feels like an elephant sitting on my chest."),
    ("exertional, colloquial",
     "My chest goes tight when I walk up hills and settles when I stop."),
    ("squeezing plus autonomic",
     "Got a squeezing feeling in my chest and I have gone all clammy."),
    ("radiation, no 'chest' framing",
     "There is a heaviness across my front and my left arm has gone dead."),
    ("reflux idiom, the GERD side",
     "Bad indigestion that will not shift and I feel a bit sick with it."),
    ("vague, which is how people actually open",
     "Something is not right in my chest and it has been a while now."),
    ("pleuritic, colloquial",
     "Sharp stabbing in my side when I take a deep breath."),
    ("musculoskeletal, the green side",
     "My chest hurts when I press on it."),
    ("woke with it", "Woke up with a dull ache in the middle of my chest."),
    ("panic side", "My heart is pounding and my chest feels tight and I cannot "
     "calm down."),
]

# Out of scope: nothing the chest-pain chunks can speak to.
OUT_SCOPE = [
    ("original best out-of-scope",
     "My toddler has a fever and is pulling at her ear"),
    ("ankle", "I rolled my ankle playing football and it is swollen."),
    ("headache", "I have had a bad headache for three days."),
    ("knee", "My knee has been sore since I started running."),
    ("rash", "I have got a rash on my arm that itches."),
    ("mental health", "I have been feeling really down and cannot sleep."),
    ("dental", "My tooth is killing me and the side of my face aches."),
    ("urinary", "I keep needing to pee and it stings when I go."),
    ("gastro", "I have had diarrhoea since yesterday and my stomach is cramping."),
    ("eye", "My eye is red and watery and it feels gritty."),
    ("wrist", "I sprained my wrist falling off my bike."),
    ("ENT, the near miss", "I have a sore throat and a cough."),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=float, default=None,
                    help="floor to judge against (default: guards.SCOPE_FLOOR)")
    args = ap.parse_args()

    from hybrid import HybridRetriever
    sys.path.insert(0, str(HERE.parent / "02-pairs"))
    import guards
    floor = args.floor if args.floor is not None else guards.SCOPE_FLOOR

    r = HybridRetriever()

    def score(q):
        return max(r._cosines(q).values())

    rows_in = sorted(((score(q), n, q) for n, q in IN_SCOPE))
    rows_out = sorted(((score(q), n, q) for n, q in OUT_SCOPE), reverse=True)

    print(f"floor under test: {floor}\n")
    print("IN SCOPE (must pass; a refusal here is the catastrophic direction)")
    for s, n, q in rows_in:
        bad = "  <-- REFUSED" if s < floor else ""
        print(f"  {s:.3f}  {n:<38} {q[:46]}{bad}")
    print("\nOUT OF SCOPE (must refuse; a pass here costs 45 s, not a life)")
    for s, n, q in rows_out:
        bad = "  <-- PASSED" if s >= floor else ""
        print(f"  {s:.3f}  {n:<38} {q[:46]}{bad}")

    worst_in = rows_in[0][0]
    best_out = rows_out[0][0]
    fp = [x for x in rows_in if x[0] < floor]
    fn = [x for x in rows_out if x[0] >= floor]
    print("\n" + "=" * 70)
    print(f"  worst in-scope   {worst_in:.3f}  ({rows_in[0][1]})")
    print(f"  best out-scope   {best_out:.3f}  ({rows_out[0][1]})")
    print(f"  gap              {worst_in - best_out:+.3f}")
    print(f"  n                {len(IN_SCOPE)} in, {len(OUT_SCOPE)} out")
    print(f"  at floor {floor}: {len(fp)} in-scope refused, "
          f"{len(fn)} out-of-scope passed")
    if worst_in > best_out:
        lo, hi = best_out, worst_in
        print(f"  separable. any floor in ({lo:.3f}, {hi:.3f}] classifies this "
              f"sample perfectly.")
        print(f"  midpoint would be {(lo + hi) / 2:.3f}")
    else:
        print("  NOT SEPARABLE on this sample. No single floor works; the "
              "post-flight empty-citations check has to carry it.")
    print("=" * 70)
    return 0 if not fp else 1


if __name__ == "__main__":
    sys.exit(main())
