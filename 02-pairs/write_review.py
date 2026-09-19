#!/usr/bin/env python3
"""Render every frozen pair as a human-readable review file.

    python 02-pairs/write_review.py                      # -> review/FULL-REVIEW.txt
    python 02-pairs/write_review.py --out somewhere.txt

WHY THIS IS A SCRIPT AND NOT A ONE-OFF. `SAMPLE.txt` was written by hand on
2026-09-17 and every one of the six pairs it documents was cut the next day, so
the file now describes nothing that exists. A review file that cannot be
regenerated from the pairs goes stale silently, and a stale review file is worse
than none because it reads authoritative.

WHAT IT SHOWS AND WHY. Contrast sets are rendered as a shared prefix plus two
tails, which is the format that made the second sample readable: it is the only
layout where a second, unintended difference between the halves is visible
rather than something you have to hold in your head. Everything else is rendered
whole. RETRIEVED CONTEXT is deliberately omitted from the case blocks. It is
identical across a set by construction and it is the thing that must NOT be the
source of a finding, so putting it next to the answer invites exactly the
misreading constraint 11 exists to prevent. The citation keys are listed instead.
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "review" / "candidates-60.jsonl"

KIND_ORDER = ["contrast", "grounding", "underspecified", "standalone"]
KIND_TITLE = {
    "contrast": "CONTRAST SETS",
    "grounding": "GROUNDING",
    "underspecified": "UNDER-SPECIFIED",
    "standalone": "STANDALONE",
}
KIND_NOTE = {
    "contrast": (
        "Two halves that differ in ONE stated finding and nothing else. Read the\n"
        "shared block once, then the two tails. If anything other than the named\n"
        "discriminator differs, the set is broken. Constraint 14: the axis must\n"
        "quote a line from a chunk both halves cite, and that line is printed."),
    "grounding": (
        "The answer must cite the key that carries the criterion it applies, and\n"
        "must not assert a finding the case does not state. Check the red_flags\n"
        "against the SYMPTOMS block, not against the chunk list."),
    "underspecified": (
        "In scope but missing the fact that separates two categories. Rule 6 says\n"
        "assign the higher category and put the gap in follow_up_questions. These\n"
        "replaced the decline pairs, which were reframed on 2026-09-17."),
    "standalone": (
        "One case, one answer. The bulk of the set. Check urgency against the case\n"
        "and red_flags against the SYMPTOMS block."),
}

BLOCK = re.compile(r"\[([A-Z][A-Z ]*)\](.*?)\[/\1\]", re.S)


def blocks(human):
    """Case blocks, minus RETRIEVED CONTEXT. See the module docstring."""
    return [(n.strip(), t.strip()) for n, t in BLOCK.findall(human)
            if n.strip() != "RETRIEVED CONTEXT"]


def field(human, name):
    for n, t in blocks(human):
        if n == name:
            return t
    return ""


def shared_prefix(a, b):
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    # back up to a word boundary so the tails start on a whole word
    while i > 0 and not a[i - 1].isspace():
        i -= 1
    return a[:i]


def render_answer(ans, indent="  "):
    out = [f"{indent}urgency   : {ans['urgency'].upper()}"]
    out.append(f"{indent}rationale : {ans['rationale']}")
    for key, label in (("red_flags", "red_flags "),
                       ("next_steps", "next_steps"),
                       ("citations", "citations "),
                       ("follow_up_questions", "follow_ups")):
        vals = ans.get(key) or []
        if not vals:
            out.append(f"{indent}{label}: (empty)")
            continue
        out.append(f"{indent}{label}: {vals[0]}")
        for v in vals[1:]:
            out.append(f"{indent}            {v}")
    return "\n".join(out)


def render_pair(r, full=True):
    out = []
    keys = " ".join(r["reference_keys"])
    out.append("-" * 78)
    out.append(f"{r['id']}   target={r['target_category']}   "
               f"register={r['register']}")
    out.append(f"   chunks in context: {keys}")
    if r.get("underspecified_note"):
        out.append(f"   missing fact: {r['underspecified_note']}")
    out.append("")
    convs = r["conversations"]
    exchanges = [(convs[i], convs[i + 1]) for i in range(1, len(convs), 2)]
    for n, (human, gpt) in enumerate(exchanges, 1):
        tag = f"  TURN {n}" if len(exchanges) > 1 else "  CASE"
        out.append(tag)
        for name, text in blocks(human["value"]):
            if not full and name == "PATIENT PROFILE":
                continue
            out.append(f"    [{name}]")
            for line in text.splitlines():
                out.append(f"      {line.strip()}")
        out.append("")
        out.append("  ANSWER")
        out.append(render_answer(json.loads(gpt["value"]), indent="    "))
        out.append("")
    return "\n".join(out)


# Axis grounding, verified against the chunk text 2026-09-18. Keyed by the
# chunk family the set cites. Constraint 14 requires the quote, so it is stored
# here rather than paraphrased into the prose.
AXIS = {
    ("CP-ANG-001", "CP-ANG-002"): (
        "does the exertional tightness resolve on rest, or persist",
        'CP-ANG-001: "Symptoms often go away with rest and return when you are '
        'active or under stress."\n'
        '    CP-ANG-001: "Chest pain or discomfort that does not go away or '
        'occurs while you are\n    resting might be a sign of a heart attack."'),
    ("CP-GERD-001", "CP-GERD-002"): (
        "is there black tarry stool alongside the reflux",
        'CP-GERD-002 lists under signs of bleeding in the digestive tract: '
        '"stool that\n    contains blood or looks black and tarry."'),
    ("CP-PERI-001", "CP-PERI-002"): (
        "is there severe shortness of breath",
        'CP-PERI-001: "If you have chest pain or severe shortness of breath, or '
        'your symptoms\n    get worse, call 9-1-1 or seek medical help right '
        'away."'),
}


def render_contrast_sets(rows, out):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["register"], tuple(r["reference_keys"]))].append(r)
    order = {"green": 0, "yellow": 1, "red": 2}
    for n, (key, pair) in enumerate(sorted(groups.items()), 1):
        register, keys = key
        pair.sort(key=lambda r: order[r["target_category"]])
        axis, quote = AXIS.get(keys, ("UNKNOWN", "NO QUOTE ON FILE"))
        out.append("")
        out.append("#" * 78)
        out.append(f"# SET {n}   {keys[0].rsplit('-', 1)[0]}   register: {register}")
        out.append(f"# axis: {axis}")
        out.append("#" * 78)
        out.append("")
        out.append("  CONSTRAINT 14, the line that draws the distinction:")
        out.append(f"    {quote}")
        out.append("")
        syms = [field(r["conversations"][1]["value"], "SYMPTOMS") for r in pair]
        pre = shared_prefix(*syms) if len(syms) == 2 else ""
        if len(pre) > 20:
            out.append(f"  SHARED, identical in both halves ({len(pre)} characters):")
            for line in pre.strip().splitlines():
                out.append(f"    {line}")
            out.append("")
            for r, s in zip(pair, syms):
                out.append(f"  {r['id']} ({r['target_category']}) continues:  "
                           f"{s[len(pre):].strip()}")
        else:
            out.append("  NO SHARED PREFIX. The halves diverge from the first "
                       "word, so check by hand.")
        out.append("")
        for r in pair:
            out.append(render_pair(r))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "review" / "FULL-REVIEW.txt"))
    args = ap.parse_args()

    rows = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    by_kind = defaultdict(list)
    for r in rows:
        by_kind[r["kind"]].append(r)

    out = []
    out.append("=" * 78)
    out.append("FULL REVIEW  -  all %d frozen pairs" % len(rows))
    out.append("written 2026-09-18  |  PIPELINE-TEST DATA, NOT TRAINING DATA")
    out.append("=" * 78)
    out.append("""
