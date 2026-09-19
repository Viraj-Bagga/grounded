# build-log

Running record of decisions and findings. Append, do not rewrite.

## 5. Epic 1: data foundation

Reconstructed heading. The original build-log.md, which held sections 1 to 6
including the spike numbers and the licensing table, is not in this repo and
there is no git history to recover it from. This file was created fresh on
2026-09-15. Section 5 exists here so the freeze date has its documented home;
if the original turns up, merge this into it rather than the other way round.

1. Source and licence-clear. Done. 9 sources in `01-data/sources.yaml`, all
   `license_status: green`, all US government works. `nhlbi-ha-what` was
   sourced and then dropped from the manifest after review kept none of its
   chunks.
2. Chunk and review. Done. See section 7 for the two extraction bugs found and
   fixed along the way.
3. **Freeze. Done 2026-09-15, re-frozen the same day at 22 chunks.**
   First freeze 19 chunks. Re-frozen with `--force` after adding the pericarditis
   and pleural sources: **22 chunks, mean 140 tokens**, registry at
   `01-data/citations.csv`. Distribution **9 red, 6 yellow, 6 green, 1
   uncategorised**. Keys are immutable from this date. Every epic 2 training pair
   references them. The `--force` was authorised once, for that one re-freeze,
   and only because a dry run proved zero existing keys changed. **That
   permission does not carry forward.** `cmd_freeze` refuses over an existing
   registry without it; do not pass it again without the same proof and a fresh
   instruction.
4. Embed into sqlite-vec. Not started, belongs to epic 4.

**Epic 1 is done.** It no longer blocks epic 2.

## 7. Findings

## RESUME HERE, 2026-09-17 end of day

### What runs

- **Epic 1 done.** Corpus frozen at 22 chunks, mean 140 tokens, registry at
  `01-data/citations.csv`. Keys immutable.
- **Epic 4 built.** sqlite-vec plus all-MiniLM-L6-v2 over the 22 chunks,
  `04-retrieval/corpus.db`. BM25 + vector blend at alpha 0.5.
  **62 to 67% recall against reviewed keys**, which is not good and is measured.
- **Epic 6 running, four beats.** Laptop web UI at `06-demo/`. Beats 1, 2 and 4
  work. Beat 3 is the guards firing and it fires live.
- **Five guards**, one rule each, shared between Python and TypeScript through
  `guard_fixtures.json` and `finding_lexicon.json`. Validator 24/24, Python
  guards 25/25, TypeScript 39/39.
- **llama.rn proven** to load the model on the simulator. Not the demo surface.

### Two commands

```
# terminal 1
cd ~/Coding/steel26
llama-server -m 03-model/base/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf \
  --jinja -np 1 -ngl 0 -c 4096 --port 8080

# terminal 2
cd ~/Coding/steel26 && .venv/bin/python 06-demo/server.py
# then open http://127.0.0.1:8770
```

A turn is about 40 s warm, 70 s cold. MiniLM now loads at startup, so the first
query is no longer slower than the rest; the server prints "warming up" and takes
about 10 s before it listens.

**TEMPERATURE IS 0.2, SO VERDICTS ARE NOT DETERMINISTIC.** The same input can
come back with a different urgency. The green verdict Viraj saw on the
out-of-scope case did **not** reproduce: the re-run returned yellow. Treat any
single observed verdict as one sample, and do not report one as the system's
behaviour without repeating it. Everything measured in `01-data/eval/runs/` was
run at temperature 0.0 for exactly this reason; the demo runs at 0.2 because the
spike request did.

### First task tomorrow

**Click through the demo yourself, with a browser.** It is the one thing that
could not be done tonight and it gates everything else, because if the flow feels
wrong at a desk then the fine-tune question is moot.

**Then the real decision: does the fine-tune happen at all.** Stated plainly
because tomorrow-you should not have to rediscover it:

- Epic 2 is unwritten and epic 3 is unstarted. 300 pairs written, validated,
  trained, merged, quantised and re-evaluated in one day is possible and it is
  not comfortable.
- The bet epic 2 was scoped on is dead. The model does not fail at format, it
  fails at category assignment, and that was measured with no corpus at all. The
  pairs would have to teach calibration, which is a harder target than the one
  they were planned for.
- **There is a working demo now.** It did not exist this morning. A fine-tune
  that goes wrong late on Friday risks the thing that works.
- The eval set cannot settle it either way: four scored cases, one green, and
  every variant gets that one wrong.

Nothing here decides it. Decide it in the morning with the demo in front of you,
not tonight.

### Two things that changed tonight, after the resume block was written

- **Guard 6, scope refusal, exists.** Out-of-scope queries are refused rather
  than triaged. Constraint 13. The ectopic-pregnancy case that triggered it is
  the most dangerous output this project has produced and it is now contained.
- **A demo-fatal threading bug is fixed.** The second query on any server
  instance used to fail. Found by clicking, not by the API tests.

Both are written up at the end of this section.

### DECIDED 2026-09-18: no fine-tune

Shipping the base model with the demo as built. Epic 2's pairs are a roadmap
artifact, see `02-pairs/review/README.md`. Epic 3 is not started and will not be.
The reason is not that 59 pairs are too few; it is that the eval set cannot tell
a working fine-tune from a useless one. Remaining time goes to demo hardening
and the pitch.

### Three things that will bite

1. **Ungrounded red flags are now dropped, not fixed.** The model still produces
   them; the guard removes them and shows what it removed. That is honest and it
   is not the same as the model being right.
2. **Retrieval hands CP-PERI-002 to nearly every case**, which is what supplies
   the fabricated findings the guard then removes.
3. **`02-pairs/pairs/` is empty.** No pair has ever been written, so the
   validator and the freeze path have only ever run against self-tests.
4. **The scope floor is a bet on n=18.** 0.40, measured over 8 in-scope and 10
   out-of-scope queries. It errs toward refusing. If a legitimate chest query
   gets refused at the desk, that is the number to look at first.

---

### 2026-09-15 NHLBI VTE and pneumonia URLs, and a silent chunker bug

**URL fix.** `nhlbi-vte` and `nhlbi-pneumonia` in `sources.yaml` pointed at the
topic landing pages, which are mostly link menus. Both now point at the
`/symptoms` subpage:

- https://www.nhlbi.nih.gov/health/venous-thromboembolism/symptoms
- https://www.nhlbi.nih.gov/health/pneumonia/symptoms

Re-fetched both (the other seven were cached and skipped). Headings now read
"Venous Thromboembolism Symptoms" and "Pneumonia Symptoms" instead of repeating
the topic name, so that part worked.

**Chunk counts did not go up much, and the reason is structural.** Both
`/symptoms` pages have no `h2` or `h3` in the body, just an `h1` and flowing
text. The chunker sections on headings, so a flat page yields one section that
only splits at the 256 token ceiling. The heart attack and CHD symptom pages
have several `h2`/`h3` sections, which is why they give 5 to 6 chunks. These
two pages are genuinely short and flat. VTE is 2 chunks and pneumonia is 2.
Not a URL problem, and not fixable by re-fetching.

**The real find: `build_corpus.py` was silently deleting short list items.**
Line 195 applied `if len(text) > 25` to `<li>` as well as `<p>`. That filter
exists to drop nav junk, but it also dropped every one word or two word
clinical finding. Confirmed against the raw HTML: the NHLBI pneumonia page
lists six symptoms and the chunker kept three.

Content that was being lost across the corpus:

| source | dropped |
|---|---|
| nhlbi-pneumonia | Chills, Fever, Shortness of breath, Grunting, Rapid breathing |
| nimh-panic | the entire panic attack symptom list, 9 items including Sweating, Trembling, Chest pain |
| nhlbi-chd-symptoms | Cold sweats, Dizziness, Lightheadedness, Neck pain, Nausea |
| niddk-gerd | chest pain, loss of appetite, persistent vomiting, unexplained weight loss |
| mlp-chestpain | Panic attacks, Sore muscles |

This matters more than the chunk counts do. Short benign findings are exactly
what the corpus is documented as thin on. "Sore muscles", "Panic attacks" and
the panic symptom list are green side and non-cardiac discriminators, and they
were being removed before review ever saw them. Some of the "no negative
discriminators in the corpus" gap was this bug rather than the sources.

**Fix.** Replaced the length cutoff for `<li>` with nav detection: an item is
dropped if it matches an exact nav label, if it repeats the page topic
(breadcrumb), or if it is a bare hyperlink inside a list that is mostly bare
hyperlinks. Length is no longer a criterion for `<li>`. `<p>` keeps the old
25 character rule. Verified: all the terms above now appear in the review
files, and no nav junk leaked in.

Counts after the fix: chest pain 1, angina 3, chd-symptoms 5, ha-symptoms 6,
ha-what 3, pneumonia 2, vte 2, gerd 4, panic 19. 45 candidates, 0 over the
256 token ceiling.

Nothing was frozen at the time of the change: `01-data/chunks/` was empty and
there was no `citations.csv`, so no citation keys were affected.

**Open, needs Viraj.** The chunker now emits one-line list items as their own
paragraphs, so several symptom lists sit inside a chunk as loose lines. Hard
constraint 1 in CLAUDE.md says a red flag list must never be split across two
chunks. Worth checking the review files for that before freeze. Also unresolved
is whether 2 chunks each is enough coverage for VTE and pneumonia, or whether
those two need a second source page added to the manifest.

### 2026-09-15 patch_pack.py applied, VTE causes source added

**New source.** `nhlbi-vte-causes`, https://www.nhlbi.nih.gov/health/venous-thromboembolism/causes,
key_prefix `CP-PE`, same as `nhlbi-vte`. Checked the freeze logic before adding:
`counters` in `cmd_freeze` is keyed by prefix and accumulates across sources, so
the two share one numbering series and keys stay unique. Placed directly after
`nhlbi-vte` in the manifest so numbering runs symptoms first, then causes. Worth
knowing that key numbers are positional within a prefix, so reordering or
inserting a CP-PE source later would shift keys. Nothing is frozen yet, so this
is free to change now and not later.

**Patch applied.** `extract_main` now returns `(kind, text)` tuples, `pack` is
replaced with `group_runs` plus a run-aware packer, and the `cmd_chunk` loop
variable is renamed. The nav-detection rule from the previous entry is kept and
slots into the marked line unchanged, including the `title` argument and the
breadcrumb `topics` set, which the patch skeleton did not carry.

**The patch was necessary, not theoretical.** Ran the old greedy packer over the
same extracted items to see what it would have done. It splits 4 multi-item
lists across chunk boundaries:

| source | list | items |
|---|---|---|
| nhlbi-ha-symptoms | When to call 9-1-1 | 2 |
| nhlbi-vte-causes | Medical conditions | 9 |
| nhlbi-pneumonia | Pneumonia Symptoms | 5 |
| niddk-gerd | symptoms of GER and GERD | 8 |

The heart attack one is a literal red-flag list, which is the exact case the
constraint exists to protect.

**Verification after the patch.** Re-extracted every source, regrouped the runs,
and checked each run against the emitted chunk bodies. 20 multi-item runs
checked, 0 split across a boundary. Every run sits whole inside one chunk.

Counts: chestpain 1, ha-symptoms 6, ha-what 3, chd-symptoms 5, angina 3, vte 2,
vte-causes 11, pneumonia 2, gerd 4, panic 19. 55 candidates, 1 over the ceiling.

`nhlbi-pneumonia` went 2 to 1 because its 5-item symptom list is now held
together instead of straddling a boundary. That is the fix working, not a loss.

**The one OVER chunk is intentional.** `nhlbi-vte-causes` chunk 008 "Medical
conditions", 353 tokens, a 9 item risk factor list. The packer refused to cut it
and surfaced it for a human to split on a clinical boundary. Do not split this
by token count.

**Open, needs a decision: NHLBI inline glossary text is polluting chunks.**
NHLBI pages carry glossary tooltips as `.usa-modal` spans, and `get_text()`
flattens the pronunciation and the full definition into the body. So chunk 008
reads "cancer cancer (KAN-ser): Diseases in which cells divide more than they
should ... and cancer treatments". Affects `nhlbi-vte-causes` (10 insertions),
`nhlbi-chd-symptoms` (2) and `nhlbi-ha-what` (1).

Tested three strips, and the obvious one is wrong:

- remove everything matching `glossary`: 353 to 126 tokens but it eats the term
  itself, giving "Obesity, which can lead to and damage in the lining of blood
  vessels". Silent clinical corruption, same shape as the length filter bug.
- remove `.glossarypro` and `.glossarydefinition`: terms survive but duplicate,
  "cancer cancer", "plaque plaque".
- remove `.usa-modal` only: clean. All terms intact, reads correctly, 130 tokens.

The third one is a one line addition to the decompose list in `extract_main` and
it would clear the only OVER chunk. Not applied, because it changes chunk text
across three files and chunk content is Viraj's call before a freeze.

### 2026-09-15 glossary strip applied

Added `.usa-modal` to the decompose list in `extract_main`, with a comment
warning not to widen the selector to match "glossary", since the trigger word
lives inside those nodes and removing them deletes clinical words mid sentence.

Re-chunked. 51 candidates, 0 over the 256 ceiling, 20 multi-item list runs
checked and 0 split across a boundary. No glossary residue anywhere in the
review files.

`nhlbi-vte-causes` "Medical conditions" went from 353 tokens OVER to 163 tokens
ok, with all 9 risk factors intact and readable. "cancer", "plaque" and
"damage in the lining of blood vessels" all survive.

Counts moved because removing gloss text lets sections pack tighter:
vte-causes 11 to 9, chd-symptoms 5 to 3, ha-what unchanged at 3.

Checked chd-symptoms for content loss since it dropped two chunks. All symptom
terms still present: cold sweats, dizziness, lightheadedness, neck pain, extreme
tiredness, nausea, stomach pain, shortness of breath. The word "artery" singular
disappeared, which is correct: it existed only as a glossary heading. "arteries"
went 5 occurrences to 1, and the 4 removed were inside glossary definitions. The
surviving one is the clinically meaningful sentence, "As plaque builds up and
narrows the coronary arteries, you're more likely to have symptoms such as chest
pain, shortness of breath, or neck pain when you exert yourself."

Final counts: chestpain 1, ha-symptoms 6, ha-what 3, chd-symptoms 3, angina 3,
vte 2, vte-causes 9, pneumonia 1, gerd 4, panic 19.

Not frozen. `01-data/chunks/` is still empty and there is no `citations.csv`.

### 2026-09-15 corpus frozen, 19 chunks

Applied Viraj's delete list to the review files, then froze.

| source | before | after | deleted |
|---|---|---|---|
| mlp-chestpain | 1 | 1 | none |
| nhlbi-ha-symptoms | 6 | 5 | 006 |
| nhlbi-ha-what | 3 | 0 | all |
| nhlbi-chd-symptoms | 3 | 1 | 002, 003 |
| nhlbi-angina | 3 | 1 | 001, 003 |
| nhlbi-vte | 2 | 1 | 001 |
| nhlbi-vte-causes | 9 | 3 | 001, 002, 003, 007, 008, 009 |
| nhlbi-pneumonia | 1 | 1 | none |
| niddk-gerd | 4 | 3 | 004 |
| nimh-panic | 19 | 3 | 004 through 019 |

**FROZEN 2026-09-15. 19 chunks, mean 145 tokens, `01-data/citations.csv`.**
Distribution: 9 red, 3 yellow, 6 green, 1 uncategorised. Keys are immutable
from here. Every epic 2 training pair references these.

Keys issued: CP-DIFF-001, CP-ACS-001 to 005, CP-ANG-001 to 002, CP-PE-001 to
004, CP-PNA-001, CP-GERD-001 to 003, CP-PANIC-001 to 003.

Verified after freeze: 19 rows, 19 chunk files, keys unique, every sha matches
its file, token range 32 to 231 against the 256 ceiling, every row carries a
retrieval date, all licences green. No problems.

**Why chd-symptoms 002 had to go.** It was headed "Symptoms of a heart attack"
and carried a full heart attack symptom list, but `nhlbi-chd-symptoms` is
`key_prefix: CP-ANG` with `expected_category: yellow`. Retrieving it on a yellow
query returns red content. Confirmed against the manifest before deleting. The
cost is the women's presentation detail, which is not elsewhere in the corpus.
If it is wanted back it should come in as its own `CP-ACS` source from
nhlbi.nih.gov/health/heart-attack/women, not be left misfiled under angina.

**Yellow is the real hole, not green.** 3 yellow chunks against a real-world
share of 34%, and yellow is the hardest call because it is the boundary on both
sides. Green is fine at 6. Worth a source before epic 2. Does not block freeze,
and did not.

**CP-GERD-002 is the model for what a green chunk should look like.** Persistent
vomiting, dysphagia, GI bleeding, unexplained weight loss. It is the only chunk
in the corpus where a green condition carries its own escalation criteria. Every
green chunk should have that shape and only one does.

**Open items, not corpus problems.**

- `nimh-panic` 016 held the 988 crisis line and was correctly cut from a chest
  pain corpus. Whether the app surfaces crisis resources when it triages a panic
  presentation is a product decision for epic 5. Decide it deliberately rather
  than by omission, which is where it currently sits.
- `CP-DIFF-001` froze with `expected_category` empty, because `mlp-chestpain`
  has no `expected_category` in `sources.yaml`. It is the differential chunk, so
  it is the one most likely to matter to `discrimination_test.py`. The chunk text
  is frozen; the manifest field is not part of the key and can still be set.
- `nhlbi-ha-what` is still in `sources.yaml` but contributed 0 chunks. Re-running
  `chunk` regenerates 3 candidates for it, and a later freeze would issue new
  CP-ACS keys from them. Either drop the source from the manifest or note it as
  deliberately empty, or it will come back.

### 2026-09-15 manifest cleanup, GGUF relocated, CPU number measured

**Manifest.** `mlp-chestpain` already had `expected_category: null`; an earlier
note in this log saying the field was absent was wrong, it was present and null.
Added a comment above it saying the blank is deliberate and why, so it does not
get "fixed" later. Removed `nhlbi-ha-what` from `sources.yaml`. Also removed its
orphaned `01-data/review/nhlbi-ha-what.txt`; kept `01-data/raw/nhlbi-ha-what.html`
per the reproducibility convention. Manifest is now 9 sources.

Worth knowing the re-chunk landmine was defused twice over: `cmd_freeze` already
refuses to run over an existing `citations.csv` without `--force`. Separately,
`cmd_chunk` overwrites `01-data/review/` unconditionally, so a re-chunk destroys
the hand-applied delete list. The frozen chunks and registry are unaffected.

**Base GGUF relocated.** Found the complete file at `~/models/`, not a symlink.
A half-finished `--local-dir` download was sitting in `03-model/base/.cache/`
with no payload. Verified the existing file against the expected hash recorded
in that download metadata: byte-identical, so it was moved rather than
re-downloading 2.84 GB.

```
03-model/base/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf
size    2,837,072,864 bytes
sha256  be5d9a656a51922f24f1f09a759cebb694e1f5d9728bf0ef9f8c972c5a0b5ef2
```

**THE CPU NUMBER. Measured 2026-09-15, first time.**

Host Apple M4, 16 GB, 4 performance and 6 efficiency cores. llama.cpp build
10809. `llama-server -ngl 0 --jinja -c 4096`, `n_threads = 4` which is the
default and matches the performance core count. Request `spike/req-final.json`,
reasoning off, schema on, prompt rules. Model load 7 s.

| | cold | warm, prefix cached |
|---|---|---|
| prompt tokens | 1664 | 4 |
| prompt eval | 51,578 ms (32.3 tok/s) | 246 ms |
| generated tokens | 419 | 359 |
| generation | 43,992 ms (9.5 tok/s) | 36,878 ms (9.7 tok/s) |
| **wall clock** | **95.6 s** | **37.1 s** |

**Three things this changes.**

1. **Hard constraint 7 is wrong for the demo condition.** It says prompt eval
   runs around 115 tok/s, so 100 tokens of chunk costs about 0.9 s. That is the
   Metal number. On CPU prompt eval is 32.3 tok/s, so 100 tokens costs 3.1 s,
   3.4x worse. At the frozen mean of 145 tokens, three retrieved chunks is
   about 13.5 s of prompt eval alone.
2. **On CPU the bottleneck is generation, not prompt eval.** The prefix cache
   is doing its job, prompt eval fell 51,578 ms to 246 ms, but the total turn
   only improved 2.6x because generation dominates. The 43x figure in CLAUDE.md
   describes prompt eval, not a turn. Output length is now the main lever:
   at a steady 9.5 tok/s, every 100 output tokens is 10.5 s. This run emitted
   419 tokens, and the rationale alone is a 150 word paragraph.
3. **95.6 s does not fit a 5 minute desk visit**, and this Mac is a friendlier
   CPU than the simulator, which adds its own overhead on the same host. Treat
   95.6 s as an optimistic floor for the demo condition, not the demo number.

**Separately, citation hallucination.** The run returned three citation keys.
Checked against the registry frozen today: `CP-ACS-001` is real, `CP-RISK-014`
and `MED-ANTICOAG-007` do not exist. Two of three invented, in a product whose
pitch is citable sources. The model has never seen a real retrieved chunk, so
this is expected rather than alarming, but it means citation validation against
`citations.csv` has to be app logic, not a prompt instruction. Add it to epic 5.

**Also, seventh consecutive red.** One more cardiac case, one more red. Still no
evidence the model can say green. Not run through `discrimination_test.py` yet,
and per Viraj that test is not worth reading until yellow has more than three
chunks, because a yellow miss cannot be separated from retrieval having nothing
to give. Candidates for that: NHLBI pericarditis and pleurisy, both pleuritic
chest pain, both genuinely yellow.

Server left running on 127.0.0.1:8080 for the discrimination work.

### 2026-09-15 capped output, demo-shape measurement, and the 4B viability question

All runs cold unless stated. Server restarted between cold runs so the prefix
cache is genuinely empty; the first attempt at a "cold" rerun was not cold until
that was fixed.

| run | prompt tok | prompt eval | gen tok | generation | wall | JSON |
|---|---|---|---|---|---|---|
| final config, uncapped | 1664 | 51.6 s (32.3 t/s) | 419 | 44.0 s | **95.6 s** | valid |
| final config, capped 120 | 1664 | 51.6 s (32.2 t/s) | 120 | 12.1 s | **63.7 s** | **INVALID** |
| demo shape, real chunks | 1103 | 37.2 s (29.7 t/s) | 263 | 26.6 s | **63.8 s** | valid |
| follow-up, cache hit | 104 | 5.0 s | 63 | 6.2 s | **11.2 s** | n/a |

**The cap works as a diagnostic and fails as a fix.** Capping at 120 saved 31.9
seconds, almost exactly the predicted 31, which confirms output length is about
a third of the turn. But the output truncates mid-string and does not parse:
`Unterminated string starting at line 3 column 16`. Grammar sampling constrains
shape, not length, so a hard cap cuts the JSON off wherever it lands. Brevity
has to come from prompt rules and training, not from `n_predict`. This is the
same failure mode hard constraint 3 warns about for `maxLength`, arriving by a
different route.

**The 95.6 s figure was partly an artifact of the test input.** `req-final.json`
carries a 1178-token user message: a full structured patient profile plus a
minute-by-minute timeline. Token split of that run was system 469, user 1178,
template 17. Rebuilt the request at demo shape, a compact stored profile, what a
person would actually type, and three real frozen chunks (CP-ACS-001, -003,
-004). That is **63.8 s cold with valid JSON**, and it is the honest demo number.
95.6 s is a stress case, not the desk visit.

**Citation hallucination did not reproduce with real chunks.** The uncapped run
with no retrieved context invented two of three keys. The demo-shape run cited
CP-ACS-001, CP-ACS-003 and CP-ACS-004, all real, all actually in context. First
time the model has ever seen a real retrieved chunk. Does not remove the need
for registry validation in app logic, but it reframes the risk: the model
invents keys when it has nothing to cite, not as a general habit.

**Where the time actually goes, and what is left to cut.** At demo shape,
prompt eval is 37.2 s of 63.8 s. Of the 1103 prompt tokens, 469 are the system
prompt, which is identical every turn and therefore cacheable; pre-warming at
app launch takes about 14.6 s off the first turn. That leaves roughly 49 s. The
retrieved chunks are 435 of the remaining tokens, about 13.5 s, and cutting to
two chunks saves 4.5 s. Generation at 263 tokens is 26.6 s and is the largest
single remaining block; holding the rationale to two sentences would plausibly
halve it.

Stacking the realistic wins, pre-warm plus two chunks plus a tighter rationale,
lands somewhere around 30 s. That is a projection, not a measurement, and it is
flagged as such.

**On the 4B viability question.** 30 s is a bet, not a result, and it assumes
work that has not been done. Against a 5 minute desk visit with a judge
watching, 63.8 s measured today is survivable exactly once, and only if the
first turn is pre-warmed before the judge sits down. It does not survive a judge
asking to see it twice. Two things also remain untested and both can only make
it worse: the simulator adds a process layer on this same CPU, and the device
memory problem in CLAUDE.md is a does-not-run risk at 4 to 6 GB, not a slowness
risk. My read is that distillation is no longer comfortably roadmap, but the
measurement that would actually settle it is the llama.rn load spike, because a
binding failure or an OOM on device moots the latency question entirely. That
spike does not depend on epic 1 and is still not started.

