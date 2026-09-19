#!/usr/bin/env python3
"""
Discrimination test.

The single most important unanswered question in this project: can the model
say anything other than red? Six spike runs, one cardiac case, six reds. A
model that always returns red would have scored 6/6.

This runs one case per triage category against a local llama-server and reports
the distribution. It does not need retrieval, the fine-tune, or the app. It
needs the model file and a server.

    llama-server -m 03-model/base/<file>.gguf --jinja -np 1 -ngl 0 -c 4096 --port 8080
    python eval/discrimination_test.py

Two variants, and the difference between them is the whole point:

    --chunks matched    each case gets chunks appropriate to its condition
    --chunks red-only   every case gets the cardiac chunks

If the model returns red for everything under `matched`, the model cannot
discriminate. If it discriminates under `matched` but goes all-red under
`red-only`, the problem is retrieval and corpus balance, not the model. Those
are different bugs with different fixes, and right now you cannot tell them
apart.

Chunk text is loaded from ../chunks/ by citation key. Run build_corpus.py first.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
CHUNKS = HERE.parent / "chunks"
ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"

# Reconcile with the real schema in steelhacks-project-spec.md before trusting
# these results. Deliberately NO maxLength anywhere: the spike showed it
# truncates mid-token and corrupts strings. Brevity is a prompt rule.
SCHEMA = {
    "type": "object",
    "properties": {
        "urgency": {"type": "string", "enum": ["red", "yellow", "green"]},
        "rationale": {"type": "string"},
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["urgency", "rationale", "red_flags", "follow_up_questions", "citations"],
    "additionalProperties": False,
}

SYSTEM = """You are an offline triage assistant using the WHO Interagency Integrated Triage Tool.
Assign exactly one category: red, yellow, or green.

red    = time-critical, needs emergency care now
yellow = urgent, needs to be seen but not immediately
green  = non-urgent, can be managed with self-care and watchful waiting

Rules:
- red_flags holds only findings that raise urgency, each with its discriminating
  qualifier, not the bare symptom. "Central pressure-like pain at rest beyond 20
  minutes", not "chest pressure". Keep each under 15 words.
- rationale holds risk factors and modifiers. Do not put them in red_flags.
- follow_up_questions MUST be empty when urgency is red. A red verdict means call
  for emergency help now; there is no questioning round.
