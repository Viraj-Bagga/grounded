# CLAUDE.md

Project context for Claude Code. Read this before touching anything in this repo.

---

## What this is

Offline on-device medical triage app. Fine-tuned Nemotron 3 Nano 4B running entirely on a phone, no internet. Text or voice symptom input, structured follow-up questions, a WHO-standard urgency category with next steps and citable sources.

Built solo for SteelHacks XIII at Pitt, **September 19 to 20 2026**. Three tracks: Beyond the Chatbot (NVIDIA), Seed Round (Pear VC / Afore), Cold Start.

Judging is expo-style desk visits, about 5 minutes per judge. Judges cannot install anything, so nothing may require them to install anything.

**The demo surface is a laptop web UI against `llama-server`, decided 2026-09-17.** The iOS simulator was the plan until it was measured: one completion takes **3 min 56 s in Release** there, against about 40 s under `llama-server` on the same Mac, and a visit is 5 minutes. The simulator has no Metal, but the bigger factor is that it is a translation layer, roughly 4x slower than the host CPU on the same `-ngl 0` path. The phone appears as a screenshot, evidence that it runs on-device, and nothing in the five minutes waits on it.

**CPU is still the demo condition and every latency number that matters is still a CPU number**, just the host's rather than the simulator's: prompt eval 30 to 32 tok/s, generation 9.5 to 10 tok/s, both re-confirmed live on the demo path 2026-09-17.

The point of the product is care where there is no clinic. That framing drives real decisions, including which devices matter and why the roadmap goes to a smaller model rather than a bigger one.

---

## Division of labour

**Claude Code owns:** the app shell, UI, retrieval layer, build tooling, data pipeline mechanics, test harnesses.

**Viraj owns:** the model work (training data, QLoRA, quantisation), all clinical judgment, chunk boundary review, and anything that assigns or freezes a citation key.

When a task crosses into his column, do the mechanical part and stop with a clear report. Do not make a clinical call or freeze a corpus on your own.

---

## Repo layout

```
01-data/          corpus pipeline (epic 1)
  sources.yaml      source manifest with verified licences
  build_corpus.py   fetch / chunk / freeze
  raw/              fetched HTML, kept for reproducibility
  review/           candidate chunks awaiting human review
  chunks/           frozen chunks, one file per citation key
  citations.csv     the registry, written by freeze
  eval/
    discrimination_test.py
03-model/
  base/             base GGUF lives here, NOT in a scratch dir
spike/            throwaway CLI experiments
build-log.md      running record of decisions and findings. APPEND TO THIS.
```

---

## Stack

Nemotron 3 Nano 4B → LoRA (rank 16, alpha 32, **6 modules, see below**, 2 epochs; **bf16 base, not 4-bit, see below**) → merge → eval → F16 GGUF → llama-imatrix → Q4_K_M (~2.84 GB) → **llama.rn pinned at exactly `0.12.9`** on React Native.

**The model is `nemotron_h`: hybrid Mamba2 plus attention, not a dense transformer.** Verified 2026-09-15 from three independent sources that agree: the GGUF tensor table, `config.json` `hybrid_override_pattern`, and the safetensors header of `nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16`. 42 blocks split **21 Mamba2 / 4 attention / 17 MLP**, with attention only at blocks 12, 17, 24 and 32. "Dense" in the old note meant not-MoE; it does not mean transformer.

**This breaks the "7 modules" QLoRA plan and the module list is now an open decision, not a default.** Real leaf module names and their share of the 3.97 B parameters:

| module | params | share | in |
|---|---|---|---|
| `in_proj` | 1.15 B | 29.0% | Mamba2 |
| `out_proj` | 0.51 B | 12.7% | Mamba2 |
| `conv1d` | 0.001 B | 0.0% | Mamba2 |
| `up_proj` / `down_proj` | 1.34 B | 33.6% | MLP |
| `q_proj` / `o_proj` | 0.13 B | 3.2% | attention |
| `k_proj` / `v_proj` | 0.026 B | 0.6% | attention |

There is **no `gate_proj`**; this MLP is not gated, so that target matches nothing.

**DECIDED. `target_modules = ["q_proj","k_proj","v_proj","o_proj","up_proj","down_proj"]`.** Six, not seven. Config and the assertion live in `03-model/qlora_config.py`. Do not reopen this on Brev; the reasoning is:

- **`gate_proj` is dropped because it does not exist.** It matched nothing.
- **The Mamba2 mixers are deliberately not targeted**, despite `in_proj` plus `out_proj` being 41.7% of parameters. **Coverage is the wrong objective.** This is a light-touch format fine-tune, about 500 pairs for 2 epochs, teaching output shape. The spike showed the failures are teachable at the prompt level, so it is not a behavioural rewrite. More trainable parameters against 500 examples buys overfitting, not capability.
- **`in_proj` is skipped for a second reason too.** It is a fused projection emitting x, B, C, dt and z, so a low-rank update smears across five semantically different outputs. LoRA on Mamba2 is thinner ground than LoRA on attention, and four days out is the wrong time to be the person testing it.
- **Attention is kept despite being 3.8% of parameters, and not for parameter count.** Copying a citation key like `CP-ACS-001` verbatim out of a retrieved chunk is in-context copying, which lives in attention heads. There are four attention blocks in the entire model. Those are the ones that must learn citation fidelity, and citation fidelity is demo beat four.

**Module paths do not look like a transformer's.** Every projection sits under `.mixer.`, attention included: `backbone.layers.12.mixer.q_proj`, `backbone.layers.1.mixer.up_proj`. The top-level prefix is `backbone.`, not `model.`. PEFT matches on the suffix so the plain names in `TARGET_MODULES` work as written, but anything that greps, filters or freezes by path (layer-wise LR, partial unfreezing, `modules_to_save`, a regex target) must expect `.mixer.` or it will silently match nothing. Attention exists only at layers 12, 17, 24 and 32.

**It is LoRA, not QLoRA, and that was forced rather than chosen (2026-09-19).** The
Mamba2 mixer needs the fused `mamba_ssm` and `causal_conv1d` kernels or training
does not fit on a 48 GB card at all: the reference PyTorch fallback peaked at
47.29 GiB of 47.40, against 21.29 GiB with the kernels. But the fused kernel
multiplies `in_proj` and `out_proj` itself, so bitsandbytes' packed 4-bit weights
die on shape (`mat1 and mat2 shapes cannot be multiplied`), at any batch size,
and excluding those modules from quantisation does not help. **Kernels or 4-bit,
not both**, so the base trains in bf16 at 7.95 GB on the device. The adapter,
targets, rank, data and merge are all unchanged. The live gap is that training
saw unquantised weights while the demo ships Q4_K_M.

Retrieval: sqlite-vec plus all-MiniLM-L6-v2. Speech: **whisper.cpp v1.9.4 built from source, `ggml-base.en-q5_1`, 57 MB, CPU** for STT (built 2026-09-19, `03-model/whisper/build.sh`); native OS TTS, not built. **Not brew:** `brew install whisper.cpp` would upgrade llama.cpp and ggml, which every latency number here was measured on. Model chosen over five others by measurement, `01-data/eval/runs/2026-09-19-whisper-model-choice.txt`: tiny mangled "angina" and "stent", small.en cost 3.2x the size for no WER gain.

Training on HuggingFace TRL + PEFT, on NVIDIA Brev. English only for the MVP.

Triage framework is WHO's Interagency Integrated Triage Tool (red / yellow / green). Clinical export is a SOAP note.

