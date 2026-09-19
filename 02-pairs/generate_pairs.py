#!/usr/bin/env python3
"""
Epic 2 generator harness. Mechanics only. It writes no clinical content.

Same discipline as the corpus: plan, scaffold into review/, a human fills and
edits, validate, freeze. Both guards that bit epic 1 are built in from the
start rather than added after they cost a review pass:

    scaffold  refuses to overwrite an existing review file without --force
    freeze    refuses to run over an existing frozen file without --force

    python 02-pairs/generate_pairs.py plan --total 300
    python 02-pairs/generate_pairs.py scaffold --total 300
    python 02-pairs/generate_pairs.py freeze --heldout 40

WHAT A SLOT IS. The harness cannot write a presentation, so it writes the part
that is derivable from the frozen corpus: which chunks go in the reference
block, what category the pair is targeting, how many turns it has, and which
phrasing register it should use. Everything a clinician has to decide is left
as a TODO marker, and validate_pairs.py errors on any TODO that survives.

WHY plan EXISTS AND NOT JUST scaffold. The memorisation risk is a property of
the corpus, not of the pairs, and it is countable before a single pair is
written. Every retrieved chunk in a green pair comes from one of two conditions,
so a green pair count is really a per-condition repetition count. `plan` prints
that number. It is the number that decides how many pairs to write.
"""

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pair_format import (HERE, SYSTEM_PROMPT, TODO, build_human_turn,
                         load_chunk_texts, load_registry)

REVIEW = HERE / "review"
PAIRS = HERE / "pairs"

# Phrasing registers. Labels only; the generation session writes the text.
# training-data-format.md section 4: textbook-only phrasing means the model
# only works for people who talk like textbooks.
REGISTERS = ["terse adult", "panicked caregiver", "verbose and anxious",
             "poor spelling and punctuation", "describing a third person",
             "plain and factual", "minimising the symptom"]

# UNDER-SPECIFIED pairs. Chunks ARE retrieved and the case is too thin to commit
# to a category, so the answer is follow-up questions rather than a confident
# verdict.
#
# This replaces the old decline pairs, which had an EMPTY reference block.
# Dropped 2026-09-17 because guard 6 made them train a state the app cannot
# produce: the pre-flight relevance floor refuses before generating when nothing
# is close enough, so a no-reference case never reaches the model, and the
# post-flight check refuses any answer that cites nothing. Those pairs were the
# countermeasure to the CP-RISK-014 fabrication and guard 6 now prevents it
# upstream instead.
#
# The state that IS real and untrained is: relevance floor cleared, chunks in
# context, and a case with too little in it to separate two categories. Rule 6
# of the system prompt says assign the higher one and put the missing
# information in follow_up_questions. Nothing in the data teaches that yet.
UNDERSPECIFIED_SHARE = 0.08

# Share of pairs that are multi-turn. training-data-format.md section 4 puts
# multi-turn at 30% and skews it red/yellow, since a green case rarely needs a
# questioning round. Red cannot be multi-turn at all under hard constraint 4:
# a red verdict ends the conversation.
MULTITURN_SHARE = {"red": 0.0, "yellow": 0.40, "green": 0.15}

