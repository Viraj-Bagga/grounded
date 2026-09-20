Staging dir for the F16 conversion of the 120-pair fine-tune, built 2026-09-19.

model.safetensors is a SYMLINK to ../merged-120pairs/model.safetensors
(sha256 1393cc3141428418ffa06053d9acd0ee0339598116426fd578a45e0a6b757eea).

Every other file is copied from 03-model/hf-bf16, i.e. NVIDIA's own metadata,
not what transformers 5.17 wrote beside the merge. Reasons:

- The merged config.json has no hybrid_override_pattern. It has 5.x's
  layers_block_type plus a block of MoE defaults that do not apply to this
  model. The converter reads either, but the base config is the one section 3
  of RUNBOOK.md was proven with, so the only thing that differs between that
  run and this one is the weights.
- The merged tokenizer_config.json is 5.x's minimal TokenizersBackend form:
  364 bytes, no added_tokens_decoder, no add_bos_token, no chat template.
  The base one carries all of it.
- tokenizer.json is byte-identical in both (sha 623c34567aebb185), so nothing
  about the vocab changes by taking the base metadata.
- merged/chat_template.jinja and the template embedded in the base
  tokenizer_config.json differ only in blank lines that 5.x inserted. Checked
  line by line: 26 diff lines, all whitespace.

LoRA merging does not change architecture or vocabulary, so this staging dir
is the merged weights under the base model's proven metadata.

2026-09-19, after the F16 gate passed: merged-120pairs/model.safetensors was
deleted to make room for imatrix and Q4_K_M, so the symlink here now dangles.
The F16 GGUF is everything imatrix and quantize read. To rebuild the merge,
re-run the merge stage of 03-model/brev_train_qlora.py against the adapter in
03-model/adapter-120pairs (40 MB, kept).
