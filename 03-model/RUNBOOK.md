# Epic 3 runbook — base model conversion chain

Written 2026-09-18 from an actual run on the M4, no training involved. Every
command below was executed. Every trap below was hit.

**What this proves.** `nemotron_h` converts, calibrates and quantizes, and the
rebuilt Q4_K_M is behaviourally identical to the artifact that has been demoed
against all week: 5 of 5 matching verdicts on `format3_probe.py`, including
reproducing the three known failures. See
`01-data/eval/runs/2026-09-18-rebuilt-imatrix-q4km.txt`.

**What this does NOT prove.** Anything about a fine-tuned model. No adapter was
trained or merged. That is section 8 and it has not been run.

---

## The one-screen version

Everything below is detail. If the machine is working and you just need the
chain, it is this, run from the repo root:

```bash
python /tmp/llama.cpp/convert_hf_to_gguf.py 03-model/hf-bf16 \
  --outfile ./03-model/base/f16.gguf --outtype f16          # 53 s

#   >>> GATE: load f16.gguf and make it say something. Do not skip. <<<

llama-imatrix -m ./03-model/base/f16.gguf \
  -f 03-model/imatrix/calibration.txt \
  -o ./03-model/imatrix/imatrix.dat --chunks 32 -ngl 0 -c 512            # 9 min

llama-quantize --imatrix ./03-model/imatrix/imatrix.dat \
  ./03-model/base/f16.gguf ./03-model/base/final-Q4_K_M.gguf Q4_K_M 8    # 49 s

llama-server -m ./03-model/base/final-Q4_K_M.gguf --jinja -np 1 -ngl 0 -c 4096
python 01-data/eval/format3_probe.py                                     # 5 min
```

Three things in there are load-bearing and look like style:

1. **`--outtype f16`, never `q8_0`.** Section 3.
2. **The leading `./` on every path.** Section 5.
3. **The gate after conversion.** Section 3.1.

---

## 0. Before you start: disk

This is the thing that will stop you, not the model.

| artifact | size |
|---|---|
| HF BF16 weights, single unsharded file | **7.4 GiB** |
| F16 GGUF | 7.4 GiB |
| Q4_K_M GGUF, the output | 2.6 GiB |
| imatrix file | 2.1 MiB |
| llama.cpp shallow clone | 209 MiB |

Peak is **weights plus conversion output held at once**, so F16 needs about
**14.8 GiB free**.

**`df` under-reports what you can get back.** `xcrun simctl shutdown all`
released several GiB that `df` had been counting as used. If you are close, shut
the simulators down before concluding you have no room.

**Do not choose Q8_0 to save disk.** That was tried here, because F16 did not fit
at the time, and it cost the whole afternoon. Section 3 explains. Free space
instead; the peak is transient.

**Only F16, the HF weights and the imatrix file are worth keeping.** The Q4_K_M
regenerates from F16 in 49 seconds. The imatrix is 2.1 MiB and is the expensive
one at 9 minutes, so it is pure profit to keep. Any Q8_0 lying around is scratch
and can go; section 4 explains why you do not need one at all.

---

## 1. Tooling

Homebrew's `llama.cpp` ships **binaries only**. There is no converter in
`/opt/homebrew`. You need a source checkout for the Python side:

```bash
cd /tmp && git clone --depth 1 https://github.com/ggml-org/llama.cpp.git
```

**The converter is a 312-line wrapper.** Model classes live in `conversion/`, so
`grep Nemotron convert_hf_to_gguf.py` returns nothing and looks like the
architecture is unsupported. It is not. Resolve through the registry:

```bash
python -c "
import sys; sys.path[:0]=['/tmp/llama.cpp','/tmp/llama.cpp/gguf-py']
from conversion import get_model_class
print(get_model_class('NemotronHForCausalLM'))"
# -> <class 'conversion.nemotron.NemotronHModel'>, subclasses GraniteHybridModel
```

### Trap: the requirements file downgrades torch

```bash
pip install -r /tmp/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
```

This **downgraded torch 2.14.0 to 2.11.0 and numpy 2.5.3 to 2.2.6**, pulling a
fresh 400 MiB package. On a tight disk that alone caused `ENOSPC` at 82% of the
first conversion. Install requirements **before** downloading the weights.