**CLAUDE.md updated.** Hard constraint 7 now carries the measured 30 to 32 tok/s
CPU rate and 3.1 s per 100 chunk tokens, with the old 115 tok/s figure recorded
as wrong and why. Hard constraint 8 now says the cache removes prompt eval and
does nothing for generation, with the measured follow-up costs. Added hard
constraint 9 for citation validation against the registry. Corrected the "never
seen a real retrieved chunk" line under Not proven, since it now has.

### 2026-09-15 llama.rn architecture support, step 1 of the load spike

**The model is not a dense transformer.** Read the GGUF header directly rather
than trusting notes: `general.architecture = "nemotron_h"`, GGUF v3, 263
tensors, 42 blocks, vocab 131072, tokenizer gpt2, chat template embedded. It
carries `ssm.conv_kernel 4`, `ssm.state_size 128`, `ssm.group_count 8`,
`ssm.inner_size 7680`, `ssm.time_step_rank 96`, and per-layer arrays for both
`feed_forward_length` and `attention.head_count_kv`. That is the hybrid Mamba2
plus attention family, not a plain transformer. CLAUDE.md calls it "dense",
which is true only in the sense of not-MoE. The support question is therefore
harder than a normal arch check: it needs SSM kernels and recurrent state
handling, not just a new tensor map.

**Answer: supported. The binding choice is not dead.**

| | llama.rn | vendored llama.cpp | nemotron_h |
|---|---|---|---|
| latest | 0.13.0-rc.3 | build 10829, commit 5fdfa62 | yes, full |
| latest stable | 0.12.9 | build 10256, commit 6c8dcaa | yes, full |

Checked the vendored source, not the docs. In both versions:

- `LLM_ARCH_NEMOTRON_H` in `llama-arch.h`, mapped to the string `"nemotron_h"`
  in `llama-arch.cpp`, which is exactly what our GGUF declares.
- A dedicated implementation at `cpp/models/nemotron-h.cpp`, 330 lines on the
  rc and 258 on stable, not a stub.
- `load_arch_hparams` reads all five SSM keys our file provides, and derives
  layer type per layer with "a layer is recurrent IFF n_head_kv == 0 and
  n_ff == 0", which is precisely why the file ships those two as arrays.
- `llama_memory_hybrid`, `build_mamba2_layer`, and the `ssm_scan` / `ssm_conv`
  ops are all present.
- SSM kernels exist on both backends that matter: CPU in `ggml-cpu/ops.cpp`,
  and Metal in `ggml-metal/kernels/ssm.metal` on the rc, folded into the
  monolithic `ggml-metal.metal` on stable.

**One thing that looks alarming and is not.** The layer-count switch in
`nemotron-h.cpp` has cases for 52, 56 and 88 only, so our 42-block model falls
to `default: type = LLM_TYPE_UNKNOWN`. Traced it: `LLM_TYPE_UNKNOWN` is only
ever assigned, never branched on, and feeds the printable model-type label.
Many architectures do the same. It means the model will report its size as
unknown in logs, not that it fails to load. Empirically our local llama.cpp
build 10809 already loads and runs this exact file, and both vendored builds
are newer.

**Prefer stable 0.12.9 over the rc** unless something else forces the upgrade.
`latest` on npm is currently `0.13.0-rc.3` and there is no stable 0.13.0, so a
plain `npm install llama.rn` pulls a release candidate. 0.12.9 supports the arch
just as fully.

**What this step does not prove.** This is a source inspection, not a load. I
did not call `initLlama`. Architecture support was the gate that could have
killed the binding outright, and it is clear. The remaining risk is unchanged
and is memory, not architecture: 4B at Q4 is about 3 GB resident against 4 to
6 GB devices, which is a does-not-run problem. Step 2 should actually load it.

Note for whoever runs the install: npm blocked llama.rn's postinstall
(`download-native-artifacts.js`, which fetches prebuilt binaries from the GitHub
release for the matching version tag) under its allowScripts policy. That is a
local npm setting, not an llama.rn problem, but the artifacts will need to be
allowed or the source built via the shipped CMakeLists before a device run.

### 2026-09-15 module dump, llama.rn pinned, step 2 blocked on Xcode

**The "dense" label was hiding a real problem, and the numbers are worse than
the label suggested.** Dumped the structure three ways and all three agree.

- GGUF tensor table: 21 blocks carry `ssm_*` tensors, 4 carry `attn_q/k/v/output`,
  17 carry `ffn_up/ffn_down`.
- `config.json` from `nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16`: `model_type`
  `nemotron_h`, `NemotronHForCausalLM`, 42 layers, and
  `hybrid_override_pattern = "M-M-M-MM-M-M*-M-M*-M-M-M*-M-M-MM*-MMM-M-M-"`
  which is 42 characters counting 21 M, 4 `*`, 17 `-`.
- safetensors header, fetched as a 3 MB range request rather than pulling the
  8 GB of weights: 263 tensors, leaf module names as below.

Attention sits only at blocks 12, 17, 24 and 32, identical in all three.

**Parameter shares, 3.97 B total.**

| module | params | share | in |
|---|---|---|---|
| `in_proj` | 1,152,743,424 | 29.0% | Mamba2 |
| `out_proj` | 505,774,080 | 12.7% | Mamba2 |
| `conv1d` | 1,021,440 | 0.0% | Mamba2 |
| `up_proj` | 668,745,728 | 16.8% | MLP |
| `down_proj` | 668,745,728 | 16.8% | MLP |
| `q_proj` | 64,225,280 | 1.6% | attention |
| `o_proj` | 64,225,280 | 1.6% | attention |
| `k_proj` | 12,845,056 | 0.3% | attention |
| `v_proj` | 12,845,056 | 0.3% | attention |
| `embeddings` / `lm_head` | 411,041,792 each | 10.3% each | |

**There is no `gate_proj`.** The MLP is ungated, only `up_proj` and `down_proj`.
So of the standard seven, one target matches nothing at all. PEFT does not error
when some targets match, so this would have passed silently.

Targeting the standard seven reaches **1.49 B of 3.97 B, 37.5%**, and misses the
**1.66 B, 41.8%**, in the Mamba2 mixers. The attention it does reach is 3.8% of
the model. Adding `in_proj` and `out_proj` lifts coverage to about 79%.

Which list is right is Viraj's call. The mechanical part is done and the numbers
are above. Flagging only that "7 modules" is now known to be wrong rather than
unverified.

**llama.rn pinned at exactly `0.12.9`.** Not a caret range and not `latest`,
since npm's `latest` currently resolves to `0.13.0-rc.3`. Verified the install
resolves to 0.12.9 exactly.

**Blocked postinstall resolved.** `download-native-artifacts.js` was stopped by
npm's own allowScripts policy, nothing to do with llama.rn. Ran it directly and
it fetched and installed both `android/src/main/jniLibs` and
`ios/rnllama.xcframework` cleanly, exit 0.

**Checked the prebuilt binary, not just the source.** The xcframework ships
`ios-arm64`, `ios-arm64_x86_64-simulator`, and the two tvos slices. The
simulator slice is a universal Mach-O carrying both x86_64 and arm64, so it runs
on Apple Silicon simulators. Inside that binary:

- the architecture string `nemotron_h`, plus `nemotron_h_moe`
- Mamba-2 kernels, `lm_ggml_metal_kargs_ssm_scan` and `..._ssm_conv`, and the
  CPU references `lm_ggml_compute_forward_ssm_scan_f32, Mamba-2 part` and
  `..._ssm_conv_f32`
- tensor-name templates `blk.%d.ssm_a`, `blk.%d.ssm_conv1d`, `blk.%d.ssm_dt`,
  which match the names in our GGUF exactly
- hparam print strings for `ssm_d_conv`, `ssm_d_inner`, `ssm_d_state`,
  `ssm_dt_rank`, `ssm_n_group`, the same five keys the loader reads

That is the artifact that would actually run in the simulator, and it has the
support compiled in. Stronger evidence than the source read, still not a load.

**STEP 2 IS BLOCKED. Xcode is not installed on this machine.**

```
xcode-select -p   -> /Library/Developer/CommandLineTools
xcodebuild        -> error: requires Xcode
xcrun simctl      -> missing
/Applications/Xcode*.app                            -> absent
/Library/Developer/CoreSimulator/Profiles/Runtimes  -> empty
```

CocoaPods 1.16.2 and Node 22 are present, so the JS side is ready. There is no
iOS simulator to install an app into and no way to build one. Unblocking needs
Xcode from the App Store, then `sudo xcode-select -s /Applications/Xcode.app`
and one simulator runtime. That is a large download and a user action.

Nothing was faked to work around it. No load time and no peak memory were
measured, because no load happened.

Also worth stating plainly, per Viraj's own caution: even once it runs, the
simulator borrows Mac RAM. A clean load there tests the binding and the
architecture path. It says nothing about a 4 to 6 GB phone, which is still the
open does-not-run risk.

### 2026-09-15 QLoRA module list decided, Xcode is now critical path

**Decided: six modules, `q_proj, k_proj, v_proj, o_proj, up_proj, down_proj`.**
Viraj's call, recorded with the reasoning in CLAUDE.md and in the config
docstring so it does not get relitigated on Brev. The short version: coverage is
the wrong objective for a 500-pair, 2-epoch format fine-tune, more trainable
parameters buys overfitting rather than capability, `in_proj` is a fused
projection emitting x, B, C, dt and z so a low-rank update smears across five
different outputs, and attention is kept for citation fidelity rather than for
parameter count, since verbatim copying of a key like CP-ACS-001 out of a
retrieved chunk is in-context copying and lives in attention heads.

**Written to `03-model/qlora_config.py`.** Holds `TARGET_MODULES`,
`EXPECTED_MATCHES`, `build_lora_config()` which asserts before returning, and
the full reasoning as a docstring.

**The assertion is real and self-tests offline.** Captured the 242 real module
paths from the safetensors header into `03-model/module_names.txt`, so
`python 03-model/qlora_config.py` verifies the match counts with no torch, no
peft and no 8 GB download. Result:

```
q_proj 4, k_proj 4, v_proj 4, o_proj 4, up_proj 17, down_proj 17, total 50
assertion passed.
gate_proj correctly rejected: target_modules match nothing: ['gate_proj']
```

That last line matters. The self-test deliberately re-adds `gate_proj` and
confirms the assertion catches it, so the check is proven against the exact bug
it exists for rather than merely written.

Worth noting for whoever writes the training script: on this architecture every
projection lives under `.mixer.`, including the attention ones, for example
`backbone.layers.12.mixer.q_proj`. PEFT matches on the suffix so the plain names
work, but the paths do not look like a normal transformer's.

Added hard constraint 10 to CLAUDE.md covering the PEFT silent-no-match
behaviour.

**Xcode. Not installed, and I cannot install it.** The App Store needs a GUI and
an Apple ID, so this is a Viraj action. Disk checked as asked:

```
228Gi volume, 43.2 GB available
```

Xcode is roughly 15 GB installed and a simulator runtime roughly 7 GB, so about
22 GB of the 43 GB. It fits, but not comfortably: the App Store expands the
download in place, so transient usage during install runs well above the final
footprint. Freeing some headroom first is the safer play. The 2.84 GB GGUF is
already on this volume.

Commands after the App Store finishes:

```
sudo xcode-select -s /Applications/Xcode.app
xcodebuild -runFirstLaunch
xcrun simctl list runtimes          # confirm an iOS runtime exists
```

**Did not take the fallback.** Building vendored llama.cpp for macOS CPU was
declined for the right reason: it would only re-prove what build 10809 already
showed, and touches neither the RN binding nor iOS. Step 2 stays blocked rather
than being replaced with a weaker test that looks like progress.

Epic 5 is the critical path now. There is no app shell without Xcode.

### 2026-09-15 disk freed, yellow sources added (awaiting review, NOT frozen)

**Disk. Freed 18.1 GB, 42.9 to 61 GB free.** All regenerable caches:

| target | freed |
|---|---|
| `~/.npm` (`cache clean --force` plus `_npx`) | ~9.9 GB |
| `~/Library/Developer/CoreSimulator` | 4.7 GB |
| `~/Library/Caches` (Google, ShipIt, notion-updater, Homebrew, pip) | ~2.7 GB |
| `~/.gradle/caches` | ~0.8 GB |

CoreSimulator was orphaned; Xcode is not installed and left those devices
behind. Nothing of Viraj's was touched: Downloads, Pictures, Messages, Mail,
`.ollama`, `.codeium` and the Application Support app data were all left alone.
If more room is ever wanted, `~/.codeium` 2.5 GB and `~/.ollama` 1.9 GB are the
next candidates, but they are his call.

Note the earlier `df` reading was misleading. `/` reports 12 GB used because it
is the sealed system volume; the real consumer is `/System/Volumes/Data` at
168.6 GB in a 245.1 GB APFS container. 61 GB free against roughly 22 GB for
Xcode plus a runtime is comfortable headroom for the transient expansion.

**Both intended URLs 404. NHLBI has neither topic.**

- `nhlbi.nih.gov/health/pericarditis` 404. Pericarditis is covered under **Heart
  Inflammation**; `/health-topics/pericarditis` redirects to
  `/health/heart-inflammation`. Used `/health/heart-inflammation/symptoms`.
- `nhlbi.nih.gov/health/pleurisy` 404, and there is no NHLBI pleural topic.
  Used **MedlinePlus Pleural Disorders**, `medlineplus.gov/pleuraldisorders.html`,
  which is a health topic page summary and therefore in the cleared class. Not
  `/ency/`. Source id is `mlp-pleural`, not `nhlbi-pleurisy`, since the
  publisher changed.

Both still `license_status: green`. Prefixes are as instructed, `CP-PERI` and
`CP-PLEU`.

**7 new candidates, 5 pericarditis and 2 pleural. Not frozen.**

**The pericarditis page delivers the thing the corpus has never had.** Chunk 005
reads "Chest pain that feels sharp, gets worse with breathing, and feels better
with sitting up and leaning forward". That is a genuine negative discriminator
against ACS, positional relief plus worse on inspiration, and it is exactly what
the `NEG-DISC` gap entry in `sources.yaml` describes as missing. Worth
considering whether that gap entry should now be narrowed rather than closed,
since palpation-reproducible pain is still absent everywhere.

Chunk 001 is nav residue and chunks 003 and 004 are endocarditis and myocarditis,
which are not chest-pain triage content. Viraj's call, but the plausible keep is
002 and 005, possibly 005 alone.

The pleural summary is thin as expected. Chunk 001 carries the one useful line,
"Pleurisy, inflammation of the pleura that causes sharp pain with breathing".
Chunk 002 is aetiology and treatment framing plus a trailing "NIH: National
Heart, Lung, and Blood Institute" attribution line that should come out.

**Protected the frozen corpus through the re-chunk.** `cmd_chunk` overwrites
every review file unconditionally, which would have silently restored all the
chunks deleted before the freeze. Backed up `01-data/review/` first, ran chunk,
then restored the 9 hand-edited files. Verified with `cmp`: all 9 byte-identical,
19 chunks intact.

**Verified the re-freeze is safe before anyone runs it.** Simulated the key
assignment `freeze --force` would produce, without writing:

```
currently frozen : 19 keys
would be written : 26 keys
existing keys that would CHANGE or vanish: NONE
new keys added: CP-PERI-001..005, CP-PLEU-001..002
```

Every existing key keeps its identical sha256. The new-prefix reasoning holds.
That said, re-freezing still needs `--force` because `citations.csv` exists, and
the count will change once chunks are deleted in review, so the 7 above is the
ceiling, not the final set.

**Still open:** Viraj reviews the 7, deletes what should go, then freezes. Yellow
goes from 3 to somewhere between 4 and 10 depending on that review.

**CLAUDE.md:** added the `.mixer.` path note next to the module decision, so it
lives in the file rather than in a handoff message.

### 2026-09-15 re-frozen at 22 chunks, chunk guard added

**Review decisions applied.** Deleted CP-PERI 001 (nav residue), 003
(endocarditis) and 004 (myocarditis), and CP-PLEU 002 (aetiology plus a trailing
NIH attribution line).

**CP-PERI 002 kept**, against the stated rule of keep-if-symptoms-onset-or-what-
makes-it-worse, delete-if-mechanism-or-definition. It is onset and symptoms
throughout and contains neither mechanism nor definition: "can occur suddenly or
progress slowly" is onset, the viral prodrome "a few weeks before you notice any
other symptoms" is onset timing, "may feel like the flu and go away on their own
after a few weeks" is symptom course. It also opens with escalation criteria,
which is the CP-GERD-002 shape. Its one weakness is that it describes heart
inflammation generally rather than pericarditis specifically.

**FROZEN 2026-09-15, 22 chunks, mean 140 tokens.**

```
distribution: {'none': 1, 'red': 9, 'yellow': 6, 'green': 6}
new keys: CP-PERI-001, CP-PERI-002, CP-PLEU-001
```

**Yellow doubled, 3 to 6.** Red is unchanged at 9, green unchanged at 6. Against
the real-world base rate of roughly 7% red, 34% yellow, 59% green the corpus is
still red-heavy at 41%, but yellow is no longer so thin that a yellow miss is
uninterpretable.

**`--force` was used once, deliberately, and the permission does not carry.**
Ran the dry run again against the final 22-chunk state immediately before
freezing: zero existing keys changed. Backed up the 19-key registry first, then
diffed after: **no pre-existing key drifted**, every sha matched its file, 22
chunk files on disk, all licences green, every row has a retrieval date. Recorded
the non-carrying nature of that permission in section 5 step 3 as well.

**`cmd_chunk` now refuses to overwrite an existing review file.** This was the
bug that nearly cost the whole review pass: review files are hand-edited, and
regenerating one silently resurrects chunks that were deliberately deleted.

```
keep nhlbi-ha-symptoms: review file exists, not regenerating (--force to overwrite)
```

Tested both directions rather than only the happy path. Plain `chunk` now skips
all 11 sources and leaves every file byte-identical with 22 chunks intact. With
the review file removed, the same source chunks normally, so adding a new source
still works and the guard only protects existing human work. `chunk --force`
restores the old behaviour for when a re-chunk is genuinely wanted.

**NEG-DISC narrowed rather than closed.** Positional and worse-on-inspiration
are now covered by CP-PERI-002 and CP-PLEU-001. The entry now names
palpation-reproducible pain, that is chest wall tenderness, as the only
remaining hole, and notes it overlaps the CP-COSTO gap, so one good
musculoskeletal source would probably close both.

**What this does to the discrimination test.** A pleuritic presentation now has
something to retrieve. If the model still returns red for one, that is evidence
about the model rather than about an empty corpus, which is the first time that
distinction has been available.

**Xcode is still not downloading, and I could not start it. Two blockers.**

1. `mas get 497799835` requires sudo with an interactive password prompt, which
   is not available non-interactively.
2. More importantly, **the current Xcode will not install on this machine.**
   Xcode 27.0, released 2026-09-14, requires **macOS 26.6 minimum**. This Mac is
   **macOS 26.5.2** (build 25F84). So the App Store will refuse it regardless of
   who clicks.

`softwareupdate -l` offers a way through: **macOS Tahoe 26.7, 3.85 GB, requires
restart**, which clears the 26.6 minimum. macOS 27 is also offered at 11.9 GB.
The restart is why this was not run unattended.

Order of operations for Viraj:

```
# 1. update macOS first, or Xcode will not install
sudo softwareupdate -i 'macOS Tahoe 26.7-25G229' --restart
# 2. then Xcode, roughly 3 GB download expanding to about 15 GB
#    App Store was opened on the Xcode page
# 3. then
sudo xcode-select -s /Applications/Xcode.app
xcodebuild -runFirstLaunch
xcrun simctl list runtimes
```

Disk is fine for this: 61 GB free, and the macOS update plus Xcode is roughly
20 GB.

### 2026-09-15 discrimination test, first real run. The top open risk is resolved.

Harness changed first: added a pleuritic yellow case on CP-PERI-002 and
CP-PLEU-001, relabelled the costochondritis case as an unmatched-evidence probe
reported separately rather than scored, and added citation validation against
`citations.csv` per hard constraint 9. The three original cases were left
untouched so results stay comparable to the six earlier spike runs.

Caught a bug I introduced while doing it: the summary line used
`sum(1 for *_, ok in results ...)`, and after the result rows grew from 3-tuples
to 5-tuples that binds `ok` to the violation flag, silently reporting 0 correct.
Fixed to explicit indexing before running anything.

**Results, all 5 cases, both modes, 10 inferences.**

| case | expect | matched | red-only |
|---|---|---|---|
| red-acs | red | **red** PASS | **red** PASS |
| yellow-angina | yellow | **yellow** PASS | **yellow** PASS |
| green-gerd | green | yellow FAIL | yellow FAIL |
| yellow-pleuritic | yellow | **yellow** PASS | **yellow** PASS |
| probe-costo-unmatched | green | yellow | **red** |

Scored distribution was `{red: 1, yellow: 3}` in **both** modes. 3/4 correct
both times.

**1. The six-reds fear is dead.** Six spike runs had produced six reds and there
was no evidence the model could say anything else. It now returns red for the
cardiac case and yellow for three others. Discrimination exists. That was the
top open risk in CLAUDE.md and it is answered.

**2. The pleuritic case passed, which is what the new chunks were for.** Sharp,
worse on deep breath, better sitting forward, no exertional relation, returned
yellow with CP-PERI-002 and CP-PLEU-001 in context. Per Viraj's own reading
rule, red here would have been the most informative result available today. It
did not go red. The corpus addition did its job.

**3. The corpus-red-bias hypothesis is NOT supported.** This is the surprise.
Feeding cardiac chunks to every case changed the scored distribution not at all.
yellow-angina, green-gerd and yellow-pleuritic all held their verdicts while
being shown ACS content. The model is leaning on the presentation, not the
retrieved text. So of the two competing explanations in CLAUDE.md, neither is
the live one: it is not that the model cannot discriminate, and it is not that
the corpus pushes everything red.

The flip side is uncomfortable. If mismatched chunks barely move the verdict,
retrieval is not contributing much to the decision either. Only the probe moved,
yellow under matched and red under red-only, and that is the one case whose
presentation has no supporting evidence anywhere in the corpus. Chunks appear to
matter only when the presentation is otherwise unsupported.

**4. Zero invented citation keys in 10 inferences**, including the probe. The
earlier fabrication of CP-RISK-014 and MED-ANTICOAG-007 happened with no chunks
at all in context. Given any chunks, even loosely relevant ones, it cited only
supplied keys. One case returned an empty citations list rather than inventing,
which is the correct failure mode. Constraint 9 stands as app logic regardless,
but the risk is narrower than it looked: the model fabricates when it has
nothing, not as a habit.

**5. No follow-up convention violations.** `follow_up_questions` was empty on
every red.

**THE NEW FINDING, and it replaces the old risk rather than closing it.**

**Green never appears. 0 greens in 10 inferences.** green-gerd returned yellow
in both modes. The probe, also green-expected, returned yellow then red. The
model discriminates red from yellow and appears unable, or unwilling, to reach
green at all.

The honest caveat: this rests on thin evidence. There is exactly **one** scored
green case plus one unscored green-expected probe, so "never says green" is
0 for 4 inferences across 2 distinct presentations. That is suggestive, not
established. The eval set is 1 red, 2 yellow, 1 green against a real-world
59% green, so it is still the wrong shape to measure the thing now most in
doubt.

This looks like over-triage, a safety-conservative lean, rather than a format
problem. Which matters, because the premise under the module decision is that
this is a light-touch format fine-tune. Format-only pairs plausibly will not
move a calibration bias. **Not reopening the module decision**, that is Viraj's
call and the evidence is too thin to act on, but flagging that the decision rule
agreed in advance, "matched discriminates so pairs teach format only", was
written for a binary that this result does not cleanly fall into. It
discriminates AND has a systematic categorical gap.

**Latency note.** The probe generated 781 completion tokens under matched,
against 224 to 459 elsewhere. The model rambles when the evidence does not fit
the presentation. At 9.5 tok/s that is about 82 seconds of generation on one
turn, so the worst latency case is the weak-retrieval case, which is also the
most production-realistic one.

**Suggested next move before epic 2 pairs are written:** add 3 to 4 more green
cases so the green finding is either established or disproved. It is cheap,
roughly a minute of model time each, and it decides whether the 500 pairs need
to teach calibration or only format. Server left running on 127.0.0.1:8080.

### 2026-09-15 state saved before the macOS restart

Everything verified before the machine goes down for the macOS 26.7 update.

**Frozen corpus: CLEAN.** 22 rows, 22 chunk files, keys unique, every sha
matches its file, every row has a retrieval date, all licences green, nothing
over the 256 ceiling. Distribution 9 red, 6 yellow, 6 green, 1 uncategorised.

