"""QLoRA target module config for Nemotron 3 Nano 4B (`nemotron_h`).

Run `python 03-model/qlora_config.py` to self-test the assertion offline, with
no torch and no model download. It checks the expected match counts against
`module_names.txt`, which was read from the safetensors header of
nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16 on 2026-09-15.

--------------------------------------------------------------------------
THE DECISION, so it does not get relitigated on Brev at 2am
--------------------------------------------------------------------------
The model is hybrid Mamba2 plus attention, 42 blocks split 21 Mamba2, 4
attention, 17 MLP. Attention sits only at blocks 12, 17, 24 and 32.

Target six modules: q_proj, k_proj, v_proj, o_proj, up_proj, down_proj.

1. `gate_proj` is dropped because it does not exist. This MLP is ungated.
   It was in the original seven and it matched nothing.

2. The Mamba2 mixers are deliberately NOT targeted, even though `in_proj` and
   `out_proj` are 41.7% of parameters. Coverage is the wrong objective. This is
   a light-touch format fine-tune, roughly 500 pairs for 2 epochs, teaching
   output shape. The spike showed the failures are teachable at the prompt
   level, so this is not a behavioural rewrite. More trainable parameters
   against 500 examples buys overfitting, not capability.

3. `in_proj` is skipped for a second reason on top of that. It is a fused
   projection emitting x, B, C, dt and z, so a low-rank update smears across
   five semantically different outputs. LoRA on Mamba2 is thinner ground than
   LoRA on attention, and four days out is the wrong time to be the person
   testing it.

4. Attention is kept despite being only 3.8% of parameters, and not for
   parameter count. Copying a citation key such as CP-ACS-001 verbatim out of a
   retrieved chunk into the output is in-context copying, which lives in
   attention heads. There are four attention blocks in the whole model. Those
   are the ones that have to learn citation fidelity, and citation fidelity is
   demo beat four.
"""

# Six modules. Not seven. See point 1 above.
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj"]

# How many modules each target must match in this specific model. Attention
# exists in 4 blocks, MLP in 17. Every projection lives under `.mixer.`,
# including the attention ones, e.g. `backbone.layers.12.mixer.q_proj`.
EXPECTED_MATCHES = {
    "q_proj": 4,
    "k_proj": 4,
    "v_proj": 4,
    "o_proj": 4,
    "up_proj": 17,
    "down_proj": 17,
}
EXPECTED_TOTAL = sum(EXPECTED_MATCHES.values())  # 50

LORA_KWARGS = dict(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                   task_type="CAUSAL_LM")


def count_matches(module_names):
    """Count how many modules each target matches, by leaf-name suffix.

    PEFT matches `target_modules` against the end of the module path, so this
    mirrors its behaviour without needing torch.
    """
    counts = {t: 0 for t in TARGET_MODULES}
    for name in module_names:
        leaf = name.rsplit(".", 1)[-1]
        if leaf in counts:
            counts[leaf] += 1
    return counts


def assert_targets_matched(module_names, expected=None):
    """Fail loudly if the target list does not match what we expect.

    PEFT does NOT error when a target matches nothing, as long as at least one
    other target matches. That is how `gate_proj` sat in the config matching
    zero modules and would have trained silently. Never trust the absence of an
    exception; assert the count.
    """
    expected = expected or EXPECTED_MATCHES
    counts = count_matches(module_names)

    unmatched = sorted(t for t, n in counts.items() if n == 0)
    if unmatched:
        raise AssertionError(
            "target_modules match nothing: %s. PEFT would not have raised. "
            "Check the module names against the architecture." % unmatched)

    wrong = {t: (n, expected[t]) for t, n in counts.items()
             if t in expected and n != expected[t]}
    if wrong:
        raise AssertionError(
            "matched count differs from expected (got, expected): %s. "
            "The model is not the one this config was written for." % wrong)

    total = sum(counts.values())
    if total != EXPECTED_TOTAL:
        raise AssertionError(
            "total matched modules %d, expected %d" % (total, EXPECTED_TOTAL))
    return counts


def build_lora_config(model):
    """Build the LoraConfig and assert it actually matched before returning."""
    from peft import LoraConfig

    assert_targets_matched([n for n, _ in model.named_modules()])
    return LoraConfig(target_modules=TARGET_MODULES, **LORA_KWARGS)


if __name__ == "__main__":
    import pathlib
    import sys

    path = pathlib.Path(__file__).parent / "module_names.txt"
    if not path.exists():
        sys.exit("missing %s, cannot self-test" % path)

    names = path.read_text(encoding="utf-8").split()
    counts = assert_targets_matched(names)

    print("module names checked : %d" % len(names))
    print("targets              : %s" % ", ".join(TARGET_MODULES))
    for t in TARGET_MODULES:
        print("  %-12s matched %2d  (expected %2d)" % (t, counts[t], EXPECTED_MATCHES[t]))
    print("total matched        : %d" % sum(counts.values()))
    print("\nassertion passed.")

    # And prove the assertion actually catches the bug it exists for.
    saved = list(TARGET_MODULES)
    try:
        TARGET_MODULES.append("gate_proj")
        assert_targets_matched(names)
        print("REGRESSION: gate_proj was not caught")
    except AssertionError as e:
        print("gate_proj correctly rejected: %s" % str(e).split(".")[0])
    finally:
        TARGET_MODULES[:] = saved