Both downgrades are deliberate on llama.cpp's part, not accidents. `torch==2.11.0`
is pinned in the convert requirements; `numpy~=2.2.6` is pinned across its
sibling requirements files. Let them win. Do not "fix" the versions afterwards.

### Exact versions that produced the working artifact

```
python            3.14.7
numpy             2.2.6      <- llama.cpp pins numpy~=2.2.6. Keep it.
torch             2.11.0     <- llama.cpp pins torch==2.11.0. Keep it.
transformers      4.57.6
safetensors       0.8.0
sentencepiece     0.2.2
protobuf          4.25.9

llama.cpp clone    HEAD 4fea119                              (the converter)
llama.cpp binaries 0.4.0, build 10809, commit 5266f24da      (Homebrew, runtime)
```

**Converter and runtime are different revisions and that turned out to be fine.**
The skew was a live suspect during debugging and was **eliminated**: both the
clean F16 and the corrupt Q8_0 were written by the same converter and read by the
same binaries, and only one was broken. numpy was eliminated the same way. If
something breaks on a fresh machine, suspect the outtype first, not the versions.

---

## 2. Download the weights

**Do not use `snapshot_download`.** It ran at 1.42 MB/s and then Xet stalled
completely: two chunk files frozen at exact byte counts, a third at zero, process
alive, nothing moving, indefinitely. `hf_transfer` is deprecated in
`huggingface_hub` 0.36 and forwards to `HF_XET_HIGH_PERFORMANCE`, which stalls
the same way.

Plain HTTP works, **8.12 MB/s, about 14 minutes**:

```bash
mkdir -p 03-model/hf-bf16 && cd 03-model/hf-bf16
BASE=https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16/resolve/main
curl -L -C - -O $BASE/model.safetensors
for f in config.json generation_config.json tokenizer.json tokenizer_config.json \
         special_tokens_map.json configuration_nemotron_h.py modeling_nemotron_h.py; do
  curl -sL -O $BASE/$f
done
```

`-C -` resumes, so a dropped connection is not a restart.

### Verify before converting

```
model.safetensors   7,947,142,640 bytes   sha256 starts 55d4e2519456c4a9
263 tensors, all BF16
config.json: architectures ['NemotronHForCausalLM'], model_type nemotron_h,
             num_hidden_layers 42,
             hybrid_override_pattern M-M-M-MM-M-M*-M-M*-M-M-M*-M-M-MM*-MMM-M-M-
```

**Keep these weights.** They were deleted once here to free space and it cost a
15 minute re-download the moment a hypothesis needed retesting.

---

## 3. Convert to GGUF, at F16

```bash
python /tmp/llama.cpp/convert_hf_to_gguf.py 03-model/hf-bf16 \
  --outfile ./03-model/base/nemotron3-nano-4b-F16.gguf \
  --outtype f16
```

**Measured: 53 seconds, exit 0, 263 tensors, 7.4 GiB, zero warnings.**

### `--outtype q8_0` SILENTLY PRODUCES A BROKEN MODEL

This cost an afternoon and an earlier draft of this runbook told you to ignore
the symptom. Read this section before deciding to save disk.

Both outtypes exit 0. The Q8_0 path emits these:

```
RuntimeWarning: overflow encountered in divide        gguf/quants.py:386
RuntimeWarning: invalid value encountered in subtract gguf/quants.py:47
RuntimeWarning: invalid value encountered in cast     gguf/quants.py:392
```

`invalid value` is numpy for NaN, and casting NaN to int8 is how you get
uniformly corrupt weights. That GGUF **loaded, reported the correct architecture,
and quantized to within 320 bytes of the known-good artifact.** Then it generated
`FoundationFoundationFoundation...` until it hit the token limit.

**Every step reported success. Nothing errored. The model was garbage.** The only
signal before generation was three numpy warnings that look like noise.

Isolated with three runs: with imatrix, broken. Without imatrix, broken. Q8_0
straight to Q4_K_M, broken. F16 through the identical chain, clean. The bug is
the Python Q8_0 packing path in `gguf/quants.py`. F16 is a dtype cast that never
enters that code.

**If you need a Q8_0, make it with `llama-quantize` from the F16, not with the
converter.** The C++ quantizer is a different implementation and it is fine.
That is exactly what section 4 does.