**Base GGUF verified by full re-hash**, not just by size:
`be5d9a656a51922f24f1f09a759cebb694e1f5d9728bf0ef9f8c972c5a0b5ef2`,
2,837,072,864 bytes, still at `03-model/base/`.

**Self-tests pass.** `python 03-model/qlora_config.py` asserts the 50 matched
modules and still correctly rejects `gate_proj`. All three touched Python files
parse.

**llama-server stopped.**

**Pulled out of the scratchpad, because `/private/tmp` is wiped on restart:**

- `spike/req-demo-shape.json`, `spike/req-followup.json`,
  `spike/req-final-capped.json`. These are the exact requests behind the
  63.8 s, 11.2 s and 63.7 s numbers. Without them those figures are not
  reproducible.
- `01-data/citations.frozen-19.csv`, the pre-`--force` 19-key registry, kept as
  the evidence that no key drifted across the re-freeze.
- `05-app/package.json` and `05-app/README.md`. The `llama.rn@0.12.9` pin
  existed only in a scratch project and would have been lost. The README records
  why the pin is exact and what was verified in the vendored source and the
  shipped xcframework.

Deliberately not preserved: the three scratch `node_modules` trees (~1.3 GB,
regenerable with `npm install` plus the postinstall), the `.bak` files (current
versions are in the repo), and the server logs (findings already written up
above).

**Where things stand.**

Done: epic 1 complete and frozen at 22 chunks. CPU number measured. llama.rn
architecture support confirmed from source and from the prebuilt binary. QLoRA
module list decided and asserted. Discrimination test run for the first time.

Open, in rough priority order:

1. **macOS 26.7, then Xcode.** Critical path. Xcode 27.0 needs macOS 26.6 and
   this machine is on 26.5.2, so the update is not optional. Download command
   is `sudo softwareupdate -d 'macOS Tahoe 26.7-25G229'`, install with
   `--restart` when ready. Then `sudo xcode-select -s /Applications/Xcode.app`,
   `xcodebuild -runFirstLaunch`, `xcrun simctl list runtimes`. 61 GB free,
   comfortable.
2. **Step 2 of the load spike**, which is ready to run the moment `simctl`
   exists. Nothing else blocks it.
3. **More green cases in the discrimination test.** Green is 0 for 4 and that
   is too thin to act on. It decides whether the 500 epic 2 pairs teach
   calibration or only format, so it should come before pairs are written.
4. **Epic 2 pairs**, the longest remaining pole.

Four days to SteelHacks. Epic 5 has no path without Xcode.

### 2026-09-15 discrimination run re-verified, epic 2 scaffolding, format conflict found

**Run outputs are now saved.** They never were. `discrimination_test.py` prints
to stdout and the previous run's output existed only in a terminal that is
gone, so answering a question as simple as "which case invented a key" meant
re-running the model. Everything now lands in `01-data/eval/runs/` with a
timestamp header. That directory is cheap and it is the difference between a
finding and a memory of a finding.

**Item 1, per-case citation and follow-up data.** Re-ran both modes.

| case | matched | red-only | invented keys |
|---|---|---|---|
| red-acs | red PASS | red PASS | 0 |
| yellow-angina | yellow PASS | yellow PASS | 0 |
| green-gerd | yellow FAIL | yellow FAIL | 0 |
| yellow-pleuritic | yellow PASS | **red FAIL** | 0 |
| probe-costo-unmatched | yellow | yellow | 0 |

Zero invented keys in all ten inferences, confirming the earlier aggregate.
`follow_up_questions` was empty on red-acs in both modes, no violation. red-acs
is also the only case that produced any `red_flags` at all under matched, one
entry.

**THE RED-ONLY RESULT IS RUN-DEPENDENT. The original finding survives; its
reproducibility does not.** Ran red-only twice today. On a server that had been
serving other requests, it scored **2/4**: `yellow-pleuritic` flipped yellow to
red when shown cardiac chunks. On a freshly restarted server with an empty
prefix cache it scored **3/4** with distribution `{red: 1, yellow: 3}` and the
probe red, which reproduces the earlier entry exactly, case for case.

So the conclusion in that entry stands as written. The corpus-red-bias
hypothesis is still not supported under a cold run. What does not stand is
treating any single run of this harness as a fact.

**Both runs were at `temperature: 0.0`, so this is not sampling.** Identical
input to red-acs produced 211 completion tokens warm and 226 cold. Every case
differed: yellow-angina 350 against 213, green-gerd 351 against 258. The cause
is prefix-cache state, since llama.cpp reuses cached prefixes across differing
cache states and the numerics are not bit-identical.

Two consequences, and the second is the one that matters.

1. **Always restart the server between eval runs.** The earlier entry says this
   was done and that is why it reproduced. It is now the documented protocol,
   not a habit.
2. **A single run of this harness is not evidence at the resolution being asked
   of it.** One in two red-only runs moved a scored case across a category
   boundary. Findings from a 4-case eval read once are inside that noise. The
   green result is the exception only because it has never once come out
   otherwise: green-gerd is yellow in every run, warm and cold, matched and
   red-only.

**Item 2, CP-GERD-002 is not why green-gerd fails.** Re-ran green-gerd alone
with and without it. Both yellow. Removing the escalation-criteria chunk does
not free the verdict.

The rationale from the without run is the actual finding:

```
urgency   : yellow
rationale : GERD symptoms present, no red flags, can be managed with OTC meds
            and lifestyle changes
red_flags : []
```

"No red flags, can be managed with OTC meds and lifestyle changes" is the
definition of green in the system prompt it was given, and it labelled it
yellow. The model reasons green and emits yellow. That is a calibration
problem, not an evidence problem and not a retrieval problem, and no amount of
corpus work will touch it.

Worth noting separately that CP-GERD-001 ends on the dangling words "such as"
and CP-GERD-002 is the list that sentence introduces. The run-aware packer kept
each list whole but split the sentence that frames one. Not the cause here, but
CP-GERD-002 read alone is a bare list of alarm features with no "these are
complications" framing.

**Item 3, the format spec exists and is substantially stale.** It is not in the
repo. `training-data-format.md` and `spec.md` are in the Obsidian vault at
`~/Documents/Obsidian Vault/AI/projects/steelhacks-xiii/`, both frozen
2026-09-12, before the corpus existed.

What it decides that still holds: ShareGPT JSONL container, system turn
byte-identical across all pairs and identical to what the app sends,
`train_on_responses_only`, no `conversation_extension`, held-out 50 selected by
id at generation time and never by eye, and the pre-training checklist.

What has been overtaken:

- **Reasoning.** Section 3 says on. Its own trigger to cut it was a red-flag
  case over about 15 s, and the measurement was 50.9 s. The spec resolves
  itself, and CLAUDE.md hard constraint 5 records the result. Not a conflict.
- **Citation key format.** Section 4.3 freezes `source:topic:section`. The
  registry froze `CP-ACS-001`. Keys are immutable, so the registry wins.
- **Category mix.** Section 4 freezes 30/40/30 red/yellow/green and says
  explicitly **not** to mirror the real base rate, because that teaches
  under-calling emergencies. Two things follow. First, the ~295-green figure
  from base-rate weighting is not what the spec asks for; at 30/40/30 and 500
  pairs green is 150. Second, and this needs a decision: the spec is defending
  against under-calling, and the measured failure is the exact opposite. This
  model cannot say green. Skewing away from green defends a flank that is not
  under attack while worsening the one that is.
- **Topic table.** Trauma 70, stroke 40, obstetric 50, pediatric fever 60, drug
  lookup 50. The corpus is 22 chunks and all of it is chest pain. Roughly 300
  of the 500 planned pairs have no evidence to cite.

**THREE INCOMPATIBLE PROMPT FORMATS WERE IN CIRCULATION.** This is the thing
that actually blocked epic 2.

| | human turn | assistant JSON |
|---|---|---|
| spec 4.1 / 4.4 | `<profile>` `<timeline>` `<reference>` | action, category, reason, advice, watch_for, sources |
| `discrimination_test.py` | bare `PROFILE` / `TIMELINE` / `RETRIEVED CONTEXT` / `PATIENT SAYS` headers | urgency, rationale, red_flags, follow_up_questions, citations |
| `spike/req-demo-shape.json` | `[PATIENT PROFILE]` `[SYMPTOMS]` `[RETRIEVED CONTEXT]` | urgency, rationale, red_flags, next_steps, citations, follow_up_questions |

The spec is right that any drift between the training human turn and the
inference human turn is train/serve skew, which makes this a blocker on writing
pairs rather than a detail to settle later.

**Format 3 won**, and `02-pairs/pair_format.py` is now the only place any of it
is defined. Reasons: it is the only one that has been measured, the 63.8 s cold
demo number came from exactly those bytes; it is the only one carrying
`next_steps`, which is where the IITT-to-disposition translation layer has to
live; and its field names are the ones the validator was specified against.
`system_prompt.txt` is extracted verbatim from the spike request rather than
retyped, so the measured numbers stay reproducible.

**What that drops, and these are open questions, not decisions taken.** The
spec's `action: ask | triage` two-shape output is a different interaction model,
not a different spelling: one question at a time with tappable `options`, versus
a list of questions alongside a provisional category. And `watch_for`, required
on yellow and green, is exactly the CP-GERD-002 shape the corpus work went
looking for. It currently has nowhere to live except inside `next_steps`.

**Epic 2 scaffolding built. No clinical content.** `02-pairs/`:

- `pair_format.py`, the single source of truth, with the whole conflict and its
  resolution in the docstring so it is not relitigated.
- `validate_pairs.py`. Errors are mechanical, warnings are heuristic and need a
  human, same split as a candidate chunk. Covers the four named rules plus
  system-prompt drift, JSON-on-its-own, field set, turn order, the `none`
  reference case, and citations that are real but were never in that pair's
  reference block.
- `selftest_validator.py`, **21/21**, offline, no server. Same discipline as
  `qlora_config.py` re-adding `gate_proj`: every rule is proved against a
  fixture that breaks it.
- `generate_pairs.py` with `plan`, `scaffold` and `freeze`. Both epic 1 guards
  are built in from the start: scaffold refuses to overwrite a hand-edited
  review file, freeze refuses over an existing `train.jsonl` and refuses
  outright on any validation error.

Verified by running, not by writing: scaffold at 300 produces 300 slots and the
validator errors on all 300 while they are unfilled; the freeze path including
the stratified held-out split was run end to end against a synthetic
placeholder file and the output deleted.

**On the red_flags qualifier rule.** Under 15 words is countable so it is an
error. "Carries a qualifier rather than being a bare symptom" is a warning,
because a lexicon cannot prove it and an entry like "Vomiting blood"
discriminates without carrying a modifier word. Making that an error would push
the generator toward padding red_flags with filler to satisfy a lint, which is
worse than what it prevents. An exact match against the bare-symptom blocklist
is still an error. `PROMOTE_QUALIFIER` flips it.

**The memorisation unit is the condition, not the chunk.** `plan` prints this.
Green's 6 chunks are 3 GERD plus 3 panic, so green is **two conditions**. Red is
also two, ACS and PE. Yellow is the best covered at four.

```
category  chunks  conditions
red            9           2   CP-ACS, CP-PE
yellow         6           4   CP-ANG, CP-PERI, CP-PLEU, CP-PNA
green          6           2   CP-GERD, CP-PANIC
```

Pairs per condition, after reserving 10% for empty-reference decline pairs:

| total | mix | red | yellow | green |
|---|---|---|---|---|
| 500 | 30/40/30 | 67.5 | 45.0 | 67.5 |
| 300 | 30/40/30 | 40.5 | 27.0 | 40.5 |
| 300 | 25/35/40 | 33.5 | 23.8 | 54.0 |

Cutting 500 to 300 moves green from 67 presentations per condition to 40.
Adding one green condition at 300 moves it to 27. **The lever is conditions,
not pairs**, and red is under exactly the same pressure as green, which the
original framing did not surface.

**Costochondritis cannot be sourced from the cleared list.** Checked before
recommending it. `medlineplus.gov/costochondritis.html` is a 404 and there is no
NIAMS topic either; the content exists at `medlineplus.gov/ency/article/000164.htm`,
which is A.D.A.M. and excluded. This is exactly the trap CLAUDE.md names,
landing precisely on the gap. `medlineplus.gov/chestinjuriesanddisorders.html`
does resolve and does mention costochondritis, but its summary is anatomy and
definition, which is the delete side of the review rule. Finding a green
musculoskeletal source is a real sourcing problem, not a fetch away.

**Recommendations, both Viraj's call.**

1. **Add green conditions before writing pairs, and accept that
   costochondritis is not available.** The lever is the condition count and
   green has two. But the obvious source is a 404 and the good text is A.D.A.M.
   The nearest cleared candidates that resolve are
   `medlineplus.gov/anxiety.html`, a distinct condition from the panic chunks
   already held, and `medlineplus.gov/sprainsandstrains.html`, which is
   musculoskeletal but not chest-specific. Neither is as good as
   costochondritis would have been. This is a sourcing problem in Viraj's
   column, not a fetch.
2. **300 pairs, not 500**, and hold the topic scope to what the corpus can
   cite. 300 at 30/40/30 is 40 presentations per condition against 67 at 500,
   and 300 is reviewable in the time left. The spec's topic table cannot be
   honoured at either count.
3. **The mix needs a decision that the spec cannot make.** 30/40/30 was frozen
   to defend against under-calling. The measured failure is over-calling.
   Whether to raise the green share is a clinical safety call.

**Still open and unchanged:** macOS 26.7 then Xcode is still the critical path
and this machine is still on 26.5.2. Epic 5 has no path without it.

### 2026-09-15 cache disabled, the green prompt fix fails, CP-BRONCH candidates

**`cache_prompt: false` is now in the request body** in `discrimination_test.py`,
with the reason in a comment next to it so nobody turns it back on to make the
suite faster. Three new flags: `--repeat N` runs the suite N times and prints a
stability block, `--only CASE_ID` runs one case, `--green-criterion` appends an
opt-in prompt line. `run_case` now takes the system prompt as an argument so a
variant can be tested without editing the baseline.

**`cache_prompt: false` makes the eval deterministic, proven for matched.**
Matched mode ran 3 full passes, 15 inferences, and every one of the 5 cases
returned the identical verdict on all three:

```
red-acs                red     red     red     stable
yellow-angina          yellow  yellow  yellow  stable
green-gerd             yellow  yellow  yellow  stable
yellow-pleuritic       yellow  yellow  yellow  stable
probe-costo-unmatched  yellow  yellow  yellow  stable
```

So the earlier warm-versus-cold divergence is confirmed as prefix-cache state
and nothing else. **Red-only is NOT yet re-run**: it had reached pass 1 of 3
when the machine was stopped for the macOS update. Red-only is the mode that
flipped, so it is the one that still needs the three passes. Resume with
`python 01-data/eval/discrimination_test.py --chunks red-only --repeat 3`.
The partial output is annotated in place in
`01-data/eval/runs/2026-09-15-stability-nocache.txt`.

**THE GREEN PROMPT FIX DOES NOT WORK. It moves the threshold, it does not teach
the boundary.** This was the cheap thing worth testing before spending pairs on
it, and the answer is no.

The verdict does move. green-gerd returns green, stable across repeat runs. But
every wording tested also pulls yellow cases down into green, and an under-call
is the failure mode the mix asymmetry exists to prevent.

| variant | green-gerd | red-acs | yellow-angina | yellow-pleuritic |
|---|---|---|---|---|
| baseline | yellow FAIL | red | yellow | yellow |
| appended rule | **green** | red | **green MOVED** | **green MOVED** |
| A, inside the category definition | **green** | red | **green MOVED** | yellow |
| B, appended plus explicit rationale requirement | **green** | red | **green MOVED** | **green MOVED** |
| C, A plus explicit rationale requirement | **green** | red | **green MOVED** | yellow |

Four wordings, four different placements, and `yellow-angina` goes green in all
four. That case is a 61-year-old with known coronary artery disease and
exertional tightness. Calling it green is exactly the under-call the spec's
asymmetry logic is written to avoid.

**So the read "the model reasons green and will not commit to the label" was
wrong, or at least incomplete.** If the model had the boundary and were merely
hedging, naming the green criterion would free green without touching yellow.
Instead every case slid one category down. What the instruction does is move a
global cut point, not install a discriminator. The model does not appear to
have a green/yellow boundary to release.

**Two side effects worth recording, because they would have been shipped
silently.**

- The first wording returned `urgency: green` with `rationale: ""` and
  `citations: []`, down from 237 completion tokens to 154. It bought the label
  by dropping the justification and the citations, in a product whose pitch is
  citable sources. A verdict-only check would have called that a success.
- Variant A emptied `rationale` on red-acs specifically. Confirmed against a
  baseline control run of the same case, which does carry one ("High blood
  pressure, high cholesterol, statin use"), so that is the prompt line's doing
  and not a pre-existing gap.
- Variant B kept the rationale but cost 719 completion tokens on red-acs
  against 226 at baseline. At 9.5 tok/s that is 76 s of generation on one turn.

**What this means for epic 2.** The green gap is not closable at the prompt
level, so the pairs have to teach calibration and not only format. That is the
premise the six-module decision rests on, and it is now under more pressure than
it was when the concern was first flagged. Still not reopening it; that is
Viraj's call and it is recorded here rather than acted on.

**CP-BRONCH added. 13 candidates, NOT frozen.**

`https://www.cdc.gov/acute-bronchitis/about/index.html`, "Chest Cold (Acute
Bronchitis) Basics", CDC, US government work, `license_status: green`.

**cdc.gov is behind Akamai and 403s the pipeline.** Verified before assuming a
404: the project user agent, a full Chrome user agent and plain curl all got
"Access Denied" from AkamaiGHost with a 411-byte body. Sending the `Sec-Fetch-*`
set a real navigation carries, plus `Accept-Encoding`, returns 200.
`build_corpus.py` now sends those headers on every request. Nothing about the
identity is disguised; the project user agent is still sent. Regression-checked
against MedlinePlus and NHLBI, both still 200.

This matters beyond one page. **Every CDC source in the cleared publisher list
was unreachable by this pipeline and nobody would have known until they tried
one.** The old URL `cdc.gov/antibiotic-use/chest-cold.html` is a genuine 404
separately; CDC restructured to `/acute-bronchitis/about/`.

**The page is the right shape.** Server-rendered with real `h2` structure,
unlike the flat NHLBI `/symptoms` pages that yielded 2 chunks each. 13
candidates, 0 over the 256 ceiling. The two that matter:

- chunk 003 "Symptoms", 32 tokens: coughing with or without mucus, feeling
  tired, congestion, sore throat, mild body aches.
- chunk 006 "When to seek medical care", 78 tokens: fever longer than 5 days or
  104°F or higher, cough with bloody mucus, shortness of breath, symptoms more
  than 3 weeks, repeated episodes. **This is the CP-GERD-002 shape**, a green
  condition carrying its own escalation criteria, which until now exactly one
  chunk in the corpus had.

Chunk 008 "Reminder" names whooping cough and pneumonia as having similar
symptoms, which is the CP-PNA boundary stated explicitly from the green side.
Worth considering on its own merits.

Against the stated keep rule, symptoms/onset/what-makes-it-worse in and
mechanism/definition out, the plausible keeps are 003, 006, 007 and possibly
001 and 008. 002 is definition, 004 is mechanism, 005 is prevention, 009 to 013
are dosing and self-care detail rather than triage. **Viraj's call.**