Python: use the repo venv at `.venv`. The system has multiple interpreters and `pip` and `python3` resolve differently outside it.

---

## Hard constraints

Violating any of these silently breaks something downstream. They are not preferences.

1. **Citation keys are immutable once frozen.** Every epic 2 training pair references a key. Re-chunking after pairs exist breaks all of them. Never run `freeze --force` over an existing registry without explicit instruction. **New sources are added with `freeze --append --only <ids>`** (built 2026-09-19): it appends rows, continues each prefix from its highest key, keeps every frozen row and chunk file byte-identical, and refuses a source that is already frozen.

2. **256 word-piece ceiling on every chunk.** all-MiniLM-L6-v2 truncates there. Anything longer is silently invisible to retrieval past the cut. Reject oversized chunks, never truncate them.

3. **No `maxLength` in the output JSON schema.** It truncates mid-token and corrupts strings, including producing stray characters mid-word. Brevity is enforced by prompt rules, with schema caps generous as a safety net only.

4. **`follow_up_questions` must be empty when urgency is red.** A red verdict means call for emergency help now; there is no questioning round. The schema cannot enforce this, so app logic must.

5. **Reasoning is OFF.** Measured 50.9 s with it against 14.4 s without, on Metal, which is the friendliest hardware in the chain. Training pairs carry no think blocks. This is decided; do not reopen it.

   **Off has to be requested on every call, and nothing warns you if it is not.** A request without `"chat_template_kwargs": {"enable_thinking": false}` gets a reasoning trace back in `reasoning_content`, next to perfectly normal JSON in `content`. `discrimination_test.py` ran that way until 2026-09-17, so every verdict it recorded before then is a reasoning-on verdict, and the two configs disagree: green-gerd is yellow with reasoning and red without. Any new harness, and the epic 5 llama.rn call, must send the switch and should check that `reasoning_content` comes back empty.

6. **Never ship content that is not licence-cleared.** See the licensing section. `sources.yaml` carries a `license_status` field and the pipeline skips anything not green or amber.

7. **Chunk size is a latency decision.** Prompt eval runs at **30 to 32 tokens/sec on CPU**, measured 2026-09-15 with `-ngl 0` on an M4. Every 100 tokens of retrieved chunk costs about **3.1 s** on a cold turn. Three chunks at the frozen 145-token mean is 13.5 s of demo. The earlier figure here, 115 tokens/sec and 0.9 s per 100 tokens, was derived by arithmetic across the 50.9 s and 14.4 s Metal runs and never held on CPU. Do not reuse it.

8. **Do not re-run retrieval on follow-up turns** unless the query materially changed. The prefix cache makes prompt eval nearly free on a follow-up, measured 51,578 ms down to 246 ms. It does **nothing for generation**, which runs at a flat 9.5 to 10 tok/s cold or warm. So a follow-up costs roughly `output_tokens / 10` seconds, measured 11.2 s for a 63-token answer and 37.1 s for a 359-token one. Re-retrieving throws away the prompt-eval saving and adds the chunk cost back.

9. **Validate every citation key against `citations.csv` before rendering.** The model invents keys. Measured 2026-09-15: with no chunks in context it returned `CP-RISK-014` and `MED-ANTICOAG-007`, neither of which exists. Drop any key not in the registry, and never let an invented key reach the citation expander. A judge clicking a citation that does not resolve is worse than showing no citations. This is app logic; a prompt instruction will not hold it.

    **Validate each entry's LEADING key, not the whole string.** Measured 2026-09-18: on textbook ACS the model cited `"CP-ACS-003: Chest pain, heaviness, or discomfort..."`, the right key with the chunk's line appended. Exact matching dropped it, the list came out empty, and the post-flight scope check (constraint 13) refused a heart attack as out of scope in 2 of 4 runs. `screen_citations` and `screenCitations` now take the key at the start of each entry, after at most an opening bracket, and the key must be whole: `CP-ACS-0031` is not `CP-ACS-003`. Only the key is rendered, never the model's appended text, because the expander shows the chunk's real text. Prose that merely mentions a key is still dropped, and a key cited twice is kept once. Verified 2026-09-18: 4 of 30 live runs produced the annotated shape, the old rule would have refused all 4, and all 4 rendered red. Constraint 13 has the detail, including the empty-citation reds this cannot reach, which are handled there by never withholding a red.

    **Prompt sections cited in place of keys, measured 2026-09-19.** Across every assessment the demo saved that day, **8 of 37 model turns cited a section of the prompt rather than a key**: `PATIENT PROFILE: ...`, `SYMPTOMS: ...`, `FOLLOW-UP: ...` and `RETRIEVED CONTEXT: CP-ACS-003 (...)`. The guard drops all of them. 4 of the 8 had no valid key left after that. All 4 were the sick-and-sweaty text on Mum, and all 4 rendered as a not-grounded red. So this is one way a turn ends up with nothing cited; the other, more common one is an empty list (Current state). **2 of the 8 had the right key behind the label**, `RETRIEVED CONTEXT: CP-ACS-003 (...)`. In one of them the model attached three glosses to that key, and two of them are not in CP-ACS-003: "more than 10 minutes" and "high-risk patients". **Whether a key behind a label should count is an open guards call.** The guard is unchanged. Constraint 15 records a compare run rescued this way. Run: `06-demo/results/2026-09-19-prompt-section-citations.txt`.

10. **PEFT does not error on a `target_modules` entry that matches nothing.** As long as one other target matches, it builds the adapter and trains silently. That is exactly how `gate_proj`, which does not exist on this architecture, sat in the seven-module list and would have produced a clean-looking run. After building the config, assert the matched module count is non-zero **and equals what you expect**, per target. `03-model/qlora_config.py` does this and self-tests offline with `python 03-model/qlora_config.py`. Expected for this model: q/k/v/o_proj 4 each, up/down_proj 17 each, 50 total.

