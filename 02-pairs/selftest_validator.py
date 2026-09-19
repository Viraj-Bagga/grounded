#!/usr/bin/env python3
"""
Proves validate_pairs.py catches each bug it exists for, offline, no server.

    python 02-pairs/selftest_validator.py

Same discipline as 03-model/qlora_config.py deliberately re-adding gate_proj:
a check that has only been written is not a check that has been proven. Every
case below is a synthetic fixture with placeholder text, not a training pair,
and nothing here is clinical content.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pair_format import SYSTEM_PROMPT, build_human_turn, load_chunk_texts, load_registry
from validate_pairs import check_pair

TXT = load_chunk_texts()
REG = load_registry()


def pair(assistant, keys=("CP-GERD-001",), human_extra=None, system=SYSTEM_PROMPT,
         symptoms="Placeholder symptom text."):
    convs = [{"from": "system", "value": system},
             {"from": "human", "value": build_human_turn(
                 "age: 30, sex: female\nconditions: none\nmedications: none",
                 symptoms, list(keys), TXT)}]
    if isinstance(assistant, dict):
        assistant = json.dumps(assistant)
    convs.append({"from": "gpt", "value": assistant})
    if human_extra:
        convs.append({"from": "human", "value": human_extra})
    return {"id": "fixture", "conversations": convs}


GOOD = {
    "urgency": "green",
    "rationale": "Placeholder rationale sentence.",
    "red_flags": [],
    "next_steps": ["Placeholder step one.", "Placeholder step two."],
    "citations": ["CP-GERD-001"],
    "follow_up_questions": ["Placeholder question?"],
}


def run(name, obj, expect_error_substr=None, expect_warn_substr=None):
    E, W = check_pair(1, obj, REG)
    if expect_error_substr is None and expect_warn_substr is None:
        ok = not E and not W
        detail = f"errors={E} warnings={W}"
    elif expect_error_substr is not None:
        ok = any(expect_error_substr in m for m in E)
        detail = f"errors={E}"
    else:
        ok = any(expect_warn_substr in m for m in W)
        detail = f"warnings={W}"
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        {detail}")
    return ok


def main():
    results = []
    print("baseline")
    results.append(run("clean pair produces nothing", pair(GOOD)))

    print("\nthe four rules Viraj named")
    results.append(run(
        "invented citation key",
        pair({**GOOD, "citations": ["CP-RISK-014"]}),
        expect_error_substr="not in citations.csv"))
    results.append(run(
        "real key never supplied in the reference block",
        pair({**GOOD, "citations": ["CP-ACS-001"]}),
        expect_error_substr="never in this"))
    results.append(run(
        "think block present",
        pair("<think>placeholder</think>" + json.dumps(GOOD)),
        expect_error_substr="think block"))
    results.append(run(
        "follow_up_questions non-empty on red",
        pair({**GOOD, "urgency": "red", "red_flags": ["Placeholder finding at rest beyond 20 minutes"],
              "follow_up_questions": ["Placeholder question?"]}),
        expect_error_substr="follow_up_questions on a red"))
    results.append(run(
        "red_flag of 15 words or more",
        pair({**GOOD, "red_flags": [" ".join(["word"] * 15) + " at rest"]}),
        expect_error_substr="must be under 15"))
    results.append(run(
        "red_flag is a bare symptom",
        pair({**GOOD, "red_flags": ["Chest pain"]}),
        expect_error_substr="bare symptom"))
    results.append(run(
        "red_flag with a qualifier is accepted",
        pair({**GOOD, "urgency": "yellow",
              "red_flags": ["Central pressure-like pain at rest beyond 20 minutes"]})))
    results.append(run(
        "red_flag with no recognised qualifier warns, does not error",
        pair({**GOOD, "urgency": "yellow", "red_flags": ["Vomiting blood"]}),
        expect_warn_substr="no recognised qualifier"))

    print("\ncontainer and train/serve skew")
    results.append(run(
        "system prompt drift",
        pair(GOOD, system=SYSTEM_PROMPT + " "),
        expect_error_substr="byte-identical"))
    results.append(run(
        "assistant value is not JSON",
        pair("Here is my answer: green."),
        expect_error_substr="does not parse as JSON"))
    results.append(run(
        "missing required field",
        pair({k: v for k, v in GOOD.items() if k != "next_steps"}),
        expect_error_substr="missing fields"))
    results.append(run(
        "extra field",
        pair({**GOOD, "category": "green"}),
        expect_error_substr="unexpected fields"))
    results.append(run(
        "urgency not lowercase enum",
        pair({**GOOD, "urgency": "GREEN"}),
        expect_error_substr="not one of"))
    results.append(run(
        "conversation does not end on an assistant turn",
        pair(GOOD, human_extra="[PATIENT PROFILE]\nx\n[/PATIENT PROFILE]\n\n"
                               "[SYMPTOMS]\ny\n[/SYMPTOMS]\n\n"
                               "[RETRIEVED CONTEXT]\nnone\n[/RETRIEVED CONTEXT]"),
        expect_error_substr="does not end on an assistant turn"))
    results.append(run(
        "unfilled TODO marker",
        pair({**GOOD, "rationale": "TODO"}),
        expect_error_substr="unfilled TODO"))
    results.append(run(
        "empty next_steps",
        pair({**GOOD, "next_steps": []}),
        expect_error_substr="next_steps is empty"))

    print("\nthe `none` reference case, which is what teaches declining")
    results.append(run(
        "reference none with citations is an error",
        pair({**GOOD, "citations": ["CP-GERD-001"]}, keys=()),
        expect_error_substr="reference block is `none`"))
    results.append(run(
        "reference none with empty citations is fine",
        pair({**GOOD, "citations": []}, keys=())))

    print("\nhard constraint 11, red_flags grounded in the case")
    results.append(run(
        "red_flag asserting a finding absent from the case warns",
        pair({**GOOD, "urgency": "yellow",
              "red_flags": ["Fever persisting beyond 5 days"]}),
        expect_warn_substr="never mention"))
    results.append(run(
        "the same finding present in the symptoms does not warn",
        pair({**GOOD, "urgency": "yellow",
              "red_flags": ["Fever persisting beyond 5 days"]},
             human_extra=None, symptoms="Placeholder text, fever since Tuesday.")))
    results.append(run(
        "a finding that appears ONLY in the retrieved chunk still warns",
        # CP-PERI-002 is three lines and two of them are `Fast heartbeat` and
        # `Fever`. This is the measured failure: the model read findings out of
        # the chunk and asserted them as the patient's.
        pair({**GOOD, "urgency": "yellow",
              "red_flags": ["Fast heartbeat with sharp pain worse on inspiration"],
              "citations": ["CP-PERI-002"]},
             keys=("CP-PERI-002",)),
        expect_warn_substr="never mention"))

    print("\nsoft shape checks")
    results.append(run(
        "red verdict with empty red_flags warns",
        pair({**GOOD, "urgency": "red", "follow_up_questions": []}),
        expect_warn_substr="empty red_flags"))
    results.append(run(
        "green verdict carrying red_flags warns",
        pair({**GOOD, "red_flags": ["Placeholder finding worse on exertion"]}),
        expect_warn_substr="carrying 1 red_flags"))

    n_ok = sum(results)
    print(f"\n{n_ok}/{len(results)} self-tests passed.")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