WHAT THESE ARE. The 45 pairs frozen on 2026-09-18 as
02-pairs/pairs/PIPELINE-TEST-{train,heldout}.jsonl. They were frozen to prove
the training pipeline runs, NOT because the content was signed off. Nothing here
has been approved. Read them as drafts.

WHY THIS FILE REPLACES SAMPLE.txt. SAMPLE.txt documents P0001, P0005, P0006,
P0010, P0033 and P0038. All six were cut on 2026-09-18 with sets C04, C05, C06,
C09, C10, C11 and C12. It covers NOTHING that survives, so the whole of the
frozen set is printed here rather than a remainder.

THE FIVE SURVIVING CONTRAST SETS RUN ON THREE AXES, all three re-verified
against the chunk text on 2026-09-18 and all three passing constraint 14. The
quote is printed above each set so the claim can be checked rather than trusted.

WHAT TO LOOK FOR, in rough order of how much damage it does:

  1. A red_flag or a rationale clause stating a finding the SYMPTOMS block does
     not state, or contradicts. Constraint 11. This is the failure that reads
     exactly like a real finding and that nothing downstream can catch.
  2. A second difference inside a contrast set. The set then teaches the wrong
     thing and no amount of careful wording elsewhere fixes it.
  3. next_steps instructing a medication dose. Constraint 12, and the fastest
     thing a medical-track judge finds.
  4. follow_up_questions present on a red verdict. Constraint 4.
  5. A cited key whose chunk does not carry the criterion being applied.

