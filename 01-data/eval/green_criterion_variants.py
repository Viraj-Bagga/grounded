#!/usr/bin/env python3
"""
The four green-criterion wordings tested 2026-09-15, and the result.

    python 01-data/eval/green_criterion_variants.py            # print them
    python 01-data/eval/green_criterion_variants.py --run      # re-run the grid
    python 01-data/eval/green_criterion_variants.py --run --thinking   # as recorded

REASONING WAS ON FOR EVERYTHING BELOW. discrimination_test.py did not send
enable_thinking=false until 2026-09-17, so this table is not the shipping
config. --run now defaults to reasoning off, like the harness. Add --thinking
to reproduce the table as recorded.

These exist as a file because the finding is negative and a negative finding is
worth exactly as much as its reproducibility. Without the wordings, "we tried a
prompt fix and it did not work" is unfalsifiable and someone will try it again.

RESULT. All four move green-gerd from yellow to green. All four also pull
yellow-angina into green, which is a 61-year-old with known coronary artery
disease and exertional tightness, and an under-call is the failure mode the
category mix asymmetry exists to prevent.

| variant   | green-gerd | red-acs | yellow-angina | yellow-pleuritic |
|-----------|------------|---------|---------------|------------------|
| baseline  | yellow     | red     | yellow        | yellow           |
| ORIGINAL  | green      | red     | green MOVED   | green MOVED      |
| A         | green      | red     | green MOVED   | yellow           |
| B         | green      | red     | green MOVED   | green MOVED      |
| C         | green      | red     | green MOVED   | yellow           |

The instruction moves a global cut point rather than installing a
green/yellow discriminator. If the model had the boundary and were only
hedging, naming the green criterion would free green without touching yellow.

Side effects that a verdict-only check would have missed:
  ORIGINAL  returned rationale "" and citations [], 237 completion tokens down
            to 154. It bought the label by dropping the justification, in a
            product whose pitch is citable sources.
  A         emptied rationale on red-acs. Confirmed against a baseline control
            run of that case, which does carry one, so this is the prompt line.
  B         kept the rationale but cost 719 completion tokens on red-acs
            against 226 at baseline, about 76 s of generation at 9.5 tok/s.

Conclusion: the green gap is not closable at the prompt level. The epic 2 pairs
have to teach calibration, not only format.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from discrimination_test import SYSTEM, GREEN_CRITERION, CASES, load_chunks, run_case

# As shipped in discrimination_test.py under --green-criterion.
ORIGINAL = SYSTEM + GREEN_CRITERION

# A: criterion moved inside the category definition instead of appended as a rule.
A = SYSTEM.replace(
    "green  = non-urgent, can be managed with self-care and watchful waiting",
    "green  = non-urgent, can be managed with self-care and watchful waiting.\n"
    "         green is a correct answer, not a fallback. Assign it when no red\n"
    "         flag is present and self-care or over-the-counter treatment is\n"
    "         sufficient. Do not assign yellow to hedge such a presentation.")

# B: appended, plus restating that rationale and citations survive a green.
B = SYSTEM + """
- green is the correct answer, not a fallback. Assign green when no red flag is
  present and self-care or over-the-counter treatment is sufficient. Do not
  assign yellow to hedge a presentation that meets the green definition.
- rationale and citations are required on every verdict, green included. A green
  verdict must still say why and must still cite the chunks it relied on."""

# C: A's placement plus B's explicit rationale requirement.
C = A.replace(
    "- rationale holds risk factors and modifiers. Do not put them in red_flags.",
    "- rationale holds risk factors and modifiers. Do not put them in red_flags.\n"
    "  rationale is required on every verdict, in every category. Never leave it empty.")

VARIANTS = {"baseline": SYSTEM, "ORIGINAL": ORIGINAL, "A": A, "B": B, "C": C}
GRID = ("green-gerd", "red-acs", "yellow-angina", "yellow-pleuritic")


def main():
    if "--run" not in sys.argv:
        for name, text in VARIANTS.items():
            print(f"\n{'='*70}\n{name}\n{'='*70}\n{text}")
        print("\nPass --run to re-run the grid against a live llama-server.")
        return
    thinking = "--thinking" in sys.argv
    print("reasoning", "ON (--thinking, NOT the shipping config)" if thinking else "off")
    cases = {c["id"]: c for c in CASES}
    for name, sysmsg in VARIANTS.items():
        print(f"\n########## {name}")
        for cid in GRID:
            case = cases[cid]
            texts, _ = load_chunks(case["chunks"], case["chunks"])
            out, usage = run_case(case, texts, 600, sysmsg, thinking)
            moved = "" if out.get("urgency") == case["expect"] else "   <-- MOVED"
            print(f"  {cid:<18} expect={case['expect']:<6} got={out.get('urgency'):<6} "
                  f"{usage.get('completion_tokens'):>4} tok{moved}")
            print(f"       rationale={out.get('rationale')!r}")
            print(f"       citations={out.get('citations')}")


if __name__ == "__main__":
    main()