Genuinely harmless output, by contrast:

- `WARNING: Duplicated key name 'tokenizer.ggml.add_bos_token', overwriting`
- A block of Jinja chat-template lines echoed to stdout

Success line: `Model successfully exported to ...`.

### 3.1 GATE: prove the F16 generates before spending 9 minutes on imatrix

Do not carry an unverified conversion into calibration. The imatrix run is the
long pole and a corrupt input wastes all of it.

```bash
llama-server -m ./03-model/base/nemotron3-nano-4b-F16.gguf \
  --jinja -np 1 -ngl 0 -c 4096 --port 8080
curl -s localhost:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "messages":[{"role":"user","content":"Reply with exactly: OK"}],
  "max_tokens":16, "temperature":0,
  "chat_template_kwargs":{"enable_thinking":false}}' | python -m json.tool
```

**Pass looks like:** the content is `OK`, and `finish_reason` is `stop`.
**Fail looks like:** one token repeated until `max_tokens`, and `finish_reason`
is `length`. If it fails, stop here. The problem is conversion, and nothing
downstream will fix it.

Split the decision cleanly: **if F16 is clean, conversion is proven, so any later
corruption is the quantizer's fault, not the converter's.**

---

## 4. imatrix

`llama-imatrix` measures per-tensor activation importance and decides where
Q4_K_M spends its bits.

**Feed it the F16 directly. Do not build a Q8_0 intermediate.**

```bash
llama-imatrix -m ./03-model/base/nemotron3-nano-4b-F16.gguf \
  -f 03-model/imatrix/calibration.txt \
  -o ./03-model/imatrix/imatrix.dat \
  --chunks 32 -ngl 0 -c 512
```

**Measured: 65.4 s per pass, about 9 minutes for 32 chunks. Output 2.1 MiB.**

The actual run on 2026-09-18 went through a `cpp-Q8_0.gguf` intermediate, and
**that step was unnecessary.** It was inherited from the corrupt chain, where the
Q8_0 came from the converter, and never questioned once F16 became the source.
Verified after the fact: `llama-imatrix` loads the F16 and returns a normal PPL.
Skipping it saves 24 s and **3.9 GiB of peak disk**, which is the one resource
section 0 says will actually stop you.

If you do want a Q8_0 for some other reason, make it with `llama-quantize` from
the F16, never with the converter. Section 3 explains why.

### Trap: the output is GGUF now, whatever you name it

```
save_imatrix: saving imatrix using GGUF format with a different suffix than .gguf
W  if you want the previous imatrix format, use --output-format dat
```

This build writes imatrix files in **GGUF format regardless of the `.dat`
extension** you ask for. `llama-quantize` from the same build reads it without
complaint, so the warning is cosmetic **here**. It stops being cosmetic if
anything else ever has to read that file, in which case pass
`--output-format dat`. Do not assume a `.dat` name means legacy format.

### Do not calibrate on wikitext

This model sees a fixed system prompt, a structured case block, retrieved chunk
text, and emits JSON. Almost none of that is prose, and importance estimated on
prose describes a different workload.

`03-model/imatrix/calibration.txt` is 116 KiB built from the real thing: the
shipping system prompt, all 22 frozen chunks, and every pipeline-test pair
rendered as the model sees it, human turn and JSON answer.

### The PPL line is a free health check on the model, not a verdict on the corpus

`llama-imatrix` prints a final perplexity. Use it.

| model fed to imatrix | chunks | final PPL |
|---|---|---|
| Python-converted Q8_0, the corrupt one | 32 | **390,043** |
| `llama-quantize` Q8_0 from the clean F16 | 32 | **5.9045 +/- 0.15151** |
| F16 itself | 1 | 22.3351 +/- 4.74472 |

The first two are the comparison that matters: same calibration file, same
binary, same 32 chunks. The F16 row is a 1-chunk smoke test and is **not**
comparable to them, which the +/- 4.74 interval makes plain. Do not read it as
the F16 scoring worse.

**A five-figure PPL means the model is broken, not that the calibration text is
wrong.** That distinction cost
real time here: 390,043 was first read as evidence the domain-matched corpus was
a bad choice against wikitext, and it was not. At 5.90 the model finds this
corpus highly predictable, which retires the question.

If you see PPL in the hundreds of thousands, go back to section 3.1.