# CONTRAST SETS. Two pairs that retrieve THE SAME CHUNKS and reach DIFFERENT
# verdicts, differing only in one named discriminator.
#
# This is the backbone of the 60-pair plan and it exists because of what was
# measured on 2026-09-17, not because contrastive data is fashionable:
#
#   1. The category head is movable but NOT case-sensitive. GREEN_CRITERION
#      freed green on green-gerd and simultaneously dragged the known-CAD case
#      to green. Any signal that shifts a global cut point reproduces that. A
#      contrast set cannot shift a cut point, because both members share the
#      chunks and only the case text separates them.
#   2. Green carries 11 pairs across 2 conditions at this size, so the shortcut
#      "GERD chunk therefore green" is learnable from the data alone. Contrast
#      sets break it by construction: the same chunk appears under two verdicts.
#   3. The model already gets red right on chest pain and gets nothing else
#      right, so the teaching signal has to be the boundary, not the category.
#
# Each axis is (condition keys, the discriminator, the two verdicts). The
# discriminator is written into the slot so whoever fills it knows the two cases
# must differ in THAT and nothing else. Same age band, same register, same
# chunks. If they differ in anything else the pair teaches that instead.
CONTRAST_AXES = [
    # ONE DISCRIMINATOR PER AXIS. Revised 2026-09-17 after an audit found 9 of
    # 12 sets carried a second difference. Two of those, C06 and C12, were the
    # scaffolder's fault rather than the author's: the VTE axis read "is there a
    # thrombosis risk factor AND sudden onset", which is two discriminators in
    # one line and could not produce a clean set however carefully it was
    # written. A compound axis guarantees a compound difference.
    #
    # The rule now: the axis names exactly one thing, and the two sketches differ
    # in that thing and say nothing else. Everything the two halves share,
    # including the history that makes the presentation plausible, belongs in
    # BOTH sketches, not in one.
    ("CP-ANG", "does the exertional pain resolve with rest",
     ("yellow", "red"),
     "usual pattern, resolves within minutes of stopping"
     " / usual pattern, unchanged after 30 minutes at rest"),

    ("CP-GERD", "is there black tarry stool",
     ("green", "yellow"),
     "burning after meals, worse lying flat, eased sitting up, no other change"
     " / burning after meals, worse lying flat, eased sitting up, plus two days of black tarry stool"),

    ("CP-PERI", "is there breathlessness at rest",
     ("yellow", "red"),
     "positional pleuritic pain after a recent virus, breathing comfortably"
     " / positional pleuritic pain after a recent virus, breathless at rest"),

    # The profile difference IS the axis here, so it is named rather than left
    # to the author to improvise. Medications must match; a prior diagnosis is
    # the discriminator, a prior prescription is a second one.
    # One concept, stated consistently in the profile and the history: a
    # previously diagnosed and recognised pattern, or a first episode. An
    # earlier wording said "identical episode" on BOTH halves, which is
    # incoherent for a patient with no prior episodes to be identical to.
    # Neither half has cardiac history: the old C10 gave the yellow side
    # hypertension and amlodipine, which justified yellow on its own and made
    # the diagnosis axis unnecessary.
    ("CP-PANIC", "is this a previously diagnosed and recognised pattern",
     ("green", "yellow"),
     "same symptoms as many previous attacks, settling, panic disorder in the profile, no cardiac history"
     " / first episode of these symptoms, settling, no prior diagnosis in the profile, no cardiac history"),

    ("CP-PLEU", "is the pain reproducible on palpation",
     ("green", "yellow"),
     "sharp pain after a day of heavy lifting, reproduced exactly by pressing the spot"
     " / sharp pain after a day of heavy lifting, pressing the spot changes nothing"),

    # WAS: "is there a thrombosis risk factor and sudden onset". Split. Onset
    # speed is the discriminator; the risk factor is held constant and present in
    # BOTH halves, so the set teaches the onset and not the flight.
    ("CP-PE", "did the pain come on suddenly or build gradually",
     ("yellow", "red"),
     "pain on breathing after a recent long flight, built up over four days"
     " / pain on breathing after a recent long flight, came on suddenly an hour ago"),
]

# GROUNDING SLOTS. The retrieved chunk lists findings the patient does NOT have,
# and the correct assistant turn must omit them from red_flags. This is hard
# constraint 11 taught directly rather than guarded after the fact. CP-PERI-002
# is the obvious vehicle: it is three lines and two of them are "Fast heartbeat"
# and "Fever", and copying those onto a patient who has neither is the single
# most reproduced failure in this project.
GROUNDING_KEYS = ["CP-PERI-002", "CP-PNA-001", "CP-ACS-003"]


def condition_of(key):
    """CP-ACS-001 -> CP-ACS. The condition, which is the unit that repeats."""
    return re.sub(r"-\d+$", "", key)


def corpus_shape(registry):
    """category -> {condition -> [keys]}, plus the uncategorised pool."""
    by_cat = defaultdict(lambda: defaultdict(list))
    for key, row in registry.items():
        cat = (row.get("expected_category") or "").strip() or None
        by_cat[cat][condition_of(key)].append(key)
    return by_cat


