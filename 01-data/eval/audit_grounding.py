#!/usr/bin/env python3
"""
Audit every saved run for ungrounded findings, by config.

    python 01-data/eval/audit_grounding.py            # summary by config
    python 01-data/eval/audit_grounding.py --detail   # plus every instance

THE CLASS BEING COUNTED. A red_flag or a rationale that asserts a clinical
finding the case never mentions. Measured origin, 2026-09-17: the format 3
probe returned red_flags ['fast heartbeat', 'fever'] on yellow-pleuritic, and
both strings are lines in CP-PERI-002, the chunk that case supplies. So the
grounding question is asked against the profile, timeline and symptom text
only, never against the retrieved chunk. Hard constraint 11.

It reuses ungrounded_findings() from 02-pairs/validate_pairs.py rather than
reimplementing the rule, so this audit and the pair validator cannot drift.

WHAT IT CAN AND CANNOT SEE.

  - red_flags CONTENT exists only in runs from 2026-09-17 onward. Before that
    the harness printed `red_flags=1`, a count with no text, so those runs
    cannot be audited for this at all. That is why the harness now prints the
    content.
  - rationale text is missing from the three earliest 2026-09-15 runs.
  - the lexicon knows about 20 findings. A fabrication it has no word for is
    invisible here, so these counts are a floor, not a total.

NEGATION. A rationale saying "no dyspnea" mentions a finding in order to rule
it out, which is correct behaviour, not a fabrication. Mentions preceded by a
negation cue are counted separately and excluded from the headline number.
red_flags entries are not negation-filtered: an entry in that list asserts the
finding by being there.
"""

import argparse
import ast
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "02-pairs"))
from discrimination_test import CASES, SYSTEM, GREEN_CRITERION  # noqa: E402
from validate_pairs import (FINDING_SYNONYMS, _mentions,  # noqa: E402
                            contradicted_findings, ungrounded_findings)

# PROMPT REVISION. Added 2026-09-17 because this script bucketed runs by
# (format, reasoning, chunks, criterion) and had no notion of which prompt text
# produced them. The moment `02-pairs/system_prompt.txt` was rewritten that
# afternoon, pre-fix, change-set-A and change-set-B format 3 runs all collapsed
# into one row and the table said the fabrication rate was unchanged when in
# fact it was three different prompts averaged together. A config is not a
# config without the prompt.
#
# Format 3 runs carry their prompt sha in a header comment. Format 2 does not
# use system_prompt.txt at all; its prompt is the SYSTEM constant in
# discrimination_test.py, so that is hashed live and will move on its own if
# anyone edits it.
PROMPT_SHA = re.compile(r"system_prompt\.txt\s+sha256\s+(?:[\w-]+\s+)?([0-9a-f]{64})")

PROMPT_LABELS = {
    "dafa139cb2136c568081acf05a187dc572cd990aa87beca46f3c1ddc5d25645e": "fmt3 pre-fix",
    "2427e6230e688197623e5f3db74159b8911c8a718a6355a3641bad6d005089ab": "fmt3 A ground+7/8",
    "ca631a3dedc8eb9a3aa71ce8eaffd1b19524fc17dd6f678b4c24c0e279b9400a": "fmt3 B +rule3",
    "871748eaada02a33c01bd88e8c07fd0a29aeb907d1f2163dfa0cdd8a2248eeaf": "fmt3 C rule7-cond",
    # B plus the worked-example fix: the analgesia line that taught a
    # medication instruction was replaced 2026-09-17. Rules unchanged from B.
    "102e751168f59c1a63e95ff6323aab29228ba6702f0bce1f77b76efd940b7956": "fmt3 B+example-fix",
    # Rule 4 rewritten 2026-09-17: a finding requiring emergency care now
    # forces red; findings that raise urgency without that support yellow.
    # Reopened deliberately to test whether rule 4 was mechanically
    # forcing red by converting any non-empty red_flags into a red.
    "26e4f4ff3e30c899d51f97877b5e7f90b16053c90c593954a04ab14b8b71a2b7": "fmt3 D rule4-rewrite",
}
# Runs made before the sha was recorded in the header. Both predate the rewrite.
PRE_FIX_FILES = {"2026-09-17-format3-probe.txt",
                 "2026-09-17-format3-probe-pass2.txt"}


def _fmt2_label(criterion):
    text = SYSTEM + (GREEN_CRITERION if criterion else "")
    return "fmt2 builtin " + hashlib.sha256(text.encode()).hexdigest()[:8]


