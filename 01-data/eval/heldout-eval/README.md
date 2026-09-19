# Held-out eval set: NEVER TRAINING DATA

`HELDOUT-EVAL-v1.json` is a 22-case set for judging the fine-tune. It has
known correct verdicts, spread across the nine conditions, and 4 red, 7
yellow and 11 green (18/32/50%).

**Frozen 2026-09-19 after Viraj's review. sha256
`6d1af06eb393d4afd2c6dc4af1669b70dbc0d6e5f46accf88b686fe3e6826035`.** The
checker refuses the file if that changes. A verdict change is a new version,
`HELDOUT-EVAL-v2.json`, never an edit.

The review kept a 2/7/11 draft, weighted to the IITT base rate of 7/34/59.
It then added two reds, HE21 (heart inflammation) and HE22 (pneumonia). That
moves away from the base rate on purpose, so the set can catch the
chunk-to-colour shortcut on two more prefixes.

**The rule.** These cases never become training pairs, few-shot examples or demo
presets, and no pair may paraphrase one. The eval exists to measure whether the
model learned to condition its verdict on the case. A training example that
resembles a held-out case turns that into a memory test.

**The check.** `check_heldout.py` verifies the set and guards it:

```
python 01-data/eval/heldout-eval/check_heldout.py                  # the set
python 01-data/eval/heldout-eval/check_heldout.py --pairs X.jsonl  # a batch of pairs
```

On the set, it checks that:
- every quote is verbatim in its chunk, and every key is in the registry;
- the mix and the conditions covered are as expected;
- no case trips the pregnancy or child exclusions;
- every case clears the scope floor on its symptoms alone.

It also reports which justifying keys retrieval returns, and the overlap with
every case text in 02-pairs/, the 2026-09-17 eval cases and the demo presets.

With `--pairs`, it exits non-zero if any pair is too close to a held-out case.
Too close means MiniLM cosine of 0.85 or more, or word-set Jaccard of 0.50 or
more; 0.75 to 0.85 is reported as a warning. Every pair batch runs it before
review.

**Each case carries:**
- the verdict, and the condition it exercises;
- a structured profile, the same shape as the demo's people;
- the symptoms and an optional timeline;
- the justifying keys, with the verbatim lines that justify the verdict;
- a one-line reason, and flags where the call is Viraj's or the grounding is
  thin.

**What this set cannot see.** It can only tell whether a verdict follows the
case or the chunk where a prefix carries more than one verdict. Six of nine
do: CP-ACS, CP-DIFF, CP-GERD, CP-PE, CP-PERI, CP-PNA.

**CP-PANIC and CP-PLEU cannot be made mixed.** CP-PANIC-002 states that
"panic attacks themselves are not life-threatening", which contradicts any
yellow or red panic case. CP-PLEU-001 gives pleurisy no disposition at all.
A model that learned "panic chunk means green" or "pleurisy chunk means
yellow" would score perfectly on those cases, and this set could not tell.
Either needs a new source, not a new case.

**CP-ANG is single-colour by choice.** An unstable angina red is groundable
in CP-ANG-006 and CP-ANG-010. It was not added, to limit the move from the
base rate.

**Thin grounding, marked in the file:**
- HE06, pleurisy: yellow is a clinical reading, since pleurisy has no
  disposition.
- HE19 and HE20, chest wall: CP-DIFF-001 only names sore muscles and
  costochondritis. They stay because they are the only greens outside GERD
  and panic.
