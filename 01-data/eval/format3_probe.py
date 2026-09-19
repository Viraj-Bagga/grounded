#!/usr/bin/env python3
"""
The discrimination cases, sent the way the app will send them. A probe, not a
replacement for discrimination_test.py.

    python 01-data/eval/format3_probe.py              # matched chunks, one pass
    python 01-data/eval/format3_probe.py --only green-gerd

WHY. Found 2026-09-17: discrimination_test.py differs from the shipping request
in two ways, and every verdict it has recorded carries both.

  1. It did not send enable_thinking=false, so reasoning was on. Fixed in the
     harness the same day, with --thinking to reproduce the old runs.
  2. It still builds format 2, its own PROFILE / TIMELINE / PATIENT SAYS prompt
     with its own system prompt and a schema without next_steps. What ships is
     format 3, defined in 02-pairs/pair_format.py: a different system prompt
     with a worked green example, and rule 6, "assign the higher one" when the
     information cannot separate two categories.

This sends the same five cases with case content verbatim. The only changes
are the system prompt, the block format and the schema, all imported from
pair_format.py. It sends format 3 with reasoning off, matching
spike/req-demo-shape.json except temperature, which is 0.0 here for
repeatability where the demo request uses 0.2. The profiles stay in the cases'
prose rather than the app's compact "age: / conditions: / medications:" form,
because converting them would mean inventing fields the cases do not state.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "02-pairs"))
from discrimination_test import CASES, ENDPOINT  # noqa: E402
from pair_format import (ASSISTANT_SCHEMA, REGISTRY, SYSTEM_PROMPT,  # noqa: E402
                         build_human_turn, load_chunk_texts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", metavar="CASE_ID")
    args = ap.parse_args()

    texts = load_chunk_texts()
    with open(REGISTRY, encoding="utf-8") as f:
        registry = {r["key"] for r in csv.DictReader(f)}
    cases = [c for c in CASES if not args.only or c["id"] == args.only]
    if not cases:
        sys.exit(f"no case `{args.only}`")

    print("format 3 (02-pairs/pair_format.py), matched chunks, reasoning off, "
          "temperature 0.0, cache_prompt off\n")
    for case in cases:
        body = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_human_turn(
                    case["profile"], case["symptom"], case["chunks"], texts,
                    timeline=case["timeline"])},
            ],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "triage",
                                                "schema": ASSISTANT_SCHEMA}},
            "temperature": 0.0,
            "max_tokens": 1024,
            "cache_prompt": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        r = requests.post(ENDPOINT, json=body, timeout=600)
        r.raise_for_status()
        p = r.json()
        msg = p["choices"][0]["message"]
        reasoning = msg.get("reasoning_content") or ""
        try:
            out = json.loads(msg["content"])
        except json.JSONDecodeError as e:
            print(f"  {case['id']:<22} INVALID JSON ({e}), "
                  f"finish_reason={p['choices'][0].get('finish_reason')}")
            continue

        urgency = out.get("urgency")
        tag = "PROBE" if case.get("probe") else (
            "PASS" if urgency == case["expect"] else "FAIL")
        cites = out.get("citations") or []
        invented = [c for c in cites if c not in registry]
        unsupplied = [c for c in cites if c in registry and c not in case["chunks"]]
        print(f"  {case['id']:<22} expect={case['expect']:<6} got={urgency:<6} {tag}")
        print(f"       tokens={p['usage']['completion_tokens']} "
              f"reasoning_chars={len(reasoning)} red_flags={out.get('red_flags')}")
        print(f"       rationale={out.get('rationale')!r}")
        print(f"       next_steps={out.get('next_steps')}")
        print(f"       citations={cites}")
        print(f"       follow_up_questions={out.get('follow_up_questions')}")
        if invented:
            print(f"       INVENTED KEYS (not in registry): {invented}")
        if unsupplied:
            print(f"       real but not supplied in context: {unsupplied}")
        if urgency == "red" and out.get("follow_up_questions"):
            print("       [VIOLATION: questions on a red]")
        if reasoning:
            print("       REASONING LEAKED: enable_thinking=false was sent "
                  "and a trace came back anyway")


if __name__ == "__main__":
    main()
