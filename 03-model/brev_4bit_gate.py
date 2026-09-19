#!/usr/bin/env python3
"""Epic 3, step 2. THE GATE: can bitsandbytes 4-bit a hybrid Mamba2 model?

    python 03-model/brev_4bit_gate.py --model nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16

Run this on Brev BEFORE attaching LoRA and long before training. It answers one
question and exits. Nothing downstream is worth starting if this fails.

WHY THIS EXISTS, AND WHY IT GENERATES RATHER THAN JUST LOADING.

2026-09-18, the F16 lesson: a `--outtype q8_0` GGUF loaded cleanly, reported the
correct architecture, and quantized to within 320 bytes of the known-good
artifact. It also generated `FoundationFoundationFoundation...` forever. Loading
is not proof. The only proof is output.

The same trap has a 4-bit shape, and it is worse because it is quieter.
`load_in_4bit=True` does NOT guarantee every Linear became 4-bit. bitsandbytes
skips what it cannot handle and reports success. On a hybrid Mamba2 model the
plausible failure is that the SSM projections stay in bf16 while attention and
MLP quantize, so the model "loads in 4-bit", runs, and silently costs far more
memory than budgeted. That is why check 2 counts module TYPES rather than
trusting the flag.

Three checks, each of which can fail independently:

  1. LOADS       from_pretrained with a 4-bit config completes at all.
  2. QUANTIZES   the SSM projections are actually Linear4bit, not left behind.
                 Reported per module family so a partial result is legible.
  3. GENERATES   a forward pass gives finite logits and a short generate
                 produces text that is not a single repeated token.

Exit 0 means the gate is open. Exit 1 means it is not, and the message says
which check failed. Hard constraint from the day: report the result before
running anything expensive.
"""

import argparse
import sys
from collections import Counter

# Module families for this architecture. From claude.md, verified 2026-09-15
# against the safetensors header: 42 blocks, 21 Mamba2 / 4 attention / 17 MLP,
# attention only at layers 12, 17, 24, 32. Every projection sits under `.mixer.`
# and the top-level prefix is `backbone.`, not `model.`.
FAMILIES = {
    "in_proj":   ("Mamba2", 21),   # fused x,B,C,dt,z. 29.0% of params
    "out_proj":  ("Mamba2", 21),   # 12.7%
    "up_proj":   ("MLP",    17),
    "down_proj": ("MLP",    17),
    "q_proj":    ("attn",    4),
    "k_proj":    ("attn",    4),
    "v_proj":    ("attn",    4),
    "o_proj":    ("attn",    4),
}

PROMPT = "Reply with exactly: OK"