11. **`red_flags` entries must be grounded in the case text, and no clinical finding may be sourced from a retrieved chunk and attributed to the patient.** Findings about the patient come only from the profile, timeline and symptom text. Retrieved context supplies criteria, never findings. A red flag is a finding in *this patient*: the chunk says which findings would be red flags, only the case text says which ones the patient actually has.

    Measured 2026-09-17: given a pleuritic case whose text mentions neither, the base model returned `red_flags: ["fast heartbeat", "fever"]`. Both strings are lines in `CP-PERI-002`, the chunk supplied to that case, which is three lines long. It copied findings out of the chunk and asserted them as the patient's own. This is worse than an invented citation key: constraint 9 can drop a key that does not resolve, but a fabricated finding reads exactly like a real one and nothing downstream can tell.

    **The class is wider than chunk copying.** The full audit of every saved run, same date, found three more shapes on `probe-costo`, whose timeline says `T+2:00 unchanged`: `red_flags: ["sudden onset and progression"]`, where the case says the pain was noticed on waking and never changed; `red_flags: ["possible pleurisy as a cause"]`, which is not a finding about the patient at all but a hypothesis lifted out of `CP-PLEU-001`; and a rationale asserting "pressure-like quality, but onset within 20 minutes" for a case that is sharp and worse on **pressing**, with no pressure anywhere in it. So the guard has to reject three things, not one: findings the case does not state, findings the case contradicts, and chunk content placed in a findings field.

    **A fabricated red flag is not cosmetic, it decides the verdict.** Rule 4 of the format 3 prompt makes any red flag force red regardless of other factors, so an ungrounded entry deterministically produces a red. Both fabrications measured in that config landed on cases that went red, and in both the fabricated finding is the stated reason.

    `validate_pairs.py` warns on this for training pairs, checking the case text and never the retrieved context. A lexicon cannot prove it, so it is a warning that a human clears, same call as the qualifier rule. Its lexicon knows 20 findings, and every extra shape above was invisible to it, so treat its count as a floor.

    **The app guard now exists and it DROPS rather than warns.** `screen_red_flags` in `02-pairs/guards.py` and `screenRedFlags` in `05-app/spike-load/guards.ts`, both reusing `ungrounded_findings` and `contradicted_findings` from `validate_pairs.py` so there is one rule and not three. A pair gets a warning because a human clears it before the pair is frozen; the demo path has no human between the model and the screen, so it fails closed and renders what it removed. Verified live 2026-09-17: the model copied `fast heartbeat` and `fever` out of CP-PERI-002 and both were dropped on screen.

    **A denial is not a licence.** Until 2026-09-17 the check asked only whether a finding's word appeared in the case at all, so a patient saying "No fever" made a `fever` red flag pass. Fixed: a finding counts as supported only if the case *asserts* it. Watch the clause window when touching this, because `medications: none` in a structured profile once negated a fever asserted two lines later.

    **One thing the guard will not catch.** Reasoning-off runs mostly do not fabricate, they copy the prompt's own worked example: "X at rest beyond 20 minutes" came back for ACS, pleuritic pain and reflux alike. Each was literally true of its case, so a grounding check passes it, but the ACS frame is what turned those cases red. Real finding, imported frame. Different bug, no guard for it yet.

12. **`next_steps` never instructs medication administration. Enforced in app logic, not the prompt.** Measured 2026-09-17, no-chunk probe on yellow-angina: the model returned `next_steps: ["Call emergency services immediately", "Administer nitroglycerin if prescribed and available", "Monitor for recurrence or worsening symptoms"]`. That is a consumer app telling someone to take a cardiac drug. Nitroglycerin drops blood pressure and is contraindicated in several presentations, including inferior MI with right ventricular involvement, aortic stenosis, hypotension, and recent PDE5 inhibitor use. None of which this app can rule out, because it has no vitals and no exam.

    The app must drop or rewrite any `next_steps` entry that directs the user to take, administer, give, apply or dose a medication. "Call emergency services" survives; "chew aspirin", "administer nitroglycerin", "take an antacid" do not, and note the third is the benign-looking one that makes a blanket rule easier to defend than a drug list. Telling someone to bring their medications, or that a prescribed medication exists, is not the same as instructing a dose, and the wording has to separate those. Prompt rules cannot hold this for the same reason constraint 9 cannot be held by a prompt: it has to fail closed.

    **A line that both instructs and prohibits was flagged and KEPT until 2026-09-19.** "Take medication as prescribed; do not stop unless directed by provider" contains "do not", and the prohibition escape rescued the whole line, so an instruction to take a medication reached the screen wearing a "flagged, kept" tag. Measured live on the demo path that day. Each clause is now judged on its own and any clause that instructs drops the whole step. Clauses split on `;` and `.` only, because a comma or "and" separates a lead from its object: "Bring your medications and your inhaler" must not lose its second half.

    **The lexicon did not match the plural either.** "Continue current medications and follow up with cardiology as per routine plan" passed untouched, because the pattern held `medication` and not `medications`. Plurals are in now, here and in `guards.ts`. Both measured lines are fixtures in `02-pairs/guard_fixtures.json`, and the suites pass: 87 in Python, 48 in `guards.ts`. **A pronoun still escapes**, knowingly: "Do not stop your medication; take it as prescribed" names no medication in its second clause, and a lexicon cannot see it.

    This is also the fastest thing a medical-track judge finds.