def cmd_plan(args):
    registry = load_registry()
    shape = corpus_shape(registry)
    mix = dict(zip(("red", "yellow", "green"), args.mix))
    total = args.total

    print(f"corpus: {len(registry)} frozen chunks\n")
    print(f"{'category':<10} {'chunks':>7} {'conditions':>11}  conditions")
    for cat in ("red", "yellow", "green", None):
        conds = shape.get(cat, {})
        n_chunks = sum(len(v) for v in conds.values())
        label = cat or "(none)"
        print(f"{label:<10} {n_chunks:>7} {len(conds):>11}  "
              f"{', '.join(sorted(conds)) or '-'}")

    print(f"\nplan for {total} pairs, mix "
          f"{mix['red']:.0%}/{mix['yellow']:.0%}/{mix['green']:.0%} red/yellow/green\n")
    print(f"{'category':<10} {'pairs':>6} {'w/ ref':>7} {'no ref':>7} "
          f"{'per chunk':>10} {'per condition':>14}")
    worst = None
    for cat in ("red", "yellow", "green"):
        conds = shape.get(cat, {})
        n_chunks = sum(len(v) for v in conds.values()) or 1
        n_cond = len(conds) or 1
        n = round(total * mix[cat])
        no_ref = round(n * NO_REFERENCE_SHARE)
        with_ref = n - no_ref
        per_chunk = with_ref / n_chunks
        per_cond = with_ref / n_cond
        print(f"{cat:<10} {n:>6} {with_ref:>7} {no_ref:>7} "
              f"{per_chunk:>10.1f} {per_cond:>14.1f}")
        if worst is None or per_cond > worst[1]:
            worst = (cat, per_cond, n_cond)

    print(f"\nMEMORISATION PRESSURE. The unit that repeats is the condition, not")
    print(f"the chunk: two chunks from the same source page describe the same")
    print(f"presentation, so a pair citing either one teaches the same")
    print(f"chunk-to-verdict shortcut. Worst category is {worst[0]}, at")
    print(f"{worst[1]:.0f} pairs across {worst[2]} condition(s).")
    print(f"\nThe lever is conditions, not pairs. Adding one green source page")
    print(f"moves green from {len(shape.get('green', {}))} conditions to "
          f"{len(shape.get('green', {})) + 1}, which cuts the per-condition")
    print(f"number by a third at the same pair count. Cutting the pair count")
    print(f"alone leaves the ratio of presentations to conditions unchanged.")


def build_contrast_slots(registry, shape, n_sets, rng):
    """Pairs of slots sharing chunks and differing only in the discriminator."""
    slots = []
    for i in range(n_sets):
        cond, axis, verdicts, sketch = CONTRAST_AXES[i % len(CONTRAST_AXES)]
        pool = sorted(k for k in registry if condition_of(k) == cond)
        if not pool:
            continue
        keys = pool[:2] if len(pool) >= 2 else pool
        cid = f"C{i + 1:02d}"
        for side, (verdict, half) in enumerate(zip(verdicts, sketch.split(" / "))):
            slots.append({
                "target_category": verdict,
                "reference_keys": list(keys),
                "exchanges": 1,
                # REGISTER IS HELD CONSTANT WITHIN A SET, varied across sets.
                # It was indexed by (set, side) at first, which made register
                # covary with verdict inside every set: terse adult yellow,
                # panicked caregiver red. That is a second discriminator, and
                # the whole claim of a contrast set is that exactly one thing
                # differs. Across 12 sets the registers still rotate, so the
                # model still sees every verdict in several voices.
                "register": REGISTERS[i % len(REGISTERS)],
                "contrast_id": cid,
                "contrast_axis": axis,
                "contrast_side": half.strip(),
                "kind": "contrast",
            })
    return slots