def bail(check, msg, hint=""):
    print(f"\n  GATE FAILED at check {check}.\n  {msg}")
    if hint:
        print(f"\n  {hint}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16")
    ap.add_argument("--attach-lora", action="store_true",
                    help="step 3: also attach LoRA and assert 50 matched modules")
    args = ap.parse_args()

    try:
        import torch
        from transformers import (AutoModelForCausalLM, AutoTokenizer,
                                  BitsAndBytesConfig)
        import bitsandbytes
    except ModuleNotFoundError as e:
        sys.exit(f"missing {e.name!r}. This runs on Brev, not the laptop: "
                 f"bitsandbytes is CUDA-only.\n"
                 f"  pip install trl peft bitsandbytes transformers accelerate")

    print(f"torch        {torch.__version__}")
    print(f"bitsandbytes {bitsandbytes.__version__}")
    import transformers; print(f"transformers {transformers.__version__}")
    if not torch.cuda.is_available():
        bail(0, "no CUDA device. This script is for Brev, not the laptop.")
    print(f"gpu          {torch.cuda.get_device_name(0)}")
    print()

    # ---- check 1: loads -----------------------------------------------------
    # nf4 + double quant + bf16 compute is the standard QLoRA recipe. If the
    # architecture is going to refuse 4-bit, it refuses here.
    qcfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    print("check 1  loading in 4-bit ...")
    try:
        # NOT the repo's own modeling file. It imports mamba_ssm's rmsnorm_fn
        # unconditionally (lines 61-65) and raises without it, so on the five
        # pip packages check 1 would fail on a missing package, not on 4-bit.
        # transformers 5.x ships nemotron_h natively with reference PyTorch
        # fallbacks. Verified 2026-09-19 on CPU with 5.17.0: 0 missing keys,
        # backbone. renamed to model. on load, finite logits.
        model = AutoModelForCausalLM.from_pretrained(
            args.model, quantization_config=qcfg, device_map={"": 0},
            trust_remote_code=False,
        )
    except Exception as e:
        bail(1, f"from_pretrained raised {type(e).__name__}: {e}",
             "Fallback per the plan: load in bf16 with a smaller batch.")
    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=False)
    mem = torch.cuda.memory_allocated(0) / 1e9
    print(f"check 1  PASS. loaded, {mem:.2f} GB on device\n")

    # ---- check 2: actually quantized ---------------------------------------
    # The quiet failure. Count concrete types per family; bnb leaves what it
    # cannot handle as nn.Linear and says nothing.
    print("check 2  did the SSM tensors actually quantize?")
    seen = {name: Counter() for name in FAMILIES}
    for mod_name, mod in model.named_modules():
        leaf = mod_name.rsplit(".", 1)[-1]
        if leaf in seen:
            seen[leaf][type(mod).__name__] += 1

    print(f"    {'module':<11} {'block':<7} {'found':>5} {'expected':>8}   types")
    ssm_bad, any_bad = [], []
    for leaf, (block, expected) in FAMILIES.items():
        counts = seen[leaf]
        total = sum(counts.values())
        types = ", ".join(f"{k}x{v}" for k, v in counts.items()) or "NONE FOUND"
        flag = "" if total == expected else "   <-- COUNT MISMATCH"
        print(f"    {leaf:<11} {block:<7} {total:>5} {expected:>8}   {types}{flag}")
        not4bit = sum(v for k, v in counts.items() if "4bit" not in k.lower())
        if total != expected or not4bit:
            any_bad.append(leaf)
            if block == "Mamba2":
                ssm_bad.append(leaf)

    if ssm_bad:
        bail(2, f"SSM projections not fully 4-bit: {ssm_bad}. bitsandbytes left "
                f"Mamba2 tensors unquantized, which is 41.7% of parameters "
                f"staying in bf16.",
             "This is the answer the gate exists to find. Report it, do not "
             "work around it. Fallback: bf16 with a smaller batch.")
    if any_bad:
        bail(2, f"non-SSM families wrong: {any_bad}.")
    print("check 2  PASS. every projection is 4-bit, Mamba2 included\n")

    # ---- check 3: generates -------------------------------------------------
    # Loading is not proof. See the module docstring.
    print("check 3  generating ...")
    ids = tok(PROMPT, return_tensors="pt").to(0)
    with torch.no_grad():
        logits = model(**ids).logits
    if not torch.isfinite(logits).all():
        bail(3, "forward pass produced non-finite logits (NaN or inf). "
                "The 4-bit weights are corrupt.")
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=24, do_sample=False)
    text = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
    print(f"    logits finite: yes")
    print(f"    output: {text!r}")

    # The Foundation-loop check, in its 4-bit form.
    toks = text.split()
    if len(toks) > 4 and len(set(toks)) == 1:
        bail(3, f"degenerate output, one token repeated: {toks[0]!r}. "
                f"This is the 4-bit version of the Q8_0 corruption.")
    print("check 3  PASS\n")

    print("=" * 62)
    print("  GATE OPEN. 4-bit works on this hybrid Mamba2 model.")
    print("=" * 62)

    if not args.attach_lora:
        print("\nNext: rerun with --attach-lora for step 3.")
        return

    # ---- step 3: LoRA, asserted against the REAL model ----------------------
    # Hard constraint 10: PEFT does not error on a target that matches nothing.
    # qlora_config.py self-tests against a STORED name list offline; this is the
    # same assertion against the actually-loaded 4-bit model, which is the one
    # that counts. 4-bit swaps nn.Linear for Linear4bit while leaving names
    # alone, so a stale list could pass while reality differed.
    print("\nstep 3  attaching LoRA ...")
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    # Import the hyperparameters rather than restating them. qlora_config.py is
    # the single source for r, alpha and the expected counts; a second copy here
    # is a copy that drifts.
    from qlora_config import (TARGET_MODULES, EXPECTED_MATCHES,  # noqa: E402
                              EXPECTED_TOTAL, LORA_KWARGS)
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    model = prepare_model_for_kbit_training(model)
    peft_model = get_peft_model(model, LoraConfig(
        target_modules=list(TARGET_MODULES), **LORA_KWARGS))

    got = Counter()
    for n, _ in peft_model.named_modules():
        if n.endswith("lora_A.default"):
            got[n.rsplit(".lora_A", 1)[0].rsplit(".", 1)[-1]] += 1
    total = sum(got.values())
    print(f"    {'target':<11} {'matched':>7} {'expected':>8}")
    ok = True
    for t in TARGET_MODULES:
        exp = EXPECTED_MATCHES.get(t)
        mark = "" if got[t] == exp else "   <-- MISMATCH"
        if got[t] != exp:
            ok = False
        print(f"    {t:<11} {got[t]:>7} {exp:>8}{mark}")
    print(f"    total       {total:>7} {EXPECTED_TOTAL:>8}")
    peft_model.print_trainable_parameters()
    if not ok or total != EXPECTED_TOTAL:
        bail(3, f"matched-module assertion failed: {total} of {EXPECTED_TOTAL}. "
                f"Constraint 10: PEFT would have trained silently.")
    print(f"\nstep 3  PASS. {EXPECTED_TOTAL} matched, adapter attached. "
          f"Not trained.")


if __name__ == "__main__":
    main()
