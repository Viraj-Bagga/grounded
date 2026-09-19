#!/usr/bin/env python3
"""One case, format 3, NO retrieved chunks at all. A measurement, not a fix.

    python 01-data/eval/no_chunk_probe.py                        # yellow-angina, 2 passes
    python 01-data/eval/no_chunk_probe.py --only green-gerd --repeat 3

WHY THIS EXISTS. As of 2026-09-17 the prompt has been the lever three times,
change sets A, B and C, and the verdict distribution has not moved once: 1/4
every time, with yellow-angina red, green-gerd yellow and yellow-pleuritic red.
Fabrication fell with each change set. Discrimination did not budge.

That leaves the base model as the suspect, and this separates it from
everything else. Feeding the case text with `[RETRIEVED CONTEXT]\nnone` removes
the corpus from the experiment entirely. yellow-angina is the case to ask,
because it is the clearest under-call: a 61-year-old with known CAD whose
exertional tightness RESOLVED COMPLETELY with rest, which is stable angina and
a yellow.

  red with no chunks  -> the red bias is in the base model. Neither prompt work
                         nor corpus work touches it, and the fine-tune has to
                         carry category assignment on its own.
  not red             -> retrieved content is pushing the verdict, and corpus
                         balance is back on the table.

Either answer is worth knowing before 300 pairs get written.

An empty reference list is also the case spec 4.1 calls the decline-rather-than
-invent condition, and the measured origin of the CP-RISK-014 and
MED-ANTICOAG-007 fabrications, so watch the citations field too.

The prompt sha is printed into the output. Do not rely on a hand-written header
for it: audit_grounding.py had to special-case two files that predated this.
"""

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "02-pairs"))
from discrimination_test import CASES, ENDPOINT  # noqa: E402
from pair_format import (ASSISTANT_SCHEMA, REGISTRY, SYSTEM_PROMPT,  # noqa: E402
                         build_human_turn)
from validate_pairs import contradicted_findings, ungrounded_findings  # noqa: E402

PROMPT_PATH = HERE.parent.parent / "02-pairs" / "system_prompt.txt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="yellow-angina", metavar="CASE_ID")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    cases = [c for c in CASES if c["id"] == args.only]
    if not cases:
        sys.exit(f"no case `{args.only}`. Have: "
                 f"{', '.join(c['id'] for c in CASES)}")
    case = cases[0]

    with open(REGISTRY, encoding="utf-8") as f:
        registry = {r["key"] for r in csv.DictReader(f)}

    sha = hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()
    case_text = "\n".join([case["profile"], case["timeline"], case["symptom"]])
    case_present = "\n".join([case["timeline"], case["symptom"]])

    # reference_keys empty writes `none` into the RETRIEVED CONTEXT block.
    human = build_human_turn(case["profile"], case["symptom"], [], {},
                             timeline=case["timeline"])

    print(f"NO-CHUNK PROBE: {case['id']}, expect={case['expect']}, "
          f"{args.repeat} passes")
    print(f"system_prompt.txt sha256 {sha}")
    print("format 3, RETRIEVED CONTEXT = none, reasoning off, temperature 0.0, "
          "cache_prompt off\n")
    assert "[RETRIEVED CONTEXT]\nnone\n[/RETRIEVED CONTEXT]" in human, \
        "expected an empty retrieved-context block; build_human_turn changed"

    verdicts = Counter()
    for n in range(1, args.repeat + 1):
        body = {
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": human}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "triage",
                                                "schema": ASSISTANT_SCHEMA}},
            "temperature": 0.0,
            "max_tokens": 1024,
            "cache_prompt": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        r = requests.post(ENDPOINT, json=body, timeout=args.timeout)
        r.raise_for_status()
        p = r.json()
        msg = p["choices"][0]["message"]
        reasoning = msg.get("reasoning_content") or ""
        out = json.loads(msg["content"])

        urgency = out.get("urgency")
        verdicts[urgency] += 1
        tag = "PASS" if urgency == case["expect"] else "FAIL"
        cites = out.get("citations") or []
        invented = [c for c in cites if c not in registry]
        rf = out.get("red_flags") or []

        print(f"  pass {n}/{args.repeat}  expect={case['expect']:<6} "
              f"got={urgency:<6} {tag}   tokens={p['usage']['completion_tokens']} "
              f"reasoning_chars={len(reasoning)}")
        print(f"       red_flags={rf}")
        print(f"       rationale={out.get('rationale')!r}")
        print(f"       next_steps={out.get('next_steps')}")
        print(f"       citations={cites}")
        print(f"       follow_up_questions={out.get('follow_up_questions')}")
        if invented:
            print(f"       INVENTED KEYS (nothing was supplied to cite): {invented}")
        if cites and not invented:
            print("       NOTE: real registry keys cited with no context supplied")
        if urgency == "red" and out.get("follow_up_questions"):
            print("       [VIOLATION: questions on a red]")
        if reasoning:
            print("       REASONING LEAKED: enable_thinking=false was sent")
        for entry in rf + [out.get("rationale") or ""]:
            for f in ungrounded_findings(entry, case_text):
                print(f"       UNGROUNDED {f!r} in {entry[:60]!r}")
            for axis, said, incase in contradicted_findings(entry, case_text,
                                                            case_present):
                print(f"       CONTRADICTS {axis}: says {said!r}, "
                      f"case says {incase!r} in {entry[:60]!r}")

    print(f"\nverdicts across {args.repeat} passes: {dict(verdicts)}")
    if len(verdicts) == 1 and next(iter(verdicts)) == "red":
        print("RED WITH NOTHING RETRIEVED. The bias is in the base model, not in")
        print("the corpus and not in the retrieved chunk. Prompt and corpus work")
        print("do not reach it; the fine-tune has to carry category assignment.")
    elif case["expect"] in verdicts:
        print("Not red without chunks. Retrieved content is moving the verdict,")
        print("so corpus balance is back on the table.")


if __name__ == "__main__":
    main()