def build_slots(registry, total, mix, seed, n_contrast_sets=0, n_grounding=0):
    """Deterministic slot assignment. Same seed, same plan."""
    rng = random.Random(seed)
    shape = corpus_shape(registry)
    # The uncategorised differential chunk is supporting context, never the
    # sole evidence for a verdict.
    support = [k for k in shape.get(None, {}) for k in shape[None][k]]

    slots = []
    for cat in ("red", "yellow", "green"):
        conds = sorted(shape.get(cat, {}))
        n = round(total * mix[cat])
        n_thin = round(n * UNDERSPECIFIED_SHARE)
        n_multi = round((n - n_thin) * MULTITURN_SHARE[cat])
        for i in range(n):
            thin = i < n_thin
            cond = conds[i % len(conds)] if conds else None
            pool = sorted(shape[cat][cond]) if cond else []
            if thin:
                # Chunks ARE present: the floor was cleared, the case is thin.
                keys = rng.sample(pool, min(len(pool), 2)) if pool else []
            else:
                # 1 to 3 chunks, the retrieval top-k the app will actually send.
                # Hard constraint 7: three chunks at the frozen 140-token mean
                # is about 13 s of prompt eval, so 2 is the realistic default.
                take = min(len(pool), rng.choice([1, 2, 2, 2, 3]))
                keys = rng.sample(pool, take)
                if support and rng.random() < 0.15:
                    keys.append(rng.choice(support))
            slots.append({
                # An under-specified pair answers with follow-up questions, and
                # constraint 4 forbids those on a red, so "assign the higher
                # one" can never mean red here. It also must not mean green:
                # committing to self-care on a case too thin to separate is the
                # under-call the whole category mix exists to prevent. Yellow is
                # the only coherent target for this kind.
                "target_category": "yellow" if thin else cat,
                "reference_keys": keys,
                "exchanges": 2 if (n_thin <= i < n_thin + n_multi) else 1,
                "register": REGISTERS[len(slots) % len(REGISTERS)],
                "kind": "underspecified" if thin else "standalone",
                **({"underspecified_note":
                    "Chunks cleared the relevance floor but the case is too thin "
                    "to separate two categories. Rule 6: assign the higher one "
                    "and put what is missing in follow_up_questions. Do NOT "
                    "invent detail the case does not give."} if thin else {}),
            })
    # Contrast and grounding slots REPLACE standalone ones rather than adding
    # to them, so --total stays the number of pairs a human has to write.
    extra = build_contrast_slots(registry, shape, n_contrast_sets, rng)
    for i in range(n_grounding):
        key = GROUNDING_KEYS[i % len(GROUNDING_KEYS)]
        extra.append({
            "target_category": "yellow" if i % 2 else "green",
            "reference_keys": [key],
            "exchanges": 1,
            "register": REGISTERS[i % len(REGISTERS)],
            "kind": "grounding",
            "grounding_note": (
                f"{key} lists findings this patient must NOT have. The case text "
                f"must omit them and red_flags must not contain them. This is "
                f"hard constraint 11 taught, not guarded."),
        })
    if extra:
        rng.shuffle(slots)
        slots = slots[:max(0, len(slots) - len(extra))] + extra

    rng.shuffle(slots)
    for i, s in enumerate(slots, 1):
        s.setdefault("kind", "standalone")
        s["id"] = f"P{i:04d}"
    return slots


def cmd_scaffold(args):
    registry = load_registry()
    texts = load_chunk_texts()
    mix = dict(zip(("red", "yellow", "green"), args.mix))
    REVIEW.mkdir(parents=True, exist_ok=True)
    out = REVIEW / args.out

    if out.exists() and not args.force:
        sys.exit(f"{out} exists. Review files are hand-edited; regenerating one "
                 f"silently discards that work. Pass --force only if you mean it.")

    slots = build_slots(registry, args.total, mix, args.seed,
                        getattr(args, "contrast_sets", 0),
                        getattr(args, "grounding", 0))
    with open(out, "w", encoding="utf-8") as f:
        for s in slots:
            human = build_human_turn(
                profile=TODO, symptoms=TODO,
                reference_keys=s["reference_keys"], chunk_text_by_key=texts,
                timeline=TODO if s["exchanges"] > 1 else None)
            convs = [{"from": "system", "value": SYSTEM_PROMPT},
                     {"from": "human", "value": human}]
            for turn in range(s["exchanges"]):
                if turn > 0:
                    convs.append({"from": "human", "value": build_human_turn(
                        profile=TODO, symptoms=TODO,
                        reference_keys=s["reference_keys"],
                        chunk_text_by_key=texts)})
                convs.append({"from": "gpt", "value": TODO})
            rec = {
                "id": s["id"],
                "kind": s.get("kind", "standalone"),
                "target_category": s["target_category"],
                "reference_keys": s["reference_keys"],
                "register": s["register"],
            }
            for k in ("contrast_id", "contrast_axis", "contrast_side",
                      "grounding_note"):
                if k in s:
                    rec[k] = s[k]
            rec["conversations"] = convs
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    cats = Counter(s["target_category"] for s in slots)
    print(f"wrote {len(slots)} slots to {out}")
    print(f"  category targets : {dict(cats)}")
    print(f"  no reference     : {sum(1 for s in slots if not s['reference_keys'])}")
    print(f"  multi-turn       : {sum(1 for s in slots if s['exchanges'] > 1)}")
    kinds = Counter(s.get("kind", "standalone") for s in slots)
    print(f"  by kind          : {dict(kinds)}")
    csets = sorted({s['contrast_id'] for s in slots if 'contrast_id' in s})
    if csets:
        print(f"  contrast sets    : {len(csets)} ({', '.join(csets)}), "
              f"each 2 pairs sharing chunks with opposite verdicts")
    print(f"\nEvery profile, symptom and assistant turn is `{TODO}`.")
    print(f"validate_pairs.py errors on any {TODO} that survives, so a "
          f"half-filled file cannot freeze.")


