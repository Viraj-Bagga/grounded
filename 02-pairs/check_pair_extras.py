#!/usr/bin/env python3
"""Checks on a candidates file that validate_pairs.py does not make.

    python 02-pairs/check_pair_extras.py review/candidates-120.jsonl

validate_pairs.py checks the container, the schema, the citation keys and the
red_flags shape. This checks the things that only exist because of decisions
taken after it was written:

  * QUOTES (constraint 14, generalised). Every pair written on 2026-09-19
    carries the verbatim lines that justify its verdict. Each must appear in the
    chunk it is attributed to, and that chunk must be in the pair's reference
    keys. Pairs written before that carry no quotes and are reported, not failed.
  * THE CONTRAST AXIS. Both halves must cite the chunk the axis quote comes
    from, share the same chunks and register, differ in verdict, and differ in
    case text. A set whose halves differ in more than the discriminator teaches
    the wrong thing, and one whose axis is not in a shared chunk is the failure
    constraint 14 exists for.
  * THE SCOPE FLOOR. A case below it is refused before the model sees it, so a
    pair teaching a verdict on it trains a state the app cannot reach.
  * THE EXCLUSIONS. Same reason: a pregnancy or child case is refused before
    generation.
  * THE APP GUARDS. screen_next_steps (constraint 12) and screen_red_flags
    (constraint 11) are run over every gold answer. A pair the app would edit on
    the way to the screen is a pair that teaches something the app will undo.
  * THE VERDICT SPREAD PER PREFIX. The top open item of epic 2: if every pair
    carrying a chunk shares one verdict, the model can read the verdict off the
    retrieval instead of off the case.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "04-retrieval"))

CHUNKS = REPO / "01-data" / "chunks"


def symptoms_of(turn):
    m = re.search(r"\[SYMPTOMS\]\n(.*?)\n\[/SYMPTOMS\]", turn, re.S)
    return m.group(1).strip() if m else ""


def case_text_of(turn):
    parts = []
    for block in ("PATIENT PROFILE", "SYMPTOM TIMELINE", "SYMPTOMS"):
        m = re.search(rf"\[{block}\]\n(.*?)\n\[/{block}\]", turn, re.S)
        if m:
            parts.append(m.group(1).strip())
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    args = ap.parse_args()
    path = Path(args.file) if Path(args.file).is_absolute() else HERE / args.file
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    text = {p.stem: p.read_text(encoding="utf-8") for p in CHUNKS.glob("*.txt")}
    problems, notes = [], []

    # --- quotes --------------------------------------------------------------
    quoted = [r for r in rows if r.get("quotes")]
    n_lines = 0
    for r in quoted:
        for key, lines in r["quotes"].items():
            if key not in r["reference_keys"]:
                problems.append(f"{r['id']}: quotes {key}, which is not in its reference keys")
            for line in lines:
                n_lines += 1
                if key in text and line not in text[key]:
                    problems.append(f"{r['id']}: not verbatim in {key}: {line[:60]!r}")
    print(f"== QUOTES: {len(quoted)} of {len(rows)} pairs carry them, {n_lines} lines checked")
    print(f"   {len(rows) - len(quoted)} older pairs carry none (written before the rule)")

    # --- contrast sets -------------------------------------------------------
    sets = defaultdict(list)
    for r in rows:
        if r.get("contrast_id"):
            sets[r["contrast_id"]].append(r)
    print(f"\n== CONTRAST SETS: {len(sets)}")
    for cid, halves in sorted(sets.items()):
        ok = True
        if len(halves) != 2:
            problems.append(f"{cid}: {len(halves)} halves, expected 2")
            continue
        a, b = halves
        if set(a["reference_keys"]) != set(b["reference_keys"]):
            problems.append(f"{cid}: halves cite different chunks")
            ok = False
        if a["register"] != b["register"]:
            problems.append(f"{cid}: halves are in different registers")
            ok = False
        if a["target_category"] == b["target_category"]:
            problems.append(f"{cid}: both halves are {a['target_category']}")
            ok = False
        sa, sb = (symptoms_of(x["conversations"][1]["value"]) for x in (a, b))
        if sa == sb:
            problems.append(f"{cid}: halves have identical case text")
            ok = False
        axis = a.get("axis_quote") or {}
        if not axis:
            notes.append(f"{cid}: no axis quote recorded (pair written before the rule)")
        for key, line in axis.items():
            for half in (a, b):
                if key not in half["reference_keys"]:
                    problems.append(f"{cid}: axis quote is from {key}, which {half['id']} does not cite")
                    ok = False
            if key in text and line not in text[key]:
                problems.append(f"{cid}: axis quote not verbatim in {key}: {line[:60]!r}")
                ok = False
        print(f"   {cid} {a['target_category']:>6}/{b['target_category']:<6} {'ok  ' if ok else 'BAD '} "
              f"{a.get('contrast_axis', '')[:58]}")

    # --- scope floor, exclusions, guards ------------------------------------
    from guards import (SCOPE_FLOOR, child_term, excluded_subject, screen_next_steps,
                        screen_red_flags, screen_follow_ups)
    from hybrid import HybridRetriever
    r_index = HybridRetriever()
    worst = (1.0, None)
    for row in rows:
        for i in range(1, len(row["conversations"]), 2):
            human, gpt = row["conversations"][i]["value"], row["conversations"][i + 1]["value"]
            sym, case = symptoms_of(human), case_text_of(human)
            cos = max(r_index._cosines(sym).values())
            # The floor is a FIRST-TURN gate. The app retrieves and scope-checks
            # on the opening message; a follow-up turn is not re-checked, by
            # constraint 8, so a low-scoring follow-up is not a broken pair.
            if i == 1:
                if cos < SCOPE_FLOOR:
                    problems.append(f"{row['id']}: below the scope floor at {cos:.3f}")
                worst = min(worst, (cos, row["id"]))
            elif cos < SCOPE_FLOOR:
                notes.append(f"{row['id']} turn {i // 2 + 1}: scores {cos:.3f}, under the floor, "
                             f"which is fine: follow-up turns are not scope-checked")
            if excluded_subject(case)[0]:
                problems.append(f"{row['id']}: trips the pregnancy exclusion, so the app refuses it")
            if child_term(sym):
                notes.append(f"{row['id']}: contains a child word ({child_term(sym)}), so the page would ask who it is for")
            a = json.loads(gpt)
            kept, dropped, rewritten = screen_next_steps(a.get("next_steps"))
            if dropped or rewritten:
                problems.append(f"{row['id']}: the app would edit a next step (constraint 12): "
                                f"{dropped or rewritten}")
            kept_rf, dropped_rf = screen_red_flags(a.get("red_flags"), case)
            if dropped_rf:
                problems.append(f"{row['id']}: the app would drop a red flag (constraint 11): "
                                f"{[d['entry'] for d in dropped_rf]}")
            kept_q, cleared = screen_follow_ups(a.get("urgency"), a.get("follow_up_questions"))
            if cleared:
                problems.append(f"{row['id']}: follow-up questions on a {a.get('urgency')} (constraint 4)")
    print(f"\n== SCOPE, EXCLUSIONS, APP GUARDS: floor {SCOPE_FLOOR}, lowest case {worst[0]:.3f} ({worst[1]})")

    # --- the spread that matters --------------------------------------------
    print("\n== VERDICT PER CITED PREFIX (a pair counts once under each prefix in its reference keys)")
    by_prefix = defaultdict(Counter)
    for row in rows:
        v = json.loads(row["conversations"][2]["value"])["urgency"]
        for pfx in {re.sub(r"-\d+$", "", k) for k in row["reference_keys"]}:
            by_prefix[pfx][v] += 1
    for pfx, cnt in sorted(by_prefix.items()):
        total = sum(cnt.values())
        cells = "  ".join(f"{v} {cnt[v]:>2}" for v in ("red", "yellow", "green"))
        print(f"   {pfx:<9} {total:>3} pairs  {cells}  "
              f"{'mixed' if len(cnt) > 1 else 'SINGLE COLOUR'}")
    single = [p for p, c in by_prefix.items() if len(c) == 1]
    print(f"   single-colour prefixes: {', '.join(sorted(single)) or 'none'}")

    mix = Counter(json.loads(r["conversations"][2]["value"])["urgency"] for r in rows)
    kinds = Counter(r["kind"] for r in rows)
    print(f"\n== MIX  red {mix['red']}  yellow {mix['yellow']}  green {mix['green']}  "
          f"({', '.join(f'{100 * mix[v] / len(rows):.0f}%' for v in ('red', 'yellow', 'green'))})")
    print(f"   kinds: {dict(kinds)}")
    print(f"   registers: {dict(Counter(r['register'] for r in rows))}")

    for n in notes:
        print("   note:", n)
    print(f"\nRESULT: {len(problems)} problem(s)")
    for p in problems:
        print("  ", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