13. **Out-of-scope queries must be REFUSED, not triaged.** The corpus is chest pain and nothing else: 35 chunks since 2026-09-19, every one under topic `chest_pain`. The system has no knowledge of anything else and must say so rather than produce a verdict.

    Found by clicking through the demo 2026-09-17. **"My stomach hurts and my period is late", 29-year-old woman, came back as a triage verdict with empty `red_flags` and ZERO citations.** That presentation includes ectopic pregnancy, which is life-threatening and time-critical. Retrieval had returned GERD, panic disorder and angina because that is all the corpus holds, and the model reasoned from them anyway and called it non-urgent. Re-run the same evening it returned yellow rather than green, temperature being 0.2. **The label is not the point.** A system with no knowledge of a condition produced a reassuring answer about it, and that is the most dangerous output this project has produced.

    `scope_check` in `02-pairs/guards.py`, two independent conditions, either one refuses:
    - **Relevance floor, checked BEFORE generating.** Max cosine over all chunks below `SCOPE_FLOOR` (**0.25**, lowered from 0.40 through 0.33 on 2026-09-18). **Scored on the SYMPTOMS text only.** Retrieval still uses symptoms plus timeline; scope does not, because the timeline is mostly `T+0:00` markers and averaging them in pulls the embedding away from chunk space without saying anything about topic.

      **The 09-17 calibration was wrong twice and neither error was visible from inside it.** First, it scored symptoms-only while the demo scored symptoms-plus-timeline, worth up to 0.095 of cosine. Second, all 8 in-scope queries were written in corpus language, so the sample could not see what colloquial phrasing does. It reported worst in-scope 0.482 / best out-of-scope 0.338 / gap 0.144, and **those numbers do not reproduce**: the same query measures 0.386 today on both scorers. It was never written to disk, which is the exact failure the "every eval to disk" convention exists to prevent.

      **Re-calibrated 2026-09-18, 12 in-scope against 12 out-of-scope, in-scope half written in plain English.** `04-retrieval/calibrate_scope.py`, re-runnable, results in `01-data/eval/runs/`.

      **worst in-scope 0.314, best out-of-scope 0.450, gap MINUS 0.136. The classes overlap and no threshold separates them.** The old picture, a floor sitting safely in a gap, was an artefact of the textbook-worded sample. A floor is now a choice about which error to make.

      **So the floor is set for the cheap error, and it is not the safety mechanism.** Refusing a real presentation costs a life; passing an out-of-scope query costs about 45 s and is then caught post-flight by the empty-citations condition, which needs no threshold. Do not tune the floor as though it were the guard.

      **0.25 clears all 12 in-scope queries with 0.064 of margin and lets 8 of 12 out-of-scope through.** It went 0.40 to 0.33 to 0.25 in one evening. 0.33 still refused "There is a heaviness across my front and my left arm has gone dead" at **0.314**, textbook ACS with radiation, scoring low only because the wording contains neither "chest" nor "pain". That is the phrasing the product exists to serve, so the floor had to go below it.

      **The post-flight check was then tested rather than assumed.** All 8 out-of-scope queries clearing 0.25 were run end to end on 2026-09-18. **Seven of eight were refused post-flight**, including all four that 0.25 newly admits and including the three-day headache, which is the most dangerous of them.

      **That was one run each, and one of the seven does not hold on repeats.** Three runs each later the same night: six were refused 3 of 3, headache included. **"My tooth is killing me and the side of my face aches", 0.291, one of the four 0.25 newly admits, was triaged red in 2 of 3 runs**, citing CP-PERI-002 and CP-PERI-001 by exact key, with "chest pain that feels sharp, gets worse with breathing, and feels better with sitting up and leaning forward" asserted as the patient's. The red-flag guard kept it, because its lexicon has no chest-pain, pleuritic or positional term. Same hole as the toddler: an adjacent chunk defeats the post-flight check. A floor of 0.30 would refuse this query pre-flight and leave 0.014 of margin under the worst in-scope query measured. That is a call, not a fix. Run: `06-demo/results/2026-09-18-leading-key-live.txt`, section C.

      **The one that got through was a hole the floor never closed by design.** "My toddler has a fever and is pulling at her ear", 0.341, was **triaged red**, citing CP-PNA-001, with the rationale "possible meningitis". **"meningitis" appears in no chunk.** But CP-PNA-001 genuinely says "Young children, older adults... are at risk" and lists fever, so the key resolves and the citation guard is right to pass it. **That is the limit of the post-flight check: it fires only on EMPTY citations, so an adjacent-but-wrong chunk defeats it.** Raising the floor does not fix this, it only catches this one query by luck of a number. **This query is now refused before generation by the paediatric exclusion, verified live 2026-09-18. The limit itself is not fixed** and applies to any out-of-scope subject no exclusion names. Extending the grounding check to the rationale would catch the invented "meningitis"; that is roadmap.

      **Lowering to 0.25 cost the ectopic case its floor coverage.** "My stomach hurts and my period is late" scores 0.321: refused by the floor at 0.40 and 0.33, **not refused at 0.25**. For part of 2026-09-18 only the post-flight check caught it (yellow withheld, 42.3 s).

      **It is two layers again: `excluded_subject` now refuses it before generation, verified live 2026-09-18.** It never used to, because `PREGNANCY` needed an explicit pregnancy word, and the whole clinical point of an ectopic is that the patient does not know she is pregnant. Viraj's call: forms of "late period", "missed period" and "period is late" are now pregnancy terms. **The three phrases alone would have changed nothing.** `PREGNANCY_SYMPTOM` covered only the upper abdomen, and "stomach hurts" is not "upper stomach". It now covers the whole abdomen and pelvis, which also refuses lower abdominal pain in someone who says she is pregnant.

      This was all found because the floor **refused a live evolving-MI description** on 2026-09-18: "Chest got tight walking up the hill to my car... It has not shifted, it has been half an hour now" scored 0.394 against the 0.40 floor and was told it was out of scope.
    - **Empty citations, checked after the citation guard.** The model grounded the answer in nothing. Needs no threshold, so it is the more robust of the two. **A yellow or green that cites nothing is refused. A red is never withheld** (decided 2026-09-18, `post_flight` in `guards.py`). It renders as the red banner and its disposition, plus a neutral grey "Not grounded in sources" line saying the system could not ground this answer and that only the urgency is shown. The rationale, red flags, next steps and sources panel do not render, because none of it is grounded. The server withholds those fields, and the page has its own branch as well. **It must never render as a clean, confident red with an empty sources panel.**

      **It also refused real ACS. Both causes are now handled, 2026-09-18.** "There is a heaviness across my front and my left arm has gone dead" was refused post-flight in 2 of 4 live runs, red verdict withheld, shown as out of scope. That is the catastrophic direction. 30 more runs, raw output kept and both rules scored on the same outputs, found two causes:
      - **The right key with the chunk's line appended**, `"CP-ACS-003: Chest pain, heaviness..."`. The exact-match citation guard dropped it, and the refusal said "the model cited nothing", which was false. **Fixed** by constraint 9's leading-key rule: 4 of the 30 runs produced this shape and all 4 rendered red. Replaying the original failing output through the demo server, the old rule refuses it and the new rule renders red citing CP-ACS-003.
      - **Genuinely empty citations.** 3 of the 30 runs returned `citations: []` with urgency **red** and a rationale saying "possible heart attack". One of them names CP-ACS-003 in the rationale text itself. The post-flight check used to withhold that red and call a heart attack out of scope. **Now handled by never withholding a red**, above. All 3 recorded outputs were replayed through the demo server and rendered in Chrome. Each showed RED, "Call emergency services now" and the not-grounded line, with no other sections. An out-of-scope green that cited nothing was still refused, and a cited red still rendered in full.

      **Net on those 30 outputs: 27 render as a grounded red and 3 as a flagged red. None is withheld, where the old rules withheld 7.** The 19 out-of-scope refusals measured the same night all withheld green or yellow, never red, so none of them gets through. **That is the bet this rule rests on:** an out-of-scope query that comes back red with nothing cited will now show a flagged red instead of a refusal. Tonight's data says the model does not do that, on 19 runs. Runs: `06-demo/results/2026-09-18-leading-key-live.txt`, `2026-09-18-leading-key-replay.txt` and `2026-09-18-ungrounded-red-replay.txt`, with screenshots beside them.

    **Categorical exclusions, checked before either condition.** The discriminator is subject matter, not similarity, so no threshold is involved.
    - **Pregnancy, including a late or missed period**, with a chest or abdominal symptom: `excluded_subject`, text-based, its own refusal message.
    - **Children: decided by the selected PROFILE'S AGE since 2026-09-19, not by text.** A profile under 16 gets the scope notice and no verdict, before retrieval, whatever the text says. On an adult profile, a child word in the text (`child_term`) **refuses nothing**. The page asks "who is this for?", and the user picks that person's profile or continues as themselves. Viraj's call. It replaced the 2026-09-18 text rule, which failed both ways: it refused adults who mentioned a daughter, including training pairs P0008 (aged 19) and P0030 (17), and it failed open on any child presentation without a word from its symptom list. `child_term` now has no symptom half, because it only decides whether to ask. **The corpus is not strictly free of paediatric content:** CP-PNA-001 has one passage on pneumonia in babies, which is what the toddler case grounded on. One paragraph on one condition is no basis for triaging children.

    **Pregnancy fails closed and over-refuses, knowingly.** "My wife is pregnant" with chest pain refuses, and so does "my period is not late". Recorded as fixtures so they are not mistaken for bugs.

    **Two desk phrasings no longer refuse, fixed and verified live 2026-09-18.** Both were ordinary chest pain refused as pregnancy. "I was expecting it to settle": `expecting` now counts only in its pregnancy senses, "I'm expecting" ending a clause or followed by and, but, in and the like, or "expecting a baby", "twins", "my first". "I am not pregnant": a denial directly before pregnant (not, n't, never been) is removed before the search. **Uncertainty is not a denial:** "not sure if I am pregnant" and "don't think I'm pregnant" still refuse, and a denial does not mask a late period in the same text. Live, both desk phrasings were triaged red, and "I'm expecting and I have terrible heartburn" and "I'm not pregnant but my period is late and my stomach hurts" were still refused before generation.

    **Not covered, a clinical call:** bleeding, spotting, shoulder-tip pain or fainting with no abdominal word; "cramps" alone, which would also refuse leg cramps in pregnancy; "overdue", "no period", "haven't had my period"; "I'm 14" with no "years old". `guards.ts` has no exclusion or scope port; the demo is Python.

    **The fail-open gap found 2026-09-18 is closed by that redesign.** A child word plus "panic attack", "asthma attack" or "swallowed a button battery" now asks on an adult profile, and a child's own profile never reaches the text at all. Verified live 2026-09-19: `06-demo/results/2026-09-19-escalation-live.txt`.

    The refusal must not read as a fourth, milder triage category. It is rendered in neutral grey, never in a triage colour, and it withholds the verdict rather than showing it.

    **This does not fix the underlying problem, it contains it.** Widening the corpus beyond chest pain widens what can be triaged; until then the exclusions, the floor and the post-flight check are all that stand between a judge and a reassuring answer about a condition the system has never heard of.

14. **A contrast axis must quote the line in the cited chunk that draws the distinction, or the set is not built.** Not paraphrased, not implied, not "the chunk is about this topic". The actual sentence, from a chunk both halves cite.

    Found 2026-09-17 auditing the 60 training pairs. **Six of twelve contrast sets rested on a criterion no cited chunk states**, which is the ungrounded-advice failure reproduced inside the training data, and it is worse there than at inference: a guard can drop a fabricated `red_flag`, but nothing can catch a fabricated criterion in the reasoning, and the pairs would have taught the model to produce them.

    | axis | verdict | evidence |
    |---|---|---|
    | exertional pain resolves with rest | PASS | CP-ANG-001: "Symptoms often go away with rest and return when you are active", and "Chest pain or discomfort that does not go away or occurs while you are resting might be a sign of a heart attack" |
    | black tarry stool | PASS | CP-GERD-002: "stool that contains blood or looks black and tarry" |
    | breathlessness at rest | PASS, weakly | CP-PERI-001 says "severe shortness of breath"; the axis said "at rest", which is a gloss, not the chunk's word |
    | reproducible on palpation | **FAIL** | CP-PLEU-001 never mentions palpation, tenderness or pressing. This is the NEG-DISC gap: the corpus has no negative discriminators and palpation is the canonical one |
    | sudden versus gradual onset | **FAIL** | CP-PE-001 and CP-PE-002 never mention onset speed at all |
    | previously diagnosed pattern | **FAIL, contradicted** | CP-PANIC-002 says without qualification that "panic attacks themselves are not life-threatening", which argues green for BOTH halves. The chunk actively contradicts the yellow side |

    **Absent and contradicted are not the same severity.** CP-PE's criterion is merely unsupported. CP-PANIC's is refuted by the chunk it cites, which is strictly worse and was the failure nobody predicted.

    **The sets were cut, not rebuilt.** Rebuilding means inventing chunk support that does not exist. If an axis matters clinically and the corpus cannot ground it, the fix is a source, not a sentence.

    Corollary, from the same audit: when an axis is corrected, the discriminator held constant must itself be grounded. The CP-PE rebuild held the risk factor constant to isolate onset, and the risk factor was the only thing those chunks actually supported. It removed the grounded discriminator and kept the invented one.

15. **Profile escalation only ever RAISES urgency, and every rule quotes its chunk verbatim.** `02-pairs/escalation.py`, added 2026-09-19 for the Beyond-the-Chatbot track. It is deterministic rules, not the model: the model-based version of "the profile changes the answer" was cut on 2026-09-17 because both profiles came back red. A rule fires on a structured profile fact AND a symptom asserted in the case text. That text is the symptoms and timeline, never the chunks or the model's output, as in constraint 11. It raises the verdict **one level, capped at red** (R3 is capped at yellow), and several rules together still raise one level in total. A rule that would lower a verdict is not implemented, and `escalate` asserts it. **`verify_grounding` checks that every rule's quote is verbatim in its chunk file and its key is in the registry, and the demo server will not start otherwise.** Constraint 14 is enforced mechanically.

    | rule | profile fact + symptom | chunk | quote |
    |---|---|---|---|
    | R1 | diabetes + mild or vague | CP-ACS-002 | "Silent heart attacks are more common in older adults and in people who have high blood sugar or diabetes." |
    | R2 | age ≥ 70 + mild or vague | CP-ACS-002 | the same line. 70 is Viraj's cutoff; the corpus has no age number anywhere |
    | R3 | known CAD + chest symptoms on exertion, cap yellow | CP-ANG-002 | "Angina can be a warning sign that you are at a higher risk of having a heart attack." |
    | R4 | cancer or chemotherapy + pain on breathing | CP-PE-004, CP-PE-001 | "cancer and cancer treatments including chemotherapy and surgery" |
    | R5 | surgery ≤ 13 weeks + pain on breathing or leg | CP-PE-003, CP-PE-001 | "The chance of developing a blood clot is highest in the first 3 months after surgery and lowers with time." |
    | R6 | female + unexplained tiredness, **flag only** | CP-ACS-003 | "Feeling unusually tired for no reason, sometimes for days (this is more common in women)" |

    **R3, R4 and R5 were first cited to chunks that do not state them** (CP-ANG-001, CP-PE-002, CP-PE-004) and were re-keyed on Viraj's call. R4's original key was the P0003 error again.

    **When the model already said red, a rule whose conditions hold is still shown, as "supports this red",** Viraj's call. That matters because of the model's red bias. **Measured live 2026-09-19: the model said red in 6 of 6 rule cases, so every line read "supports", and a live raise happened once in 3 runs of the best candidate** (Grandpa, "Bit of a niggle in my chest": yellow raised to red by R2). The raising path is proven by fixtures and that one run, not by a reliable demo.

    **The layer leaves refusals alone, and that is its main limit.** It runs only on verdicts that are shown. **The 2026-09-19 sweep** was 18 mild or vague presentations on the profiles whose rules they target, 3 repeats each at temperature 0.2, 99 runs in all. The model said red in 85 of them. Of the 14 non-red verdicts, **11 cited nothing and were refused before the layer ran**. The 3 that were shown were all raised, and **no presentation raised 3 of 3**; the best was 1 of 3. The limit is the refusal gate, not the phrasing. Results: `06-demo/results/2026-09-19-escalation-sweep.txt`.

    **BUILT 2026-09-19, Viraj's call: a rule overrides a post-flight refusal only when its result is red.** It is `rescue_refusal` in `escalation.py`. A refused yellow that a rule raises goes out as a red through the never-withhold-red path: flagged as not grounded, with the rule's quoted line. A refused green that would only become yellow stays refused. **His reason: a refusal that hides a yellow the rules would raise is the same failure class as withholding a red.** None of the 7 recorded out-of-scope texts fires a rule on any adult profile, so the breadth risk is constructed rather than measured. It is recorded as an accepted fixture: Dad with "My shoulder aches a bit after the gym" is rescued if the model withholds a yellow. On the sweep's 99 runs the rescue takes raises from 3 to 10. **Verified live, both branches:** the S04 phrasing gave 3 withheld yellows that were rescued to red and 3 withheld greens that stayed refused.

    **The demo preset since 2026-09-19: "Indigestion (You and Mum)",** which is "A bit of indigestion after lunch, nothing much." **One click turns Compare on, sets You against Mum and sends**, so the whole beat is one tap at the desk. That side-by-side is beat 3, reframed on Viraj's call: **same symptom, two people.** Mum gets a red escalated by R1, with the rule line and its source; You gets refused, because the model cited nothing. One screen shows the profile layer and the refusal guard, and it held on every run on the 35-chunk corpus: **You refused 6 of 6, Mum escalated to red 3 of 3**, one a grounded raise citing CP-ANG-003 and CP-ACS-003 and two through the refusal rescue. On 22 chunks the same text came back green on Mum 2 of 3, which R1 lifts only to yellow, and a yellow that cites nothing stays refused. CP-ANG-003 lists "heartburn or indigestion" as an angina symptom, which is the likely reason the model now says yellow. Results: `01-data/eval/runs/2026-09-19-beat3-reframe-indigestion-pairs.txt`.

    **Why the beat is a red next to a refusal and not two verdicts.** The previous preset, "Feeling a bit sick and sweaty after dinner", escalated Mum 5 of 5, and one page comparison came back You YELLOW, Mum RED. That was the one-in-three outcome: on that text You is refused 2 of 3, on 22 and 35 chunks alike. Six more mild or vague texts, 3 runs each on You, came back refused or red every time. No You-versus-Mum pairing gives two different shown verdicts reliably, because the model cites nothing when it is reassured (Current state). `01-data/eval/runs/2026-09-19-stairs-and-pairing-screen.txt`, `06-demo/results/2026-09-19-rescue-preset-live.txt`.

    **Observed, not changed:** that compare run was rescued only because the model cited `"RETRIEVED CONTEXT: CP-ACS-003 (…)"`, a label in front of the key. The leading-key rule of constraint 9 drops it, as specified.

    **Symptom matching is lexical.** A miss means no escalation, and the model's verdict stands. Profile facts are structured. Python and demo only; `guards.ts` has no port.

16. **The steps shown must match the urgency that is SHOWN, not the one the model gave.** When the escalation layer raises a verdict, the model wrote its `next_steps` for its own lower verdict, and they then sit under a disposition that contradicts them. **Measured 2026-09-19** on the one-click comparison: Mum's RED banner, "Call emergency services now", above "Monitor symptoms; if chest pain, pressure, or worsening indigestion occurs, seek immediate care" and, in another run, "Follow up with primary care provider within 24 hours". It was on screen in every run of that beat, because R1 raises that case every time. This is app logic, like constraints 9 and 12; a prompt rule cannot hold it, because the model never sees the raised verdict.

    **A raise to red replaces the steps with the app's own:** "Call emergency services now.", "Do not drive yourself.", "Stay where you are." They are the app's words, like the disposition itself, so they carry no citation and need none. Viraj's wording and his call. `RAISED_RED_STEPS` in `06-demo/pipeline.py`.

    **A raise of any kind also strikes out the rationale**, added 2026-09-19 on Viraj's call, because the same contradiction reads worse in prose: a red bar above "no red flags present" and "do not meet emergency criteria" is the system arguing against its own verdict. The model wrote that Why for the verdict IT gave. Nothing replaces it: the rule line above the answer already says what raised it and quotes the chunk line that justifies it.

    **Nothing is hidden.** The rationale and the steps both render struck through, tagged "removed: written for a yellow", and they count in the removed total on the Checked line, same as every other guard removal. The rationale is shown whole, not clipped like a removed citation, because it is the model's entire reason. Verified live 2026-09-19: `06-demo/results/2026-09-19-copy-and-one-click.txt`, and the compare check in `06-demo/ui_check.mjs` asserts both.

    **Where the two rules differ, and why:** the rationale goes on any raise, to yellow or to red, because it always argues for the lower verdict. The steps are only replaced on a raise to red, because those three lines are red instructions and there is no equivalent set for a yellow, so **a raise that ends at yellow still shows the model's steps.** Python and the demo only; `guards.ts` has no port.

---

## Licensing: what may and may not ship

The corpus is redistributed inside the app, so this is distribution, not linking.

**Cleared (US government works, public domain):**
- MedlinePlus **health topic page summaries** only (`medlineplus.gov/<topic>.html`)
- NHLBI, NIDDK, NIMH, NINDS, CDC

**Cleared with conditions, regional add-on packs only (2026-09-19):**
- **WHO fact sheets** (`who.int/news-room/fact-sheets/...`). **CC BY-NC-SA 3.0 IGO**, from WHO's site-wide terms of use; the fact sheets themselves print no licence line, and the packs record that. **ShareAlike: chunking is adaptation, so any pack containing WHO text is CC BY-NC-SA as a whole.** **NonCommercial: such a pack may not ship in a commercial product**, which bears on the Seed Round pitch exactly as StatPearls' NC does. Attribution in WHO's own form: `[Title]. Geneva: World Health Organization; [Year]. Licence: CC BY-NC-SA 3.0 IGO.` **Licence is recorded PER PACK**, and **the base pack stays US government public domain: nothing WHO is ever appended to `01-data/citations.csv`.** Built as the `regional-india` and `regional-africa-ssa` overlay packs in `07-distribute/regional/`, frozen 2026-09-19.

**Excluded, do not add back:**
- **MedlinePlus Medical Encyclopedia** (`medlineplus.gov/ency/...`). A.D.A.M. content, licensed to NLM for MedlinePlus use only. Copyrighted. This is the trap, because the `/ency/` pages have the best clinical detail.
- **StatPearls.** CC BY-NC-ND 4.0. ND forbids derivatives and chunking is a derivative. NC separately conflicts with the Seed Round pitch.
- **Schmitt-Thompson Clinical Content protocols.** Commercially licensed, including to developers building RAG triage. The approach is usable, the text is not.
- **India MoHFW.** Viraj's check 2026-09-19: its sites carry inconsistent copyright policies and the main ministry site requires written permission. WHO covers the same ground under a licence that is actually stated.
- **AHA, Mayo, Merck Manuals, UpToDate, WebMD.** Copyrighted. Note MedlinePlus links out to AHA and Mayo; a `.gov` URL does not make the target public domain.

Every source needs publisher, URL, retrieval date and licence recorded. A citation without a retrieval date is not reproducible.

**The model licence needs legal review before any real distribution.** NVIDIA Nemotron Open Model License, clause 7: "You will indemnify and hold harmless NVIDIA from and against any claim by any third party arising out of or related to your use or distribution of the Works, Derivative Works thereof, or output from the Works or Derivative Works." In this app the output is a triage verdict. Accepted for the hackathon on 2026-09-19, not beyond it. Clause 3a requires giving recipients a copy of the licence; the model pack in `07-distribute/` ships it. NVIDIA's own LICENSE file on Hugging Face is empty; the text is from nvidia.com.

---

## Epics and dependency order

1. **Data foundation.** Source, chunk, key, embed. **Hard-blocks epic 2**, because pairs need real citation keys from real chunks.
2. **Training data.** ~500 pairs. No think blocks. **Top open item, 2026-09-18: chunk identity predicts the verdict.** In four conditions every surviving pair has the same verdict: CP-PANIC all green, CP-PLEU and CP-PNA all yellow, CP-PE all red. Constraint 14 cut exactly the contrast sets those conditions had, and tonight's cuts removed the only green CP-PNA pair. 40 pairs remain in `02-pairs/review/candidates-60.jsonl`, and seven more are flagged for rationales that credit a chunk with a line it does not contain. `02-pairs/review/FINDINGS-2026-09-18-night.txt` has all of it.
3. **Model pipeline.** QLoRA, merge, eval, GGUF, imatrix, Q4_K_M.
4. **Retrieval layer.** sqlite-vec, MiniLM, top-k into the prompt.
5. **App shell.** React Native, llama.rn, Whisper, TTS.
6. **Demo.** Four beats, on a **laptop web UI against llama-server**, with a phone screenshot as evidence. No live simulator inference: one completion in the simulator is 3 min 56 s in Release against about 40 s here, and a judge visit is about 5 minutes.
   1. **Symptom checker flow.** Free text in, retrieval, streamed generation.
   2. **Red triage result.** Urgency banner, red flags, next steps, disposition.
   3. **The guards firing, and profile escalation (constraint 15).** Family cards, a rule line under the verdict, and a side-by-side of two profiles, which took 86 s on CPU at `-np 2`, the two generations decoding together. **Reframed 2026-09-19: same symptom, two people**, the "Indigestion (Mum)" preset in compare mode. Mum's red, escalated by R1 with the rule line and its source, sits next to You refused because the model cited nothing. It held on every run measured (constraint 15), where the two-verdict version held one run in three. The guards beat replaced "family profile changes the answer", which was cut on 2026-09-17 because it did not work: both profiles returned red, since the base model returns red for everything. This beat shows three things that do work and are all real: a fabricated red flag dropped, follow-up questions cleared off a red, and an invented citation key refused by the expander.
   4. **Citation expander.** Click a key, get the real chunk text, publisher, URL and retrieval date.

   Built at `06-demo/`. Run `llama-server -m 03-model/base/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf --jinja -np 2 -ngl 0 -c 8192 --port 8080`, then `python 06-demo/server.py`, then open 127.0.0.1:8770. **`-np 2` since 2026-09-19** so the side-by-side's two generations decode together: 86 s against 112 s sequential at `-np 1`. `-c 8192` keeps 4096 tokens per slot. **Turn macOS Low Power Mode off for the demo:** it was on during that measurement, and turns on that contended with other load ran at 4 to 7 tok/s, against 8.8 on an uncontended one. **Grant Chrome the microphone on 127.0.0.1:8770 once before judging**, by tapping the mic button and clicking Allow. It is remembered per origin, and the alternative is a permission dialog in front of a judge inside a 5 minute visit.

   **VOICE INPUT, built 2026-09-19.** A mic button in the composer: tap to record, tap to stop, and **the transcript goes in the box as editable text and is never sent straight to triage.** A misheard symptom is a wrong verdict, so the person reads what was heard and fixes it first. Under the composer: "Heard in 0.5 s. Read it before you send", and "then edited" once they change it. 6 s of speech transcribes in about 0.5 s, 25 s in about 0.8 s, at 265 MB for the life of a subprocess that then exits; model load is 46 ms, which is why nothing is held resident. `POST /api/transcribe` returns text and an id and touches no conversation. The page resamples to 16 kHz mono itself, so the server needs no ffmpeg. **`heard` rides on the turn and the SOAP note says the symptoms were spoken, by whom transcribed, and whether the patient corrected it**, decided server-side by comparing what arrived against what was transcribed. Nothing reads it on the way to the model. `06-demo/voice.py`, `06-demo/static/js/voice.js`, `node 06-demo/ui_check.mjs voice OUTDIR [URL]`.

   **The microphone cannot work over `--lan` and is not worked around.** Confirmed by measurement: on a plain http address `navigator.mediaDevices` is undefined, not merely refused. The button is absent there with a reason. **Whisper invents sentences out of non-speech:** silence came back as "you" and a test beep as "Oh, my God. Oh, it can't get us back in the fight." Bracketed annotations are dropped and a peak floor of 0.01 refuses a dead microphone, but **a hallucination from real room noise is caught only by the person reading the box.** Results: `06-demo/results/2026-09-19-voice-live.txt`.

   **`--lan`, built 2026-09-19, so a phone on the same wifi can open the page.** `python 06-demo/server.py --lan` binds 0.0.0.0, prints the wifi URL, and says plainly that anyone on the network can read every assessment and add or delete people, because there is no password. **127.0.0.1 stays the default.**

   **A phone on the wifi is a SCREEN and proves nothing about running on a phone.** The model runs on the laptop. `/api/health` carries `remote` for a client that is not loopback, and the page words itself from it: the empty screen reads "the model runs on the laptop, not on this phone", the lamp reads "Model on the laptop, ready", and the SOAP note says the model ran "on the machine that wrote this note". **The phone screenshot is still the only claim this project makes about on-device inference**, and nothing in the page may imply otherwise. Checked over the wifi at 390x844 with touch: `06-demo/results/2026-09-19-phone-over-wifi.txt`, `node 06-demo/ui_check.mjs phone OUTDIR URL`.

   **Clinical export, built 2026-09-19.** `GET /api/conversations/<id>/soap.txt` renders a SOAP note from a SAVED assessment as plain text, linked under the last answer as "Download the SOAP note". It reads the saved JSON and the registry: no model call, no retrieval, nothing on the triage path, no new dependency, and one SOAP block per person so a comparison gives two. **O carries every guard removal with its reason**, because a clinician has to see what was taken out as well as what was kept; a raised verdict records the rule, its quoted chunk, and that the rationale and steps were replaced; an ungrounded red carries the not-grounded note in A; and the header names the model, the corpus sha256 and the prompt sha256 and says it is not a clinical record. `06-demo/soap.py`, example in `06-demo/results/2026-09-19-soap-note.txt`.

**Re-checked on the 35-chunk corpus 2026-09-19:** the four beats hold, and the Mum preset and the side-by-side behave as on 22 chunks. **"Tight chest on the stairs" regressed and was reworded, Viraj's call, instead of rolling the index back:** the old text retrieved and cited CP-PNA-002, a pneumonia risk-factor chunk, through a BM25 match on "going" and "down". The new text, "Tightness in my chest when I climb stairs or walk uphill. It goes away within a few minutes when I rest, same as the last few months.", retrieves CP-ANG-005, CP-ANG-009 and CP-ACS-005 and held 3 of 3 live, citing only those. **The preset itself was then CUT from the demo, 2026-09-19, Viraj's call:** it came back red like "Crushing chest pressure", so it duplicated the first beat. "Burning after a meal" went with it, because the green path it demos is usually refused (Current state: the model cites nothing when it is reassured). **Three presets remain, one per beat:** crushing chest pressure, sharp pain when breathing in, and Indigestion (You and Mum). The rewording above stands if the stairs text is ever wanted back. Build-log 2026-09-19. The 22-chunk index is `04-retrieval/corpus-22.db`.

Epic 5's llama.rn spike does **not** depend on epic 1 and should run in parallel.

---

## Current state

**Proven:** model loads and runs under llama-server on macOS; reasoning switches off via chat template with `--jinja`; grammar sampling via `--json-schema` holds the output shape; prefix caching removes prompt eval on follow-ups but not generation. Corpus pipeline runs end to end with exact word-piece counts. **Corpus frozen 2026-09-15, re-frozen the same day at 22 chunks**, mean 140 tokens, 9 red / 6 yellow / 6 green / 1 uncategorised. **Appended 2026-09-19 to 35 chunks**, 16 red / 12 yellow / 6 green / 1 uncategorised, mean 128: 13 symptom chunks from four NHLBI pages, Viraj's review, cutting causes, prevention and hospital tests. Unstable, microvascular and vasospastic angina are frozen **red** inside the yellow CP-ANG prefix through a per-chunk `category=` override in the review file, because angina at rest is the ACS pattern. The 22-chunk registry and index are kept as `01-data/citations.frozen-22.csv` and `04-retrieval/corpus-22.db`. The 0.25 scope floor behaves exactly as before on 35 chunks. Base GGUF relocated to `03-model/base/` and the CPU number measured. **It declines rather than invents:** given a case with `RETRIEVED CONTEXT = none` it returns `citations: []` and fabricates no key, measured 2026-09-17 under the format 3 prompt at sha `ca631a3d`. The same condition produced `CP-RISK-014` and `MED-ANTICOAG-007` under the earlier prompt, so this is a real change and it is worth saying at the desk.

**Voice input is proven on the laptop, 2026-09-19.** whisper.cpp transcribes into the composer end to end, 15 checks passing live (`node 06-demo/ui_check.mjs voice`), and the transcript is editable before it is sent. **Proven with a synthetic voice only:** every clip in the model-choice set is macOS `say`, so accuracy on a real voice at a noisy desk is unmeasured and will be worse. Viraj records the three presets before judging and base.en gets re-scored against small.en on that.

**Not proven:** never run on a phone; never run through llama.rn; `initLlama` has never been called; not fine-tuned. Whisper has never run under llama.rn or on a phone either. Architecture support for `nemotron_h` in llama.rn 0.12.9 is settled by source inspection, which is not a load.

**The QLoRA path is proven up to training, on Brev, 2026-09-19.** On an A6000, bitsandbytes turns every projection into Linear4bit, the Mamba2 `in_proj`/`out_proj` included, at 3.28 GB on the device. The model generates, and matches the bf16 output. LoRA attaches with exactly 50 matched modules (constraint 10). **It needs transformers 5.x and `trust_remote_code=False`**, because the repo's own modeling file hard-imports `mamba_ssm`. Nothing has been trained. Results are in `01-data/eval/runs/2026-09-19-brev-4bit-gate.txt`.

**The top open risk: discrimination. Located 2026-09-17, and it is the base model.**

Reasoning off, which is the shipping config, the model returns red for every case in the set, deterministically, across **four** prompt revisions. The decisive measurement is `01-data/eval/runs/2026-09-17-no-chunk-angina.txt`: yellow-angina with `RETRIEVED CONTEXT = none`, no corpus in the experiment at all, came back red twice, and the rationale it wrote unprompted says "complete resolution upon rest", "consistent with angina" and "symptoms resolved quickly". **It extracts the fact that makes the case a yellow and assigns red anyway.** So the failure is in category assignment, downstream of comprehension. Not retrieval, not grounding, not the prompt.

The corpus-bias explanation is ruled out as the driver, though not as a contributor: with the prefix cache off, `--chunks red-only` and `--chunks matched` produce **verdict-identical** runs in both reasoning modes. Feeding cardiac chunks to all five cases moves nothing. A green-rich corpus has never been tested, so corpus composition is narrowed, not cleared.

**Do not conclude the model can only say red.** Reasoning off plus `GREEN_CRITERION` returns `red / green / green / red / green`, stably. It emits all three labels. What nothing has done is condition the label on the case: the instruction that freed green on green-gerd also dragged the known-CAD case to green, which is the dangerous direction. **The category head is movable but not case-sensitive.** The adapter therefore has something to act on, and what it must teach is conditioning, not vocabulary.

**This kills the original epic 2 bet.** Pairs were scoped to teach output shape on the premise that the model already reasons. It reasons and then mislabels. The pairs have to teach category assignment itself, in the shipping config, and nothing before Saturday tests whether 300 is enough. **Prompt iteration is closed**; four revisions moved zero verdicts. See build-log 2026-09-17.

**The model cites nothing when it is reassured, so a non-red verdict is usually refused.** Measured 2026-09-19 over the 50 live answers saved that day: 19 of 25 non-red answers came back with no citation that resolves, usually an empty list and sometimes a label in front of the key that constraint 9 drops. None of the 25 reds did. A yellow or green that cites nothing is refused (constraint 13), and a red is never withheld, so the reds reach the screen with their sources and the calm answers mostly do not. It is the same root cause as the red bias, the untuned base model, and it is why there is no reliable two-verdict comparison: the reassured side of a pair is usually the refused side (constraint 15, beat 3). **Say this at the desk before a judge finds it.**

**The eval set cannot measure the fine-tune.** Four scored cases and one probe, 1 red / 2 yellow / 1 green. At that size a fine-tune that fixes yellow-angina and breaks green-gerd scores the same as one that does nothing. The green side is a single case and every variant gets it wrong. More green cases, chest wall pain especially, are needed before the adapter can be judged. Viraj's call, it needs clinical judgment.

**Real-world base rate:** roughly 7% red, 34% yellow, 59% green (IITT validation study, ANGAU Memorial Provincial Hospital, Papua New Guinea; ~70% sensitivity for time-critical illness). An eval set that is mostly red does not resemble use.

---

## Known design gaps

**IITT categories assume a facility.** Red, yellow and green are emergency department zones with time-to-care targets. WHO states outright that a triage category is not a diagnosis. Our user has no ED, so the app needs an explicit translation layer:

| IITT | Disposition |
|---|---|
| Red | Call emergency services now |
| Yellow | Be seen today |
| Green | Self-care, and the signs that change the answer |

This is the page's wording, word for word (`DISPOSITION` in `06-demo/static/js/answer.js`). The table was changed to match the page on 2026-09-19, Viraj's call, because the page is what a person reads.

**The green side is under-sourced.** Government health sites cover what kills people, so costochondritis and chest wall pain are thin. Same side the model has no evidence on. Both problems point the same direction.

**Seven of nine conditions have no green chunk at all, recorded 2026-09-19 at 35 chunks.** Heart attack, angina, blood clots, pneumonia, heart inflammation and pleurisy are all red or yellow, and the chest pain overview is uncategorised. Only GERD and panic have green chunks, and nothing else. For those seven, no chunk supports a green, so retrieval cannot ground one whatever the model does. Viraj's finding. Noted, not being fixed now. Per condition: `01-data/eval/runs/2026-09-19-green-by-condition.txt`. It does not account for all of the red bias: the no-chunk angina probe came back red with no corpus at all (Current state).

**No negative discriminators anywhere in the corpus.** Nothing states that pain which is positional, reproducible on palpation, or worse on inspiration argues against a cardiac cause. Those are what rule cardiac out. Consumer health sites do not teach people what is benign.

**Device memory.** 4B at Q4 is ~3 GB resident. Target devices often have 4 to 6 GB total shared with the OS. This is a does-not-run problem, not a slowness problem, and the answer is distillation to 1 to 1.5B on the roadmap. Do not claim a speed multiplier for distillation; nothing has been measured.

---

## Working conventions

- **Nothing counts as ready until it has run once.** Downloaded is not verified.
- Go one step at a time and report back. Do not batch multiple epics into a single pass.
- Append findings to `build-log.md` section 7 with a date. That file is how this project survives a context reset.
- **Every eval result is written to disk before the next task begins. Nothing lives only in context.** Redirect the run to `01-data/eval/runs/<date>-<what>.txt` with a header saying the date, the config and the build, then move on. A whole session was rebuilt from that directory on 2026-09-17 with no other state, and it worked. The one place it failed is the lesson: the harness had printed `red_flags=1`, a count with no text, so answering "was that finding actually in the patient" meant standing the server back up and re-running every config. **Save the content, not the summary.** A number you can recompute is not worth a re-run.
- Do not overstate that a question is closed. If something is a bet, say it is a bet.
- Do not use em dashes in anything written for Viraj.
- Flag anything that sounds AI-generated in prose so he can rewrite it in his own voice.

---

## Immediate next actions

1. **Relocate the base GGUF** into `03-model/base/` with `--local-dir`, not a symlink into the HF cache. `llama-imatrix` and `llama-quantize` both need it there in epic 3. Record the SHA256 in `build-log.md`.
2. **Get the CPU number.** Final config (reasoning off, schema on, prompt rules) with `-ngl 0`. Never measured. It is the demo number.
3. **Finish epic 1.** Review chunks, then Viraj freezes.
4. **llama.rn load spike**, in parallel. Check the vendored llama.cpp commit supports the Nemotron 3 Nano architecture before anything else, because if it does not, `initLlama` fails and the binding choice is dead.