def cmd_freeze(args):
    from validate_pairs import check_pair
    registry = load_registry()
    src = REVIEW / args.out
    PAIRS.mkdir(parents=True, exist_ok=True)
    train_p, held_p = PAIRS / "train.jsonl", PAIRS / "heldout.jsonl"

    if not src.exists():
        sys.exit(f"no review file at {src}")
    if (train_p.exists() or held_p.exists()) and not args.force:
        sys.exit(f"{train_p} already exists. Re-freezing changes what trained. "
                 f"Pass --force only with a reason.")

    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    errs = 0
    for i, r in enumerate(rows, 1):
        E, _ = check_pair(i, r, registry)
        errs += len(E)
    if errs:
        sys.exit(f"{errs} validation errors in {src}. Run validate_pairs.py. "
                 f"Nothing frozen.")

    # Stratified by category and by condition signature, selected by seed and
    # never by eye, per training-data-format.md section 5.
    rng = random.Random(args.seed)
    strata = defaultdict(list)
    for r in rows:
        sig = tuple(sorted({condition_of(k) for k in r.get("reference_keys", [])}))
        strata[(r.get("target_category"), sig)].append(r)
    held = []
    want = args.heldout
    keys = sorted(strata, key=lambda k: (-len(strata[k]), str(k)))
    while len(held) < want and any(strata[k] for k in keys):
        for k in keys:
            if strata[k] and len(held) < want:
                held.append(strata[k].pop(rng.randrange(len(strata[k]))))
    held_ids = {r["id"] for r in held}
    train = [r for r in rows if r["id"] not in held_ids]

    for path, data in ((train_p, train), (held_p, held)):
        with open(path, "w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps({"id": r["id"],
                                    "conversations": r["conversations"]},
                                   ensure_ascii=False) + "\n")

    with open(PAIRS / "manifest.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "split", "target_category", "exchanges",
                    "register", "reference_keys"])
        for r in rows:
            w.writerow([r["id"], "heldout" if r["id"] in held_ids else "train",
                        r.get("target_category"),
                        sum(1 for t in r["conversations"] if t["from"] == "gpt"),
                        r.get("register"), " ".join(r.get("reference_keys", []))])

    print(f"frozen. train {len(train)}, heldout {len(held)}")
    print(f"  train   : {dict(Counter(r.get('target_category') for r in train))}")
    print(f"  heldout : {dict(Counter(r.get('target_category') for r in held))}")
    print(f"  manifest: {PAIRS / 'manifest.csv'}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "scaffold", "freeze"):
        p = sub.add_parser(name)
        p.add_argument("--total", type=int, default=300)
        p.add_argument("--mix", type=float, nargs=3, default=[0.30, 0.40, 0.30],
                       metavar=("RED", "YELLOW", "GREEN"),
                       help="category shares. training-data-format.md section 4 "
                            "freezes 30/40/30 and says explicitly not to mirror "
                            "the real base rate, since that teaches under-calling "
                            "emergencies.")
        p.add_argument("--seed", type=int, default=26)
        p.add_argument("--out", default="candidates.jsonl")
        p.add_argument("--force", action="store_true")
        p.add_argument("--heldout", type=int, default=40)
        p.add_argument("--contrast-sets", type=int, default=0,
                       help="N sets of 2 pairs sharing chunks and reaching "
                            "opposite verdicts, differing only in one named "
                            "discriminator. They REPLACE standalone slots, so "
                            "--total stays the number of pairs to write.")
        p.add_argument("--grounding", type=int, default=0,
                       help="N pairs whose retrieved chunk lists findings the "
                            "patient must NOT have, teaching hard constraint 11 "
                            "directly instead of guarding it afterwards.")
    args = ap.parse_args()
    {"plan": cmd_plan, "scaffold": cmd_scaffold, "freeze": cmd_freeze}[args.cmd](args)


if __name__ == "__main__":
    main()
