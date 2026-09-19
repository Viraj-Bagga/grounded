# 02-pairs/review — roadmap artifact, not dead work

**No fine-tune happened.** Decided 2026-09-18: ship the base model with the demo
as built. These pairs were not thrown away, and they are not a failed attempt.

## What is here

`candidates-60.jsonl`: 40 validated pairs, 0 errors, 0 warnings. Originally 60.

```
contrast 10 (5 sets)   grounding 5   under-specified 3   standalone 22
green 12   yellow 19   red 9
```

`CUT-2026-09-18-night.jsonl`: the five pairs cut on 2026-09-18 night, verbatim.
`FINDINGS-2026-09-18-night.txt`: Viraj's review of all 45, and every check behind it.
`SAMPLE.txt` — the review sample.
`AUDIT-2026-09-17.txt` — the pregnancy, rule 4 and contrast-difference audits.

## What was cut and why

15 pairs. P0051 for triaging third-trimester retrosternal burning as green when
the corpus has two words of obstetric content pointing the wrong way. Then seven
contrast sets, 14 pairs, because their axes were not grounded in the chunks the
pairs cite. See hard constraint 14.

Surviving sets: C01, C07 (pain resolves with rest), C02, C08 (black tarry
stool), C03 (breathlessness at rest). Every one quotes a line from a chunk it
cites.

Five more on 2026-09-18 night, from Viraj's read of all 45, kept verbatim in
`CUT-2026-09-18-night.jsonl`:

- P0008, P0027: the paediatric exclusion refuses them, so they train behaviour
  the app never reaches. P0027 taught green on a six-year-old from CP-PNA-001,
  the chunk the toddler failure grounded on. P0008's patient is 19; "my
  daughter" alone refuses it.
- P0030: cut as instructed, although the exclusion does NOT fire on it, because
  "panic attack" is not in its symptom lexicon. That is a gap in the guard,
  written up in the findings file.
- P0037: its rationale rests on a palpation criterion that no cited chunk
  states. Constraint 14 in a standalone pair. Cut, not rewritten.
- P0055: trained on GERD chunks for an undifferentiated chest complaint in a
  47-year-old man. For that text the app retrieves CP-ANG-001, CP-PERI-002 and
  CP-ANG-002.

## Why this is worth keeping

The pairs are the cheap part. What took the day was the method around them:

- a scaffolder that separates mechanics from clinical content, so re-scaffolding
  never destroys authored text
- a validator that catches train/serve skew, invented citation keys, questions
  on a red, ungrounded findings, contradicted findings, and slot/verdict drift
- fixtures shared between the Python and TypeScript guards so two ports of one
  policy cannot disagree
- the axis-grounding check in constraint 14, which caught six of twelve sets

Every one of those was added because something real slipped past. Writing pairs
in patient register found a live app bug where the guard stripped true red flags
off the screen for anyone who said "out of breath" instead of "short of breath".

## Before anyone trains on this

1. **Chunk identity predicts the verdict. This is the top open item.** In four
   conditions every pair has the same verdict: CP-PANIC 5/5 green, CP-PLEU 3/3
   yellow, CP-PNA 3/3 yellow, CP-PE 2/2 red. PANIC, PLEU and PE lost their only
   contrast sets to constraint 14. PNA lost its only green pair tonight. A
   model trained on this can learn the verdict from which chunk was retrieved
   instead of from the case, which is the opposite of what the adapter has to
   teach. Each condition needs a grounded pair with a different verdict, and
   that needs a source, not a sentence.
2. Seven surviving pairs are flagged, not cut. P0003, P0014 and P0023 credit
   the retrieved context with a line that is only in a chunk they do not cite.
   P0031, P0049 and P0052 credit it with reflux triggers that no chunk
   contains. P0009 says "no relationship to exertion", which its case never
   says.
3. 16 of the 40 carry reference keys that the app does not retrieve for their
   own text. Decide whether a pair carries the right chunks or the retrieved
   ones.
4. Constraint 14. Quote the line or do not build the set.
5. A prompt edit invalidates every pair: the system turn is byte-compared. Re-stamp.
6. The eval set cannot measure a fine-tune. Four scored cases, one green, and
   the green is the one every configuration has failed. Fix that first or you
   will not know whether training worked.

---

## candidates-120.jsonl, 2026-09-19: 120 pairs against the 35-chunk corpus

**Written after the held-out eval set was frozen**, so the eval could not leak
into the training data. Every pair is checked against it, and three were
reworded when they came too close: P0124, P0130 and P0135 sat at 0.900, 0.866
and 0.861 cosine to HE19, HE21 and HE08.

```
candidates-120.jsonl   120 pairs   the 40 above, unchanged, plus 80 new
                       contrast 44 (22 sets)  standalone 67  grounding 6  underspecified 3
                       red 32 (27%)  yellow 57 (48%)  green 31 (26%)
content-p1-contrast-2026-09-19.py    16 pairs, 8 contrast sets
content-p2-newchunks-2026-09-19.py   19 pairs on the 13 appended chunks
content-p3-registers-2026-09-19.py   45 pairs, 9 more sets and register breadth
```

Each content module holds the slot and the clinical content together.
`assemble_candidates.py` writes the rows, `fill_pairs.py` applies the content,
and `check_pair_extras.py` checks what `validate_pairs.py` does not: verbatim
quotes, the contrast axis living in a chunk both halves cite, the scope floor,
the exclusions, the app's own guards run over every gold answer, and the verdict
spread per prefix.

**Every new pair carries its quotes.** 348 verbatim lines across the 80, with
the chunk each is attributed to. The 40 older pairs carry none, which is
reported rather than failed.

**What it did to the top open item.** Verdict per cited prefix, the 40 before
against the 120 now:

| prefix | before | after | |
|---|---|---|---|
| CP-ACS | 4/1/1 | 10/1/1 | |
| CP-ANG | 2/5/0 | 11/18/2 | |
| CP-DIFF | 1/0/0 | 4/2/4 | was single |
| CP-GERD | 0/3/5 | 0/10/17 | |
| CP-PANIC | 0/0/5 | 0/0/8 | **still single** |
| CP-PE | 2/0/0 | 6/6/0 | was single |
| CP-PERI | 1/4/1 | 2/8/1 | |
| CP-PLEU | 0/3/0 | 0/3/0 | **still single** |
| CP-PNA | 0/3/0 | 4/13/0 | |

Read red/yellow/green. Three of the five single-colour prefixes are mixed now.

**CP-PANIC and CP-PLEU cannot be fixed with pairs.** CP-PANIC-002 states that
panic attacks themselves are not life-threatening, which contradicts any yellow
or red panic pair; that is the C04/C10 failure from 2026-09-18, and rebuilding
it would mean inventing chunk support. CP-PLEU-001 gives pleurisy no
disposition at all, which is what killed C05/C11. Each needs a source, not a
case. Same conclusion as the held-out set reached:
`01-data/eval/heldout-eval/README.md`.

**Not frozen.** These are candidates awaiting Viraj's review, like the 40.
