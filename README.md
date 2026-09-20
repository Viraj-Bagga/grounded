# Triage

Offline medical triage that runs on the device. Describe chest pain in plain
language and get a WHO urgency category back, with what to do, why, and the
government sources it read.

No internet. No API key. The model, the corpus and the retrieval index all sit
on the machine.

Built solo for SteelHacks XIII at Pitt, 19 to 20 September 2026.

> **Not a medical device.** This is a hackathon prototype. It has no clinical
> validation, no regulatory approval and no users. Do not use it to make a real
> decision about a real person.

---

## The problem it is aimed at

Most triage tools assume a clinic at the other end, and a network to reach it.
This one assumes neither.

The target is care where there is no clinic and no signal: a health worker in
a village, or a person at home deciding whether the chest pain their mother has
is worth a long journey. That framing drove the technical choices. It is why the
model is 4B and not 70B, why the roadmap goes to a *smaller* model rather than a
bigger one, and why everything is measured on CPU.

---

## What it actually does

A person types or speaks what is happening. The app retrieves three chunks from
a frozen corpus of government health sources, builds a prompt, and the model
returns structured JSON: urgency, a reason, red flags, next steps, citation
keys, follow-up questions.

Then the app takes that output apart.

That second half is the interesting part. A small model left alone will invent a
citation key, copy a symptom out of a source document and attribute it to the
patient, tell someone to take a cardiac drug, and answer confidently about a
condition it has never read a word about. All four were measured here, not
imagined. Each one has a guard in app logic that removes it and shows on screen
what was removed and why.

The rule throughout: **the model proposes, deterministic code disposes.** A
prompt instruction cannot hold a safety property, because the next sampling run
can ignore it.

---

## The guards

These run on every answer. Each came from something the model actually did.

**Citation keys are checked against the registry.** With no sources in context
the model returned `CP-RISK-014` and `MED-ANTICOAG-007`. Neither exists. Any key
not in `citations.csv` is dropped before the answer renders, so a judge clicking
a source never hits a dead one.

**Red flags must be grounded in the case text.** Given a pleuritic case whose
text mentions neither, the model returned `red_flags: ["fast heartbeat",
"fever"]`. Both strings are lines in the source chunk it was handed. It had
copied findings out of the document and asserted them as the patient's own. This
is worse than an invented key, because a fabricated finding reads exactly like a
real one. Findings now come only from the case text. Retrieved sources supply
criteria, never findings.

**Next steps never instruct a medication.** The model produced "Administer
nitroglycerin if prescribed and available." Nitroglycerin drops blood pressure
and is contraindicated in several presentations this app cannot rule out,
because it has no vitals and no exam. Any step that directs someone to take,
give, apply or dose a drug is removed. "Bring your medications" survives.
"Chew aspirin" does not.

**Out-of-scope questions are refused, not triaged.** The corpus is chest pain and
nothing else. Asked about stomach pain and a late period, the model produced a
reassuring non-urgent verdict with zero citations. That presentation includes
ectopic pregnancy. A system with no knowledge of a condition had produced a
calm answer about it, which is the most dangerous output this project made.
Refusal now happens on three independent conditions: categorical exclusions
before generation, a relevance floor, and an empty-citation check afterwards.
A refusal is drawn in neutral grey and never looks like a fourth, milder
category.

**A profile can raise urgency and never lower it.** Six rules read structured
facts from a household profile. Diabetes plus vague symptoms raises, because
silent heart attacks are more common in people with diabetes. Each rule quotes
the line from the source that justifies it, verbatim, and the server refuses to
start if a quote has drifted from its chunk.

**The steps shown must match the urgency shown.** When a rule raises a verdict,
the model wrote its steps for the lower one. Leaving them produces a red banner
above "monitor symptoms and follow up within 24 hours". Those get replaced, and
the originals stay on screen struck through and labelled.

Nothing is hidden. Every removal renders in place with its reason, and the
answer carries a count.

---

## The model

Nemotron 3 Nano 4B, fine-tuned with LoRA and quantised to Q4_K_M at 2.84 GB.

It is not a dense transformer. It is `nemotron_h`, a hybrid: 42 blocks split 21
Mamba2, 4 attention, 17 MLP, with attention only at blocks 12, 17, 24 and 32.
That was verified three ways before anything was trained, and it invalidated the
original adapter plan. The standard target list includes `gate_proj`, which this
architecture does not have. PEFT does not error on a target that matches
nothing, so the run would have looked clean and trained the wrong thing.

Final targets: `q_proj`, `k_proj`, `v_proj`, `o_proj`, `up_proj`, `down_proj`.
Rank 16, alpha 32, 2 epochs, 120 pairs, on one A6000.

Attention is only 3.8% of the parameters and is deliberately kept, because
copying a citation key verbatim out of a retrieved chunk is in-context copying,
and that lives in attention heads. There are four attention blocks in the whole
model. Those are the ones that had to learn it.

The Mamba2 mixers are 41.7% of the parameters and are deliberately *not*
targeted. With 120 examples, more trainable parameters buys overfitting rather
than capability.