### Confirm the imatrix was actually applied

There is **no banner in the quantize log on this build**, so absence of one
proves nothing. The provenance is written into the output GGUF instead:

```
quantize.imatrix.file          = 03-model/imatrix/imatrix-f16path.dat   <- name from the 09-18 run
quantize.imatrix.dataset       = 03-model/imatrix/calibration.txt
quantize.imatrix.entries_count = 92
quantize.imatrix.chunks_count  = 32
```

**92 is full coverage for this architecture** and worth checking, because a
partial number would mean the calibration missed whole blocks:

| block type | count | tensors each | total |
|---|---|---|---|
| attention, layers 12/17/24/32 | 4 | q, k, v, o | 16 |
| MLP | 17 | up, down | 34 |
| Mamba2 | 21 | in_proj, out_proj | 42 |
| | | | **92** |

The Mamba2 mixers are calibrated even though QLoRA deliberately does not train
them. Those are unrelated decisions; quantization covers everything, training
targets six modules.

---

## 5. Quantize to Q4_K_M

```bash
llama-quantize --imatrix ./03-model/imatrix/imatrix.dat \
  ./03-model/base/nemotron3-nano-4b-F16.gguf \
  ./03-model/base/FINAL-imatrix-Q4_K_M.gguf Q4_K_M 8
```

**Measured: 49 seconds, 2,837,073,184 bytes.**

### TRAP: a path that starts with a digit breaks argument parsing

`llama-quantize` takes an optional trailing thread count and parses positionals
with `stoi`. **`03-model/...` parses as the number 3.** The positionals shift and
you get:

```
error: invalid nthread '03-model/base/...'
```

which reads like a thread-count problem and is not. It is the **output path**
being eaten as an integer.

**Every directory in this repo starts with a digit** (`01-data`, `02-pairs`,
`03-model`, `04-retrieval`, `06-demo`), so this will bite again. Confirmed:
`9x.gguf` fails, `x9.gguf` works, `./03-model/...` works.

**Always write `./` in front of paths passed to `llama-quantize`.** Cheap habit,
and it costs nothing to apply it to `llama-imatrix` and `llama-server` too.

Pass the thread count explicitly (`8` above). Relying on the default is what puts
you next to the parsing bug in the first place.

### Expected, not a problem

```
llama_model_quantize_impl: WARNING: 51 of 263 tensor(s) required fallback quantization
```

Hybrid Mamba2 tensors whose shapes are not divisible by the K-quant superblock
size, so they take a different type. It appears identically on the shipped
artifact. Size confirms nothing went wrong:

| artifact | bytes | delta |
|---|---|---|
| shipped, built before this repo existed | 2,837,072,864 | baseline |
| rebuilt from F16, no imatrix | 2,837,072,960 | +96 |
| rebuilt from F16, with imatrix | 2,837,073,184 | +320 |

The deltas are the `quantize.imatrix.*` metadata keys, not weight differences.

---

## 6. Load and generate

```bash
llama-server -m ./03-model/base/FINAL-imatrix-Q4_K_M.gguf \
  --jinja -np 1 -ngl 0 -c 4096 --port 8080
```

Hard constraint 5: **send `"chat_template_kwargs": {"enable_thinking": false}` on
every call** and check `reasoning_content` comes back empty. Nothing warns you if
you forget.

Measured on the rebuilt artifact, `-ngl 0`: prompt eval **28.8 tok/s**,
generation **8.54 tok/s**. The shipped artifact measures 30 to 32 and 9.5 to 10
on the same machine. The gap is machine load during a day of conversions, not the
imatrix; do not record it as a regression without a quiet-machine re-measure.

---

## 7. Acceptance test: is the rebuild the same model?

Loading is not proof. The corrupt Q8_0 loaded. **Run the probe and diff the
verdicts against the last known-good run.**

```bash
python 01-data/eval/format3_probe.py          # 5 minutes, five cases
```

Compare with `01-data/eval/runs/2026-09-17-rule4-after.txt`, which is the shipped
model on the same prompt sha `26e4f4ff`.

| case | shipped | rebuilt |
|---|---|---|
| red-acs | red | red |
| yellow-angina | red | red |
| green-gerd | yellow | yellow |
| yellow-pleuritic | red | red |
| probe-costo | red | red |

