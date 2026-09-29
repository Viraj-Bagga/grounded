#!/usr/bin/env python3
"""
Single source of truth for the epic 2 pair format.

WHY THIS FILE EXISTS. Three mutually incompatible prompt formats and three
mutually incompatible assistant schemas were in circulation when epic 2 started:

  1. the frozen spec, training-data-format.md / spec.md section 4, written
     2026-09-12 before the corpus existed: <profile> <timeline> <reference>
     blocks, assistant JSON keyed action / category / reason / advice /
     watch_for / sources, citation keys shaped source:topic:section.
  2. 01-data/eval/discrimination_test.py: bare PROFILE / TIMELINE /
     RETRIEVED CONTEXT / PATIENT SAYS headers, assistant JSON keyed urgency /
     rationale / red_flags / follow_up_questions / citations, no next_steps.
  3. spike/req-demo-shape.json: bracketed [PATIENT PROFILE] / [SYMPTOMS] /
     [RETRIEVED CONTEXT] blocks, assistant JSON as 2 plus next_steps.

training-data-format.md section 2 is right that any drift between the training
human turn and the inference human turn is train/serve skew. That makes the
choice a hard blocker on writing pairs, not a detail to settle later. Nothing
imports a prompt string of its own; everything imports this module.

WHICH ONE WON, AND WHY. Format 3, the spike request.

  - it is the only one that has been measured. The 63.8 s cold demo number and
    the valid-JSON result behind it came from exactly these bytes.
  - it carries next_steps, which the other two lack, and next_steps is where
    the IITT-to-disposition translation layer in CLAUDE.md lands: red becomes
    call emergency services now, yellow becomes be seen today and how to get
    there, green becomes self-care plus the signs that change the answer.
    Without that field there is nowhere to put the thing the app is for.
  - its field names are the ones Viraj used when specifying the validator.

WHAT THAT DROPS, and these are open questions for Viraj, not decisions taken:

  - the spec's `action: ask | triage` two-shape output. Format 3 has a single
    shape and expresses the questioning round through follow_up_questions.
    These are different interaction models, not different spellings. The spec's
    version asks one question at a time with tappable `options`; format 3
    returns a list of questions alongside a provisional category. The demo beat
    is "structured follow-up questions", which both satisfy.
  - the spec's `watch_for`, required on yellow and green. Its content is what
    CP-GERD-002 is praised for in build-log.md, the escalation criteria that
    change the answer. It currently has to live inside next_steps.
  - the spec's `advice`, which maps onto next_steps.

REASONING IS OFF, so no pair carries a think block. training-data-format.md
section 3 says reasoning is on, but that section set its own trigger to cut it,
a red-flag case running longer than about 15 s. Measured 50.9 s with reasoning
against 14.4 s without, on Metal, which is the friendliest hardware in the
chain. The spec's own rule fires. CLAUDE.md hard constraint 5 records the
result. This is not a conflict, it is the spec resolving itself.

CITATION KEYS are whatever 01-data/citations.csv says, shaped CP-ACS-001. The
spec's source:topic:section format predates the freeze. Keys are immutable per
hard constraint 1, so the registry wins and the spec line is stale.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REGISTRY = REPO / "01-data" / "citations.csv"
CHUNKS = REPO / "01-data" / "chunks"

# Byte-identical across every pair and to what the app sends at inference.
# Extracted verbatim from spike/req-demo-shape.json rather than retyped, so the
# measured numbers stay reproducible. Do not edit here without editing the app.
SYSTEM_PROMPT = (HERE / "system_prompt.txt").read_text(encoding="utf-8")

# The assistant turn. Mirrors response_format.json_schema.schema in
# spike/req-demo-shape.json exactly. No maxLength anywhere, per hard
# constraint 3: it truncates mid-token and corrupts strings.
ASSISTANT_SCHEMA = {
    "type": "object",
    "properties": {
        "urgency": {"type": "string", "enum": ["red", "yellow", "green"]},
        "rationale": {"type": "string"},
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "next_steps": {"type": "array", "items": {"type": "string"}},
        "citations": {"type": "array", "items": {"type": "string"}},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["urgency", "rationale", "red_flags", "next_steps",
                 "citations", "follow_up_questions"],
    "additionalProperties": False,
}

REQUIRED_FIELDS = tuple(ASSISTANT_SCHEMA["required"])
URGENCIES = ("red", "yellow", "green")

# Marker the scaffolder writes into every slot a human or the generation
# session must fill. Nothing carrying it may be frozen.
TODO = "TODO"


def build_human_turn(profile: str, symptoms: str, reference_keys, chunk_text_by_key,
                     timeline: str = None) -> str:
    """The inference-time human turn, block order fixed.

    reference_keys in order. An empty list writes `none`, which is the case
    that teaches the model to decline rather than invent, per spec 4.1.
    CP-RISK-014 and MED-ANTICOAG-007 are NOT from this case, whatever older
    notes say: they were placeholder chunk keys in the spike request
    (spike/req-final.json), which the model copied back. Corrected 2026-09-29.
    """
    parts = [f"[PATIENT PROFILE]\n{profile}\n[/PATIENT PROFILE]"]
    if timeline is not None:
        parts.append(f"[SYMPTOM TIMELINE]\n{timeline}\n[/SYMPTOM TIMELINE]")
    parts.append(f"[SYMPTOMS]\n{symptoms}\n[/SYMPTOMS]")
    if reference_keys:
        body = "\n\n".join(f"[{k}]\n{chunk_text_by_key[k].strip()}" for k in reference_keys)
    else:
        body = "none"
    parts.append(f"[RETRIEVED CONTEXT]\n{body}\n[/RETRIEVED CONTEXT]")
    return "\n\n".join(parts)


def load_registry():
    """key -> row, from the frozen registry. Hard constraint 9's source of truth."""
    import csv
    with open(REGISTRY, encoding="utf-8") as f:
        return {r["key"]: r for r in csv.DictReader(f)}


def load_chunk_texts():
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(CHUNKS.glob("*.txt"))}


def reference_keys_in(human_turn: str):
    """Keys actually present in this pair's RETRIEVED CONTEXT block.

    Parsed from the block rather than carried alongside it, so the check is
    against what the model saw and not against what the generator intended.
    """
    import re
    m = re.search(r"\[RETRIEVED CONTEXT\]\n(.*?)\n\[/RETRIEVED CONTEXT\]",
                  human_turn, re.DOTALL)
    if not m:
        return None
    body = m.group(1)
    if body.strip() == "none":
        return []
    return re.findall(r"^\[([A-Z0-9-]+)\]$", body, re.MULTILINE)


if __name__ == "__main__":
    reg = load_registry()
    txt = load_chunk_texts()
    print(f"registry {len(reg)} keys, chunks {len(txt)} files")
    assert set(reg) == set(txt), "registry and chunk files disagree"
    demo = build_human_turn(
        "age: 58, sex: female\nconditions: none\nmedications: none",
        "Placeholder.", ["CP-ACS-001", "CP-ACS-003"], txt)
    assert reference_keys_in(demo) == ["CP-ACS-001", "CP-ACS-003"]
    assert reference_keys_in(build_human_turn("p", "s", [], txt)) == []
    print(f"system prompt {len(SYSTEM_PROMPT)} chars, "
          f"schema fields {list(ASSISTANT_SCHEMA['properties'])}")
    print("self-test passed.")