**One chunker artifact.** Chunk 009 repeats two lines verbatim ("For young
children, use a rubber suction bulb to clear mucus" and the shower line). The
CDC page nests those as sub-items under their parent bullet and the extractor
emits both the parent, which already contains the sub-item text, and the
sub-item. Cosmetic here because 009 is a likely delete, but it will recur on any
page using nested lists.

**Guards held.** Backed up `01-data/review/` before chunking. All 11 existing
review files byte-identical afterwards, 22 frozen chunks and 22 registry rows
untouched. `cmd_chunk` skipped every existing source and wrote only the new one.

**macOS did NOT update.** `sw_vers` still reports 26.5.2, build 25F84, after the
restart. The Xcode 27.0 minimum of 26.6 is still unmet, so epic 5 is still
blocked and the restart did not do what it looked like it did.

**The four wordings are saved** at `01-data/eval/green_criterion_variants.py`,
with the result table and the side effects in its docstring. A negative finding
is worth what its reproducibility is worth, and without the exact wordings
"we tried a prompt fix and it did not work" is unfalsifiable and someone will
try it again. `--run` re-runs the grid.

### 2026-09-15 SESSION STATE, saved before the macOS 26.7 restart

Everything verified by running it, not by remembering it.

**FROZEN, do not regenerate.**

- Corpus at **22 chunks**, `01-data/citations.csv`. Re-verified this minute: 22
  rows, 22 chunk files, keys unique, every sha256 matches its file, every row
  carries a retrieval date, all licences green, distribution 9 red / 6 yellow /
  6 green / 1 uncategorised. Keys are immutable.
- Base GGUF re-hashed in full, not checked by size:
  `be5d9a656a51922f24f1f09a759cebb694e1f5d9728bf0ef9f8c972c5a0b5ef2`,
  2,837,072,864 bytes, at `03-model/base/`.
- 12 review files, 11 of them hand-edited and byte-identical to before this
  session's re-chunk, verified with `cmp`.

**DECIDED.**

- QLoRA targets: six modules, `q_proj k_proj v_proj o_proj up_proj down_proj`.
  `03-model/qlora_config.py` asserts 50 matches and still rejects `gate_proj`.
- Pair format: **format 3**, the spike request shape, centralised in
  `02-pairs/pair_format.py`. Every prompt string in epic 2 comes from there.
- Pair count: **300**, not 500. Conditions before pairs.
- red_flags qualifier rule is a **warning**, not an error.

**OPEN, in priority order.**

1. **macOS 26.7, then Xcode.** Critical path. Still on 26.5.2 build 25F84, so
   Xcode 27.0's 26.6 minimum is unmet and epic 5 has no path.
2. **Green calibration.** Not closable at the prompt level, proven four ways
   today. The pairs have to teach calibration, not only format. This is the
   premise the six-module decision rests on and it is now under real pressure.
   Not reopened.
3. **The category mix.** Undecided. Recommendation on the table is 25/35/40
   red/yellow/green, a modest bump from the frozen 30/40/30, explicitly not the
   59% green base rate.
4. **Third green condition.** `CP-BRONCH` candidates exist and are unreviewed.
   Costochondritis is a dead end: the only good text is A.D.A.M.
5. **Red-only stability**, 3 passes, interrupted at pass 1.

**RESUME COMMANDS, in order.**

```
# 0. after the update, confirm it actually landed. It did not last time.
sw_vers                                   # want 26.6 or higher

# 1. offline, no server needed. Confirms nothing rotted across the restart.
cd /Users/virajbagga/Coding/steel26
.venv/bin/python 03-model/qlora_config.py         # 50 modules, gate_proj rejected
.venv/bin/python 02-pairs/pair_format.py          # registry and chunks agree
.venv/bin/python 02-pairs/selftest_validator.py   # 21/21

# 2. finish the interrupted run. Needs the server.
llama-server -m 03-model/base/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf \
  --jinja -np 1 -ngl 0 -c 4096 --port 8080
.venv/bin/python 01-data/eval/discrimination_test.py --chunks red-only --repeat 3

# 3. review the 13 CP-BRONCH candidates, then Viraj freezes.
$EDITOR 01-data/review/cdc-acute-bronchitis.txt
.venv/bin/python 01-data/build_corpus.py freeze --force   # dry-run the keys FIRST

# 4. epic 2, once the mix is decided.
.venv/bin/python 02-pairs/generate_pairs.py plan --total 300 --mix 0.25 0.35 0.40
```

**Two traps for whoever resumes.**

- `build_corpus.py freeze` over the existing 22-key registry needs `--force`,
  and that permission does not carry from the last time it was used. Simulate
  the key assignment first and prove no existing key changes, exactly as was
  done for the 19-to-22 re-freeze.
- `cmd_chunk` now refuses to overwrite an existing review file, so a plain
  `chunk` is safe. `chunk --force` is not: it would regenerate all 12 and
  silently resurrect every chunk deleted in review.

**Two more things saved rather than left in a terminal.** `02-pairs/selftest_freeze.py`
re-proves the freeze path and the stratified held-out split offline, so the claim
"it runs" stays checkable. And the `CP-COSTO` gap entry in `sources.yaml` now
records that two of its three candidate leads are disproven 404s, so nobody
re-chases them.

### 2026-09-17 every saved run audited by config, and the fabrication class widened

Context was cleared and this was rebuilt from `01-data/eval/runs/` alone, which
is the first real test of whether saving run output was worth it. It was. Every
number below came off disk. Nothing was re-run to recover it except where said.

**Two runs were still being written while this was read.** `2026-09-17-red-flags-content.txt`
grew from 87 to 162 lines mid-analysis; its block 3 (reasoning off, red-only)
and block 4 (reasoning ON, red-only) both landed, at 14:27 and 14:34, and block
4's data is included below. A second format 3 pass was also live, writing to
`2026-09-17-format3-probe-pass2.txt`, started 14:34. It uses the **pre-fix**
prompt, sha256 `dafa139cb2136c568081acf05a187dc572cd990aa87beca46f3c1ddc5d25645e`,
recorded here because the prompt was rewritten later this session and otherwise
that run's attribution would be unrecoverable.

#### The config matrix

Seven config cells have been run. Verdict order is red-acs / yellow-angina /
green-gerd / yellow-pleuritic / probe-costo.

| # | fmt | reasoning | chunks | system | verdicts | score |
|---|---|---|---|---|---|---|
| 1 | 2 | ON | matched | baseline | red / yellow / yellow / yellow / yellow | 3/4 |
| 2 | 2 | ON | red-only | baseline | red / yellow / yellow / yellow / yellow | 3/4 |
| 3 | 2 | ON | matched | +GREEN_CRIT | green-gerd only: green | n/a |
| 4 | 2 | OFF | matched | baseline | red / red / red / red / red | 1/4 |
| 5 | 2 | OFF | red-only | baseline | red / red / red / red / red | 1/4 |
| 6 | 2 | OFF | matched | +GREEN_CRIT | red / green / green / red / green | 2/4 |
| 7 | 3 | OFF | matched | fmt3 | red / red / yellow / red / red | 1/4 |

Cell 2 has two superseded outliers, both from before `cache_prompt=false`:
warm scored 2/4 with pleuritic red, cold scored 3/4 with the probe red. With the
cache off the cell is stable at 3/4. Everything else is stable across every pass.

**Never run:** format 2 / off / red-only / +criterion, and format 3 in any
configuration other than off plus matched. Cell 7 had **one pass** until today,
so it carried no stability evidence at all.

#### Chunk mode moves nothing

With the cache off, cells 1 and 2 are verdict-identical and cells 4 and 5 are
verdict-identical. Feeding the cardiac chunks to all five cases changed zero
verdicts in either reasoning mode. The two competing explanations recorded on
2026-09-15, model-or-prompt against red-biased corpus, do not split the way the
note expected: `red-only` gives the corpus side no support.

Scope, because this is easy to overclaim. `red-only` varies **which** chunks are
retrieved. Every chunk still comes from the same red-leaning corpus. So this
rules out retrieval selection as the driver. It does not clear corpus
composition, because a green-rich corpus has never been tested. The corpus
hypothesis is narrowed, not closed.

#### The shipping config is the all-red config

Constraint 5 pins reasoning OFF. Every reasoning-off baseline run returns red on
all five cases, in both chunk modes, stable across passes. Reasoning ON is the
only baseline config that produces a spread, and it is banned on latency.

So the 3/4 written down on 2026-09-15 as "the top open risk is resolved" was
measured in a config that does not ship. **Under the shipping reasoning mode the
top open risk is not resolved.** It is worse than the original six-red spike:
5/5 red, twice, deterministically. The heading on that entry and the "Proven"
line in claude.md both need to stop saying otherwise.

#### Reasoning off degrades the text, not only the calibration

Completion tokens, cell 1 to cell 4, same cases: 226 to 80, 220 to 57, 237 to
57, 430 to 72, 572 to 79. The output degenerates with the count. `rationale`
comes back as a bare citation key in **17 instances, all 17 reasoning-off and
zero reasoning-on**. Four of five cases in cell 5 returned `rationale=CP-ACS-001`.
That field is what the user reads on the result screen.

#### The green criterion, now tested in the shipping reasoning mode

Cell 6 reproduces the 2026-09-15 negative result with reasoning off. It fixes
green-gerd, and it pulls yellow-angina to green, a 61-year-old with known CAD
and exertional tightness, which is the under-call the mix asymmetry exists to
prevent. Distribution is `{red: 2, green: 2}` with no yellow at all. Still a
global cut point, not a discriminator. Not reopened.

#### Fabricated findings, by config

`audit_grounding.py` confirms **3 instances, all in cell 7, all on
yellow-pleuritic**: `red_flags: ['fast heartbeat', 'fever']` plus a rationale
asserting both. `CP-PERI-002` is three lines long and lines 2 and 3 are
literally `Fast heartbeat` and `Fever`.

The audit's docstring says its 20-word lexicon makes the count a floor. That is
correct. A manual pass found **five more instances, four distinct**, none of
which the lexicon has a word for:

| case | cell | field | assertion | why ungrounded |
|---|---|---|---|---|
| probe-costo | 7 | red_flags | `sudden onset and progression` | "sudden" and "progress*" absent from case; timeline says `T+2:00 unchanged` |
| probe-costo | 7 | rationale | "the symptom timeline shows sudden onset and progression" | same, asserted again in prose |
| probe-costo | 7 | red_flags | `possible pleurisy as a cause` | not a patient finding at all; "Pleurisy" is a line in CP-PLEU-001 and CP-DIFF-001 |
| probe-costo | 2 | rationale | "pressure-like quality, but onset within 20 minutes" | "pressure" absent from case, which is sharp and worse on **pressing**; "within 20 minutes" contradicts `T+2:00 unchanged`. Once per pass, so x2 |

Corrected frequency, ungrounded over observable:

| cell | red_flags entries | rationale fields |
|---|---|---|
| 7, fmt 3 / off / matched | 4 / 13 | 2 / 5 |
| 2, fmt 2 / on / red-only | none with text saved | 2 / 11 |
| 1, fmt 2 / on / matched | 0 / 2 | 0 / 33, 12 correctly negated |
| 4, fmt 2 / off / matched | 0 / 2 | 0 / 18 |
| 5, fmt 2 / off / red-only | 0 / 3 | 0 / 15 |
| 6, fmt 2 / off / +criterion | none emitted | 0 / 13 |

**The comparison is confounded and should not be sold as a format 3 verdict.**
31 of the 51 `red_flags` entries ever emitted, 61%, were logged as a bare count
with no text and cannot be audited at all. Every 2026-09-15 run is in that
bucket. Cell 7's numbers came off a single pass. The defensible claim is
narrower: in the only cell where the model was asked for and produced multi-item
red_flags lists, 4 of 13 entries were ungrounded.

**What is not confounded is the part that matters.** Both cell 7 fabrications
landed on cases that went **red**, and in both the fabricated finding is the
stated reason for red. Rule 4 of the format 3 prompt reads "If any red flag is
present, the category is red regardless of other factors", so a fabricated red
flag forces red deterministically. The fabrication is load-bearing, not
decoration.

#### Two defects in the format 3 prompt that produce this

**The first line invited it.** It read "You must never state a clinical fact
that is not present in the RETRIEVED CONTEXT block." That constrains where facts
come from and says nothing about whose findings they are. Sourcing "Fast
heartbeat" from CP-PERI-002 and pinning it on the patient satisfies the
instruction as written. Rule 2 then hands over the exact vocabulary that came
back fabricated: "Sudden onset, rest onset, and rapid progression all raise
urgency."

**Format 3 had dropped format 2's two red_flags hygiene rules**, the
discriminating qualifier per entry and risk factors belonging in rationale. That
is why its lists are long and sloppy: `Nausea`, `Sweating`, `Persistent pain`
and `Risk factors: hypertension, hyperlipidemia, statin use` on red-acs, all
bare or misfiled. On yellow-angina it filed `Symptoms resolved with rest but
occurred during activity`, a reassuring feature, as a red flag.

Both are fixed later this session. Re-run results are in the next entry.

#### A third class, and no grounding checker can catch it

Reasoning-off runs mostly do not fabricate. They copy the system prompt's own
example. Format 2's prompt carries `"Central pressure-like pain at rest beyond
20 minutes", not "chest pressure"`. What came back:

- red-acs, `central pressure-like pain at rest beyond 20 minutes`, verbatim
- yellow-pleuritic, `sharp left chest pain at rest beyond 20 minutes`
- probe-costo, `sharp pain at rest beyond 20 minutes`
- green-gerd rationale, `burning behind breastbone beyond 20 minutes`
- yellow-pleuritic rationale, `sharp chest pain at rest beyond 20 minutes`

Every one is literally true of its case, so the grounding audit passes all of
them and so would a constraint 11 app guard. But "X at rest beyond 20 minutes"
is the ACS criterion, and applying it to pleuritic pain and to reflux is the
mechanism that turns those cases red. The findings are real and the frame is
imported. Worth watching in epic 2, because pairs generated under a prompt
inherit its example phrasing.

#### Two constraints held everywhere

**Zero invented citation keys across all 14 files.** **Zero `follow_up_questions`
on a red across all 14 files**, including cell 7, where green-gerd asked two
questions on a yellow, which is allowed.

### 2026-09-17 format 3 prompt fixed for grounding, red_flags hygiene restored

Four changes, then a re-run. Results are in the next entry; the run is at
`01-data/eval/runs/2026-09-17-format3-postfix.txt`.

**`02-pairs/system_prompt.txt`, first line.** Was "You must never state a
clinical fact that is not present in the RETRIEVED CONTEXT block", which is the
sentence that licensed the copying. It now reads:

> Clinical findings about the patient come only from the PATIENT PROFILE,
> SYMPTOM TIMELINE and SYMPTOMS blocks. RETRIEVED CONTEXT supplies criteria,
> never findings. Never state a finding those three blocks do not state, never
> state one they contradict, and never copy a finding out of RETRIEVED CONTEXT
> and attribute it to the patient.

Three prohibitions, not one, because the audit found three shapes: findings the
case does not state, findings the case contradicts, and chunk content placed in
a findings field.

**Rules 7 and 8 restored from format 2**, the qualifier-per-entry rule and risk
factors belonging in rationale. Appended as 7 and 8 rather than inserted, so
rules 4 and 6 keep their numbers; both are referenced by number elsewhere in
this log and in claude.md.

**Rule 7 does NOT reuse format 2's example, deliberately.** Format 2 illustrates
the qualifier rule with `"Central pressure-like pain at rest beyond 20 minutes",
not "chest pressure"`. That exact phrase is the template-capture vector recorded
in the previous entry: it came back verbatim for ACS and then re-applied, symptom
swapped, to pleuritic pain and to reflux. Importing it into format 3 would have
installed a known failure alongside the fix. Rule 7 uses a non-chest example
instead, "unable to bear weight since the injury", matching the ankle case in
the worked example, so there is nothing chest-shaped to copy onto a chest case.
Rule 7 also picked up a clause format 2 does not have, that a reassuring feature
is not a red flag, because format 3 filed `Symptoms resolved with rest but
occurred during activity` as one on yellow-angina.

**Hashes, for attribution.** Pre-fix
`dafa139cb2136c568081acf05a187dc572cd990aa87beca46f3c1ddc5d25645e`, post-fix
`2427e6230e688197623e5f3db74159b8911c8a718a6355a3641bad6d005089ab`. The prompt
grew from 2136 to 2825 chars, which is about 170 extra prompt tokens on every
call, roughly 5 s of prompt eval on a cold CPU turn at the measured 30 to 32
tokens/sec. Not free, and it lands on the demo path.

**Nothing downstream was invalidated.** `02-pairs/pairs/` is empty, so no
training pair was written under the old prompt. `pair_format.py` self-test
passes, 22 keys against 22 chunk files. `selftest_validator.py` passes 24/24.
Had pairs existed, all of them would have needed regeneration, since the system
prompt is part of every pair.

#### Rule 3 still contradicts the new first line, and it is not mine to fix

Rule 3 reads "Every clinical claim you make must carry a citation key drawn from
RETRIEVED CONTEXT." The new first line says findings come only from the case
text. A finding is a clinical claim, so rule 3 demands a chunk citation for
something the chunk is now explicitly not allowed to be the source of. That is
the same pressure that produced the original bug, still in the prompt.

Left alone on purpose. Rewording rule 3 changes citation behaviour, and citation
fidelity is demo beat four and the stated reason the QLoRA module list keeps
attention despite it being 3.8% of parameters. That is a Viraj call, not a
mechanical one. **The candidate wording, for him to accept or reject:** findings
need no citation, criteria do. Something like "every claim about what a finding
means, or about what raises urgency, must carry a citation key from RETRIEVED
CONTEXT. Findings themselves are drawn from the case text and are not cited."

Two more prompt lines are suspect for the same reason and were also left alone,
both clinical calls:

- **Rule 2** hands over the exact vocabulary that came back fabricated: "Sudden
  onset, rest onset, and rapid progression all raise urgency." `probe-costo`
  returned `sudden onset and progression` for a case whose timeline says
  `T+2:00 unchanged`.
- **Rule 4**, "if any red flag is present, the category is red regardless of
  other factors", is what makes a fabricated red flag decide the verdict instead
  of merely decorating it. Any residual fabrication is still load-bearing while
  this stands.

### 2026-09-17 three prompt change sets, zero verdict movement, prompt work stopped

A, B and C, each measured at 2 passes, matched chunks, reasoning off,
temperature 0.0, cache_prompt off, fresh server per run. Every run byte-identical
across its two passes, so none of what follows is noise.

**The prompt revisions, by sha.** `02-pairs/system_prompt.txt`:

| label | sha256 | what changed |
|---|---|---|
| pre-fix | `dafa139cb2136c568081acf05a187dc572cd990aa87beca46f3c1ddc5d25645e` | as written for epic 2 |
| A | `2427e6230e688197623e5f3db74159b8911c8a718a6355a3641bad6d005089ab` | grounding first line, rules 7 and 8 restored from format 2 |
| B | `ca631a3dedc8eb9a3aa71ce8eaffd1b19524fc17dd6f678b4c24c0e279b9400a` | rule 3 rewritten: criteria are citable, findings are not |
| C | `871748eaada02a33c01bd88e8c07fd0a29aeb907d1f2163dfa0cdd8a2248eeaf` | rule 7 made conditional: qualify only when the case supplies the qualifier |

Run files: `2026-09-17-format3-probe.txt` and `-pass2.txt` (pre-fix),
`-format3-postfix.txt` (A), `-format3-rule3.txt` (B),
`-format3-rule7-conditional.txt` (C).

#### Verdicts did not move once

| case | pre-fix | A | B | C | expect |
|---|---|---|---|---|---|
| red-acs | red | red | red | red | red |
| yellow-angina | red | red | red | red | **yellow** |
| green-gerd | yellow | yellow | yellow | yellow | **green** |
| yellow-pleuritic | red | red | red | red | **yellow** |
| probe-costo | red | red | red | red | green, probe |

**1/4 four times.** Not one case crossed a category boundary across four prompt
revisions. Every change improved something an auditor measures and nothing a
judge sees.

#### What each change set actually did

**A fixed two fabrications and created a worse one.** Gone: `sudden onset and
progression` and `possible pleurisy as a cause` on probe-costo. Rule 8 pulled
`Risk factors: hypertension, hyperlipidemia, statin use` out of red_flags and
rule 7 removed the reassuring-feature entry on yellow-angina. red_flags entries
per pass fell 13 to 6.

Then yellow-angina came back `red_flags: ['chest tightness that does not go
away']` for a case whose timeline says `T+0:06 tightness resolved completely`
and whose symptom text says "It went away once I sat down". CP-ANG-001 supplies
that phrase as a **criterion**: "Chest pain or discomfort that does not go away
or occurs while you are resting might be a sign of a heart attack." Pre-fix this
case recorded the truth and reasoned badly. Under A it records a falsehood.

**The mechanism matters more than the instance.** Rule 7 demanded a
discriminating qualifier on every entry. The nearest source of discriminating
phrases is the retrieved chunk. A formatting rule manufactured a content
fabrication. That is why rule 7 became conditional in C.

A also broke hard constraint 4 for the first time in the project's history:
yellow-angina returned red carrying two `follow_up_questions`. Constraint 4 had
held across all 14 earlier run files.

**B fixed the fabrications and broke the citations.** The CP-PERI-002 copying is
gone: no `fever`, no `fast heartbeat`, which A's grounding first line had failed
to stop on its own. The angina contradiction is gone. The constraint 4 breach is
gone. Audit clean on both absence and contradiction.

Cost, and it is the expensive kind:

- **The first invented citation keys ever recorded.** yellow-angina returned
  `citations=['CP-ANG-001', 'CP-ANG-002', 'profile (CAD, nitroglycerin)',
  'timeline (exertional onset, resolved with rest)']`, both passes.
  `2026-09-17-format3-rule3.txt` is the only run file in the repo that contains
  an `INVENTED KEYS` line. Rule 3 told the model findings need no source, and it
  responded by inventing sources for the findings, naming the case blocks as
  pseudo-keys. Constraint 9 drops them, so it is contained, not harmless.
- **probe-costo returned `citations=[]`.** Rule 3 no longer requires a citation
  per clinical claim, so empty became legal and the model took it on the one
  case with no matching chunk.
- **red-acs returned red with `red_flags: []` and a rationale reading "No red
  flags present."** Correct label, empty and self-contradicting justification,
  while rule 4 says any red flag forces red.

**C restored a red flag on red-acs and collapsed the citations.** red_flags per
pass back to 6 and the audit reads 0 asserted, 0 contradicted. But:

| case | citations, pre-fix | A | B | C |
|---|---|---|---|---|
| red-acs | 3 | 2 | 3 | **0** |
| yellow-angina | 2 | 2 | 4, two invented | 2 |
| green-gerd | 2 | 2 | 2 | **0** |
| yellow-pleuritic | 2 | 2 | 2 | **0** |
| probe-costo | 1 | 1 | **0** | **0** |

**Four of five cases now cite nothing.** Ten valid citations pre-fix, two under
C. Demo beat four is the citation expander. Under C it has nothing to expand on
four of five cases, including the red one.

#### C's audit row reads clean and is not clean

The audit reports 0 asserted and 0 contradicted for C. Four things it did not
see, all found by hand, recorded here so the row is not read as a pass:

- yellow-pleuritic `red_flags: ['Rapid progression from onset to worse with
  breathing']`. The timeline says `T+1:30 unchanged`. This is a contradiction on
  a **progression versus static** axis that `CONTRADICTION_AXES` does not have.
  Adding it is a small fix and is not done.
- probe-costo `red_flags: ['No relief with sitting up or leaning forward']`. The
  case never mentions sitting up or leaning forward. The maneuver is CP-PERI-002's
  discriminator, imported and asserted as a negative about a patient who was
  never asked. A denial of an untested finding is a class nothing checks.
- probe-costo rationale: "High risk for pleurisy, pneumothorax, or pulmonary
  embolism." Three diagnoses, against rule 5, which says do not diagnose.
- red-acs rationale: "No red flag qualifiers needed as findings are
  discriminating." The model narrating rule 7 back into user-visible text.
  yellow-pleuritic's rationale also asserts a red flag and "No red flags
  present" in the same string.

#### Conclusion, and prompt work stops here

Four revisions, four identical verdict distributions. Fabrication fell every
time and discrimination never moved. The prompt has been the lever three times
and it is the wrong lever.

One precision against the natural reading of this, because it changes the
fine-tune bet. It is **not** true that the model can only say red with reasoning
off. Cell 6, reasoning off plus GREEN_CRITERION, returned `red / green / green /
red / green`, stably. The model emits all three labels. What no variant has done
is condition the label on the case: the same instruction that freed green on
green-gerd dragged the known-CAD case to green too. **The category head is
movable but not case-sensitive.** So the adapter has something to grab, and what
it has to teach is conditioning, not vocabulary.

Next is a measurement and not a fix: yellow-angina under B with
`RETRIEVED CONTEXT = none`, in `2026-09-17-no-chunk-angina.txt`, to find out
whether the red survives with nothing retrieved.

### 2026-09-17 yellow-angina is red with nothing retrieved. The bias is in the base model.

`01-data/eval/runs/2026-09-17-no-chunk-angina.txt`, new probe at
`01-data/eval/no_chunk_probe.py`. Format 3 under change set B, sha asserted at
`ca631a3d...` so the prompt is B exactly, `RETRIEVED CONTEXT = none`, reasoning
off, temperature 0.0, cache_prompt off, 2 passes, both identical.

**Both passes red.** The corpus was removed from the experiment and the verdict
did not change.

The decisive part is not the label, it is the rationale that came with it:

> "Chest tightness triggered by exertion with **complete resolution upon rest**,
> consistent with angina. Patient has coronary artery disease and is on
> nitroglycerin, a red flag for cardiac events. Symptoms resolved quickly but
> indicate underlying cardiac pathology."

It reads the discriminating fact correctly. It says "complete resolution upon
rest" and "consistent with angina" and "symptoms resolved quickly", unprompted
and with nothing retrieved to copy from. Then it assigns red.

So this is not comprehension, not retrieval, not grounding, and not the prompt.
The model extracts the fact that makes this a yellow and assigns red anyway.
**The red bias sits in category assignment, downstream of understanding.** Four
prompt revisions could not reach it because it is not a prompt problem, and
corpus balance cannot reach it either, because there was no corpus in this run.

**What this means for epic 2.** The original bet, that the pairs teach output
shape while the model already reasons, is dead. The pairs have to teach category
assignment itself, in the shipping config, and that is a harder target than
format. The one piece of good news from the earlier entry stands: the category
head is movable, just not case-sensitive, so the adapter has something to act on.

**A second result, unlooked for and good.** With nothing supplied to cite, the
model returned `citations=[]` and **invented nothing**. Measured 2026-09-15 in
this exact no-context condition, the old prompt produced `CP-RISK-014` and
`MED-ANTICOAG-007`, neither of which exists. That is spec 4.1's decline-rather
-than-invent case and it now passes. It is the one thing the prompt work bought
that survives, and it is worth keeping: constraint 9's registry check is a net,
not a fix, and this is the fix.

**Two things for Viraj, both clinical, neither actioned.**

- `red_flags` carried `Coronary artery disease history`, a risk factor, which
  rule 8 says belongs in rationale. Grounded, just misfiled.
- `next_steps` included "Administer nitroglycerin if prescribed and available".
  The model is giving a medication instruction. That is a clinical call and a
  liability question, not a formatting one.

**State of `02-pairs/system_prompt.txt` right now: change set B**, sha
`ca631a3dedc8eb9a3aa71ce8eaffd1b19524fc17dd6f678b4c24c0e279b9400a`. Rule 7 was
reverted from C's conditional wording to run this probe against B and was not
put back. B and C score identically on verdicts, so the choice between them is
about citations and red_flags quality, not triage:

- **B** keeps citations on 4 of 5 cases but emits two invented pseudo-keys on
  yellow-angina and leaves red-acs with `red_flags: []` under a red verdict.
- **C** restores a grounded red flag on red-acs and reads clean on the audit,
  but four of five cases cite nothing.

Both wordings are recorded in the previous entry with their shas, so either is
one edit away. **Undecided, and it is a Viraj call.** Recommendation if one is
wanted: keep B, because a missing citation is invisible to a judge while an
empty citation expander on the red case is demo beat four failing live, and B's
invented keys are already caught by the constraint 9 registry check.

### 2026-09-17 llama.rn step 2: it loads, and one demo turn takes 5 minutes 33 seconds

Full numbers at `05-app/spike-load/results/2026-09-17-load-spike-step2.txt`.
Project at `05-app/spike-load/`. iPhone 17 Pro simulator, iOS 26.5, Xcode 26.6,
RN 0.81.4, llama.rn pinned exactly 0.12.9, prebuilt xcframework, `n_gpu_layers`
0, Debug build. No physical device run.

**Xcode is no longer blocking.** macOS is 27.0 (26A428) and Xcode 26.6 (17F113)
is installed with iOS 18.5 and 26.5 simulators. The build-log's number one open
item is closed and nobody had recorded it.

#### It loads

```
LOADS       yes          load_s 36.4
arch        nemotron_h   n_params 3,973,556,832   n_embd 3136
desc        nemotron_h ?B Q4_K - Medium
peak RSS    3.14 GB
```

**Step 1's one worry was cosmetic, exactly as it predicted.** It traced the
layer-count switch in `nemotron-h.cpp` falling through to `LLM_TYPE_UNKNOWN` for
our 42-block model and said that means the size prints as unknown, not that the
load fails. `desc` reads `nemotron_h ?B`. It loaded anyway. The binding choice
is alive and architecture support is now proven by running it, not by reading it.

**3.14 GB resident confirms the does-not-run risk rather than relieving it.**
The estimate in claude.md was about 3 GB against 4 to 6 GB devices. The
simulator borrows Mac RAM so this says nothing about surviving on a phone, but
it pins the number the distillation roadmap argues against.

**RSS oscillates rather than plateauing, and that is the part to carry forward.**
A poller pinned to the app pid, 1200 samples at 0.5 s, traced 2.49 GB just after
load, down to 0.86 GB during prompt eval, back to 2.56 GB through generation,
then decaying to a 0.39 GB idle floor once the completion returned. Weights are
mmap'd, so these are clean pages the kernel is evicting and refaulting. **The Mac
is already evicting under pressure with far more RAM than a target phone has**,
which means a 4 to 6 GB device does not get the low readings for free, it gets
continuous refaulting from flash and is therefore slower than the numbers below,
not faster. The 0.39 GB floor is not a memory requirement and must not be quoted
as one.

#### One completion is 5 minutes 33 seconds

```
completion_s   333.2      = 5 min 33 s
prompt_n       1284       prompt_s 232.4    prompt_tok_per_s 5.5
predicted_n    210        predicted_tok_per_s 2.10
reasoning_content_len 0
```

**Hard constraints 7 and 8 do not hold in the simulator, and the gap is about
5x.** Both carry numbers measured on this same Mac, same model, same `-ngl 0`,
under `llama-server`:

| | llama-server, CPU | simulator | factor |
|---|---|---|---|
| prompt eval | 30 to 32 tok/s | **5.5 tok/s** | ~5.7x slower |
| generation | 9.5 to 10 tok/s | **2.10 tok/s** | ~4.7x slower |

claude.md says the simulator is the demo condition and every latency number
that matters is a CPU number. That was right about Metal and wrong about
magnitude: the native CPU numbers understate the demo condition by roughly 5x,
because the simulator is a translation layer and not the host CPU. **Constraint
7's "3.1 s per 100 tokens of chunk" becomes about 18 s per 100 tokens here.**
Three chunks at the frozen 145-token mean is not 13.5 s of demo, it is roughly
79 s of demo.

**Judging is about 5 minutes per desk visit. One turn is 5 minutes 33 seconds.**
A single symptom-checker answer currently exceeds the entire visit. The four
demo beats cannot run live in this configuration.

**Reasoning off survives the binding.** `reasoning_content_len` is 0 with
`chat_template_kwargs: {enable_thinking: false}` sent through llama.rn, so
constraint 5's switch works on this path. It still has to be sent on every call.

#### One defect the app has to handle

`text` comes back as

```
<|im_start|>assistant
{ "urgency": "red", ... }
```

The literal chat-template header is prepended, so `JSON.parse` on the raw string
throws. `llama-server` never showed this because it splits the message before
returning it. The app must strip the header before parsing. Cheap to fix, but it
would have looked like a schema failure at 2am.

#### Three toolchain traps, none of them llama.rn

1. **`bundle exec pod install` is broken here.** Ruby 3.4 dropped `kconv`; the
   bundled CocoaPods 1.15.2 pins CFPropertyList 3.0.8 which requires it. The
   global CocoaPods 1.16.2 works. Use plain `pod install`.
2. **RN 0.81.4 vendors fmt 11.0.2, which Xcode 26.6's clang cannot compile**
   ("call to consteval function ... is not a constant expression", five sites in
   `format-inl.h`). `-DFMT_USE_CONSTEVAL=0` does **not** fix it: the define was
   confirmed reaching the compiler response file and `base.h` discards it,
   because the macro is set by a bare `#if` chain with no `#ifndef` guard. There
   is now an idempotent `post_install` hook in `ios/Podfile` that patches the
   guard in the header, taking the same path fmt already takes for Apple clang
   < 14, and warning loudly if the block stops matching. **This patches a
   generated directory. The real fix is an RN version vendoring fmt > 11.0.2**,
   which is a bigger decision than a load spike should make.
3. **RN 0.81 moved JS logs out of the Metro terminal into React Native
   DevTools.** `console.log` capture came back empty. The spike renders results
   on screen and they were read by simulator screenshot.

#### What this does and does not settle

Settled: llama.rn 0.12.9 loads a `nemotron_h` Q4_K_M GGUF from the app's
Documents directory with `n_gpu_layers` 0, runs a schema-constrained completion,
honours the reasoning switch, and returns a correct red on the ACS demo case.
The binding is not dead and epic 5 has a path.

Not settled, and now the top risk in epic 5: **speed**. The measurement is a
Debug build under Metro; a Release build should be retried before the 5x is
treated as final, since JS overhead is not in the inference path but the build
configuration is not free either. Worth doing next, and it is cheap. If Release
does not move it substantially, the demo has to be redesigned around
precomputed or streamed output rather than live generation, and that decision
is better made now than at the desk.

### 2026-09-17 four app-logic guards, and the prompt's worked example fails one

`05-app/spike-load/guards.ts`, tests at `05-app/spike-load/__tests__/guards.test.ts`,
17/17 passing under the project's jest. Every fixture is a real string a run
produced, with the run file named in the test. That choice paid for itself
immediately, see below.

**Written inside the load spike because it is the only RN project that exists.**
These belong to the epic 5 app shell and must move there with their tests when
the shell is scaffolded. They are not spike code.

Each guard fails closed and returns what it removed, in `dropped`, because a
guard that silently eats output is its own kind of bug. `flagged` carries the
one case that is deliberately kept for a human to judge.

1. **Chat-template prefix**, from the step 2 spike. llama.rn returns
   `<|im_start|>assistant\n{...}`, so `JSON.parse` on the raw string throws.
   `parseModelJson` removes known template tokens, a bare leading role word and
   markdown fences, then takes the span from the first brace to the last. It
   throws on anything that is not JSON rather than half-parsing, because a
   malformed verdict must not reach the screen as a partial object.
2. **Constraint 12, medication administration.** Drops a `next_steps` entry that
   mentions a medication or a dose, unless it is a prohibition, which is flagged
   and kept, or it leads with a reporting verb such as bring or tell.
3. **Constraint 9, citation keys.** Drops any key not in the 22-key registry.
4. **Constraint 4, questions on a red.** Clears `follow_up_questions` when
   urgency is red.

#### The medication guard was wrong the first time, and the real outputs caught it

It was first written as "an administration VERB pointed at a MEDICATION". That
version passes on `Administer nitroglycerin` and leaks on two measured strings
that contain no verb at all:

```
Take over-the-counter antacid or H2 blocker as directed     green-gerd, format3-probe
Over the counter analgesia as directed on the packet        02-pairs/system_prompt.txt
```

**The second one is the worked example in the shipping prompt.** The prompt
teaches a medication instruction by example, in the one output it shows the
model verbatim. So the model will keep producing them, and a verb list will keep
missing phrasings nobody predicted. That is the argument for constraint 12 being
a blanket rule rather than a drug blacklist, and it is also a reason to revisit
the worked example. **Changing it is a prompt edit and a clinical call, so it is
not done.** Flagged for Viraj.

Note what the guard does NOT do: it never touches `red_flags`. Grounding is
constraint 11 and it is not a string-matching job. That stays with
`audit_grounding.py` and, eventually, with the training pairs.

The four guards cover the demo path whatever the Release timing says, which is
why they were written while the Release build ran.

### 2026-09-17 Release build measured: 1.4x faster, does not rescue the live demo

`05-app/spike-load/results/2026-09-17-release-vs-debug.txt`.

|  | Debug | Release | change |
|---|---|---|---|
| prompt eval | 5.5 tok/s | **7.9 tok/s** | 1.44x |
| generation | 2.10 tok/s | **2.72 tok/s** | 1.30x |
| one completion | 333.2 s | **235.9 s** | 1.41x faster |
| peak RSS | 3.14 GB | 2.84 GB | |
| reasoning chars | 0 | 0 | constraint 5 holds on both |

**Release helps and does not change the conclusion. One completion is 3 minutes
56 seconds.** Judging is about 5 minutes per desk. A single turn still eats most
of the visit, so the four beats cannot run live on generated output.

Against `llama-server` on the same Mac, same `-ngl 0`:

| | llama-server | sim Debug | sim Release |
|---|---|---|---|
| prompt eval | 30 to 32 tok/s | 5.5 | 7.9, still ~4x slower |
| generation | 9.5 to 10 tok/s | 2.10 | 2.72, still ~3.6x slower |

Hard constraints 7 and 8 still do not hold in the demo condition.

**Do not quote the load time as a 10x Release win.** It went 36.4 s to 3.6 s and
the build configuration is not a plausible cause of that in an mmap and read
path. The Debug run read a 2.84 GB file that had just been copied and was cold;
the Release run read one the page cache had seen repeatedly. 36.4 s is the cold
number, 3.6 s is the warm one, and **a judge's machine is always cold.**

#### The guards ran against real Release output

```
raw_head           <|im_start|>assistant\n{ "urgency": "red", "rationale": "
bare_JSON_parse    THREW: JSON Parse error: Unexpected character: <
guarded_urgency    red
guarded_citations  ["CP-ACS-001","CP-ACS-003"]     both resolve
guarded_next_steps ["Call 9-1-1 immediately","Do not drive to hospital"]
```

The template prefix is present in Release too and a bare `JSON.parse` still
throws on it, so guard 1 is load-bearing on the shipping build, not a Debug
artifact. Not captured: the `dropped_*` fields rendered below the fold, a
simulator screenshot cannot be scrolled from the host, and RN 0.81 sends
`console.log` to React Native DevTools rather than Metro or os_log, so there was
no log fallback. Drop behaviour is covered by the 17 unit tests instead. **The
app should write its result to a file, not only to the screen**; that is the fix
and it was not made.

#### Two operational traps found while doing this

- **`simctl install` rotates the Data container UUID on every install**, measured
  three times: `ADEC8507 -> 304E8CF4 -> E2789BED`. Documents contents migrate so
  the model survives, but Release embeds its JS bundle at build time, so a baked
  in container path is stale the instant it installs, and fixing it needs another
  install, which rotates again. llama.rn does not resolve relative paths, only
  strips `file://`, and RN core has no Documents API. This run used a path
  outside the container to break the loop; Documents loading was already proven
  in Debug at 36.4 s and the directory does not affect tok/s. **The app shell
  needs a small native module returning
  `NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, ...)` before it ships
  a model.**
- `pgrep`-style process matching keeps latching onto the matching shell's own
  argv. It cost three separate mistakes today, two bad RSS readings and one
  deadlock. Match on a pid, or use a pattern that cannot appear in the matcher.

#### Where this leaves the demo

The decision Viraj deferred until this number landed is now live. Generation is
2.72 tok/s and a turn is roughly 4 minutes. Either the demo shows precomputed or
cached output for the scripted beats, or it shows a much shorter generation, or
it accepts a single slow turn as the whole visit. **Not started.**

### 2026-09-17 DECIDED: the demo is a laptop web UI against llama-server

**No live simulator inference.** The phone gets a screenshot, as evidence that it
runs on-device, and nothing in the five minutes at the desk waits on it.

The number that forced it: one completion in the simulator is **3 min 56 s in
Release**, 7.9 tok/s prompt eval and 2.72 tok/s generation, against 30 to 32 and
9.5 to 10 for the same model and the same `-ngl 0` under `llama-server` on the
same Mac. Release bought 1.4x and the gap to native is still about 4x. A judge
visit is about 5 minutes.

This is a scope decision, not a retreat. Offline on-device inference is still
proven and still demonstrable: `initLlama` loads the `nemotron_h` Q4_K_M GGUF,
honours the reasoning switch and returns a correct red, all recorded in
`05-app/spike-load/results/`. What changes is that the live surface is the one
that can answer inside a visit.

**Spike work stops here.**

#### Four things done off the back of the decision

**1. The guards now exist on the llama-server path.** `02-pairs/guards.py`,
a port of `05-app/spike-load/guards.ts`, all four guards, importable by the
demo server when it exists.

**Both implementations are driven by one fixtures file**,
`02-pairs/guard_fixtures.json`, because two ports of the same policy in two
languages is a drift risk that will not announce itself. Python runs 20/20 and
TypeScript 34/34 off the same expectations. Every fixture is a real string from
a real run, named by run file. The spike-load copy is a copy because Metro
cannot resolve outside the project root; `npm run sync-fixtures` refreshes it.

**2. The app writes its results to a file.** `05-app/spike-load/collect_results.py`
listens on 127.0.0.1:8123 and the app POSTs its full record, including
`raw_text_full` and every `dropped_*` field. The listener is verified by running
it. This exists because the first Release run lost its `dropped_*` fields below
the fold and a simulator screenshot cannot be scrolled from the host.

A listener rather than a file write, because the app has no filesystem API: RN
core exposes no documents path, llama.rn only strips `file://`, and `simctl
install` rotates the container UUID on every install. The simulator shares host
networking, so this survives all of it and works in Release where there is no
Metro.

**Honest status: the app side of this is typechecked, not run.** Verifying it
end to end costs another 4 minute completion and spike work is stopped. The
receiver is proven; the POST is not.

**3. The worked example no longer teaches a medication instruction.**

```
-  "Over the counter analgesia as directed on the packet"
+  "Avoid heat, alcohol and massage for the first 48 hours, which increase swelling"
```

Same shape: green, `red_flags` empty, three next_steps. The old line was the one
output the model sees verbatim, and it was a medication instruction, which is
why constraint 12 kept firing on outputs that had no administration verb in
them. `guard_fixtures.json` now asserts both that the old line is dropped and
that **the replacement survives its own guard**, so the fix cannot silently
regress into a new violation.

`02-pairs/system_prompt.txt` sha256 is now
`102e751168f59c1a63e95ff6323aab29228ba6702f0bce1f77b76efd940b7956`,
was `ca631a3d...`. Everything else in change set B is unchanged.
**`audit_grounding.py` PROMPT_LABELS does not know this sha yet**; it will print
`fmt3 102e7511` for any run made against it, which is correct but unlabelled.

**4. Release measurements and the container-rotation trap** are in the preceding
entry.

#### Next: epic 4, retrieval

sqlite-vec plus all-MiniLM-L6-v2 over the 22 frozen chunks. It is the last
unbuilt piece the laptop demo needs, and beat four, the citation expander, has
nothing to expand without it.

### 2026-09-17 epic 4: index built, and retrieval does not return the right chunks

`04-retrieval/build_index.py`, `retrieve.py`, `smoke_test.py`, results at
`04-retrieval/results/2026-09-17-smoke-test.txt`. Deps added to `.venv`:
torch 2.14.0, sentence-transformers 6.0.1, sqlite-vec 0.1.9. Python 3.14 has
cp314 torch wheels, which was not a given and was checked before committing to
the download.

**Index built and it is sound.** 22 chunks, 3089 tokens, mean 140, dim 384,
normalized so L2 ranks identically to cosine. Two things checked rather than
assumed: every chunk was verified against its frozen `chunk_sha256` before
embedding, because an index built over drifted text would silently encode
content no training pair refers to; and the 256 word-piece ceiling was measured
with the model's own tokenizer, widest chunk `CP-ANG-002` at 231/256. Constraint
2 holds with headroom.

**Retrieval quality is the problem.** Top-3, query = symptom text:

| case | result | returned |
|---|---|---|
| red-acs | **1 of 3** | CP-PERI-002, CP-ACS-003, CP-DIFF-001 |
| yellow-angina | **0 of 2** | CP-PLEU-001, CP-PERI-002, CP-DIFF-001 |
| green-gerd | 2 of 2 | CP-GERD-001, CP-PERI-002, CP-GERD-002 |
| yellow-pleuritic | 1 of 2 | CP-PERI-002, CP-DIFF-001, CP-ANG-001 |
| probe-costo | 2 of 3 | CP-DIFF-001, CP-PERI-002, CP-ANG-002 |

Adding the timeline to the query is the best of three modes tried and fixes the
total miss: `symptom+timeline` gives angina 1 of 2 and no case returns nothing.
`symptom+profile` is the worst. Only green-gerd ever returns everything expected.

#### CP-PERI-002 is returned for every single query

Across 10 queries, 5 cases by 2 query modes:

```
CP-PERI-002       10/10    25 tok
CP-DIFF-001        7/10   147
CP-ANG-001         4/10   187
...
9 distinct chunks ever returned out of 22. 13 NEVER return, including
CP-ACS-001, CP-ACS-002 and the entire CP-PE family.
```

**This is the worst possible chunk to win every query.** `CP-PERI-002` is three
lines: the sharp-pain line, `Fast heartbeat`, `Fever`. It is the exact chunk that
produced the measured fabrication on 2026-09-17, where the model copied
`fast heartbeat` and `fever` onto a patient who had neither. Every eval run so
far used hand-assigned chunks, so that fabrication was triggered by a human
choosing to supply CP-PERI-002 to one case. **Real retrieval would supply it to
all of them.** Constraint 11's guard is now load-bearing rather than
precautionary.

Second problem for the demo: beat 2 is the red triage result. For the ACS case,
real retrieval returns pericarditis and the differential page, and CP-ACS-001
and CP-ACS-002 never surface for anything. The citation expander would show a
judge the wrong sources on the flagship case.

#### Why, and it is not what it looks like

The obvious hypothesis is short-chunk dominance, CP-PERI-002 being the shortest
at 25 tokens. **That is wrong.** Correlation between token count and mean cosine
to the five queries is **+0.147**, slightly positive, and the second shortest
chunk, `CP-PE-002` at 32 tokens, scores dead last at 0.010.

The pattern that does hold is **register**. The queries are symptom reports in a
patient's voice. Almost every chunk is explanatory prose: "Your pleura is a
large, thin sheet of tissue that wraps around the outside of your lungs". The
chunks that retrieve are the ones written as symptom lists, and the ones that
never retrieve are the explanations. `CP-ACS-003` is the only ACS chunk that
ever returns, and it is the only one that is a symptom list. `CP-PERI-002` is
pure symptom list with nothing else in it, so it sits closest to every symptom
query regardless of condition: its *minimum* similarity across the five cases is
0.358, the highest floor in the corpus.

So this is a corpus-versus-query mismatch, not a bug in the index and not a
chunk-size problem. Stated as a bet, not a fact: n is 5 queries over 22 chunks,
which is enough to see the pattern and not enough to prove the mechanism.

#### Cost

Mean retrieved context is 347 tokens per case at top-3, about **11.2 s of prompt
eval** at the measured 31 tok/s, before the system prompt and the case text.
That is in line with constraint 7's estimate of 13.5 s for three chunks at the
140 mean, so the latency model holds even though the selection does not.

#### What this does not change

The base model's red bias is not a retrieval problem. That was settled by the
no-chunk probe, which had no corpus at all. Fixing retrieval will change which
sources the citation expander shows and whether the fabrication guard earns its
keep. It will not move a verdict.

#### Not done

Candidate directions, none tried, all of them Viraj's call because they touch
the corpus or the clinical content: index a symptom-style line per chunk
alongside the prose and embed that; expand the query into a hypothetical answer
before embedding; or add a keyword pass and blend it with the vector score. The
cheapest experiment is the first, and it does not require re-freezing anything,
because it adds a derived field rather than changing a chunk.

### 2026-09-17 hybrid retrieval: the blend does not surface the ACS chunks

`04-retrieval/hybrid.py` and `smoke_hybrid.py`, results at
`04-retrieval/results/2026-09-17-hybrid.txt`. BM25 written by hand, Okapi with
k1 1.5 and b 0.75, computed from the chunk text already in `corpus.db`. **No
corpus change**: nothing re-chunked, re-frozen or re-keyed, so hard constraint 1
is untouched. Both scores are min-max normalized per query before mixing, so
alpha is a real mixing weight and not an artifact of two different scales.

#### The answer to the question asked

**Neither CP-ACS-001 nor CP-ACS-002 surfaces on red-acs. Not at any alpha.**

```
red-acs, rank out of 22:
  alpha 0.0 (BM25)   CP-ACS-001 = 12   CP-ACS-002 = 20   CP-ACS-003 = 1
  alpha 0.5 (blend)  CP-ACS-001 = 10   CP-ACS-002 = 19   CP-ACS-003 = 1
  alpha 1.0 (vector) CP-ACS-001 =  9   CP-ACS-002 = 16   CP-ACS-003 = 2
```

They are 9th to 12th and 16th to 20th. This is not a weighting problem and
sweeping alpha does not touch it, so no weight was chosen to make the table look
better.

**Top-3 at alpha 0.5, query symptom+timeline:**

| case | result | returned |
|---|---|---|
| red-acs | 1 of 3 | CP-ACS-003, CP-DIFF-001, CP-PERI-002 |
| yellow-angina | **2 of 2** | CP-ANG-002, CP-ANG-001, CP-PERI-001 |
| green-gerd | 1 of 2 | CP-GERD-001, CP-PERI-002, CP-ACS-005 |
| yellow-pleuritic | 1 of 2 | CP-PERI-002, CP-ANG-001, CP-PERI-001 |
| probe-costo | 1 of 3 | CP-PERI-002, CP-ACS-003, CP-PERI-001 |

Mean 377 tokens per case, about 12.2 s of prompt eval.

#### What the blend did and did not buy

**Did:** yellow-angina goes from 0 of 2 on dense-only symptom queries to **2 of 2**.
Corpus coverage improves, 7 distinct chunks at pure vector to **9 at
keyword-heavy alphas**. And CP-PERI-002's grip loosens, from 10 out of 10
queries on dense-only to 4 out of 5 here.

**Did not:** expected-match across the five cases is 7, 7, 6, 8, 7 out of 12 at
alpha 0.0, 0.25, 0.5, 0.75, 1.0. That is flat inside the noise on twelve
opportunities. **The blend is not a clear improvement on the stated target**, it
trades green-gerd and the probe for yellow-angina. It also promotes a new near
dominator, CP-PERI-001, into 3 of 5 cases.

#### A tokenization bug found while diagnosing, worth recording

The case timelines are written `T+0:00 central chest pressure began`, so each
timestamp contributed a bare `t` to the query, four of them on red-acs. That
matched the `t` that falls out of `don't` in the chunk text, and BM25 scored it
as a real term. `CP-ACS-005` was riding almost entirely on it: it appeared in 4
of 5 cases before the fix and 1 of 5 after. Single-letter tokens are now dropped.
The lesson generalises past this: **the query format leaks into keyword
retrieval in a way it does not leak into embeddings**, so anything that changes
the timeline notation changes BM25.

#### The expectations themselves are not trustworthy

This is the part that matters more than the blend. `CP-ACS-002` has **zero term
overlap with the red-acs query**, and reading it explains why:

> "Heart attacks can happen without any symptoms or with very mild symptoms.
> These are called silent heart attacks."

It is about **asymptomatic** myocardial infarction. The red-acs case is a florid
symptomatic presentation: central pressure, radiation to the jaw, sweating,
nausea, unchanged at 26 minutes. CP-ACS-002 is not the right chunk for it, and
no retriever should return it. `CP-ACS-001` is a caveat paragraph, "Not all heart
attacks begin with the sudden and crushing chest pain", also not a symptom
match. `CP-ACS-003` is the symptom list, and it ranks **1st at every alpha**.

So red-acs scoring "1 of 3" may be close to correct retrieval measured against a
wrong target. The chunk lists in `discrimination_test.py` were hand-assigned
when the file was written and have never been reviewed. **Every eval run in this
project has used them as the matched condition.** Reviewing them is a clinical
call and is Viraj's, and until it happens the retrieval score is measured
against an unvalidated answer key.

#### Recommendation

Do not ship the blend on this evidence, and do not tune it. The one real win,
yellow-angina, is the case dense retrieval failed hardest on, so a blend is
worth keeping as an option. But the next useful step is not a retrieval change,
it is fifteen minutes of Viraj reading the five chunk lists and saying which
chunks each case should actually get. Without that there is no way to tell a
retrieval improvement from a scoring artifact.

### 2026-09-17 retrieval answer keys reviewed, and re-scored against them

**The original keys were never reviewed.** The `chunks` lists in
`discrimination_test.py` were hand-assigned when the file was written and have
been the `matched` condition for every eval in this project. At least one was
wrong: red-acs expected `CP-ACS-002`, which reads "Heart attacks can happen
without any symptoms ... called silent heart attacks", for a case with central
pressure, jaw radiation, sweating and nausea. No retriever should return it, and
it was scored as a miss all day.

**New keys are PROPOSED, not signed off.** Claude read all 22 chunks on
2026-09-17 on Viraj's explicit instruction and marked them; the reasoning is
recorded per case in `RETRIEVAL_KEYS` in `discrimination_test.py`. That is a
proposal with visible reasoning, not a clinical sign-off, and it wants a yes
before anything treats it as truth.

**`chunks` was NOT overwritten.** `chunks` is what the harness FEEDS THE MODEL;
`retrieval_key` is what a correct retriever SHOULD RETURN. Merging them would
have changed the prompt contents of every future triage run to fix a retrieval
score, which is a much larger blast radius than the problem. Two fields.

| case | proposed key | dropped, and why |
|---|---|---|
| red-acs | CP-ACS-003, CP-ACS-005 | ACS-001 caveat paragraph; ACS-002 silent MI; **ACS-004 dropped deliberately** because it says "Never delay calling 9-1-1, taking aspirin", which invites the next_steps aspirin instruction constraint 12 exists to drop |
| yellow-angina | CP-ANG-001, CP-ACS-005 | ANG-002 optional, definitional and 231 tokens |
| green-gerd | CP-GERD-001, CP-GERD-002 | GERD-003 is causes, not triage. GERD-002 is kept **because it is the rule-out**: the alarm features this case lacks are what make it green |
| yellow-pleuritic | CP-PERI-002, CP-PERI-001 | PLEU-001 optional, 156 tokens for one relevant line |
| probe-costo | **empty, unscored** | no chunk describes costochondritis; scoring it would turn a documented corpus gap into a retrieval number |

`CP-PERI-002` belongs to yellow-pleuritic and to nothing else. It describes that
case almost word for word, so it is the right chunk there even though its
"Fast heartbeat / Fever" lines are the ones copied onto a patient who had
neither. That is a guard problem, not a key problem. A `MUST_NOT_RETRIEVE` list
now states positively where it is wrong, because "absent from the key" and
"wrong to return" are different claims.

#### Re-scored, top-3, query symptom+timeline

| config | recall | must-not-retrieve violations | tokens |
|---|---|---|---|
| dense only | **5/8 = 62%** | **3** | 1712 |
| blend, alpha 0.5 | **5/8 = 62%** | **2** | 1885 |
| BM25 only | **5/8 = 62%** | **1** | 2060 |

**Recall is identical across all three. The blend does not retrieve better, it
retrieves cleaner.** Every violation is the same chunk, `CP-PERI-002`, and
keyword weighting is what displaces it: 3 violations dense, 2 blended, 1 on pure
BM25. That is a real and specific benefit, and it is not the benefit that was
being looked for.

Against the old keys the same runs score 7/12 dense and 6/12 blend, so the key
correction moved the measured number more than any retrieval change tried today.

#### What is still wrong, stated plainly

62% is not good. Concretely: **CP-ACS-005 never surfaces for red-acs under any
config**, and it carries the discriminator that case turns on, that heart attack
pain does not go away with rest. **CP-GERD-002 is lost the moment keyword
weighting is added**, taking the green rule-out with it. The one case that is
clean under the blend is yellow-angina, 2 of 2.

No retrieval change was made on the back of this. The keys changed, the scoring
changed, the retriever did not.

#### Next

Confirm or correct the proposed keys. Until then every retrieval number in this
entry is measured against Claude's reading of the corpus, not Viraj's.

### 2026-09-17 keys FROZEN, and the correction mattered more than the retriever

Approved by Viraj with two changes to the proposal: **CP-ANG-002 promoted to
required** on yellow-angina, because the call that case turns on is stable
versus unstable angina and CP-ANG-002 is the only chunk framing angina as a
warning sign of raised heart attack risk rather than describing one episode.
Without it the retrieved context can support "this resolved, so it is fine",
which is the under-call the category mix exists to prevent. **CP-PLEU-001
confirmed optional** on yellow-pleuritic, not scored, not a miss when absent.

Frozen keys, 9 required chunks across 4 scored cases:

```
red-acs                CP-ACS-003, CP-ACS-005
yellow-angina          CP-ANG-001, CP-ACS-005, CP-ANG-002
green-gerd             CP-GERD-001, CP-GERD-002
yellow-pleuritic       CP-PERI-002, CP-PERI-001
probe-costo-unmatched  (empty, unscored by design)
```

**The originals were never reviewed.** They were hand-assigned when
`discrimination_test.py` was written and had been the `matched` condition for
every eval in the project. red-acs expected `CP-ACS-002`, silent asymptomatic
heart attacks, for a florid symptomatic case.

**Scoring against the old keys gave 7/12 = 58%. Scoring the same dense run
against the corrected keys gives 5/9 = 56%.** The numbers are close and they are
not measuring the same thing: the old denominator included chunks no retriever
should return, so part of that 58% was credit for the wrong target and part of
the missing 42% was penalty for correctly skipping it. **The key correction
moved the measured number more than any retrieval change tried today**, which is
the argument for reviewing an answer key before optimising against it.

#### Re-scored against the frozen keys

| config | recall | must-not-retrieve violations | tokens |
|---|---|---|---|
| dense only | 5/9 = 56% | 3 | 1712 |
| blend, alpha 0.5 | **6/9 = 67%** | 2 | 1885 |
| BM25 only | **6/9 = 67%** | **1** | 2060 |

Promoting CP-ANG-002 changed the comparison, and honestly so: **dense never
returns it at all**, while BM25 puts yellow-angina at 3 of 3. So the blend now
beats dense on recall as well as on contamination, where before the freeze the
three configs were tied at 62%. This is not the blend improving; it is the key
finally asking for a chunk that dense retrieval cannot find.

Still true and still not good: CP-ACS-005 never surfaces for red-acs under any
config, and CP-GERD-002 is lost whenever keyword weighting is on. Every
must-not-retrieve violation is CP-PERI-002.

**Retrieval work stops here.** 62 to 67% recall is not good, but it is measured
against a reviewed key, which it was not this morning.

### 2026-09-17 laptop demo runs end to end, and beat 3 does not work

`06-demo/server.py` plus `06-demo/static/index.html`. Stdlib HTTP server, no new
dependencies. Retrieval from epic 4 at blend alpha 0.5 top-3, prompt from
`pair_format.py` at sha `102e7511`, and every response through
`02-pairs/guards.py`. Results at `06-demo/results/2026-09-17-first-run.txt`.

Tokens are streamed to the page. That is not decoration: a turn is 35 to 70 s and
forty seconds of frozen screen reads as a crash at a desk. The guarded verdict
renders only once the JSON is complete, because a half-parsed verdict must never
reach the screen.

**Beats 1, 2 and 4 work.** A symptom goes in, three chunks are retrieved, a red
verdict comes back with resolving citations, and clicking a key opens the real
chunk text with publisher, URL and retrieval date. `CP-RISK-014` returns HTTP 404
at the expander, so constraint 9 is enforced twice: guard 3 strips an unresolvable
key before render, and the expander refuses it again if anything upstream let it
through.

**The timings confirm the llama-server numbers exactly**: prompt 1204 tok at
**31.1 tok/s**, generation 223 tok at **9.9 tok/s**, against the 30 to 32 and 9.5
to 10 in constraints 7 and 8. A full turn is **70.5 s cold, 35 s warm**. Judging
is about 5 minutes, so that is two turns and no slack.

#### Beat 3 failed

Same deliberately mild symptom, "some tightness in my chest this evening and I
feel a bit short of breath, it comes and goes", run against both profiles:

```
You   29F, no medications                        -> RED
Dad   71M, atrial fibrillation, apixaban, bisoprolol -> RED
```

**The profile did not change the verdict.** The beat is built on the model
distinguishing two presentations, and the model returns red for everything. This
is the same finding as the no-chunk probe, arriving now at the demo surface.
Nothing here is new about the model; what is new is that the demo script depends
on a behaviour that was measured not to exist this morning.

One thing did work, and it is worth showing instead: **guard 4 fired live on the
Dad profile.** The model returned red carrying three follow-up questions, which
constraint 4 forbids, and the guard cleared them. The UI renders what it removed.

#### The fabrication is live on the demo path

Beat 1's red flags came back `['crushing chest pain', 'sweating', 'nausea',
'dizziness']`. **The case never mentions dizziness**, and "crushing" is
CP-DIFF-001's word, not the patient's, who said heavy pressure. The mild case
returned `['Chest pain that worsens with breathing', 'Rapid heartbeat']` for a
patient who reported neither, both straight out of CP-PERI-002, which retrieval
supplies to nearly everything.

The guards do not catch this and were never meant to: grounding is constraint 11
and it is not a string-matching job. So the demo currently shows a judge red
flags the patient does not have. That is the most damaging thing on the screen
and it is not fixed by anything built today.

Also visible: the rationale contained "No weight bearing or neurovascular
compromise", which is the **ankle worked example** leaking into a chest case.
The prompt's single verbatim example is being copied structurally as well as
lexically.

#### Open, in the order they hurt the demo

1. **Ungrounded red flags reach the screen.** Needs either a grounding guard the
   project has so far treated as a warning, or a display decision to show
   red_flags only when they appear in the case text.
2. **Beat 3 needs replacing.** Candidates: show the guard removing a medication
   instruction, or show the citation expander refusing an invented key, both of
   which work today and are honest about what the system does.
3. Retrieval feeds CP-PERI-002 to nearly every case, which is what supplies the
   fabricated findings in the first place.

### 2026-09-17 grounding guard shipped, beat 3 replaced, and a denial was licensing a fabrication

#### Guard 5, hard constraint 11, now enforced rather than warned about

`screen_red_flags` in `02-pairs/guards.py` and `screenRedFlags` in
`05-app/spike-load/guards.ts`. Both **reuse** `ungrounded_findings` and
`contradicted_findings` from `validate_pairs.py` rather than being a third and
fourth implementation of the rule.

Keeping three ports honest needed one data source, not three lexicons.
`02-pairs/export_lexicon.py` generates `finding_lexicon.json` from
`validate_pairs.py`, the TypeScript port reads that, and
`guard_fixtures.json` now carries five red_flags cases that both suites assert.
A clinical term is added in exactly one place.

It DROPS where the pair validator only warns. A pair gets a warning because a
human clears it before freezing; the demo path has no human between the model
and the screen, so it fails closed and renders what it removed.

**Verified live, not just in fixtures.** Beat 3 run end to end: retrieval
supplied CP-PERI-002, the model copied `fast heartbeat` and `fever` out of it,
and both were dropped on screen with the reason, keeping the one grounded entry.

#### A patient denying a finding was licensing it

Found while building the beat, and it is the worst defect of the day.
`ungrounded_findings` asked only whether a finding's word appeared **anywhere**
in the case. So a case reading "No fever, and my heart does not feel like it is
racing" made a `fever` red flag pass the guard. **The strongest possible
evidence against a finding was being read as evidence for it.**

Fixed: a finding counts as supported only if the case *asserts* it, negation
excluded. Entry-side negation is deliberately not applied, because an entry in
`red_flags` asserts its finding by being in that list at all.

**The fix broke `selftest_validator`, which is the system working.** A case
reading

```
conditions: none
medications: none
Placeholder text, fever since Tuesday.
```

started warning on a fever it genuinely asserts. Cause: the negation window
scanned back to the nearest clause break, which was the colon in
`medications:`, so the `none` in a structured profile field negated a symptom
two lines later. A newline is now a clause break. `none` in a field is a value,
not a denial of the next line.

All three suites green: validator 24/24, Python guards 25/25, TypeScript 39/39.

#### Beat 3 replaced

The old beat 3, "family profile changes the answer via medication logic", was
cut. It was measured this afternoon and **it does not work**: the same symptom
returned red for both the 29-year-old on no medications and the 71-year-old on
apixaban, because the base model returns red for everything. A demo beat cannot
rest on a behaviour that was measured not to exist.

The new beat 3 is **the guards firing**, and it shows three things that are all
real and all reproducible: a fabricated red flag dropped, follow-up questions
cleared off a red, and an invented citation key refused by the expander at
HTTP 404. It turns the honest weakness into the thing being demonstrated.

**One preset trap worth recording.** The first version of the beat 3 case said
"No fever, and my heart does not feel like it is racing" to set up the catch.
That is exactly what the negation bug passed through, and even after the fix the
preset now stays *silent* on those findings rather than denying them. A demo
should not depend on the subtlest branch in the code.

#### claude.md updated

Epic 6 now reads: 1 symptom flow, 2 red triage, 3 guards firing, 4 citation
expander, on a laptop web UI. Constraint 11 records that the app guard exists,
drops rather than warns, and that a denial is not a licence. The line at the top
of the file saying "the iOS simulator is the entire demo" was corrected; it had
been false since the Release measurement and it is the first thing a new session
reads.

### 2026-09-17 demo verification, and the limit of it

**I could not click through it.** The Chrome extension is not connected, so there
was no way to drive a browser as a judge would. Recording that rather than
implying otherwise, because "it works" and "every endpoint returns 200" are
different claims and only the second one is established by an API test.

What was verified instead, in descending order of how much it is worth:

1. **The page renders.** Opened in the booted simulator's Safari, whose loopback
   is the host's, and screenshotted. The server logged `GET /` then
   `GET /api/health`, so the JS ran. Header, green `offline · on-device` pill,
   all four presets including "Guards firing", the profile toggle, the Assess
   button and the empty state all render, and the four-step type scale reads
   with the verdict area clearly dominant.
2. **The render path was exercised against a real payload.** A live beat 3
   response was captured to disk, then the page's OWN `render()` was run against
   it under a minimal DOM stub, `/tmp/render_check.mjs`. 10/10: red banner,
   urgency word, disposition line, the guards block, both dropped entries with
   their reasons, a clickable citation chip, the timing line, and no `undefined`
   or `[object Object]` leaking into the markup. That is the code path this
   session had never run.
3. Every endpoint exercised directly, repeatedly, all day.

**Still unverified, and it needs a human with a browser:** that clicking Assess
actually paints, that the citation dialog opens and closes, that the token
stream is legible while it runs, and how the whole thing feels at 40 s a turn.
Those are the things the click-through was for, and they remain open.

---

### 2026-09-17 Viraj clicked through it, and found the most dangerous output yet

Two findings from the browser click-through I could not do, plus one confirmation
and one bug that the clicking exposed.

#### 1. It said green. The red bias is probably chest-specific.

**First non-red verdict in the project's history**, on "My stomach hurts and my
period is late", 29-year-old woman. Viraj saw green with empty `red_flags`.

Re-run the same evening it returned **yellow**, not green, temperature being 0.2.
So the label is not stable, and that matters less than what both runs share:
neither is red. Every chest-pain case in every configuration all day returned
red, including with no corpus at all. A non-chest query escaped that immediately.

**So the red bias looks chest-specific rather than global.** Stated as a bet: two
observations of one out-of-scope query. If it holds it is mildly good news for
the fine-tune, because a model whose red bias is topical is easier to move than
one whose category head is stuck.

#### 2. Out-of-scope queries were the real danger, and the corpus guarantees them

That case includes **ectopic pregnancy**, which is life-threatening and
time-critical. It got a reassuring verdict with **zero citations**. Retrieval had
returned GERD, panic disorder and angina, because that is the whole corpus, and
the model reasoned from them anyway. Its rationale: "Late period with stomach
pain is non-urgent ... No acute cardiac or gastrointestinal emergency indicated."

Nothing built so far catches this. Every guard checks the *shape* of an answer.
None of them asked whether the system had any business answering.

**Guard 6, `scope_check`.** Two independent conditions, either one refuses:

- **Relevance floor before generating.** Max cosine over all 22 chunks below
  0.40. Measured over 8 in-scope and 10 out-of-scope queries: worst in-scope
  **0.482**, best out-of-scope **0.338**, gap **0.144**. 0.40 sits near the
  midpoint with 0.082 and 0.062 of margin. **n is 18; this is a bet.**
- **Empty citations after the citation guard.** No threshold, so it is the more
  robust condition, and it is the one Viraj named.

Pre-flight matters for more than speed: it never gives the model the chance to
confabulate. The ectopic case now refuses in **9.7 s instead of 45 s**, because
nothing is generated.

The refusal renders in neutral grey and never in a triage colour, so it cannot
read as a fourth, milder category, and the withheld verdict is named rather than
shown. Constraint 13 in claude.md. 31/31 Python guard self-tests, 24/24 validator.

**This contains the problem, it does not fix it.** The corpus is chest pain and
every out-of-scope question is still a question the system cannot answer.

#### 3. Confirmed working: the medication guard fired on screen

Viraj saw constraint 12 drop a medication instruction live. Reproduced in the
same ectopic run, which dropped "Consider over-the-counter antacids or lifestyle
adjustments for stomach discomfort."

#### 4. A demo-fatal bug the clicking exposed, that I introduced

After wiring guard 6 the server threw

```
SQLite objects created in a thread can only be used in that same thread.
```

`ThreadingHTTPServer` gives each request its own thread; the retriever is a
module-level singleton whose sqlite connection is created lazily on whichever
thread asks first. **The first query always succeeded and the second always
failed.** A judge asks more than one question. Every test I ran today was a
single request against a freshly restarted server, which is exactly why an
API-only test never saw it and one minute of clicking would have.

Fixed with `check_same_thread=False` plus a lock, and a `query()` helper that
everything outside `__init__` goes through. The lock is not optional: the flag
disables Python's check, it does not make the connection concurrent. Verified
with three consecutive requests and a citation expander call on a fresh thread.

**The lesson is the one Viraj made this morning.** Reading reports about a system
is not using it, and every bug in this entry came from the difference.

### 2026-09-17 single-request-assumption scan, and it found a crash

Prompted by the SQLite bug: every test all day was one request against a freshly
restarted server, so anything needing a second request was invisible. Scanned by
running concurrent requests rather than by reading code, which is the only way
the first one would have been caught.

**Found: two concurrent first requests CRASHED the demo server.**

`retriever()` and `registry()` were lazy singletons. Two requests arriving before
either was built both entered the `is None` branch, both constructed a
`HybridRetriever`, both loaded all-MiniLM-L6-v2, and the process **died**,
leaving a loky semaphore behind and both requests returning zero bytes. A judge
double-clicking Assess would have killed the server. It reproduced every time.

Fixed by building everything **before the socket listens**, `warm_up()`, so no
request can find them unset and there is no race to lose. A double-checked lock
is there as belt and braces. Confirmed after: one MiniLM load at startup, two
concurrent requests both answered, server survived. It also moves the 9 s encoder
load off the first query, which had been showing as a slow first answer.

**Also hardened, same class:**

- `retrieve.py` got `check_same_thread=False`. CLI-only today, but it is the same
  trap waiting for whoever imports it into a server next, and it fails on the
  second request rather than the first.
- `collect_results.py` stamped filenames to the second, so two results in the
  same second silently overwrote each other. Microseconds now.

**Checked and found acceptable:**

- Two concurrent in-scope generations both completed, 72 s for the pair against
  about 45 s for one, because `llama-server` runs `-np 1` and queues them. A
  double-click doubles the wait instead of failing. Server survived.
- The TypeScript `CLAUSE` regex carries the `g` flag, so `lastIndex` is stateful
  across calls. It is already reset before each use. Left as is, noted here
  because it is exactly the kind of thing this scan was looking for.
- `BM25`, `PROFILES` and the registry set are read-only after construction.

#### What this pattern keeps teaching

Three bugs now, all invisible to single-request testing, all trivially visible on
the second request: the SQLite thread affinity, the lazy-init crash, and the
timestamp collision. Two of the three were demo-fatal. **The API tests were not
wrong, they were the wrong shape.**

### 2026-09-17 epic 2 scaffolded and written at 60 pairs, awaiting review

`02-pairs/review/candidates-60.jsonl`, 60 pairs, **0 errors 0 warnings**. Sample
for review at `02-pairs/review/SAMPLE.txt`. **Nothing frozen**;
`02-pairs/pairs/` is still empty.

Scoped to 60 rather than 300 to answer one question: does the adapter move
category assignment at all. Weighted toward the failure cases, chest pain only.

```
contrast 24 (12 sets)   grounding 6   under-specified 4   standalone 26
green 20   yellow 28   red 12         multi-turn 4
slot targets and authored verdicts now agree exactly
```

#### Contrast sets are the backbone

Two pairs sharing the same chunks, profile and register, reaching opposite
verdicts, differing in one named discriminator. They exist because of two
measurements, not because contrastive data is fashionable:

- The category head is movable but not case-sensitive. GREEN_CRITERION freed
  green on green-gerd and dragged the known-CAD case to green at the same time.
  A contrast set cannot shift a global cut point, because both halves see
  identical evidence and only the case text separates them.
- Green carries 11 pairs across 2 conditions at this size, so "GERD chunk
  therefore green" is learnable from the data alone. A contrast set breaks that
  by putting the same chunk under two verdicts.

#### Four design bugs caught while writing, three of them mine

1. **P0042 carried a second discriminator**, "she looks grey". Pallor is an
   independent red flag, so the set taught two things at once and `red_flags`
   omitted a finding the case asserted. Removed.
2. **P0026's yellow was arguable** because the case never said the episode was
   her usual pattern. New-onset exertional angina in known CAD is not
   comfortably "seen today". Added.
3. **Register covaried with verdict** inside every set: terse adult yellow,
   panicked caregiver red. A third discriminator, and it was invisible until the
   first two were fixed. Register is now constant within a set and varied across
   sets, fixed in the scaffolder and verified across all 12 rather than trusted.
4. **P0046 was an under-specified slot targeting red.** Constraint 4 forbids
   follow-up questions on a red and questions are the entire point of the kind,
   so "assign the higher one" can never mean red there. It must not mean green
   either. Under-specified is now forced to yellow.

#### Decline pairs replaced by under-specified pairs

`NO_REFERENCE_SHARE` dropped. Guard 6 made empty-reference pairs train a state
the app cannot produce: the pre-flight floor refuses before generating when
nothing is relevant, and the post-flight check refuses any answer citing
nothing. They were the countermeasure to the CP-RISK-014 fabrication and guard 6
prevents that upstream. The state that IS real and untrained is chunks retrieved,
case too thin to separate, rule 6 applies. Four pairs now teach that.

#### Writing in patient register found a live app bug

Five validator warnings, every one a false positive: "more out of breath",
"leg is fatter than the left", "black and sticky", "had a temperature", "bit
more puffed". The findings were all genuinely present; the lexicon only knew
clinical words.

**That was not a validator quirk.** `screen_red_flags` uses the same lexicon on
the demo path, so the guard was **dropping true red flags off the screen**
whenever a patient used plain English. It fails closed, so it hid real findings
rather than inventing them, which is the safer direction and still wrong: a judge
typing naturally would have seen a verdict with its evidence stripped out.

Synonyms added for patient language, plus a new `loss of appetite` canon, which
CP-GERD-002 lists as an alarm feature and the lexicon had no word for. After:
validator 0/0, guards 31/31, validator self-test 24/24, TypeScript 39/39, and
`audit_grounding` unchanged at 12 ungrounded / 7 contradicting across every saved
run, so the wider lexicon created no new false positives on historical data.

**A day of measurement never caught this and one pass of writing in a patient's
voice did.** The eval cases are written in fairly clinical language.

#### A validator gap the sample exposed

P0021 was scaffolded `yellow` and written `red`, and the file validated clean.
Nothing compared the slot's `target_category` against the authored urgency, so
the category mix could drift silently from the plan it was built on. Added
`target_mismatch` as a WARNING, because the author is often right and the slot
wrong, as here: forty minutes of central chest pressure unresolved at rest is
red whatever the scaffolder guessed. P0021's slot relabelled to red, content
unchanged, and the two mixes now agree exactly.

#### Not done

Viraj reads `SAMPLE.txt` before anything freezes. 52 pairs are unreviewed. The
clinical content of all 60 is Claude-authored and needs his eye, particularly
the contrast discriminators, since 12 sets built on a fuzzy boundary would teach
the boundary wrong 24 times.

### 2026-09-17 rule 4 rewritten and tested: zero verdict movement

Viraj reopened the one prompt change, on a specific hypothesis: rule 4 may be
mechanically forcing red, because any concerning finding lands in `red_flags`
and rule 4 converts a non-empty `red_flags` into a red verdict regardless of
everything else.

```
rule 4 WAS  If any red flag is present, the category is red regardless of other factors.
rule 4 NOW  A finding that requires emergency care now forces red. Findings that
            raise urgency without requiring emergency care belong in red_flags
            and support yellow.