- Never ask for information already present in the profile or timeline.
- Cite only the citation keys provided. Never invent one."""


# Opt-in via --green-criterion. Kept separate from SYSTEM rather than edited
# into it so the baseline stays byte-comparable and the delta is attributable.
#
# WHY. green-gerd returns yellow in every run recorded: matched, red-only,
# warm, cold, and with CP-GERD-002 ablated out. Its own rationale on the
# ablated run read "GERD symptoms present, no red flags, can be managed with
# OTC meds and lifestyle changes", which is the definition of green in the
# prompt above, emitted alongside the label yellow. The model reaches the green
# conclusion and declines to commit to the green label, so this is a
# calibration gap and not a knowledge or retrieval gap. If one prompt line
# closes it, the training pairs get to encode a behaviour that already works
# instead of fighting one that does not.
GREEN_CRITERION = """
- green is the correct answer, not a fallback. Assign green when no red flag is
  present and self-care or over-the-counter treatment is sufficient. Do not
  assign yellow to hedge a presentation that meets the green definition."""


CASES = [
    {
        "id": "red-acs",
        "expect": "red",
        "profile": "58-year-old man. History of high blood pressure and high cholesterol. Takes a statin.",
        "timeline": ("T+0:00 central chest pressure began while sitting watching television. "
                     "T+0:04 pain spread to the jaw. T+0:11 sweating and nausea. "
                     "T+0:26 pain unchanged after resting."),
        "symptom": "Heavy pressure in the middle of my chest that has not let up for almost half an hour. I feel sick and I am sweating.",
        "chunks": ["CP-ACS-001", "CP-ACS-002", "CP-ACS-003"],
    },
    {
        "id": "yellow-angina",
        "expect": "yellow",
        "profile": "61-year-old woman. Known coronary artery disease. Prescribed nitroglycerin.",
        "timeline": ("T+0:00 chest tightness began while climbing two flights of stairs. "
                     "T+0:03 sat down to rest. T+0:06 tightness resolved completely. "
                     "T+0:20 no further symptoms."),
        "symptom": "I got tight in the chest going up the stairs like I sometimes do. It went away once I sat down.",
        "chunks": ["CP-ANG-001", "CP-ANG-002"],
    },
    {
        "id": "green-gerd",
        "expect": "green",
        "profile": "29-year-old woman. No cardiac history. No regular medication.",
        "timeline": ("T+0:00 burning behind the breastbone began about 40 minutes after a large "
                     "late meal. T+0:15 worse on lying down. T+0:22 sour taste in the mouth. "
                     "T+0:35 eased after sitting upright."),
        "symptom": "Burning in my chest after dinner, worse when I lie flat, with a sour taste coming up.",
        "chunks": ["CP-GERD-001", "CP-GERD-002"],
    },
    {
        "id": "yellow-pleuritic",
        "expect": "yellow",
        "profile": "34-year-old woman. No cardiac history. Recent head cold, now resolved.",
        "timeline": ("T+0:00 sharp left-sided chest pain began at rest. "
                     "T+0:10 clearly worse on deep breath. T+0:25 easier sitting forward, "
                     "worse lying flat. T+1:30 unchanged, no relation to exertion."),
        "symptom": "Sharp pain in my left chest. It is much worse when I breathe in deeply and it eases if I sit up and lean forward. Walking around does not change it.",
        "chunks": ["CP-PERI-002", "CP-PLEU-001"],
    },
    {
        # PROBE, not a scored case. Reported separately.
        #
        # This was written against CP-COSTO-001, which does not exist: CP-COSTO
        # is a documented gap in sources.yaml. Rather than delete it, it is kept
        # as the unmatched-evidence probe, which is the most production-realistic
        # case in the set. With 22 chunks, most real queries will retrieve
        # loosely relevant material rather than the right material. It is also
        # the exact condition that produced invented citation keys earlier: the
        # model fabricates when it has nothing real to cite. So this measures
        # hallucination under weak retrieval, which is worth knowing on its own.
        #
        # Chunks below are what a similarity search would plausibly surface for
        # "sharp chest pain, worse pressing, worse deep breath" given that no
        # musculoskeletal content exists: the differential page and the two
        # pleuritic chunks. None of them describe costochondritis.
        "id": "probe-costo-unmatched",
        "expect": "green",
        "probe": True,
        "profile": "24-year-old man. No medical history. Moved apartment yesterday.",
        "timeline": ("T+0:00 sharp left-sided chest pain noticed on waking. "
                     "T+0:05 worse when pressing the area. T+0:08 worse on deep breath. "
                     "T+2:00 unchanged, no other symptoms."),
        "symptom": "Sharp pain on the left side of my chest. It hurts more when I press on it or take a deep breath.",
        "chunks": ["CP-DIFF-001", "CP-PERI-002", "CP-PLEU-001"],
    },
]


# RETRIEVAL ANSWER KEYS. FROZEN 2026-09-17, APPROVED BY VIRAJ.
#
# `chunks` above is what this harness FEEDS THE MODEL. `retrieval_key` is what a
# correct retriever SHOULD RETURN. They are deliberately separate fields:
# overwriting `chunks` would change what every triage run puts in the prompt,
# which is a much bigger blast radius than a retrieval score.
#
# WHY THESE EXIST. The `chunks` lists were hand-assigned when this file was
# written and were never reviewed. Every eval in this project has used them as
# the `matched` condition. At least one is wrong: red-acs expects CP-ACS-002,
# which is about SILENT, asymptomatic heart attacks, for a case with central
# pressure, jaw radiation, sweating and nausea. No retriever should return it,
# and it has been scored as a miss all day.
#
# PROVENANCE. Drafted by Claude after reading all 22 chunks on 2026-09-17, on
# Viraj's explicit instruction to mark them, then reviewed and APPROVED by Viraj
# the same day with two changes: CP-ANG-002 promoted to required on
# yellow-angina, and CP-PLEU-001 confirmed optional on yellow-pleuritic.
# Reasoning is recorded per case below.
#
# These are now the answer key. Unlike the `chunks` lists they replace, they
# have been read by a human against the chunk text. Changing one is a clinical
# decision, not a tuning knob, and a retrieval change that needs a key change to
# look good is not a retrieval improvement.
RETRIEVAL_KEYS = {
    # Textbook ACS. CP-ACS-003 is the symptom list and matches almost term for
    # term: centre-of-chest pain, jaw, sweating, nausea. CP-ACS-005 carries the
    # discriminator this case turns on, that heart attack pain does NOT go away
    # with rest while angina does, and the timeline says unchanged after resting.
    # DROPPED CP-ACS-001, a caveat paragraph about heart attacks that do not
    # present classically, which is the opposite of this florid presentation.
    # DROPPED CP-ACS-002, silent heart attacks, wrong for a symptomatic case.
    # DROPPED CP-ACS-004 deliberately despite being the correct disposition
    # content: it says "Never delay calling 9-1-1, taking aspirin or doing
    # anything else", and feeding that invites the exact next_steps aspirin
    # instruction constraint 12 exists to drop. The guard would catch it; better
    # not to invite it.
    "red-acs": ["CP-ACS-003", "CP-ACS-005"],

    # Stable angina: exertional onset, resolved completely with rest, known CAD.
    # CP-ANG-001 states the discriminator outright, "Symptoms often go away with
    # rest and return when you are active". CP-ACS-005 is the angina-versus-heart
    # -attack contrast and is arguably the single most relevant chunk in the
    # corpus for this case.
    # CP-ANG-002 is REQUIRED, promoted by Viraj 2026-09-17. It is the most
    # expensive chunk in the corpus at 231 tokens and it earns that: the call
    # this case turns on is stable versus unstable angina, and CP-ANG-002 is the
    # only chunk that frames angina as a warning sign of raised heart attack
    # risk rather than describing one episode. Without it the retrieved context
    # can support "this resolved, so it is fine", which is the under-call the
    # category mix exists to prevent.
    "yellow-angina": ["CP-ANG-001", "CP-ACS-005", "CP-ANG-002"],

    # CP-GERD-001 describes this case almost verbatim: burning behind the
    # breastbone, regurgitation, tasting stomach acid. CP-GERD-002 is the alarm
    # feature list, and it is what makes this GREEN rather than yellow, because
    # the case has none of them. Retrieval needs the rule-out, not just the match.
    # DROPPED CP-GERD-003, causes of GERD, which does not bear on triage.
    # CP-PERI-002 SHOULD NOT BE RETURNED for this case. Retrieval currently
    # returns it anyway.
    "green-gerd": ["CP-GERD-001", "CP-GERD-002"],

    # Positional, worse on inspiration, eased leaning forward, at rest, after a
    # recent viral illness. That is pericarditis, and CP-PERI-002 describes it
    # almost word for word, so it IS the right chunk here even though its
    # "Fast heartbeat / Fever" lines are the ones the model copied onto a patient
    # who had neither. That is a guard problem, not a key problem, and this is
    # the ONE case where the chunk belongs. CP-PERI-001 supplies the post-viral
    # link that the resolved head cold points at.
    # CP-PLEU-001 is OPTIONAL, confirmed by Viraj 2026-09-17: the pleurisy
    # differential, 156 tokens of which one line is relevant. Nice to have,
    # not scored against, and not a miss when absent.
    "yellow-pleuritic": ["CP-PERI-002", "CP-PERI-001"],

    # DELIBERATELY EMPTY AND UNSCORED. No chunk in the corpus describes
    # costochondritis; CP-COSTO is a documented gap in sources.yaml. Any key here
    # would be a guess at what similarity search surfaces rather than a claim
    # about what is right, and scoring it would turn a known corpus gap into a
    # retrieval number. Unscored for retrieval, as it is already unscored for
    # triage.
    "probe-costo-unmatched": [],
}

# Cases where a chunk must NOT be returned, stated positively because "absent
# from the key" and "wrong to return" are different claims. CP-PERI-002 is
# currently returned for 4 of 5 cases and it is the measured origin of the
# fabrication in hard constraint 11.
MUST_NOT_RETRIEVE = {
    "red-acs": ["CP-PERI-002"],
    "green-gerd": ["CP-PERI-002"],
    "yellow-angina": ["CP-PERI-002"],
}

def load_registry_keys():
    """Every citation key that actually exists, per hard constraint 9."""
    import csv
    reg = HERE.parent / "citations.csv"
    if not reg.exists():
        return None
    with open(reg, encoding="utf-8") as f:
        return {row["key"] for row in csv.DictReader(f)}


def load_chunks(keys, fallback_keys=None):
    out, missing = [], []
    for k in (fallback_keys or keys):
        p = CHUNKS / f"{k}.txt"
        if p.exists():
            out.append(f"[{k}]\n{p.read_text(encoding='utf-8').strip()}")
        else:
            missing.append(k)
    return out, missing


def build_prompt(case, chunk_texts):
    return (
        f"PROFILE\n{case['profile']}\n\n"
        f"TIMELINE\n{case['timeline']}\n\n"
        f"RETRIEVED CONTEXT\n" + "\n\n".join(chunk_texts) + "\n\n"
        f"PATIENT SAYS\n{case['symptom']}"
    )


def run_case(case, chunk_texts, timeout, system=SYSTEM, thinking=False):
    body = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": build_prompt(case, chunk_texts)},
        ],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "triage", "schema": SCHEMA}},
        "temperature": 0.0,
        # Every inference independent. Measured 2026-09-15: with the prefix
        # cache live, red-only scored 2/4 on a warm server and 3/4 on a cold
        # one, with yellow-pleuritic crossing a category boundary, at
        # temperature 0.0. Identical input to red-acs emitted 211 completion
        # tokens warm and 226 cold. llama.cpp reuses cached prefixes across
        # differing cache states and the numerics are not bit-identical, so a
        # run's result depended on what the server had served before it. That
        # is fatal for an eval and it invalidated conclusions drawn from single
        # runs. Turning the cache off costs full prompt eval on every case,
        # about 35 s, which is irrelevant for a test and is the whole point.
        # Do not turn this back on to make the suite faster.
        "cache_prompt": False,
        # Reasoning OFF, as shipped (hard constraint 5), with the same switch
        # every spike request sends. Found 2026-09-17: this body never sent
        # it, so every run before that date had reasoning ON, with the trace
        # in reasoning_content where nothing here looked. Measured: red-acs
        # spent 226 completion tokens on a 586-character trace plus the JSON,
        # against 80 tokens without, and green-gerd went from yellow with
        # reasoning to red without. --thinking restores the old behaviour so
        # those runs stay reproducible. It is not the shipping config.
        "chat_template_kwargs": {"enable_thinking": thinking},
    }
    r = requests.post(ENDPOINT, json=body, timeout=timeout)
    r.raise_for_status()
    payload = r.json()
    message = payload["choices"][0]["message"]
    usage = payload.get("usage", {})
    usage["reasoning_chars"] = len(message.get("reasoning_content") or "")
    return json.loads(message["content"]), usage


def run_suite(args, system, cases, label=""):
    """One pass over the suite. Returns {case_id: verdict} plus the rows."""
    red_chunks = CASES[0]["chunks"]
    registry = load_registry_keys()
    if registry is None:
        print("WARNING: no citations.csv, cannot validate citation keys\n")
    results, got, probes, verdicts = [], Counter(), [], {}

    reasoning = "ON (--thinking, NOT the shipping config)" if args.thinking else "off"
    print(f"mode: {args.chunks}, reasoning {reasoning}{label}\n")
    for case in cases:
        keys = red_chunks if args.chunks == "red-only" else case["chunks"]
        texts, missing = load_chunks(case["chunks"], keys)
        if missing:
            print(f"  {case['id']:<22} SKIP, missing chunks: {', '.join(missing)}")
            continue
        try:
            out, usage = run_case(case, texts, args.timeout, system, args.thinking)
        except Exception as e:
            print(f"  {case['id']:<22} ERROR {e}")
            verdicts[case["id"]] = "ERROR"
            continue

        urgency = out.get("urgency", "?")
        verdicts[case["id"]] = urgency
        is_probe = case.get("probe", False)
        if not is_probe:
            got[urgency] += 1
        ok = "PASS" if urgency == case["expect"] else "FAIL"

        # The follow-up convention is app logic plus a training convention.
        # The schema will not enforce it, so check it here.
        fq = out.get("follow_up_questions") or []
        violation = bool(urgency == "red" and fq)
        conv = "  [VIOLATION: questions on a red]" if violation else ""

        # Hard constraint 9: every key must resolve against the registry.
        cites = out.get("citations", []) or []
        invented = [c for c in cites if registry is not None and c not in registry]
        supplied = set(keys)
        unsupplied = [c for c in cites
                      if registry is not None and c in registry and c not in supplied]

        tag = "PROBE" if is_probe else ok
        print(f"  {case['id']:<22} expect={case['expect']:<6} got={urgency:<6} {tag}{conv}")
        # The content, not just the count. Saved runs recorded `red_flags=1`,
        # so answering "was that finding actually in the case" on 2026-09-17
        # meant re-running the model. Same lesson as saving run output at all.
        rf = out.get("red_flags") or []
        print(f"       tokens={usage.get('completion_tokens','?')} "
              f"red_flags={len(rf)} "
              f"reasoning_chars={usage['reasoning_chars']}")
        if rf:
            print(f"       red_flags_text={rf}")
        # The switch fails silently if a template ignores it, which is how
        # this harness ran with reasoning on for its whole life. Say so.
        if usage["reasoning_chars"] and not args.thinking:
            print("       REASONING LEAKED: enable_thinking=false was sent "
                  "and a trace came back anyway")
        print(f"       citations={cites}")
        print(f"       rationale={out.get('rationale','')}")
        if invented:
            print(f"       INVENTED KEYS (not in registry): {invented}")
        if unsupplied:
            print(f"       real but not supplied in context: {unsupplied}")

        row = (case, out, ok, invented, violation)
        (probes if is_probe else results).append(row)

    print(f"\ndistribution (scored cases only): {dict(got)}")

    all_rows = results + probes
    tot_inv = sum(len(r[3]) for r in all_rows)
    print(f"invented citation keys across all cases: {tot_inv}")
    if tot_inv:
        for case, _, _, inv, _ in all_rows:
            if inv:
                print(f"  {case['id']:<22} {inv}")
    viol = [r[0]['id'] for r in all_rows if r[4]]
    print(f"follow_up_questions non-empty on a red: {viol or 'none'}")

    if probes:
        print("\n--- unmatched-evidence probe, NOT scored ---")
        for case, out, ok, inv, _ in probes:
            print(f"  {case['id']}: expected {case['expect']}, got {out.get('urgency')} ({ok})")
            print(f"    No chunk in the corpus describes this condition. Chunks supplied")
            print(f"    were loosely relevant only. Invented keys: {inv or 'none'}")
    if len(got) == 1 and results:
        only = next(iter(got))
        print(f"\nEVERY CASE RETURNED {only.upper()}. The model is not discriminating.")
        if args.chunks == "matched":
            print("Next: re-run with --chunks red-only. If that changes nothing, the")
            print("problem is the model or the prompt. If matched discriminates and")
            print("red-only does not, the problem is corpus balance.")
    elif results:
        passed = sum(1 for _c, _o, ok, _i, _v in results if ok == "PASS")
        print(f"{passed}/{len(results)} correct. Discrimination is demonstrated, "
              f"accuracy is a separate question.")
    return verdicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", choices=["matched", "red-only"], default="matched",
                    help="matched = condition-appropriate chunks. "
                         "red-only = cardiac chunks for every case, to isolate corpus bias.")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--green-criterion", action="store_true",
                    help="append GREEN_CRITERION to the system prompt. Tests "
                         "whether the green gap is a calibration problem "
                         "closable at the prompt level.")
    ap.add_argument("--thinking", action="store_true",
                    help="reasoning ON, which is how every run before "
                         "2026-09-17 was made. Not the shipping config; "
                         "exists so those runs stay reproducible.")
    ap.add_argument("--only", metavar="CASE_ID",
                    help="run a single case by id")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run the whole suite N times. With cache_prompt off "
                         "the verdicts should be identical every time; if they "
                         "are not, nothing this harness reports is a fact.")
    args = ap.parse_args()

    if not CHUNKS.exists() or not any(CHUNKS.glob("*.txt")):
        sys.exit(f"No chunks in {CHUNKS}. Run build_corpus.py fetch/chunk/freeze first.")

    cases = CASES
    if args.only:
        cases = [c for c in CASES if c["id"] == args.only]
        if not cases:
            sys.exit(f"no case `{args.only}`. Have: "
                     f"{', '.join(c['id'] for c in CASES)}")

    system = SYSTEM + (GREEN_CRITERION if args.green_criterion else "")
    if args.green_criterion:
        print("SYSTEM PROMPT: baseline plus GREEN_CRITERION\n")

    passes = []
    for n in range(1, args.repeat + 1):
        label = f", pass {n}/{args.repeat}" if args.repeat > 1 else ""
        passes.append(run_suite(args, system, cases, label))
        if n < args.repeat:
            print()

    if args.repeat > 1:
        print(f"\n{'='*60}")
        print(f"STABILITY ACROSS {args.repeat} PASSES, cache_prompt off")
        unstable = []
        for cid in passes[0]:
            seen = [p.get(cid) for p in passes]
            mark = "stable" if len(set(seen)) == 1 else "UNSTABLE"
            if mark == "UNSTABLE":
                unstable.append(cid)
            print(f"  {cid:<22} {' '.join(f'{v:<7}' for v in seen)} {mark}")
        if unstable:
            print(f"\n{len(unstable)} case(s) moved across passes: "
                  f"{', '.join(unstable)}.")
            print("Disabling the prefix cache did NOT make this eval "
                  "deterministic. Any single-run finding is inside the noise.")
        else:
            print("\nEvery verdict identical on every pass. Results from this "
                  "harness are now reproducible,")
            print("and the earlier warm-versus-cold divergence is attributed "
                  "to prefix-cache state.")

    print("\nReal-world IITT distribution is roughly 7% red / 34% yellow / 59% green "
          "(PNG validation study). An eval set that is mostly red does not resemble use.")


if __name__ == "__main__":
    main()