RETRIEVED CONTEXT is deliberately not printed. It is identical across a set by
construction, and it is the thing a finding must NEVER come from, so showing it
beside the answer invites the exact misreading item 1 is about. The keys are
listed on each pair instead.

WHAT THE AUTOMATED CHECKS SAY, so you are not reading blind:
  validate_pairs.py  45 pairs, 0 errors, 0 warnings.
  constraint 12 guard (medication in next_steps)  0 hits.
  constraint 4  (follow_ups on a red)             0 hits.
  constraint 11 guard (red_flags)                 0 hits, after the fix below.

>> FIXED 2026-09-18. Recorded because P0042 is where you would have hit it.

   Before the fix, guards.screen_red_flags DROPPED this red flag from P0042:
     "Chest tightness unchanged after 30 minutes at rest"
   on a case that reads:
     "Chest got tight walking up the hill ... Sat on the wall. It has not
      shifted, it has been half an hour now."

   The exertion axis in validate_pairs.CONTRADICTION_AXES treats "walking up"
   (pole: exertional) and "at rest" (pole: non exertional) as contradictory. It
   is conflating WHAT BROUGHT THE PAIN ON with WHAT THE PATIENT IS DOING NOW.
   Exertional onset plus persistence at rest is not a contradiction, it is the
   evolving-ACS pattern, and it is the exact discriminator the CP-ANG sets are
   built on.

   It was phrasing-dependent, which is worse than consistent: "unchanged after
   30 minutes at rest" dropped, "unchanged after 30 minutes" kept, "after
   sitting down" kept. So whether the demo showed the correct red flag turned on
   which words the model happened to pick.

   THE FIX: `exertion` is retired from CONTRADICTION_AXES. Three axes remain,
   course, duration and rest response. The vocabulary and the reasoning are kept
   in validate_pairs.RETIRED_AXES so nobody re-adds it. `rest response` stays
   and is legitimate, because both its poles describe the same question, how the
   pain responded to rest, rather than straddling onset and current state.

   Verified live on the demo path, not just in the suites. A case reading
   "Chest tightness came on while I was walking up the stairs ... sat down to
   rest but it has not gone away ... half an hour now" returned red with two
   red flags, "chest tightness persists at rest for 30 minutes" and "persistent
   chest pain at rest". Both kept, nothing dropped. Replaying the retired axis
   against that same output drops BOTH, which would have left a red verdict with
   no supporting red flags on a textbook evolving ACS.
""")

    for kind in KIND_ORDER:
        group = by_kind.get(kind, [])
        if not group:
            continue
        out.append("")
        out.append("=" * 78)
        n_sets = f", {len(group)//2} sets" if kind == "contrast" else ""
        out.append(f"{KIND_TITLE[kind]}   ({len(group)} pairs{n_sets})")
        out.append("=" * 78)
        out.append(KIND_NOTE[kind])
        if kind == "contrast":
            render_contrast_sets(group, out)
        else:
            out.append("")
            for r in sorted(group, key=lambda r: r["id"]):
                out.append(render_pair(r))

    out.append("=" * 78)
    out.append("END. %d pairs: %s" % (
        len(rows), ", ".join(f"{k} {len(by_kind[k])}" for k in KIND_ORDER
                             if by_kind.get(k))))
    out.append("=" * 78)

    path = Path(args.out)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {path}  ({len(out)} lines, {len(rows)} pairs)")
    for k in KIND_ORDER:
        if by_kind.get(k):
            print(f"  {k:<16} {len(by_kind[k])}")


if __name__ == "__main__":
    main()
