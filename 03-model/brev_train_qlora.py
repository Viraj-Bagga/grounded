#!/usr/bin/env python3
"""Epic 3 step 5: QLoRA on the 120 pairs, then merge. Runs on the Brev A6000.

    python3 brev_train_qlora.py --stage attach --model ~/nemotron --pairs ~/candidates-120.jsonl
    python3 brev_train_qlora.py --stage train  --model ~/nemotron --pairs ~/candidates-120.jsonl \
                                --out ~/adapter --merged ~/merged

Two stages on purpose. `attach` loads in 4-bit, builds the dataset, attaches
LoRA and asserts the matched-module count, then stops without training: if
anything is wrong, it is wrong before the expensive part. `train` does the same
and then trains, saves the adapter, and merges it into a bf16 copy of the base.

THE REASONING SWITCH IS PART OF THE PROMPT. The app sends
chat_template_kwargs {"enable_thinking": false}, which makes the template end
the prompt with `<think></think>` and the model continue with JSON. With the
switch left out, the same template ends the prompt `<think>\\n`, which is a
different prompt. Checked on the laptop tokenizer before this script ran:
training therefore renders every prompt with enable_thinking=False, so what is
trained is what the app sends. Hard constraint 5, at training time.

LOSS IS ON THE COMPLETION ONLY. The dataset is prompt/completion, which TRL
masks for us, so nothing in the system prompt or the retrieved chunks is a
training target. A multi-turn pair contributes one example per assistant turn,
each with the whole conversation up to that point as the prompt.

trust_remote_code=False is not optional: the repo's own modeling file imports
mamba_ssm unconditionally. transformers 5.x has a built-in nemotron_h with
PyTorch fallbacks. See build-log 2026-09-19.
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

# Attempt 1 died with 18 GiB reserved-but-unallocated, which is fragmentation,
# and PyTorch's own OOM message names this flag. Set before torch is imported,
# because the allocator reads it once at initialisation.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

MAX_LENGTH = 2048          # longest example measured locally is 1633 tokens
EPOCHS = 2                 # the decided plan: light-touch format fine-tune
LR = 2e-4
GRAD_ACCUM = 8
WARMUP_STEPS = 3           # of 30 optimizer steps. This TRL's SFTConfig has no
                           # warmup_ratio: it was silently dropped in attempt 1,
                           # so that run had no warmup at all.


def build_examples(pairs_path, tok):
    """One prompt/completion example per assistant turn."""
    rows = [json.loads(l) for l in Path(pairs_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = []
    for r in rows:
        convs = r["conversations"]
        if convs[0]["from"] != "system":
            raise SystemExit(f"{r['id']}: first turn is not system")
        msgs = [{"role": "system", "content": convs[0]["value"]}]
        for i in range(1, len(convs), 2):
            msgs.append({"role": "user", "content": convs[i]["value"]})
            prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True,
                                             enable_thinking=False)
            if not prompt.endswith("<think></think>"):
                raise SystemExit("the prompt does not end with <think></think>: the template changed, "
                                 "and training it this way would be train/serve skew")
            out.append({"prompt": prompt, "completion": convs[i + 1]["value"] + tok.eos_token,
                        "id": r["id"]})
            msgs.append({"role": "assistant", "content": convs[i + 1]["value"]})
    return rows, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["attach", "probe", "train", "merge"], required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--out", default=None, help="where to save the adapter")
    ap.add_argument("--merged", default=None, help="where to save the merged bf16 model")
    ap.add_argument("--batch", type=int, default=1, help="per-device batch size")
    ap.add_argument("--no-quant", action="store_true",
                    help="load the base in bf16 and run plain LoRA. The fused Mamba2 kernel folds "
                         "in_proj and out_proj into itself and calls F.linear on their raw weights, "
                         "which cannot be packed 4-bit blobs. With the kernels the activations fit on "
                         "48 GB in bf16, so dropping the quantization is cheaper than dropping the "
                         "kernels. The adapter, its targets and the merge are unchanged.")
    ap.add_argument("--skip-quant", default="", help="comma-separated module names to leave in bf16. "
                    "With the fused Mamba2 kernel, transformers folds out_proj into the kernel and "
                    "calls F.linear on its raw weight, which fails on a packed 4-bit blob, so "
                    "out_proj may have to stay unquantized.")
    ap.add_argument("--grad-accum", type=int, default=GRAD_ACCUM,
                    help="gradient accumulation steps; keep batch * accum at 8")
    args = ap.parse_args()

    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if args.stage == "merge":
        # Merge an adapter that is already on disk, so a failed save does not
        # cost another training run. Nemotron's own generation_config sets top_p
        # with do_sample False, which transformers 5.17 refuses to save; the
        # sampling fields are cleared so the config validates. The app sets its
        # own temperature at inference, so nothing is lost.
        from peft import PeftModel
        tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=False)
        base = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16,
                                                    device_map={"": "cpu"}, trust_remote_code=False)
        merged = PeftModel.from_pretrained(base, args.out).merge_and_unload()
        for field in ("top_p", "top_k", "temperature"):
            if getattr(merged.generation_config, field, None) is not None:
                print(f"clearing generation_config.{field}="
                      f"{getattr(merged.generation_config, field)}", flush=True)
                setattr(merged.generation_config, field, None)
        merged.save_pretrained(args.merged, safe_serialization=True)
        tok.save_pretrained(args.merged)
        print(f"merged bf16 model saved to {args.merged}", flush=True)
        return
    print(f"torch {torch.__version__}  transformers {transformers.__version__}", flush=True)
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        print(f"gpu {props.name}, {props.total_memory / 1e9:.0f} GB", flush=True)
    else:
        raise SystemExit("no CUDA device")
    import bitsandbytes, peft, trl
    print(f"bitsandbytes {bitsandbytes.__version__}  peft {peft.__version__}  trl {trl.__version__}",
          flush=True)
    kernels = {}
    for name in ("causal_conv1d", "mamba_ssm"):
        try:
            __import__(name)
            kernels[name] = "fused"
        except Exception as e:
            kernels[name] = f"fallback ({type(e).__name__})"
    print(f"SSM kernels: {kernels}", flush=True)

    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=False)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    rows, examples = build_examples(args.pairs, tok)
    lens = [len(tok(e["prompt"])["input_ids"]) + len(tok(e["completion"])["input_ids"]) for e in examples]
    print(f"\ndata: {len(rows)} pairs -> {len(examples)} examples, "
          f"tokens min {min(lens)} median {sorted(lens)[len(lens) // 2]} max {max(lens)}, "
          f"{sum(lens)} per epoch", flush=True)
    if max(lens) > MAX_LENGTH:
        raise SystemExit(f"an example is {max(lens)} tokens, over MAX_LENGTH {MAX_LENGTH}")
    from collections import Counter
    print("verdicts:", dict(Counter(json.loads(e["completion"].replace(tok.eos_token, ""))["urgency"]
                                    for e in examples)), flush=True)

    if args.no_quant:
        model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16,
                                                     device_map={"": 0}, trust_remote_code=False)
        print(f"loaded bf16, NOT quantized: {model.get_memory_footprint() / 1e9:.2f} GB on device",
              flush=True)
    else:
        skip = [s for s in args.skip_quant.split(",") if s]
        qcfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_use_double_quant=True,
                                  bnb_4bit_compute_dtype=torch.bfloat16,
                                  **({"llm_int8_skip_modules": skip} if skip else {}))
        if skip:
            print(f"left in bf16, not quantized: {skip}", flush=True)
        model = AutoModelForCausalLM.from_pretrained(args.model, quantization_config=qcfg,
                                                     device_map={"": 0}, trust_remote_code=False)
        print(f"loaded 4-bit: {model.get_memory_footprint() / 1e9:.2f} GB on device", flush=True)

    from peft import get_peft_model, prepare_model_for_kbit_training
    from qlora_config import assert_targets_matched, build_lora_config
    # use_reentrant=False is the fix for attempt 1. Requested both ways there and
    # it did nothing: reentrant checkpointing needs the inputs to require grad,
    # which they do not under a quantised base, so every activation was kept.
    ckpt_kwargs = {"use_reentrant": False}
    if args.no_quant:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs=ckpt_kwargs)
    else:
        try:
            model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                                    gradient_checkpointing_kwargs=ckpt_kwargs)
        except TypeError:
            model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
            model.gradient_checkpointing_enable(gradient_checkpointing_kwargs=ckpt_kwargs)
    model.enable_input_require_grads()
    model.config.use_cache = False
    print(f"gradient checkpointing: {getattr(model, 'is_gradient_checkpointing', 'unknown')}, "
          f"kwargs {ckpt_kwargs}, PYTORCH_CUDA_ALLOC_CONF={os.environ.get('PYTORCH_CUDA_ALLOC_CONF')}",
          flush=True)
    peft_model = get_peft_model(model, build_lora_config(model))

    # Hard constraint 10: PEFT does not error on a target that matches nothing.
    matched = [n for n, m in peft_model.named_modules() if n.endswith("lora_A.default")]
    leaves = [n.rsplit(".lora_A", 1)[0].rsplit(".", 1)[-1] for n in matched]
    assert_targets_matched([n.rsplit(".lora_A", 1)[0] for n in matched])
    print(f"\nLoRA matched {len(matched)} modules: {dict(Counter(leaves))}", flush=True)
    trainable = sum(p.numel() for p in peft_model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in peft_model.parameters())
    print(f"trainable {trainable:,} of {total:,} ({100 * trainable / total:.3f}%)", flush=True)

    if args.stage == "attach":
        print("\nATTACH STAGE COMPLETE. Nothing trained.", flush=True)
        return

    if args.stage == "probe":
        # One forward and backward on the LONGEST example, with labels over the
        # whole sequence rather than the completion only. That is strictly more
        # work than any real step, so fitting here means the run fits.
        longest = max(examples, key=lambda e: len(tok(e["prompt"] + e["completion"])["input_ids"]))
        enc = tok(longest["prompt"] + longest["completion"], return_tensors="pt").to("cuda")
        n = enc["input_ids"].shape[1]
        capacity = torch.cuda.get_device_properties(0).total_memory / 2**30
        torch.cuda.reset_peak_memory_stats()
        before = torch.cuda.memory_allocated() / 2**30
        try:
            out = peft_model(**enc, labels=enc["input_ids"].clone())
            out.loss.backward()
        except torch.OutOfMemoryError as e:
            print(f"\nPROBE DID NOT FIT at {n} tokens: {str(e)[:200]}", flush=True)
            raise SystemExit(2)
        peak_a = torch.cuda.max_memory_allocated() / 2**30
        peak_r = torch.cuda.max_memory_reserved() / 2**30
        peft_model.zero_grad(set_to_none=True)

        # Time a second pass, after the first has warmed the allocator and any
        # kernel autotuning, so the estimate is what training will actually see.
        import time
        torch.cuda.synchronize()
        t0 = time.time()
        out = peft_model(**enc, labels=enc["input_ids"].clone())
        out.loss.backward()
        torch.cuda.synchronize()
        step_s = time.time() - t0
        peft_model.zero_grad(set_to_none=True)

        print(f"\nPROBE FITS. {longest['id']}, {n} tokens, loss {out.loss.item():.4f}")
        print(f"  weights and optimizer state before the step: {before:.2f} GiB")
        print(f"  peak allocated {peak_a:.2f} GiB, peak reserved {peak_r:.2f} GiB, "
              f"capacity {capacity:.2f} GiB, headroom {capacity - peak_r:.2f} GiB")
        print(f"  one forward+backward at {n} tokens: {step_s:.2f} s ({n / step_s:.0f} tok/s)")
        est = step_s * len(examples) * EPOCHS * (sum(lens) / len(lens)) / n / 60
        print(f"  estimate for {EPOCHS} epochs over {len(examples)} examples: about {est:.0f} min "
              f"at batch 1")
        # Activation memory scales about linearly with batch; keep 15% spare.
        per_example = max(peak_r - before, 0.1)
        fits = int((capacity * 0.85 - before) // per_example)
        print(f"  SUGGESTED BATCH: {max(1, min(fits, 8))}", flush=True)
        return

    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer
    ds = Dataset.from_list([{"prompt": e["prompt"], "completion": e["completion"]} for e in examples])
    # TRL renamed several of these between versions, and a TypeError here costs
    # GPU minutes, so keep only the keys this installed SFTConfig accepts and
    # say which were dropped. max_length was max_seq_length before TRL 1.x.
    want = dict(output_dir=args.out or "./adapter", num_train_epochs=EPOCHS,
                per_device_train_batch_size=args.batch, gradient_accumulation_steps=args.grad_accum,
                learning_rate=LR, lr_scheduler_type="cosine", warmup_steps=WARMUP_STEPS,
                logging_steps=1, save_strategy="no", bf16=True, max_length=MAX_LENGTH,
                max_seq_length=MAX_LENGTH, gradient_checkpointing=True,
                gradient_checkpointing_kwargs=ckpt_kwargs,
                optim="paged_adamw_8bit", report_to=[], seed=20260919,
                completion_only_loss=True)
    import dataclasses
    fields = {f.name for f in dataclasses.fields(SFTConfig)}
    dropped = sorted(k for k in want if k not in fields)
    cfg = SFTConfig(**{k: v for k, v in want.items() if k in fields})
    print(f"SFTConfig: dropped {dropped or 'nothing'} as unsupported in this TRL", flush=True)
    for key, value in (("processing_class", tok), ("tokenizer", tok)):
        try:
            trainer = SFTTrainer(model=peft_model, args=cfg, train_dataset=ds, **{key: value})
            break
        except TypeError as e:
            print(f"SFTTrainer({key}=...) not accepted: {e}", flush=True)
    else:
        raise SystemExit("SFTTrainer accepted neither processing_class nor tokenizer")
    print(f"\ntraining: {EPOCHS} epochs, {len(ds)} examples, batch {args.batch} x accum "
          f"{args.grad_accum}, {max(1, len(trainer.get_train_dataloader()) // args.grad_accum) * EPOCHS} "
          f"optimizer steps", flush=True)
    result = trainer.train()

    print("\n=== LOSS, every logged step")
    for h in trainer.state.log_history:
        if "loss" in h:
            print(f"  epoch {h.get('epoch', 0):.2f}  step {h.get('step')}  loss {h['loss']:.4f}"
                  f"  lr {h.get('learning_rate', 0):.2e}")
    print(f"=== final train loss {result.training_loss:.4f} over {result.metrics.get('train_steps_per_second', 0):.2f} steps/s, "
          f"{result.metrics.get('train_runtime', 0):.0f} s")

    adapter = args.out or "./adapter"
    peft_model.save_pretrained(adapter)
    tok.save_pretrained(adapter)
    print(f"adapter saved to {adapter}", flush=True)

    if args.merged:
        # Merge into a bf16 copy of the base, not into the 4-bit one: merging a
        # LoRA into quantised weights would bake in the quantisation error, and
        # the GGUF conversion wants bf16 anyway.
        del peft_model, model
        torch.cuda.empty_cache()
        from peft import PeftModel
        base = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16,
                                                    device_map={"": "cpu"}, trust_remote_code=False)
        merged = PeftModel.from_pretrained(base, adapter).merge_and_unload()
        merged.save_pretrained(args.merged, safe_serialization=True)
        tok.save_pretrained(args.merged)
        print(f"merged bf16 model saved to {args.merged}", flush=True)


if __name__ == "__main__":
    main()
