# PIPELINE TEST DATA — NOT TRAINING DATA

Frozen 2026-09-18 for one purpose: proving the epic 3 pipeline runs end to end.
**Do not train a shipped model on this and do not report a result from it as a
fine-tune outcome.**

Files are named `PIPELINE-TEST-*` deliberately so nothing picks them up as
`train.jsonl` by convention.

```
PIPELINE-TEST-train.jsonl     40 pairs   yellow 18  red 9  green 13
PIPELINE-TEST-heldout.jsonl    5 pairs   yellow 3   green 2
manifest.csv                  provenance per pair
```

**Stale against the review set since 2026-09-18 night.** This still holds all 45,
including P0008, P0027, P0030, P0037 and P0055, which were cut from
`review/candidates-60.jsonl` that night. That does not matter for a pipeline
test. Do not mistake it for the current set.

## Why it is not training data

Two reasons, both recorded in build-log.md under 2026-09-18.

**The content is only partly grounded.** Seven contrast sets were cut because
their discriminating axis was not stated in any chunk the pair cites, and one of
those axes, CP-PANIC, was actively contradicted by the chunk it cited. What
survives is grounded, but 45 pairs is not the 300 the plan called for and the
category mix is not the decided one.

**Nothing can measure whether training on it worked.** The eval set is four
scored cases with one green, and that green is the case every configuration has
failed. A fine-tune that helped and one that did nothing would score the same.

## What it IS good for

Running the pipeline once so tomorrow is not the first time: QLoRA on Brev,
merge, convert, imatrix, quantize, load. Shape and format are real. 40 pairs is
enough to make a training step execute and an adapter appear.

## Before this becomes real training data

1. Hard constraint 14: every contrast axis must quote the line in the cited
   chunk that draws the distinction.
2. Fix the eval set first, or you cannot read the result.
3. Re-stamp the system turn: a prompt edit invalidates every pair, byte-compared.