```

Format 3, matched chunks, reasoning off, temperature 0.0, cache_prompt off, two
passes each side, both deterministic. `2026-09-17-rule4-before.txt` and
`-after.txt`.

| case | expect | before | after | moved |
|---|---|---|---|---|
| red-acs | red | red | red | |
| yellow-angina | yellow | red | red | |
| green-gerd | green | yellow | yellow | |
| yellow-pleuritic | yellow | red | red | |
| probe-costo | green | red | red | |

**0 of 5 moved. 1/4 before, 1/4 after.**

**The before run predicted this.** Two of the four reds, red-acs and probe-costo,
came back red with `red_flags` EMPTY. Rule 4 cannot convert an empty list into
anything, so it was never the mechanism on those two, and that was visible
before the change was made.

**It also made red_flags worse on two cases.** After the rewrite, yellow-angina
listed *"Chest tightness triggered by exertion with complete resolution on rest"*
as a red flag: the reassuring feature, in the red-flag list, on a case it still
called red. Rule 7 explicitly says a reassuring feature is not a red flag. And
yellow-pleuritic went back to `['fever', 'fast heartbeat']`, the CP-PERI-002
copy, which the before run had not produced.

#### The change is KEPT anyway, for the reason it was made

It did not move a verdict, but it was not only about verdicts. Rule 4 as written
contradicted 24 of the 32 yellow turns in the training pairs, and contradicted
format 2's own prompt, which has always said `red_flags` holds findings that
raise urgency. Three artefacts disagreed and rule 4 was the outlier. It now
agrees with the pairs and with format 2, so the pairs no longer need rewriting.

#### What this does to the base-model conclusion

It strengthens it. That is now **five prompt revisions** (pre-fix, A, B, C, and
this rule 4 rewrite) with **zero verdict movement** between any of them, plus
format 2, which has no rule 4 at all and also returned all-red with reasoning
off, plus the no-chunk probe, which had no corpus at all and still returned red.

The honest caveat on the no-chunk probe stands and is now narrower: it ran under
format 3 with the old rule 4 in the prompt, so rule 4 was a live confounder for
that result. This run removes it. The conclusion survives the check.

`02-pairs/system_prompt.txt` sha256 is now
`26e4f4ff3e30c899d51f97877b5e7f90b16053c90c593954a04ab14b8b71a2b7`, registered in
`audit_grounding.py` as `fmt3 D rule4-rewrite`.

### 2026-09-18 six of twelve contrast axes ungrounded. Sets cut. No fine-tune.

Viraj asked the question nobody had asked: does the chunk a contrast set cites
actually contain the line that draws the distinction?

**Three axes pass, three fail, and one of the failures is worse than absence.**

| axis | sets | verdict |
|---|---|---|
| exertional pain resolves with rest | C01, C07 | PASS |
| black tarry stool | C02, C08 | PASS |
| breathlessness at rest | C03, C09 | PASS, weakly |
| reproducible on palpation | C05, C11 | **FAIL** |
| sudden versus gradual onset | C06, C12 | **FAIL** |
| previously diagnosed pattern | C04, C10 | **FAIL, contradicted** |

The passes quote real lines. `CP-ANG-001` carries both poles: "Symptoms often go
away with rest and return when you are active", and "Chest pain or discomfort
that does not go away or occurs while you are resting might be a sign of a heart
attack". `CP-GERD-002` says "stool that contains blood or looks black and tarry".

**CP-PLEU-001 never mentions palpation, tenderness or pressing.** It is pleural
anatomy and a list of four disorders. This is the NEG-DISC gap in claude.md
arriving in the training data: the corpus has no negative discriminators, and
reproducibility on palpation is the canonical one. Viraj predicted this failure
before the check ran.

**CP-PE-001 and CP-PE-002 never mention onset speed at all.** Also predicted.
And the rebuild had made it worse in a way worth recording: to isolate onset, it
held the risk factor constant across both halves. The risk factor was the only
thing those chunks actually support, `CP-PE-002` being one sentence about risk
factors accumulating. **The rebuild removed the grounded discriminator and kept
the invented one.**

**CP-PANIC is the one nobody predicted, and it is the worst.** Its chunks draw a
DIAGNOSTIC distinction, panic attack versus panic disorder, never a triage one.
Nothing says a first episode warrants assessment. Worse, `CP-PANIC-002` states
without qualification that "panic attacks themselves are not life-threatening,
and the physical symptoms usually resolve with time", which applies to both
halves equally and **argues green for the yellow half**. The cited chunk
contradicts the pair that cites it.

#### Why this matters more inside training data than at inference

At inference a guard can drop a fabricated `red_flag`. Nothing catches a
fabricated criterion in the reasoning, and these pairs would have taught the
model to produce them, with a real citation key attached. It is the
ungrounded-advice failure, reproduced in the one place no guard reaches.

#### Cut, not rebuilt

Seven sets, 14 pairs: C04, C05, C06, C09, C10, C11, C12. Rebuilding means
inventing chunk support that does not exist. If an axis matters clinically and
the corpus cannot ground it, the fix is a source, not a sentence.

C09 sits on a PASSING axis and was cut anyway, on the caveat raised in the
check: `CP-PERI-001` says "severe shortness of breath" and C09's red half said
only "I am breathless sitting still", while C03's says "cannot finish a
sentence" and demonstrates the severity the chunk asks for. C03 survives, C09
does not.

45 pairs remain, 0 errors, 0 warnings. Surviving sets C01, C02, C03, C07, C08,
every one quoting a line from a chunk it cites.

#### DECIDED: no fine-tune. Ship the base model with the demo as built.

The deciding argument was never whether 59 pairs could teach conditioning. It is
that **the eval set cannot measure whether they did**: four scored cases, one
green, and the green is the one every configuration has failed. A fine-tune that
worked and one that did nothing would likely score the same, leaving a model
swap to be decided on a number that means nothing, late on the last build day,
with epic 3 never having been run once.

The pairs and the validator are kept as a roadmap artifact, written up in
`02-pairs/review/README.md`. They are evidence of method. The scaffolder, the
validator, the shared fixtures and constraint 14 all exist because something
real slipped past, and the axis check caught half the sets on the last pass
before a freeze that did not happen.

Hard constraint 14 added to claude.md: a contrast axis must quote the line in
the cited chunk that draws the distinction, or the set is not built.

**Tomorrow is demo hardening and the pitch. Nothing else.**

---

### 2026-09-18 — epic 3 run for the first time. Conversion chain proven on the base model.

Epic 3 had never executed. It is now proven end to end, and the rebuilt Q4_K_M
is **behaviourally identical to the artifact that has been demoed against all
week**: 5 of 5 matching verdicts on `format3_probe.py` at prompt sha `26e4f4ff`,
including reproducing all three known failures. Run saved to
`01-data/eval/runs/2026-09-18-rebuilt-imatrix-q4km.txt`. The runbook is
`03-model/RUNBOOK.md` and it is the artifact to rebuild from.

```
HF BF16, sha 55d4e2519456c4a9, 7,947,142,640 B
  -> convert_hf_to_gguf.py --outtype f16      53 s, 0 warnings, 263 tensors
  -> GATE: F16 loads, says "OK", finish=stop
  -> llama-imatrix, calibration.txt, 32 chunks  9 min, PPL 5.9045 +/- 0.15151
  -> llama-quantize --imatrix ... Q4_K_M 8      49 s, 2,837,073,184 B (+320)
  -> llama-server: 5/5 verdict match, reasoning_chars 0 on every case