It ended up being LoRA rather than QLoRA, and that was forced. The Mamba2 mixer
needs fused kernels or training does not fit on a 48 GB card at all: 47.29 GiB
peak with the PyTorch fallback against 21.29 GiB with the kernels. But the fused
kernel multiplies the projections itself, so bitsandbytes' packed 4-bit weights
fail on shape. Kernels or 4-bit, not both.

### What the fine-tune changed

Scored on a held-out set of 22 cases frozen before training, 3 runs per case.

| | base | tuned |
|---|---|---|
| correct, majority of 3 | 45.5% | **81.8%** |
| yellow cases correct | 3/19 | **21/21** |
| answers citing nothing that resolves | 9/33 | **0/53** |

Yellow is the whole result. The base model returned red for almost everything,
including cases where its own written reasoning had already extracted the fact
that made it a yellow. It understood the case and then mislabelled it.

The second row matters as much. The base stopped citing sources when it was
reassured, so calm answers had nothing behind them and the empty-citation guard
refused them. That is now zero.

---

## Sources and retrieval

35 chunks, chest pain only, from US government sites. Every chunk carries a
publisher, a URL and the date it was fetched. Citation keys are frozen: once a
key exists, it never changes, because training pairs reference it.

Retrieval is sqlite-vec with all-MiniLM-L6-v2, top 3, blended with BM25.

Chunks are capped at 256 word-pieces because that is where MiniLM truncates.
Anything longer is silently invisible past the cut, so oversized chunks are
rejected rather than trimmed.

Chunk size is also a latency decision. Prompt eval runs at 30 to 32 tokens per
second on CPU, so every 100 tokens of retrieved text costs about 3.1 seconds on
a cold turn.

---

## Field and base

A health worker triages offline in a village and comes back to a clinic. The
caseload syncs to a base device.

- **Caseload** at `/queue`. A list to work down: add someone with a note, assess,
  mark seen.
- **Sync** is one direction only. Nothing is edited at base and nothing is
  pushed back, so there is no conflict to resolve and none is implemented.
- **Base** runs as its own process on its own port, out of its own data
  directory, and imports nothing from the triage path. No model, no retriever,
  no guards. If base breaks, the field app still triages. It also means base can
  run on a second device, which is how the offline claim gets staged honestly:
  base on a phone, and the laptop's wifi genuinely off.
- **The register** is a supervisor's screen. How many assessed, how many red,
  which are outstanding, which device each came from.

Sync integrity is the distribution node's rule pointed the other way. A bundle
claims a sha256 over the canonical JSON, and base recomputes it from the bytes
that actually arrived. A mismatch is refused outright, not stored with a
warning. The digest is also the identity, so a resend is a no-op and a flaky
link is safe.

---

## Distribution

Packs reach a device that has no internet from a node on the same network: a
laptop or a Raspberry Pi at a clinic, which needs no internet itself.

The node verifies before it advertises. Every file is hashed against its
manifest before its pack is listed, and again whenever the file changes on disk.
A pack with an altered file is withdrawn from the index rather than served, so a
failing SD card is caught before a phone spends 2.84 GB downloading a model that
will fail its hash.

The client hashes every file from disk after downloading it, recomputes the pack
digest from the files, and writes the manifest last. The manifest existing is
the only definition of installed.

Regional add-on packs exist for India and Sub-Saharan Africa. They are layered
on the base corpus, never swapped for it, and they are not wired into retrieval.
Selecting a region changes what the page says about emergency numbers and
nothing else.

---

## Voice

whisper.cpp with `ggml-base.en-q5_1`, 57 MB, on CPU. Six models were measured on
13 clips before choosing, then re-scored on a real recorded voice.

The transcript goes into the composer as editable text. It is never sent
straight to triage. A misheard symptom is a wrong verdict, so the person reads
what the system heard and fixes it first.

Loading the model costs 46 ms against 265 MB resident, so it is not held in
memory. One process per transcription, and the memory is gone when it returns.
Six seconds of speech transcribes in about half a second.

Two things worth knowing. Whisper invents confident sentences out of non-speech:
silence came back as "you", and a test tone came back as a full sentence about
computer cooling. There is a loudness floor to catch a dead microphone, but a
hallucination from room noise is caught by the person reading the box, which is
the design. And browsers only allow microphone access on a secure origin, so
voice does not work when the page is opened over a plain address on the wifi.
The button is absent there with a reason rather than present and broken.

---

## Running it

Needs Python 3.9+, a `llama.cpp` build, and the GGUF.

```bash
# 1. the model
llama-server -m ./03-model/base/TUNED-120pairs-imatrix-Q4_K_M.gguf \
  --jinja -np 2 -ngl 0 -c 8192 --port 8080

# 2. the field app, then open http://127.0.0.1:8770
python 06-demo/server.py

# 3. optional: the base device
python 06-demo/base_server.py          # http://127.0.0.1:8781

# 4. optional: the distribution node, for the Regions page
python 07-distribute/server.py         # http://127.0.0.1:8790
```

`-ngl 0` is deliberate. CPU is the honest condition for a phone, so every
latency number in this repo is a CPU number.