**5 of 5, 2026-09-18.** Note that this matches on the **failures** too. That is
the strong form of the result: the rebuild reproduces the red bias, the rule 7
violation on yellow-angina, and the fabricated "fever and tachycardia" on
yellow-pleuritic. A rebuild that "fixed" those would mean something had changed
that nobody chose to change.

Keep the prompt sha in the comparison. A verdict diff means nothing if the system
prompt moved underneath it.

---

## 8. The training half: ALL FIVE STEPS RUN 2026-09-19

**Step 5 ran and the result ships.** 120 pairs, 124 examples, 2 epochs, 30
optimizer steps, 189 s on one A6000, loss 1.5787 to 0.6851. Merged, then back
through sections 3 to 7 of this runbook with every gate passing, giving
`03-model/base/TUNED-120pairs-imatrix-Q4_K_M.gguf`, **which is what the demo
loads since 2026-09-19.** Held out against the base on the frozen 22: 46.0 to
81.5 per completion on matched chunks, yellow 3/19 to 21/21, non-red answers
citing nothing 9/33 to 0/53. Runs:
`01-data/eval/runs/2026-09-19-brev-qlora-trained.txt`,
`2026-09-19-tuned-conversion-chain.txt`,
`2026-09-19-heldout-{base,tuned}-{matched,retrieval}.txt`.

**It is LoRA, not QLoRA, and step 3 below is why that changed.** The fused
`mamba_ssm` and `causal_conv1d` kernels are needed to fit on a 48 GB card at all
(47.29 GiB without them against 21.29 with), and the fused kernel multiplies
`in_proj` and `out_proj` itself, so bitsandbytes' packed 4-bit weights die on
shape. Kernels or 4-bit, not both. The base trained in bf16 at 7.95 GB.
`03-model/brev_train_qlora.py` is the script that ran.

**The adapter is committed**, `03-model/adapter-120pairs/`, sha256
`eabf01c159dafaa1da8cfe6b3a9887ee93310c86450fbc5e0506091c10a57920`. The merged
bf16 was deleted to make room for the F16, so the adapter plus the merge stage
of `brev_train_qlora.py` is the way back to it.

**Steps 1 to 4 passed on Brev** (`massedcompute_A6000_base`, about $0.42). See
`01-data/eval/runs/2026-09-19-brev-4bit-gate.txt`. Every projection is
Linear4bit, Mamba2 included, at 3.28 GB on device. LoRA matched 50 of 50.

**Load with `trust_remote_code=False`, on transformers 5.x.** The repo's own
modeling file hard-imports `mamba_ssm` and fails without it. transformers 5.17
has a built-in `nemotron_h` with PyTorch fallbacks, and it loads the checkpoint
with no missing keys. `brev_4bit_gate.py` now does this. `brev exec` hung twice
this run; drive the instance with plain `ssh <instance>`.

The original list, kept for the numbers it asked for:

1. Brev provisioning
2. `pip install trl peft bitsandbytes`
3. **Loading Nemotron in 4-bit, unproven on a hybrid Mamba2 model.** The open
   question is whether bitsandbytes handles the SSM tensors. This is the first
   thing to find out and it gates everything after it.
4. Attaching LoRA with the decided six modules, `03-model/qlora_config.py`.
   **Assert the matched-module count**, hard constraint 10: PEFT does not error on
   a target that matches nothing. Expect q/k/v/o_proj 4 each, up/down_proj 17
   each, 50 total.
5. Training, merge, then re-entering this runbook at section 3.

**The merged model goes through sections 3 to 7 unchanged.** That is the whole
point of proving them separately: if tomorrow breaks, the break is in training,
not in conversion, and section 7 is the test that tells you which.

**It held.** The merge re-entered at section 3 and every gate passed with no
surprises, which is the only reason the conversion could be trusted on weights
nothing had ever converted before. One thing needed care and is written up in
`01-data/eval/runs/2026-09-19-tuned-conversion-chain.txt`: transformers 5.17
writes metadata beside the merge that is not what section 3 was proven with, so
the conversion ran from `03-model/convert-src-120pairs/`, which is the merged
weights under NVIDIA's own config and tokenizer files. `tokenizer.json` is
byte-identical in both, checked before substituting rather than assumed.
