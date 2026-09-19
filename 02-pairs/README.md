# 02-pairs

Epic 2, the training pairs. **Scaffolding only. No clinical content is written
yet.** Nothing in `review/` carries a real presentation; every profile, symptom
and assistant turn is the literal string `TODO`.

```
pair_format.py         one source of truth: system prompt, human-turn builder,
                       assistant schema. Read its docstring first.
system_prompt.txt      byte-identical to what the app sends, extracted verbatim
                       from spike/req-demo-shape.json
validate_pairs.py      the validator
selftest_validator.py  proves the validator catches each bug, offline
generate_pairs.py      plan / scaffold / freeze
review/                candidate pairs awaiting human review
pairs/                 frozen train.jsonl, heldout.jsonl, manifest.csv
```

## Read this before writing a pair

`pair_format.py` exists because **three incompatible prompt formats and three
incompatible assistant schemas were in circulation.** The frozen spec in the
Obsidian vault, `discrimination_test.py`, and `spike/req-demo-shape.json` each
use a different one. `training-data-format.md` section 2 is right that drift
between the training human turn and the inference human turn is train/serve
skew, which makes this a blocker on writing pairs rather than a detail. The
docstring records which one won, why, and what it drops. Nothing defines a
prompt string of its own; everything imports that module.

## The order

```
python 02-pairs/generate_pairs.py plan --total 300
python 02-pairs/generate_pairs.py scaffold --total 300
#   ... a human and the generation session fill every TODO ...
python 02-pairs/validate_pairs.py 02-pairs/review/candidates.jsonl
python 02-pairs/generate_pairs.py freeze --heldout 40
```

Same review-then-freeze discipline as the corpus, and both guards that bit
epic 1 are built in rather than added after they cost something:

- `scaffold` refuses to overwrite an existing review file without `--force`.
  This is the `cmd_chunk` bug: review files are hand-edited and regenerating
  one silently resurrects deleted work.
- `freeze` refuses over an existing `train.jsonl` without `--force`, and
  refuses outright if the validator finds any error.

## Errors versus warnings

Errors are mechanical and objective; a file with any error cannot freeze and
must not train. Warnings are heuristic and need a human, exactly like a
candidate chunk.

The one judgement call: "red_flags carries a qualifier rather than being a bare
symptom" is a warning, not an error, because a lexicon cannot prove it. A bare
symptom matching the explicit blocklist *is* an error. An entry like "Vomiting
blood" discriminates without carrying a modifier word and would be a false
positive, and making that an error would push the generator toward padding
red_flags with filler to satisfy a lint. Flip `PROMOTE_QUALIFIER` in
`validate_pairs.py` if that call changes.

## Verified

- `python 02-pairs/pair_format.py` — registry and chunk files agree, 22 each
- `python 02-pairs/selftest_validator.py` — 21/21
- scaffold at 300, validator errors on all 300 unfilled pairs
- the freeze path, including the held-out split, was run once end to end
  against a synthetic placeholder file and its output deleted. It runs.