def prompt_of(path, criterion, fmt):
    """Which prompt text produced this run."""
    if fmt == 2:
        return _fmt2_label(criterion)
    m = PROMPT_SHA.search(path.read_text(encoding="utf-8"))
    if m:
        return PROMPT_LABELS.get(m.group(1), f"fmt3 {m.group(1)[:8]}")
    if path.name in PRE_FIX_FILES:
        return PROMPT_LABELS["dafa139cb2136c568081acf05a187dc572cd990aa87beca46f3c1ddc5d25645e"]
    return "fmt3 UNRECORDED"

RUNS = HERE / "runs"
CASE_TEXT = {c["id"]: "\n".join([c["profile"], c["timeline"], c["symptom"]])
             for c in CASES}
# Timeline and symptoms without the profile, for the course and duration axes.
# The profile carries resolved past history and must not be read as the present
# complaint's course. See PRESENT_ONLY_AXES in validate_pairs.py.
CASE_PRESENT = {c["id"]: "\n".join([c["timeline"], c["symptom"]]) for c in CASES}

CASE_LINE = re.compile(r"^ {2}(\S+)\s+expect=(\w+)\s+got=(\w+)")
FIELD_LINE = re.compile(r"^\s+(rationale|red_flags_text|red_flags)=(.*)$")
# format3_probe.py prints the list at the end of the tokens line rather than on
# its own line, so it needs its own match.
RED_FLAGS_INLINE = re.compile(r"\bred_flags=(\[.*\])\s*$")
NEGATION = re.compile(r"\b(no|not|without|denies|denied|absent|negative for|"
                      r"none|never|lacks|lacking|rather than|instead of)\b",
                      re.IGNORECASE)
# Negation scopes over a whole list: "no crushing pressure, nausea, sweating,
# dizziness, or shortness of breath" negates all five, and the cue is nowhere
# near the last one. So the span searched runs from the clause break to the
# mention, not a fixed number of characters.
CLAUSE_BREAK = re.compile(r"[.;:!?]|\bbut\b|\bhowever\b|\balthough\b",
                          re.IGNORECASE)


def negated(text, phrase):
    """True if every mention of `phrase` sits under a negation cue."""
    for m in re.finditer(r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b",
                         text, re.IGNORECASE):
        start = 0
        for b in CLAUSE_BREAK.finditer(text[:m.start()]):
            start = b.end()
        if not NEGATION.search(text[start:m.start()]):
            return False        # at least one plain assertion of it
    return True


def split_findings(text, case_text):
    """(asserted, negated) canonical findings absent from the case text."""
    asserted, neg = [], []
    for canon in ungrounded_findings(text, case_text):
        variants = FINDING_SYNONYMS[canon]
        hit = [v for v in variants if _mentions(text, v)]
        (neg if all(negated(text, v) for v in hit) else asserted).append(canon)
    return asserted, neg


def config_of(path, reasoning, chunks, criterion):
    fmt = 3 if "format3" in path.name else 2
    return (f"format {fmt}", f"reasoning {reasoning}",
            f"chunks {chunks}", "green criterion" if criterion else "baseline",
            prompt_of(path, criterion, fmt))


