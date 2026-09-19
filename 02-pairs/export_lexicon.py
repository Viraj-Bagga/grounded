#!/usr/bin/env python3
"""Export the finding lexicon to JSON so the TypeScript port cannot drift.

    python 02-pairs/export_lexicon.py        # writes finding_lexicon.json

`validate_pairs.py` stays authoritative. This only serialises what is already
there, so there is exactly one place a clinical term is added. Re-run after any
change to FINDING_SYNONYMS or CONTRADICTION_AXES, and re-run
`05-app/spike-load` sync-fixtures after that.

Adding a term is a clinical decision. Adding it in two places is a bug waiting
for the day the two disagree.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from validate_pairs import (CONTRADICTION_AXES, FINDING_SYNONYMS,  # noqa: E402
                            PRESENT_ONLY_AXES)

out = {
    "_generated_by": "02-pairs/export_lexicon.py from validate_pairs.py",
    "_warning": "Do not hand-edit. Edit validate_pairs.py and re-export.",
    "finding_synonyms": {k: list(v) for k, v in FINDING_SYNONYMS.items()},
    "contradiction_axes": {a: {p: list(ph) for p, ph in poles.items()}
                           for a, poles in CONTRADICTION_AXES.items()},
    "present_only_axes": sorted(PRESENT_ONLY_AXES),
    "negation_cues": ["no", "not", "never", "without", "denies", "denied",
                      "absent", "none", "lacks", "lacking", "rather than",
                      "instead of"],
    "clause_breaks": [".", ";", ":", "!", "?", " but ", " however ",
                      " although ", " whereas "],
}
p = HERE / "finding_lexicon.json"
p.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print(f"wrote {p}")
print(f"  {len(out['finding_synonyms'])} findings, "
      f"{len(out['contradiction_axes'])} axes, "
      f"{len(out['present_only_axes'])} present-only")