`--lan` on either server binds to the network so a phone can open the page. It
prints a warning that anyone on the network can read every assessment, because
there is no password.

Voice needs `bash 03-model/whisper/build.sh` once. It builds whisper.cpp from
source rather than from Homebrew, because the Homebrew formula would upgrade
llama.cpp and ggml, and every measurement here was taken on the installed
versions.

The front end is static HTML, CSS and vanilla JavaScript with no build step and
nothing from a CDN. The fonts are self-hosted. It has to work with the laptop
offline.

---

## Measured on an M4 MacBook Air, CPU only

| | |
|---|---|
| prompt eval | 30 to 32 tok/s (about 72 with Low Power Mode off) |
| generation | 9.5 to 10 tok/s (about 20 with it off) |
| first turn | 15 to 55 s |
| follow-up | 7 to 25 s |
| two profiles side by side | 86 s, both decoding together (41 s with it off) |
| transcription | 0.5 s for 6 s of speech |
| model on disk | 2.84 GB, about 3 GB resident |

Follow-ups are fast because the prompt prefix is byte-identical, so llama.cpp's
cache hits: prompt eval on one measured turn went from 51,578 ms to 246 ms.
Retrieval is deliberately not re-run on a follow-up, since that would throw the
saving away.

---

## Limitations

**An under-triaged heart attack, unresolved.** One held-out case, HE01, is
textbook ACS and should be red. With chunks chosen by retrieval, the tuned model
returns yellow 3 times out of 3. The base model got it red 3 out of 3. With the
correct chunks supplied directly it is red 3 of 3, so this is retrieval handing
it something the tuned model reads down, not the fine-tune losing ACS. It is the
one error class this whole project exists to avoid, and it is invisible in the
81.8% headline. It is not fixed.

**The eval set is small.** 22 cases. A change that fixes one condition and
breaks another can score the same as one that does nothing.

**The green side is under-sourced.** Government health sites cover what kills
people, so chest wall pain and costochondritis are thin. Seven of nine
conditions have no green chunk at all, which means retrieval cannot ground a
green for them whatever the model does. There are also no negative
discriminators anywhere: nothing in the corpus states that pain which is
positional or reproducible on palpation argues against a cardiac cause, and
those are what rule cardiac out.

**It has never run on a phone.** The demo is a laptop web UI. One completion in
the iOS simulator took 3 minutes 56 seconds against about 40 seconds on the
host, so the simulator was abandoned as a demo surface. The React Native binding
has been checked by source inspection but never loaded. The phone appears as a
screenshot and nothing claims more than that.

**Device memory is a real limit.** 4B at Q4 is about 3 GB resident, and target
devices often have 4 to 6 GB shared with the OS. That is a does-not-run problem
rather than a slowness problem. The answer is distillation to 1 to 1.5B, which
is on the roadmap and has not been measured.

**Chest pain only, English only, one voice tested.**

**The guards are lexicons, and a lexicon has holes.** The medication guard misses
a pronoun: "do not stop your medication; take it as prescribed" names no drug in
its second clause. The grounding guard knows 20 findings and treats its own
count as a floor, not a total.

---

## Sources and licensing

Everything in the corpus is redistributed inside the app, so this is
distribution and not linking. Every source was checked before anything was
fetched.

**Included.** MedlinePlus health topic page summaries, NHLBI, NIDDK, NIMH,
NINDS, CDC. US government works, public domain.

**Regional packs only.** WHO fact sheets, CC BY-NC-SA 3.0 IGO. Chunking is
adaptation, so ShareAlike makes any pack containing WHO text CC BY-NC-SA as a
whole, and NonCommercial means such a pack cannot ship in a commercial product.
That is recorded per pack. The base corpus stays public domain and nothing from
WHO is ever appended to it.

**Deliberately excluded.** The MedlinePlus Medical Encyclopedia is A.D.A.M.
content licensed to NLM for MedlinePlus use only, and it has the best clinical
detail on the site, which makes it the trap. StatPearls is CC BY-NC-ND, and ND
forbids derivatives, which chunking is. Schmitt-Thompson protocols are
commercially licensed, including to developers building exactly this. AHA, Mayo,
Merck, UpToDate and WebMD are copyrighted, and a `.gov` page linking to one does
not make the target public domain.

The model is under the NVIDIA Nemotron Open Model License. Clause 7 puts
indemnity on the user for output from the model, and in this app the output is a
triage verdict. That was accepted for a hackathon and needs legal review before
anything else.

---

## Repo

```
01-data/        corpus pipeline: fetch, chunk, freeze, the citation registry
02-pairs/       training pairs, the guards, the escalation rules
03-model/       LoRA config, training, the conversion chain, GGUFs, whisper
04-retrieval/   sqlite-vec index and the hybrid retriever
05-app/         React Native spike
06-demo/        the field app, the base device, the sync
07-distribute/  the distribution node, the client, the packs
build-log.md    every decision and measurement, dated
claude.md       project constraints
```

`build-log.md` is the honest record. It has the failures in it as well as the
results, including the ones that were embarrassing.

---

## Tracks

Beyond the Chatbot (NVIDIA), Seed Round (Pear VC / Afore), Cold Start.