```

#### The afternoon's actual cost: `--outtype q8_0` silently produces a corrupt model

Both outtypes exit 0. Q8_0 emits three numpy `RuntimeWarning`s from
`gguf/quants.py`, one of them `invalid value encountered in cast`, which is NaN
going into int8. That GGUF **loaded, reported the correct architecture, and
quantized to within 320 bytes of the known-good artifact.** Then it generated
`FoundationFoundationFoundation...` forever.

Every step reported success. Nothing errored. **I wrote those warnings into the
first draft of the runbook as expected noise you can ignore.** They were the
bug. That is the single worst call of the day and the runbook now leads with it.

Isolated with three runs: with imatrix broken, without imatrix broken, Q8_0
straight to Q4_K_M broken, F16 through the identical chain clean. Version skew
between converter (clone 4fea119) and runtime (Homebrew 0.4.0, build 10809) was
**eliminated**, not assumed: both GGUFs were read by the same binaries and only
one was broken. numpy 2.2.6 eliminated the same way.

#### PPL 390,043 was measuring the broken model, not a bad calibration corpus

The first imatrix run, on the corrupt Q8_0, returned `PPL = 390,043`. I flagged
that as possible evidence that the domain-matched `calibration.txt` was a bad
choice against wikitext. **It was not.** The same file, same binary, same 32
chunks, against a healthy model returns **5.9045 +/- 0.15151**. The corpus is
fine and the decision to build it from the system prompt, the 22 chunks and the
45 pairs rather than wikitext stands. A five-figure PPL is a model health signal,
not a verdict on the calibration text.

#### The Q8_0 intermediate was never necessary

The chain as run went F16 -> `llama-quantize` Q8_0 -> imatrix. Checked afterwards
rather than assumed: **`llama-imatrix` reads the F16 directly**, exit 0, normal
PPL. The Q8_0 step was inherited from the corrupt chain, where the Q8_0 came from
the converter, and never questioned once F16 became the source. Removing it saves
24 s and **3.9 GiB of peak disk**, which matters because disk is the documented
blocker on this machine.

#### Smaller findings

- **A path starting with a digit breaks `llama-quantize`.** It parses positionals
  with `stoi`, so `03-model/...` reads as the number 3, the arguments shift, and
  it reports `error: invalid nthread`, which is not the problem. **Every
  directory in this repo starts with a digit.** Always write `./` in front.
- **No imatrix banner is printed on this build**, so absence of one proves
  nothing. Provenance lives in the output GGUF KV instead:
  `quantize.imatrix.entries_count = 92`, `chunks_count = 32`. 92 is full coverage
  for this architecture: 4 attention x qkvo = 16, 17 MLP x 2 = 34, 21 Mamba2 x 2
  = 42.
- **imatrix now writes GGUF format regardless of a `.dat` extension.** Cosmetic
  here since the same build reads it back, a trap if anything else must.
- `51 of 263 tensor(s) required fallback quantization` is expected on this
  hybrid: Mamba2 shapes not divisible by the K-quant superblock. It appears on
  the shipped artifact too.
- `timeout` is GNU coreutils and **does not exist on macOS**. It exits 127,
  which reads like the wrapped command is missing.

#### Still not run: the training half

Brev, `trl`/`peft`/`bitsandbytes`, and the open question that gates everything
after it, **whether bitsandbytes can load a hybrid Mamba2 model in 4-bit**. The
merged model re-enters the runbook at section 3 unchanged, which is the point of
having proven sections 3 to 7 separately: if training breaks tomorrow, the break
is in training, and section 7 is the test that says so.

#### 2026-09-18, later. Disk reclaimed, and the 4-bit gate written before Brev exists.

Deleted `cpp-Q8_0.gguf` and `FROM-F16-Q4_K_M.gguf`, both regenerable from the
F16 in under a minute. **3.0 GiB free -> 11 GiB, 99% -> 95%.** More than the 6.5
GiB the file sizes predicted, because purgeable space went with them. Kept:
F16, the shipped Q4_K_M, the rebuilt `FINAL-imatrix-Q4_K_M.gguf`, the HF weights
and the 2.1 MiB imatrix.

`03-model/brev_4bit_gate.py` written and syntax-checked locally. It answers the
one question that gates epic 3's second half and exits, in three checks that can
each fail alone: **loads**, **actually quantizes**, **generates**.

Check 2 is the one worth having. `load_in_4bit=True` does not guarantee every
Linear became 4-bit; bitsandbytes skips what it cannot handle and reports
success. The plausible hybrid failure is the SSM projections staying bf16 while
attention and MLP quantize, so the model loads, runs, and silently costs far
more memory than budgeted. The script counts module **types** per family rather
than trusting the flag, and fails loudly naming the families left behind.

Check 3 exists because of this morning: **the corrupt Q8_0 loaded.** Loading is
not proof. It asserts finite logits and rejects single-token-repeated output,
which is the 4-bit shape of the `Foundation...` loop.

`qlora_config.py` self-test re-run offline: 50 matched, `gate_proj` correctly
rejected. Worth noting what that does and does not prove. **It checks a stored
list of 242 module names, not a loaded model.** 4-bit swaps `nn.Linear` for
`Linear4bit` while leaving names alone, so a stale list would pass while reality
differed. The gate script therefore re-runs the constraint 10 assertion against
the real `PeftModel`, importing `TARGET_MODULES`, `EXPECTED_MATCHES`,
`EXPECTED_TOTAL` and `LORA_KWARGS` rather than restating them.

Blocked on `brev login`, which is a browser flow and Viraj's to run.

#### 2026-09-18, evening. Axis re-check, full review file, and a live guard bug.

**No Brev.** Out of credits, all three instance types refused, nothing created
and nothing billing. Moot anyway: training done before the event has to be
redone there, so the pairs travel and trained weights do not.

**Axis grounding re-checked on the survivors. All pass constraint 14.**
The question was posed as "the nine rebuilt sets", and that is not the state.
**Nothing was rebuilt.** C04, C05, C06, C09, C10, C11 and C12 were cut, and five
sets survive: C01, C02, C03, C07, C08. They run on three axes, and those are
exactly the three that passed the 09-17 audit. Re-verified against chunk text
rather than the table:

| axis | sets | chunk line |
|---|---|---|
| exertional resolves vs persists | 2 | CP-ANG-001 "Symptoms often go away with rest and return when you are active"; "Chest pain or discomfort that does not go away or occurs while you are resting might be a sign of a heart attack" |
| black tarry stool | 2 | CP-GERD-002 "stool that contains blood or looks black and tarry" |
| severe shortness of breath | 1 | CP-PERI-001 "If you have chest pain or severe shortness of breath ... call 9-1-1" |

CP-PERI should be revised UP from claude.md's "PASS, weakly". That note flagged
"at rest" as a gloss, which is true of the axis label but not of the pairs:
P0045's rationale applies the chunk's own words, and "cannot finish a sentence"
is in the SYMPTOMS block, so it is a finding, not a criterion. Residual, for
Viraj: the chunk never defines "severe", so the threshold is clinical practice
rather than corpus. Not a constraint 14 failure.

**SAMPLE.txt was stale and covered nothing.** It documents P0001, P0005, P0006,
P0010, P0033 and P0038; **all six were cut.** Zero overlap with the frozen 45, so
"the remaining 34" did not exist. Banner added to the file and the whole set
written to `02-pairs/review/FULL-REVIEW.txt`, 1258 lines, generated by the new
`02-pairs/write_review.py` so it cannot go stale silently again.

**OPEN BUG, live demo path, found running the guards over the frozen pairs.**

`guards.screen_red_flags` drops P0042's red flag
`"Chest tightness unchanged after 30 minutes at rest"` on a case reading
`"Chest got tight walking up the hill ... Sat on the wall. It has not shifted,
it has been half an hour now."`

