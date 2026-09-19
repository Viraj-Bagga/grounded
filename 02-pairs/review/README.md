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