def parse(path):
    """Yield (config, case_id, verdict, field, text) for every saved field."""
    # Reasoning state: from the mode line where present, else the file. Runs
    # before 2026-09-17 had no switch at all, so they are reasoning on.
    default_reasoning = "off" if "reasoning-off" in path.name or "format3" in path.name else "on"
    reasoning, chunks, criterion = default_reasoning, "matched", False
    case = verdict = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("############"):
            low = line.lower()
            if "reasoning off" in low:
                reasoning = "off"
            elif "reasoning on" in low:
                reasoning = "on"
            if "red-only" in low:
                chunks = "red-only"
            elif "matched" in low:
                chunks = "matched"
            if "green_criterion" in low:
                criterion = True
            continue
        if line.startswith("SYSTEM PROMPT: baseline plus GREEN_CRITERION"):
            criterion = True
            continue
        if line.startswith("mode:"):
            low = line.lower()
            chunks = "red-only" if "red-only" in low else "matched"
            if "reasoning off" in low:
                reasoning = "off"
            elif "reasoning on" in low:
                reasoning = "on"
            continue
        m = CASE_LINE.match(line)
        if m:
            case, verdict = m.group(1), m.group(3)
            continue
        m = RED_FLAGS_INLINE.search(line)
        if m and case and not FIELD_LINE.match(line):
            try:
                entries = ast.literal_eval(m.group(1))
            except (ValueError, SyntaxError):
                entries = []
            for entry in entries:
                if isinstance(entry, str) and entry.strip():
                    yield (config_of(path, reasoning, chunks, criterion), case,
                           verdict, "red_flags", entry)
            continue

        m = FIELD_LINE.match(line)
        if m and case:
            field, raw = m.group(1), m.group(2).strip()
            if field == "red_flags":
                try:
                    val = ast.literal_eval(raw)
                except (ValueError, SyntaxError):
                    continue
                if not isinstance(val, list):   # a bare count, no text saved
                    continue
                entries = val
            elif field == "red_flags_text":
                try:
                    entries = ast.literal_eval(raw)
                except (ValueError, SyntaxError):
                    continue
            else:
                try:
                    entries = [ast.literal_eval(raw)]
                except (ValueError, SyntaxError):
                    entries = [raw]
            kind = "rationale" if field == "rationale" else "red_flags"
            for entry in entries:
                if isinstance(entry, str) and entry.strip():
                    yield config_of(path, reasoning, chunks, criterion), case, verdict, kind, entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args()

    seen = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))  # cfg -> kind -> [obs, bad, negonly, contra]
    hits = defaultdict(lambda: [0, set()])   # identical output repeats across passes
    contras = defaultdict(lambda: [0, set()])
    for path in sorted(RUNS.glob("*.txt")):
        for cfg, case, verdict, kind, text in parse(path):
            ct = CASE_TEXT.get(case)
            if ct is None:
                continue
            asserted, neg = split_findings(text, ct)
            row = seen[cfg][kind]
            row[0] += 1
            if asserted:
                row[1] += 1
                key = (cfg, case, verdict, kind, tuple(asserted), text)
                hits[key][0] += 1
                hits[key][1].add(path.name)
            elif neg:
                row[2] += 1
            # Contradiction is scored independently of absence: an entry can be
            # clean on one and dirty on the other, and the angina case is.
            contra = contradicted_findings(text, ct, CASE_PRESENT.get(case))
            if contra:
                row[3] += 1
                ckey = (cfg, case, verdict, kind, tuple(sorted(set(contra))), text)
                contras[ckey][0] += 1
                contras[ckey][1].add(path.name)

    print("UNGROUNDED FINDINGS BY CONFIG")
    print("obs = fields with text saved. asserted = states a finding the case never mentions.")
    print("ruled-out = mentions one only to negate it, which is correct behaviour.")
    print("contra = asserts the opposite of something the case states. Scored separately:")
    print("         a synonym lexicon cannot see it, so `asserted` will read 0 on it.\n")
    print(f"{'config':<76} {'field':<11} {'obs':>4} {'asserted':>9} "
          f"{'ruled-out':>10} {'contra':>7}")
    for cfg in sorted(seen):
        for kind in ("red_flags", "rationale"):
            if kind not in seen[cfg]:
                continue
            obs, bad, neg, con = seen[cfg][kind]
            print(f"{' / '.join(cfg):<76} {kind:<11} {obs:>4} {bad:>9} "
                  f"{neg:>10} {con:>7}")

    total = sum(n for n, _ in hits.values())
    print(f"\n{total} instance(s) asserting an ungrounded finding, "
          f"{len(hits)} distinct:")
    for (cfg, case, verdict, kind, findings, text), (n, files) in sorted(
            hits.items(), key=lambda kv: -kv[1][0]):
        print(f"  {case} ({verdict}) {kind} asserts {list(findings)}  x{n}")
        print(f"      {' / '.join(cfg)}")
        print(f"      {', '.join(sorted(files))}")
        if args.detail:
            print(f"      {text!r}")

    ctotal = sum(n for n, _ in contras.values())
    print(f"\n{ctotal} instance(s) CONTRADICTING the case text, "
          f"{len(contras)} distinct:")
    for (cfg, case, verdict, kind, axes, text), (n, files) in sorted(
            contras.items(), key=lambda kv: -kv[1][0]):
        for axis, said, incase in axes:
            print(f"  {case} ({verdict}) {kind} says {axis}={said!r} "
                  f"but case says {incase!r}  x{n}")
        print(f"      {' / '.join(cfg)}")
        print(f"      {', '.join(sorted(files))}")
        print(f"      {text!r}")


if __name__ == "__main__":
    main()