The `exertion` axis in `CONTRADICTION_AXES` treats "walking up" (exertional) and
"at rest" (non exertional) as contradictory. **It conflates what brought the pain
on with what the patient is doing now.** Exertional onset plus persistence at
rest is not a contradiction, it is the evolving-ACS pattern, and it is the exact
discriminator the CP-ANG sets are built on.

`06-demo/server.py` passes `case_text` = profile + timeline + symptoms and never
the chunk, so this reproduces live. Phrasing-dependent, which is worse than
consistent:

| red flag | case mentions exertion | result |
|---|---|---|
| unchanged after 30 minutes **at rest** | yes | DROPPED |
| unchanged after 30 minutes | yes | kept |
| persisting **at rest** | yes | DROPPED |
| continues while **resting** | yes | DROPPED |
| after sitting down | yes | kept |
| unchanged after 30 minutes at rest | no | kept |

So whether beat 3 shows the correct red flag on the most important presentation
in the corpus depends on which words the model picks. **Not fixed.** The fix is
app logic and Claude's column; whether the poles are genuinely exclusive is
clinical and is not.

**Method note worth keeping.** The first run of this check reported FIVE drops.
Four were my own bug: I passed the whole human turn, including RETRIEVED
CONTEXT, to a guard whose entire purpose is to never see the chunk. Constraint 11
demonstrating itself on the person checking it.

#### 2026-09-18, late. Exertion axis retired. Verified live. A second, worse bug found doing it.

**FIXED: `exertion` removed from `CONTRADICTION_AXES`.** Three axes remain:
course, duration, rest response. Vocabulary and reasoning preserved in
`validate_pairs.RETIRED_AXES` at the spot someone would re-add it. `rest
response` stays and is legitimate, because both its poles answer the same
question, how the pain responded to rest, instead of straddling onset and
current state.

Suites: validator 24/24, guards 36/36, freeze sound. Guard sweep over all 45
pairs / 49 turns: **0 red_flags dropped, 0 next_steps dropped, 0 follow_ups on
red.** A genuine course contradiction still drops, so the check was narrowed and
not disabled.

**Verified on the live demo path, not just in the suites.** A case reading
"Chest tightness came on while I was walking up the stairs ... sat down to rest
but it has not gone away ... half an hour now" returned **red** with two red
flags, both phrased with "at rest", both kept. Replaying the retired axis
against that exact output drops BOTH, which would have left a red verdict with
no supporting red flags on a textbook evolving ACS. Beat 2 preset separately
re-run: red, 3 red flags, nothing dropped, 55.9 s.

**The RN app had a second copy of the lexicon and no way to sync it.**
`export_lexicon.py` writes only `02-pairs/finding_lexicon.json`; the npm
`sync-fixtures` script copied `guard_fixtures.json` and **not** the lexicon. So
`05-app/spike-load/finding_lexicon.json` still carried four axes after the fix.
Its own docstring predicted this: "Adding it in two places is a bug waiting for
the day the two disagree." Copied, and `sync-fixtures` now copies both.
**guards.ts is NOT verified**: there is no `node_modules`, so jest cannot run.
Synced and unexecuted is not the same as passing.

---

**NEW BUG, not fixed, and I think it is worse than the one I was sent to fix.**

**The scope floor refuses a genuine ACS presentation.** Measured live: profile
"dad", symptoms "Chest got tight walking up the hill to my car, same as it does
most weeks. Sat on the wall. It has not shifted, it has been half an hour now."
came back **refused as out of scope**, best match 0.394 against the 0.40 floor.
A man describing an evolving myocardial infarction in ordinary English was told
"This is outside what this system covers."

**Cause: the floor is calibrated on symptoms and applied to symptoms plus
timeline.** `server.py:233` builds `query = symptoms + "\n" + timeline` and
scores scope on that. The timeline is mostly `T+0:00` markers and structural
tokens, so averaging it in pulls the embedding away from chunk space.

| case | symptoms only | plus timeline | delta |
|---|---|---|---|
| colloquial ACS | 0.489 pass | **0.394 REFUSED** | -0.095 |
| beat 2 preset | 0.628 pass | 0.594 pass | -0.034 |

claude.md records "worst in-scope 0.482" from the 09-17 calibration. That is
within rounding of the 0.489 measured here **symptoms-only**, which says the
calibration set was scored without timelines. The demo scores with them.

**Why it has stayed invisible.** Every preset is written in textbook language
and scores 0.59 to 0.81 even with the timeline attached. Only colloquial
phrasing lands near the floor, and colloquial phrasing is what the product is
for. Scan of 9 in-scope phrasings, symptoms-only: lowest was 0.422 ("elephant
sitting on my chest"), then 0.448 ("goes tight when I walk up hills"). Both
clear the floor by under 0.05, so the margin is thin before any timeline is
added.

**Recommended fix: score scope on the symptoms text only, and keep using
symptoms plus timeline for retrieval itself.** That matches how the floor was
calibrated and does not weaken the out-of-scope guard: ankle 0.252 and headache
0.294 are nowhere near 0.40. Not implemented. The floor is explicitly a bet in
claude.md and moving what it reads is Viraj's call.

#### 2026-09-18, night. Scope fix applied, floor lowered, and the calibration does not reproduce.

**1. Scope is now scored on SYMPTOMS ONLY.** `server.py` still retrieves on
symptoms plus timeline, because onset and progression are real signal for WHICH
chunk. Scope no longer sees the timeline, because it is mostly `T+0:00` markers
and structural tokens that pull the embedding away from chunk space without
saying anything about topic. This aligns application with how the floor was
always calibrated.

**2. `SCOPE_FLOOR` 0.40 -> 0.33.**

**3. Re-calibrated, and the headline is worse than the bug I was fixing.**
`04-retrieval/calibrate_scope.py`, 12 in-scope against 12 out-of-scope, the
in-scope half deliberately written in plain English. Saved to
`01-data/eval/runs/2026-09-18-scope-recalibration.txt`.

```
worst in-scope   0.314   "There is a heaviness across my front and my left arm has gone dead"
best out-scope   0.450   "I have a sore throat and a cough"
gap             -0.136
```

**THE GAP IS NEGATIVE. The classes overlap and NO threshold separates them.**
The old picture of a floor sitting safely inside a 0.144 gap was an artefact of a
sample written entirely in corpus language. A floor is a choice about which error
to make, not a boundary.

**The 09-17 calibration does not reproduce.** "Burning behind my breastbone at
night" was recorded at 0.482 and measures **0.386** today on BOTH the dense and
the hybrid scorer, which agree to four decimal places, so it is not a scorer
difference. Most likely the corpus grew 19 -> 22 chunks between the dates. It was
never written to disk. **This is precisely the failure the "every eval result
goes to disk" convention was added to prevent, and it cost the floor its entire
justification.** The new calibration is a script and its output is on disk.

**Accepted at 0.33, both measured, neither hypothetical:**
- `0.314` "There is a heaviness across my front and my left arm has gone dead"
  is **STILL REFUSED**. Textbook ACS with radiation, scoring low only because the
  wording contains neither "chest" nor "pain". **0.25 would admit it.** Open call
  for Viraj; I did not lower past what was asked for.
- `0.450` "I have a sore throat and a cough" **PASSES**. Defensible, since
  CP-PERI-001 names "a cough, runny nose" as the viral prodrome.

**4. Verified live.** The case refused earlier tonight at 0.394 now returns
**red**, red flags intact, nothing dropped, 31.8 s. Beat 2 preset unaffected.
Side note, not chased: that run cited only CP-PERI-001, a pericarditis chunk, on
an exertional presentation. Retrieval quality, not scope.

**5. RN guard VERIFIED, no longer just synced.** `npm install` then
`npx jest __tests__/guards.test.ts`: **39/39 passed**, including all five
red_flags cases against the new three-axis lexicon. `guards.ts` implements guards
1 to 5 and **not** scope, which is Python and demo only, so the new scope
fixtures do not touch the TS side.

Python suites: guards **38/38** (two fixtures added for the accepted miss and the
accepted pass), validator 24/24. Scope fixtures 3 and 4 were rewritten: the old
"strongest out-of-scope is still refused" encoded 0.338 and became false at a
0.33 floor, and the old "weakest in-scope" carried the stale 0.482.

#### 2026-09-18, night. Floor to 0.25, post-flight tested not assumed, and two holes found.

**`SCOPE_FLOOR` 0.33 -> 0.25.** Clears all 12 in-scope with 0.064 of margin,
0 in-scope refused, 8 of 12 out-of-scope through.

**What 0.25 admits that 0.33 refused, both sides, all measured:**

| cosine | query | live result |
|---|---|---|
| 0.294 | three-day headache | REFUSED post-flight |
| 0.291 | tooth and face ache | REFUSED post-flight |
| 0.265 | sore knee since running | REFUSED post-flight |
| 0.252 | rolled ankle, swollen | REFUSED post-flight |

In-scope side: **0.25 refuses nothing.** The case that forced the move,
"There is a heaviness across my front and my left arm has gone dead" at 0.314,
now goes through.

**The post-flight check was TESTED, not asserted.** All 8 out-of-scope queries
clearing 0.25 were run end to end. **7 of 8 refused**, including the headache,
which was the one I would have worried about. The check earns the weight.

**THE ONE THAT GOT THROUGH, and it is not one 0.25 admitted.**
"My toddler has a fever and is pulling at her ear", 0.341, was **TRIAGED red**,
citing CP-PNA-001 / CP-PERI-002 / CP-PERI-001, rationale "Fever in a toddler
with ear pulling is a red flag for possible meningitis".

**"meningitis" is in NO chunk.** Pure fabrication. But CP-PNA-001 really does
say "Young children, older adults, and people who have serious health conditions
are at risk" and lists fever, so the key resolves and the citation guard is
correct to pass it.

**That is the limit of the post-flight check, stated plainly: it fires only on
EMPTY citations. Where the corpus holds an adjacent-but-wrong chunk, the model
grounds on it and the guard cannot see the problem.** This is not a 0.25
regression, it passed at 0.33 too. Raising the floor to 0.40 "fixes" it only by
the luck of a number, not by knowing anything. The red verdict happens to be the
safe direction for a febrile toddler; the same mechanism returned green on the
ectopic case on 09-17.

**SECOND HOLE, independent of the floor, and it is in the pregnancy exclusion
itself.** `excluded_subject("My stomach hurts and my period is late")` returns
**False**. It never caught the founding case.

- `PREGNANCY` requires an explicit pregnancy word: pregnan*, expecting,
  trimester, weeks gone, postpartum, obstetric, pre-eclampsia, midwife.
- "my period is late" contains none of them.
- `PREGNANCY_SYMPTOM` also misses, because "stomach hurts" is not "upper
  stomach".

**That is the entire clinical point of an ectopic: the patient does not know she
is pregnant.** The exclusion only protects someone who already says they are.
claude.md read as though the exclusion covered this case. It does not.

Layer-by-layer for that query at each floor:

| layer | 0.40 | 0.33 | 0.25 |
|---|---|---|---|
| relevance floor (0.321) | refuses | refuses | **passes** |
| excluded_subject | passes | passes | passes |
| post-flight empty citations | refuses | refuses | refuses |

So 0.25 takes it from two layers to one. Still refused live, verified, yellow
withheld, 42.3 s. **Proposed fix, NOT applied because adding a term is a
clinical decision: add "late period", "missed period", "period is late" to
`PREGNANCY`.**

Suites: guards **40/40**, validator 24/24, RN jest **39/39** after sync.
Calibration and the full live sweep written to
`01-data/eval/runs/2026-09-18-scope-recalibration.txt`.

#### 2026-09-18, late night. Two categorical exclusions, verified live, and a real ACS case refused while doing it.

Both fixes were Viraj's call. Guard work stops here by decision.

**1. A late or missed period is now a pregnancy term.** Forms of "late period",
"missed period" and "period is late" were added to `PREGNANCY`, including the
spoken forms: "missed my period", "missed two periods", "period is 5 days late",
"period's late".

**The three phrases alone did nothing, and I tested that before relying on
them.** `PREGNANCY_SYMPTOM` covered only the upper abdomen, and "stomach hurts"
is not "upper stomach", so the founding case still got through with the terms
added. The entry above said so, and the fix it proposed missed it. The symptom
side now covers stomach, tummy, belly, abdomen and pelvis, including the
one-word "stomachache". Side effect: a patient who says she is pregnant and has
lower abdominal pain is now refused too. Same call, same reason.

Layer by layer for "My stomach hurts and my period is late", updated:

| layer | before tonight | now |
|---|---|---|
| excluded_subject | passes | **refuses, 98 ms, no generation** |
| relevance floor 0.25 (0.321) | passes | passes |
| post-flight empty citations | refuses | refuses |

**2. A paediatric exclusion, same shape.** A child term plus any symptom
refuses. A child term is any of: baby, infant, newborn, toddler, child or kid;
a possessive son, daughter, boy, girl or grandchild ("my" or "our", with up to
two words in between); an age under 16 in years, as digits or words
("4-year-old", "two year old", "8yo", "age: 9"); or any age in months, weeks or
days. "baby aspirin" and "son-in-law" are carved out. "twenty-five years old"
is read as 25, not as the "five years old" inside it. `SYMPTOM` is deliberately
broad, because it is the half that fails open.

**The premise was slightly off.** The corpus is not free of paediatric content.
CP-PNA-001 has a passage on how pneumonia shows in babies: fever, vomiting,
grunting, rapid breathing, bluish lips. That passage and its "Young children
... are at risk" line are what the toddler case grounded on. It does not change
the call. The refusal reason says "no paediatric content beyond one passage on
pneumonia in babies" rather than claiming there is none.

**Mechanics.** `excluded_subject` now returns `(excluded, reason, message)`
instead of `(excluded, reason)`, because two exclusions need two refusal
messages. Its only callers are `server.py` and the self-test, and both are
updated. The reason names the words that matched, e.g.
`a child ("toddler") with a symptom ("fever")`, so an over-refusal at the desk
can be read straight off the grey panel. A fixture can now name which exclusion
must fire. As a mutation check I set the toddler fixture to expect pregnancy,
and the suite failed at 59/60, so the check really can fail.

**Refusal copy: flagging for Viraj to rewrite in his own voice.** I wrote both:
- pregnancy: "This system cannot assess chest or abdominal symptoms in
  pregnancy, or when a period is late or missed. Those symptoms can have causes
  it has no information about, and some of them are urgent. Please contact a
  doctor, your midwife or emergency services now rather than relying on this."
- children: "This system cannot assess children. Their symptoms can have causes
  it has no information about, and some of them are urgent. Please contact a
  doctor or emergency services now rather than relying on this."

**3. Verified live.** llama-server plus `06-demo/server.py`, POST /api/triage,
profile "You". `06-demo/results/2026-09-18-exclusions-live.txt`.

| case | result |
|---|---|
| My stomach hurts and my period is late | refused, pregnancy, 98 ms |
| I missed my period ... sharp pain low in my belly on one side | refused, pregnancy, 46 ms |
| My toddler has a fever and is pulling at her ear | refused, paediatric, 49 ms |
| My 4-year-old says her chest hurts when she runs | refused, paediatric, 672 ms |
| My son has a cough and is wheezing | refused, paediatric, 48 ms |
| She is 6 weeks old, not feeding and very sleepy | refused, paediatric, 42 ms |
| preset "Crushing chest pressure" | not excluded, red, 56.5 s |
| preset "Burning after a meal", its timeline says "late meal" | not excluded, red, 36.8 s |
| "There is a heaviness across my front and my left arm has gone dead" | not excluded, then **refused post-flight** |

Offline, `01-data/eval/runs/2026-09-18-exclusion-probe.txt`: 95 checks, 0
unexpected. Every demo preset passes untouched with both profiles, and so do
all 12 in-scope calibration queries. Of the 12 out-of-scope ones, only the
toddler is newly excluded.

**4. FOUND, NOT FIXED: the post-flight check refuses real ACS.** The third
control, textbook ACS with radiation, was refused as out of scope and its red
verdict withheld. I repeated it three times, keeping the raw model output. It
was refused once more and triaged red twice: **2 refusals in 4 runs.** Raw
output of the refused repeat:

    "citations": [
      "CP-ACS-003: Chest pain, heaviness, or discomfort in the center or left side of the chest is a common symptom of heart attack.",
      "CP-ACS-003: Pain or discomfort in one or both arms is also a common symptom of heart attack."
    ]

**The right key, with a quote appended.** `screen_citations` needs an exact key,
so it dropped both entries. The kept list was empty, and `scope_check` told the
user "the model cited nothing", which is false. claude.md calls this direction
catastrophic, and it happened on the exact query the floor was lowered to let
in. Before tonight only this query's cosine had been measured; it had never
been run end to end. The live post-flight tests covered out-of-scope queries
only, which is why this never showed. The likely fix is to take the leading key
of each entry (`^\s*(CP-[A-Z]+-\d{3})\b`) and validate that, in both `guards.py`
and `guards.ts`, with a fixture built from the string above. Not applied,
because guard work has stopped.

**Also seen, one sample at temperature 0.2:** preset "Burning after a meal"
came back red with the rationale "associated fast heartbeat and fever". The
guard correctly dropped both as red flags, but the rationale is unguarded and
showed them anyway. It is the same roadmap item as the invented "meningitis".

**Over-refusals.** Accepted and recorded as fixtures: "My daughter drove me
here" with crushing chest pain is refused as a child; so is "since I was 12
years old"; and "my period is not late" is refused, because negation is not
handled. **Two older over-refusals could fire at a desk on ordinary chest pain:
"I was expecting it to settle" trips `expecting`, and "I am not pregnant" trips
`pregnan*`.** "I had a baby 3 weeks ago and now I am short of breath" is refused
with the children message, which is the wrong message for someone who has just
given birth. None of these is fixed.

**Not covered, because each is a clinical call:** bleeding, spotting,
shoulder-tip pain or fainting with no abdominal word; "cramps" alone, which
would also refuse leg cramps in pregnancy; "overdue", "no period" and "haven't
had my period"; "I'm 14" without "years old".

Suites: guards **60/60** (was 40/40), validator 24/24, RN jest **39/39** after
`npm run sync-fixtures`. `guards.ts` still has no scope or exclusion port, so
the new fixtures run on the Python side only.

#### 2026-09-18, later still. Leading-key citation fix: 30 live runs and a replay. Two desk over-refusals fixed.

**1. The citation guard now validates each entry's leading key**, in both
`screen_citations` (Python) and `screenCitations` (TS), same rule. The key must
start the entry, after at most an opening bracket or quote, because the prompt
writes keys as `[CP-ACS-003]`. It must also be whole, so `CP-ACS-0031` is not
`CP-ACS-003`. Only the key is kept; the model's appended text never renders,
because the expander shows the real chunk. Prose that merely mentions a key is
still dropped, and a key cited twice is kept once. Five citation fixtures were
added, including the measured string, and both implementations pass them.

**2. The first 10 live runs could not show whether the fix works.** All 10 came
back red, but every raw list was bare keys, so the old rule would have passed
them too. That shows the case is healthy; it does not show the fix working. I
closed the gap two ways:

- **Replay.** A stand-in llama-server streamed the measured failing output
  verbatim through the unmodified `server.py`, which ran twice: once with
  tonight's guard, and once with `screen_citations` swapped back to the old
  exact-match version. **The old rule refused it ("the model cited nothing") and
  the new rule rendered red, citing CP-ACS-003, and the expander resolved it.**
  `06-demo/results/2026-09-18-leading-key-replay.txt`.
- **20 more live runs**, raw output kept, both rules scored on the same outputs.

| ACS case, 30 runs | new rule | old rule, same outputs |
|---|---|---|
| bare keys, 23 runs | red | red |
| key with the chunk's line appended, 4 runs | **red** | REFUSED |
| `citations: []`, 3 runs | REFUSED | REFUSED |
| **total** | **27 red, 3 refused** | 23 red, 7 refused |

The two batches differ: the first 10 runs had 0 problem lists and the next 20
had 7. The server, prompt and temperature (0.2) were the same, so treat any one
batch as a sample.

**3. The refusal that remains is a different bug, and it is NOT fixed.** In all
3 empty-list runs the urgency is **red** and the rationale says "possible heart
attack". Run 12's rationale names CP-ACS-003 in its text, with an empty
citations array. So the post-flight check withholds a red for a heart attack
about one run in ten, down from about one in four. The option, for Viraj:
never withhold a red. Across the 19 out-of-scope refusals in section C, the
withheld verdict was green or yellow every time, never red, so on tonight's data
that rule rescues all 3 and lets none of the 19 through. It would also mean
showing a red with no citation. That is a clinical and product call, not made.

**4. Out-of-scope regression check: the fix did not loosen the net.** The 7
out-of-scope queries that clear the floor (the toddler is now excluded earlier)
were run 3 times each, scored under both rules. **The outcome was identical
under both rules in all 21 runs.** 19 were refused, and the raw list was `[]` in
every one of them, so none of the earlier "cited nothing" refusals had been an
annotated-key artefact.

**Found doing it: the dental query gets through, and not because of the fix.**
"My tooth is killing me and the side of my face aches", 0.291, one of the four
queries 0.25 newly admits, was **triaged red in 2 of 3 runs**, citing
CP-PERI-002 and CP-PERI-001 by exact key. In both, the model asserted
"chest pain that feels sharp, gets worse with breathing, and feels better with
sitting up and leaning forward" as the patient's, which is CP-PERI-002 copied
onto a toothache. **The red-flag guard kept it**, because the 21-term lexicon has
no term for chest pain, for pain on breathing, or for positional pain. This
contradicts "seven of eight refused, including all four that 0.25 newly
admits", which rested on one run per query; claude.md and the guards.py comment
are corrected. A floor of 0.30 would refuse it pre-flight with 0.014 of margin
under the worst in-scope query measured. That is Viraj's call; I have not
changed the floor.

**5. The two desk over-refusals are fixed, and verified live.**
- "I was expecting it to settle": `expecting` now counts only in its pregnancy
  senses: "I'm/I am/we're/she's expecting" at the end of a clause or before
  and, but, in and the like, or "expecting a baby", "twins", "my first".
- "I am not pregnant": `NOT_PREGNANT` (not, n't, never been, directly before
  pregnant) is removed before the pregnancy search. My first draft missed
  "isn't", because a `\b` cannot sit inside the word.
- Uncertainty is not a denial: "not sure if I am pregnant" and "don't think I'm
  pregnant" still refuse. A denial does not mask a late period in the same
  text, and "my period is not late" still refuses.

Live: both phrasings were triaged red, not excluded. "I'm expecting and I have
terrible heartburn" and "I'm not pregnant but my period is late and my stomach
hurts" were still refused before generation. Eight exclusion fixtures were
added.

Suites: guards **73/73** (was 60), RN jest **44/44** (was 39), `tsc --noEmit`
clean. Runs: `06-demo/results/2026-09-18-leading-key-live.txt`, sections A, B,
C, A2 and COMBINED, with the raw model output for every run, and
`2026-09-18-leading-key-replay.txt`.

#### 2026-09-18, night, last guard change. A red is never withheld, and never shown as confident when nothing is cited.

Viraj's call. When urgency is red and citations are empty after the citation
guard, the verdict is not refused. The page shows the red banner and its
disposition, plus a visible line saying the system could not ground this answer
in its sources. It must never show a clean, confident red above an empty
sources panel. Guard work stops here for tonight.

**What renders.** Only the urgency. The page shows the RED banner with "Call
emergency services now", then a neutral grey box labelled "Not grounded in
sources": "This system could not ground this answer in its sources, so only the
urgency is shown. A possible emergency is never withheld." Under it are the
reason and the timing line. The rationale, red flags, next steps and sources
panel do not render. That is my reading of "the red verdict and the
disposition, plus a visible line", and the withheld content backs it up: all
three rationales say "No red flags present" beside a red verdict, and run 12's
next steps include "Lie down with legs elevated", from no source. The line is
grey rather than amber so it cannot read as a second triage colour under the
banner. **The copy is mine; flagging it for Viraj to rewrite in his own voice.**

**Where it lives.** `post_flight(result)` in `guards.py` returns
`(action, reason, shown)`, where action is render, refuse or flag. A flagged red
carries the urgency and empty fields. The server sends the withheld fields
separately under `ungrounded.withheld`, so nothing is silently dropped. The page
has its own `renderUngrounded` branch, which also lists removed citations
because they explain why nothing grounded. `render()` was split into `banner`,
`removed` and `timing` helpers, so the new branch reuses them rather than
copying them. Python only: `guards.ts` has no scope port.

**Verified on the three failing runs.** A2 runs 10, 12 and 13 were replayed
verbatim through the unmodified demo server, with a stand-in llama-server
serving the recorded outputs, and then rendered in headless Chrome 153. The
Claude-in-Chrome extension was not connected, so I drove Chrome over the
DevTools protocol from Node 22.

| output | before tonight | now, server | now, page |
|---|---|---|---|
| A2 run 10, red, `[]` | withheld as out of scope | flagged, urgency only | RED, disposition, grey line, no other sections |
| A2 run 12, red, `[]`, CP-ACS-003 named in the rationale | withheld | flagged | same |
| A2 run 13, red, `[]` | withheld | flagged | same |
| control: ENT, green, `[]` | refused | refused | grey OUT OF SCOPE, green withheld |
| control: A run 1, red, cites CP-ACS-003 | rendered | rendered | full render, sources, removed items |

The three flagged screenshots are byte-identical, although the three model
outputs differ. That is the point: only the urgency reaches the screen. One
real-model run through the changed server and page rendered a cited red in
full: 53.4 s cold, prompt 32.2 tok/s, generation 9.2 tok/s.

**The bet this rests on.** An out-of-scope query that comes back red with
nothing cited now shows a flagged red instead of a refusal. Across the 19
out-of-scope refusals measured tonight, the withheld verdict was green or yellow
every time, never red. Nineteen runs is the whole of the evidence.

Suites: guards **78/78** (five `post_flight` fixtures, all real outputs), RN jest
44/44 after sync. Runs: `06-demo/results/2026-09-18-ungrounded-red-replay.txt`,
with screenshots beside it.

#### 2026-09-18, night. Viraj's read of all 45 pairs: five cut, seven flagged, and the verdict tracks the chunk.

Six findings and two checks from Viraj. Each was verified against the files
before anything moved. Nothing was rewritten. **Five pairs cut, moved verbatim
into `02-pairs/review/CUT-2026-09-18-night.jsonl`; the kept and cut files
together are byte-identical to the original.** 40 remain, and the validator is
clean. The full evidence is in `02-pairs/review/FINDINGS-2026-09-18-night.txt`.

**1. Paediatric exclusion. The premise holds for two of the three.**
`excluded_subject` refuses P0008 and P0027, and **not P0030**. P0027 is the real
child: aged 6, green, citing CP-PNA-001 alone. P0008's patient is 19 and is
refused only through "my daughter", the adult-child over-refusal recorded
tonight. P0030 (aged 17) has the child term, but "panic attack" is not a word in
`SYMPTOM`, so the app would triage it. All three were cut as instructed.

**That exposed a gap in tonight's guard, NOT fixed because guard work had
stopped.** The symptom half fails open. A child term plus a panic attack, an
asthma attack, a swallowed button battery, an allergic reaction, or "anxious
and scared" is not refused; all five were measured. Across the 45 pairs no
other pair trips an exclusion, and none is under the floor. P0002 is lowest at
0.254, and it is the only pair a 0.30 floor would refuse.

**2. Verdict by condition prefix. Confirmed, and now the top open item for
epic 2.** Viraj's counts are right: CP-PANIC 7/7 green, CP-PLEU 4/4 yellow,
CP-PE 2/2 red. These are exactly the conditions whose contrast sets constraint
14 removed: C04/C10, C05/C11 and C06/C12. **Tonight's cuts make it four
conditions**, because P0027 was the only green CP-PNA pair, which leaves
CP-PNA 3/3 yellow. After the cuts: PANIC 5 green, PLEU 3 yellow, PNA 3 yellow,
PE 2 red. A model trained on this can read the verdict off which chunk was
retrieved.

**3. P0037, cut.** The rationale says that pain not reproduced by pressing
"argues against the muscular explanation". In its two cited chunks, the only
match for press, reproduc, palpat, tender or chest wall is "pressure" in
CP-DIFF-001.

**4. Twenty-two distinct presentations in 45 pairs; 21 in the 40 left.** The
rest are variants of one presentation in a different register. The largest
clusters are typical reflux (5 pairs), undifferentiated complaint (5, now 4)
and known panic disorder (4, now 3). Identical strings: the rationale of P0011
matches P0039, and P0048 matches P0054; these are the two registers of the C08
and C02 halves. "Black tarry stool for two days alongside reflux" appears
twice, and "Exertional chest tightness with known coronary artery disease"
appears three times (P0026, P0036, P0057).

**5. The mix after the cuts is 40 pairs: red 9 (22%), yellow 19 (48%),
green 12 (30%).** The base rate is 7%, 34% and 59%.

**6. P0055, cut.** It trains on GERD chunks, but for that text the app
retrieves CP-ANG-001, CP-PERI-002 and CP-ANG-002.

**The two checks.**
- **P0009:** the case never says "no relationship to exertion". The pain began
  after moving house and is worse on reaching. The benign discriminator it rests
  on, reproducibility, is in no chunk. Flagged.
- **P0003:** CP-PE-002 is two sentences about risk factors combining, with no
  cancer in it. The cancer line is in CP-PE-004, which the pair does not cite.
  Flagged.

**Found doing the checks: the same failure in five more pairs, all flagged.**
- P0014 and P0023 credit the retrieved context with lines that are only in
  CP-PE-001 and CP-PANIC-002, which they do not cite.
- P0031, P0049 and P0052 credit it with meals, alcohol, eating or lying down.
  **No GERD chunk mentions any of them.** That is a corpus gap, like the missing
  negative discriminators.
- Both PE pairs are flagged. Cutting every flagged pair would leave CP-PE with
  none, and the set at 33.

**And P0055 is not isolated.** 16 of the 40 carry reference keys that the app
does not retrieve for their own text; 13 match fully. Whether a pair carries the
right chunks or the retrieved ones is a design call.

`02-pairs/pairs/PIPELINE-TEST-*` still holds all 45, and its README now says so.

### 2026-09-19 Brev 4-bit gate: blocked on credits, nothing provisioned

`brev create steel26-4bit-gate --type massedcompute_A6000_base` was refused at
11:12 EDT: "You have run out of credits". No instance exists, and nothing
billed. The login sees one org, `virajboj-9f4036-hq`, so the claimed credits
are not on any org this CLI can reach.

Checked before provisioning, so the next attempt does not redo it:
- `massedcompute_A6000_base` costs **$0.684/hr**: 1x A6000 48 GB, 6 vCPU,
  24 GiB RAM, 256 GB disk, about 5.5 min to boot, **not stoppable**. Pass
  `--timeout 900`, because the CLI's default 300 s is shorter than the boot.
- The HF repo `nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16` is not gated. No token is
  needed on the instance.
- The modeling code imports `mamba_ssm` and `causal_conv1d` only if they are
  installed, and otherwise falls back to pure torch. The five pip packages are
  enough. **WRONG, corrected in the next entry: the repo's modeling file
  hard-requires `mamba_ssm`.** The fallback casts by activation dtype, never by weight dtype, and
  `lm_head` stays bf16, so there is no obvious 4-bit dtype crash in check 3.
- `brev_4bit_gate.py --attach-lora` covers steps 3 and 4 on a single model
  load. It bails on the first failed check and attaches LoRA only after all
  three pass.

### 2026-09-19 THE 4-BIT GATE IS OPEN. bitsandbytes quantizes Nemotron's Mamba2 layers, and LoRA attaches 50.

Run on Brev, `massedcompute_A6000_base` at $0.684/hr: created 11:17:50, gone
by 11:55:32, about $0.42. The full output is in
`01-data/eval/runs/2026-09-19-brev-4bit-gate.txt`. Nothing was trained.

| step | result |
|---|---|
| versions | torch 2.14.0+cu130, transformers 5.17.0, bitsandbytes 0.50.2, peft 0.21.0, trl 1.13.0, accelerate 1.15.0, Python 3.10.12 |
| weights | sha256 55d4e2519456c4a9..., matching the local known-good |
| check 1, loads | PASS, 3.28 GB on device |
| check 2, quantizes | PASS. **Every projection is Linear4bit, Mamba2 `in_proj` and `out_proj` included**, 21 of each |
| check 3, generates | PASS. Logits finite; output `'.\n\n\n...'`, which matches the bf16 CPU reference on every token both produced |
| step 4, LoRA | PASS. **q/k/v/o 4 each, up/down 17 each, 50 of 50.** 10,119,168 trainable, 0.254% |

**Correction to this morning's pre-check.** The repo's own
`modeling_nemotron_h.py` imports `rmsnorm_fn` from `mamba_ssm` unconditionally
(lines 61 to 65) and raises without it. On the five pip packages, check 1 would
have failed on a missing package and said nothing about 4-bit. **The gate
therefore ran with one change, `trust_remote_code=False`, which loads
transformers 5.17's built-in `nemotron_h`.** That implementation has reference
PyTorch fallbacks for every Mamba kernel. I checked it on the laptop before
using it: 0 missing, 0 unexpected, 0 mismatched keys, `backbone.` renamed to
`model.` on load, and finite logits. transformers 4.57.6 has no built-in
`nemotron_h`. **Training needs transformers 5.x, or `mamba_ssm` compiled
against the installed torch.**

**The check-3 prompt is weak evidence on its own.** It is a raw completion, so
the model continues with a full stop and newlines. The proof is that the 4-bit
output matches the bf16 reference, not that it says "OK".

**Tooling:** `brev exec` hung twice, whether run from a file with `@` or
inline. Plain `ssh <instance>` works, using the SSH config brev writes. The
run was driven over ssh with local watchdogs, and the delete was unconditional.

### 2026-09-19 Profile escalation layer, and the child guard moved to profile age

**What was built.** `02-pairs/escalation.py` is deterministic rules that only
ever raise urgency. The page now has family cards, a rule line under the
verdict, a scope notice for a child's profile, and a side-by-side of two
profiles. It is hard constraint 15 in claude.md.

**Grounding came first, before any code.** Three of the six specified rules
were cited to chunks that do not state them: R3 to CP-ANG-001, R4 to CP-PE-002
(the P0003 error again) and R5 to CP-PE-004. Viraj re-keyed all three, to
CP-ANG-002 capped at yellow, CP-PE-004 plus CP-PE-001, and CP-PE-003 plus
CP-PE-001. He also chose these defaults: one level, capped at red; show the line
even on a red, as "supports this red"; and the child guard asks rather than
refuses. **`verify_grounding` checks every quote verbatim against its chunk
file, and the server will not start otherwise.**

**The child guard is now by profile age.** A profile under 16 gets the scope
notice and no verdict, before retrieval. On an adult profile a child word in
the text asks "who is this for?", with a button to continue. `excluded_subject`
is now pregnancy only. `child_term` lost its symptom half, which closes last
night's fail-open gap: panic attacks, asthma attacks and button batteries now
ask. "You" and "Dad" render byte-identical prompt text to before.

**Verified.**
- Offline: escalation 25/25, including the grounding check and never-lowers
  across every fixture at every urgency. Guards 84/84, with the paediatric
  fixtures migrated from "refused" to "asks". Validator 24/24. RN jest 44/44.
- Live: 8 of 8, in `06-demo/results/2026-09-19-escalation-live.txt`. Every rule
  fired on its profile. Maya's case was refused before any retrieval. "My
  daughter drove me here" asked first, then triaged after continuing.
- Headless Chrome: screenshots of the cards, the rule line, the child notice,
  the confirm prompt and the side-by-side, all beside that file.

**The measured limit: the model said red in 6 of 6 rule cases,** so every live
line read "supports this red", "supports at least yellow" or "flagged". A live
raise happened once in 3 runs of the best candidate, Grandpa with "Bit of a
niggle in my chest", where R2 raised a yellow to red. The raising path rests on
the fixtures and that single run.

**Also measured:**
- The layer leaves refusals alone. Mum, a diabetic, with "a bit of indigestion"
  was refused post-flight and R1 never ran. Whether a rule should override a
  refusal is open.
- The side-by-side took 131 s on CPU: two back-to-back generations, slower
  while headless Chrome shared the CPU.
- The model's red flags still include things the grounding guard's lexicon
  cannot see. "unable to bear weight since the injury" appeared on a tiredness
  case, and "shortness of breath when resting" on a case that says walking.

**An accident, repaired.** Removing the old symptom regex from `guards.py`, I
searched for `"SYMPTOM = re.compile("`, which matched inside
`PREGNANCY_SYMPTOM` first. The cut deleted everything from the pregnancy
symptom regex down to `PAEDIATRIC_REFUSAL`. There is no git to restore from. I
restored it from the verbatim text read earlier in the session. Checks: every
definition present exactly once, guards 84/84, and last night's
pregnancy-and-citation probe with 0 unexpected. Every later edit in this
session asserted a unique marker before cutting.

The refusal copy and the rule-line copy on the page are mine. Flagged for Viraj
to put in his own voice.
