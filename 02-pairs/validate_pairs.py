#!/usr/bin/env python3
"""
Pair validator. Run over a review file or a frozen file before anything trains.

    python 02-pairs/validate_pairs.py 02-pairs/review/candidates.jsonl
    python 02-pairs/validate_pairs.py 02-pairs/pairs/train.jsonl --strict

ERRORS are mechanical and objective. Fix or drop the pair; a file with any
error must not be frozen and must not train. WARNINGS are heuristic and need a
human to adjudicate, exactly like a candidate chunk in 01-data/review.

--strict promotes warnings to errors.

The four rules Viraj named, and where each lands:

  citation key exists in citations.csv          ERROR  (hard constraint 9)
  no think blocks                               ERROR  (hard constraint 5)
  follow_up_questions empty when urgency is red ERROR  (hard constraint 4)
  red_flags under 15 words, qualifier not a
    bare symptom                                ERROR on the word count,
                                                WARNING on the qualifier
  red_flags grounded in the case text           WARNING (hard constraint 11)

The word count is countable so it is an error. "Carries a qualifier rather than
being a bare symptom" is a semantic judgement and a lexicon cannot prove it.
The check below catches the documented failure, red_flags reading "chest
pressure" where the system prompt asks for "Central pressure-like pain at rest
beyond 20 minutes", and it will also flag legitimate entries such as "Vomiting
blood" that discriminate without carrying a modifier word. Shipping that as an
error would silently push the generator toward padding red_flags with filler
words to satisfy a lint, which is worse than the thing being prevented. It is a
warning, it is loud, and a human clears it. Flip PROMOTE_QUALIFIER if that call
changes.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pair_format import (SYSTEM_PROMPT, REQUIRED_FIELDS, URGENCIES, TODO,
                         load_registry, reference_keys_in)

PROMOTE_QUALIFIER = False
PROMOTE_GROUNDING = False

RED_FLAG_MAX_WORDS = 15

# --- hard constraint 11, red_flags grounding --------------------------------
# A red flag is a finding in THIS patient. The retrieved chunk says which
# findings would be red flags; only the profile, timeline and symptoms say
# which ones the patient actually has. So grounding is checked against the case
# text and never against [RETRIEVED CONTEXT].
#
# Measured 2026-09-17. Given the pleuritic case, whose text mentions neither,
# the base model returned red_flags ['fast heartbeat', 'fever']. Both strings
# are lines in CP-PERI-002, which that case supplies as context. The model
# copied findings out of the chunk and asserted them as the patient's own. That
# is worse than an invented citation key: hard constraint 9 can drop a key that
# does not resolve, but a fabricated finding reads exactly like a real one and
# nothing downstream can tell.
#
# PATIENT WORDS, NOT ONLY CLINICAL ONES. Added 2026-09-17 after writing the 60
# training pairs in real registers surfaced six false warnings, every one of them
# a lexicon gap rather than a fabrication: "more out of breath", "leg is fatter
# than the left", "black and sticky", "had a temperature", "bit more puffed".
#
# This was not a validator quirk. `screen_red_flags` in guards.py uses this same
# lexicon on the demo path, so the guard was DROPPING TRUE RED FLAGS off the
# screen whenever a patient used plain English. It fails closed, so it hid real
# findings rather than inventing them, which is the safer direction and still
# wrong: a judge typing naturally would have seen a verdict with its evidence
# stripped out.
#
# The eval cases are written in fairly clinical language, which is why a whole
# day of measurement never caught this and one pass of writing in a patient's
# voice did.
#
# WARNING and not ERROR, for the same reason as the qualifier rule: a lexicon
# cannot prove it. This one knows only the findings below, so it cannot catch a
# fabrication it has no word for, and a paraphrase the synonyms miss will read
# as a false positive. Both are a human's to adjudicate. PROMOTE_GROUNDING
# flips it.
CASE_BLOCKS = ("PATIENT PROFILE", "SYMPTOM TIMELINE", "SYMPTOMS")

FINDING_SYNONYMS = {
    "fever": ("fever", "febrile", "feverish", "pyrexia", "temperature",
              "running a temperature", "high temperature", "hot and shivery"),
    "chills": ("chills", "shivering", "rigors"),
    "fast heartbeat": ("fast heartbeat", "rapid heartbeat", "fast heart rate",
                       "rapid heart rate", "racing heart", "heart racing",
                       "pounding heart", "heart pounding", "heart is racing",
                       "heart is pounding", "heart going", "thumping",
                       "tachycardia", "palpitations", "fast pulse",
                       "rapid pulse"),
    "sweating": ("sweating", "sweaty", "sweat", "sweats", "clammy",
                 "drenched", "soaked through", "pouring with sweat",
                 "diaphoresis", "diaphoretic"),
    "nausea": ("nausea", "nauseated", "nauseous", "queasy", "feel sick",
               "feeling sick"),
    "vomiting": ("vomiting", "vomit", "vomited", "throwing up", "threw up",
                 "thrown up", "been sick", "being sick", "bringing it back up",
                 "emesis"),
    "shortness of breath": ("shortness of breath", "short of breath",
                            "out of breath", "puffed", "winded",
                            "catch my breath", "catch his breath",
                            "catch her breath", "cannot catch my breath",
                            "can't catch my breath", "gasping",
                            "breathless", "breathlessness", "dyspnea",
                            "dyspnoea", "trouble breathing",
                            "difficulty breathing", "hard to breathe",
                            "cannot breathe", "can't breathe"),
    "dizziness": ("dizzy", "dizziness", "lightheaded", "light-headed",
                  "lightheadedness", "faint", "fainting", "fainted", "syncope",
                  "passed out"),
    "cough": ("cough", "coughing"),
    "coughing blood": ("coughing blood", "coughing up blood", "bloody mucus",
                       "blood in mucus", "hemoptysis", "haemoptysis"),
    "swelling": ("swelling", "swollen", "swollen up", "puffy",
                 "fatter than", "bigger than the other", "edema", "oedema"),
    "weight loss": ("weight loss", "losing weight", "lost weight"),
    "bleeding": ("bleeding", "bleed", "blood", "bloody", "tarry", "tar-like",
                 "black and sticky", "sticky black", "black and tarry",
                 "melena", "coffee grounds", "hemorrhage", "haemorrhage"),
    "fatigue": ("fatigue", "tired", "tiredness", "exhausted", "exhaustion"),
    "pallor": ("pale", "pallor", "ashen"),
    "cyanosis": ("cyanosis", "blue lips", "bluish", "turning blue"),
    "confusion": ("confusion", "confused", "disoriented"),
    "difficulty swallowing": ("difficulty swallowing", "trouble swallowing",
                              "dysphagia", "painful swallowing",
                              "pain when swallowing"),
    "numbness": ("numbness", "numb", "tingling", "pins and needles"),
    "rash": ("rash", "hives"),
    # New canon. CP-GERD-002 lists loss of appetite among its alarm features,
    # so the lexicon needed a word for it before a pair could cite that line.
    "loss of appetite": ("loss of appetite", "no appetite", "off my food",
                         "gone off my food", "off her food", "off his food",
                         "not eating", "cannot face food"),
}


def _mentions(text, phrase):
    return re.search(r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b",
                     text, re.IGNORECASE) is not None


def case_text_in(human_turn):
    """Profile, timeline and symptoms only. Never the retrieved context."""
    out = []
    for name in CASE_BLOCKS:
        for m in re.finditer(rf"\[{re.escape(name)}\]\n(.*?)\n\[/{re.escape(name)}\]",
                             human_turn, re.DOTALL):
            out.append(m.group(1))
    return "\n".join(out)


def ungrounded_findings(entry, case_text):
    """Findings this red_flag asserts that the case text does not support.

    A finding counts as SUPPORTED only if the case asserts it. A case that
    mentions it in order to DENY it does not support it, and that distinction is
    not cosmetic: found 2026-09-17 while building the demo beat, a case reading
    "No fever, and my heart does not feel like it is racing" licensed a `fever`
    red flag, because the old check asked only whether the word appeared
    anywhere. A patient explicitly denying a finding was the strongest possible
    evidence against it and was being read as evidence for it.

    Negation on the ENTRY side is deliberately not applied here: an entry in
    red_flags asserts its finding by being in that list at all. That asymmetry
    is the same one audit_grounding.py has always used.
    """
    out = []
    for canon, variants in FINDING_SYNONYMS.items():
        if not any(_mentions(entry, v) for v in variants):
            continue
        asserted_in_case = any(
            _mentions(case_text, v) and not _negated_before(case_text, v)
            for v in variants)
        if not asserted_in_case:
            out.append(canon)
    return out


# Contradiction, which is a different failure from absence and a worse one.
#
# `ungrounded_findings` asks "does the case mention this at all". It cannot see
# a claim that inverts something the case does state, because the inverting
# phrase is not a finding word. Measured 2026-09-17: with the grounding line in
# the format 3 prompt, yellow-angina came back with
# `red_flags: ['chest tightness that does not go away']` for a case whose
# timeline reads `T+0:06 tightness resolved completely` and whose symptom text
# says "It went away once I sat down". CP-ANG-001 supplies the phrase: "Chest
# pain or discomfort that does not go away or occurs while you are resting
# might be a sign of a heart attack". So the model took the chunk's CRITERION
# and asserted it as the patient's FINDING, in the teeth of the case. A synonym
# lexicon scores that clean, which is exactly how it went unnoticed.
#
# Each axis has two opposed poles. A contradiction is the output asserting one
# pole while the case text asserts the other. Both poles must be present,
# output and case, or nothing is claimed: silence in the case is absence, which
# is the other function's job.
#
# Deliberately narrow. Every pole here is a phrase a consumer health page or a
# case timeline actually uses. Adding an axis is a clinical call, same as
# adding to FINDING_SYNONYMS.
CONTRADICTION_AXES = {
    "course": {
        "persisting": ("does not go away", "doesn't go away", "not go away",
                       "does not resolve", "not resolved", "unresolved",
                       "unrelieved", "no relief", "without relief",
                       "has not let up", "has not eased", "persistent",
                       "persisting", "unchanged", "ongoing", "continuous",
                       "still present", "does not improve", "no improvement"),
        "resolving": ("resolved", "resolved completely", "went away",
                      "goes away", "gone away", "subsided", "settled",
                      "eased", "easing", "relieved", "improved", "improving",
                      "no further symptoms", "symptom free", "abated"),
    },
    "duration": {
        "brief": ("within 20 minutes", "under 20 minutes", "less than 20",
                  "within minutes", "brief", "briefly", "momentary",
                  "short lived", "short-lived", "seconds"),
        "prolonged": ("beyond 20 minutes", "over 20 minutes", "over 30 minutes",
                      "more than 30 minutes", "half an hour", "for hours",
                      "two hours", "unchanged"),
    },
    # NO `exertion` AXIS. Removed 2026-09-18. Do not add it back; the vocabulary
    # is preserved below with the reason.
    "rest response": {
        "relieved by rest": ("resolved with rest", "goes away with rest",
                             "better with rest", "eased with rest",
                             "relieved by rest", "resolved after rest",
                             "eased after sitting", "better sitting"),
        "not relieved by rest": ("despite rest", "not relieved by rest",
                                 "unchanged after resting", "no relief with rest",
                                 "does not improve with rest",
                                 "not better with rest"),
    },
}

# REMOVED AS A CONTRADICTION AXIS, 2026-09-18. Kept here so the decision is
# visible at the place someone would re-add it.
#
# It conflated WHAT BROUGHT THE PAIN ON with WHAT THE PATIENT IS DOING NOW.
# Those are different questions and the pole matcher cannot tell them apart,
# because it matches poles and not subjects (see contradicted_findings' KNOWN
# LIMIT, which this was a specific instance of).
#
# Measured on P0042, half of the flagship CP-ANG contrast set. The case reads
# "Chest got tight walking up the hill ... Sat on the wall. It has not shifted,
# it has been half an hour now." The red flag "Chest tightness unchanged after
# 30 minutes at rest" was DROPPED, because "walking up" scored `exertional` and
# "at rest" scored `non exertional`.
#
# That is not a contradiction. Exertional onset with persistence at rest is the
# textbook evolving-ACS pattern, and it is the exact discriminator the CP-ANG
# sets are built on. The guard was deleting the one finding that justifies the
# red verdict, on the most important presentation in the corpus, live on the
# demo path.
#
# Worse, it was phrasing-dependent: "unchanged after 30 minutes at rest" dropped
# but "unchanged after 30 minutes" and "after sitting down" survived, so whether
# the screen showed the correct red flag turned on the model's word choice.
#
# `rest response` stays, and is the axis people will reach for instead. It is
# legitimate because both its poles describe the SAME question, how the pain
# responded to rest, rather than straddling onset and current state.
RETIRED_AXES = {
    "exertion": {
        "exertional": ("on exertion", "with exertion", "exertional",
                       "during activity", "during exertion", "when active",
                       "climbing", "walking up", "up the stairs"),
        "non exertional": ("at rest", "while resting", "no relation to exertion",
                           "not related to exertion", "unrelated to exertion",
                           "no exertional relation", "walking around does not",
                           "not brought on by activity"),
    },
}


def _asserted_poles(text, axis):
    """Poles of `axis` this text asserts, negation excluded."""
    out = []
    for pole, phrases in CONTRADICTION_AXES[axis].items():
        for p in phrases:
            if not _mentions(text, p):
                continue
            # "no relief" is itself the persisting pole, so a bare negation
            # scan would invert it. Only a cue BEFORE the phrase and inside
            # the same clause negates it.
            if _negated_before(text, p):
                continue
            out.append(pole)
            break
    return out


_NEG_CUE = re.compile(r"\b(no|not|never|without|denies|denied|absent|none|"
                      r"lacks|lacking|rather than|instead of)\b", re.IGNORECASE)
# A NEWLINE ENDS A CLAUSE. Without it, the structured profile block
#     conditions: none
#     medications: none
#     Placeholder text, fever since Tuesday.
# let the "none" in a medications field negate a fever asserted two lines later,
# because the nearest clause break scanning backwards was the colon in
# "medications:". Found 2026-09-17 by selftest_validator, which failed the
# moment case-side negation was added. "none" in a structured field is a field
# value, not a negation of the next line.
_CLAUSE = re.compile(r"[.;:!?\n]|\bbut\b|\bhowever\b|\balthough\b|\bwhereas\b",
                     re.IGNORECASE)


def _negated_before(text, phrase):
    # Also used by ungrounded_findings above, which is defined earlier in the
    # file. Resolved at call time, so the ordering is fine.
    """True if every occurrence of `phrase` sits under a negation cue."""
    pat = r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b"
    found = False
    for m in re.finditer(pat, text, re.IGNORECASE):
        found = True
        start = 0
        for b in _CLAUSE.finditer(text[:m.start()]):
            start = b.end()
        window = text[start:m.start()]
        # A cue that is part of the phrase itself does not negate it.
        if not _NEG_CUE.search(window):
            return False
    return found


# Axes that describe the PRESENTING complaint, so past history must not be
# read as a pole. Measured 2026-09-17: yellow-pleuritic's profile says "Recent
# head cold, now resolved", and matching "resolved" out of that scored the
# rationale "unchanged over 1.5 hours" as a course contradiction. The cold
# resolved; the chest pain did not. This check compares poles, not subjects, so
# the only defence is to keep history out of the comparison for these two axes.
# Rest response stays on the full text: the profile legitimately carries
# "Prescribed nitroglycerin" style context there. (Exertion was named here too
# until it was retired on 2026-09-18; see RETIRED_AXES.)
PRESENT_ONLY_AXES = {"course", "duration"}


def contradicted_findings(entry, case_text, case_present=None):
    """Axes where `entry` asserts the opposite pole to the case.

    Returns a list of (axis, pole_asserted, pole_in_case). Empty when the
    output and the case agree, or when either is silent on the axis.

    `case_present` is the timeline and symptom text without the profile. Pass
    it and the course and duration axes ignore past history, which is the only
    way this check avoids reading a resolved prior illness as the present
    complaint resolving. Without it the axes fall back to the full case text
    and the old false positive returns.

    KNOWN LIMIT. This matches poles, not subjects. It cannot tell which finding
    a pole attaches to, so a case describing two things with opposite courses
    can still score a contradiction that a human would clear. It is a warning
    for that reason, the same call as the qualifier rule.
    """
    out = []
    for axis in CONTRADICTION_AXES:
        src = (case_present if case_present is not None
               and axis in PRESENT_ONLY_AXES else case_text)
        said = set(_asserted_poles(entry, axis))
        case = set(_asserted_poles(src, axis))
        if not said or not case:
            continue
        for pole in said:
            for other in case:
                if pole != other:
                    out.append((axis, pole, other))
    return out


def target_mismatch(obj):
    """Slot target versus authored verdict.

    The slot's target_category is the PLAN: it is what `plan` counted, what the
    category mix was built from, and what the contrast sets were laid out
    against. The authored urgency is what actually trains. Nothing compared them
    until 2026-09-17, when P0021 was scaffolded yellow and written red, and the
    file validated clean while the mix quietly drifted.

    A mismatch is a WARNING, not an error, because the author is often right and
    the slot wrong: P0021 is forty minutes of central chest pressure unresolved
    at rest, which is red whatever the scaffolder guessed. The fix is usually to
    relabel the slot, and that is a decision, so a human makes it.
    """
    target = (obj.get("target_category") or "").strip()
    turns = [c for c in obj.get("conversations", []) if c.get("from") == "gpt"]
    if not target or not turns:
        return None
    try:
        final = json.loads(turns[-1]["value"]).get("urgency")
    except (json.JSONDecodeError, TypeError):
        return None
    if final and final != target:
        return (f"slot target_category is {target} but the authored verdict is "
                f"{final}. One of them is wrong and the category mix counts the "
                f"slot, not the answer.")
    return None


THINK = re.compile(r"</?think\b|<\|think", re.IGNORECASE)

# A qualifier is anything that narrows a finding to a discriminating one:
# timing, onset, duration, provocation, relief, radiation, laterality,
# severity, or a number. Deliberately broad, since this gates a warning.
QUALIFIER = re.compile(
    r"\b("
    r"at rest|on exertion|exertional|sudden|suddenly|abrupt|gradual|persistent|"
    r"unrelieved|unresolved|ongoing|continuous|intermittent|recurrent|"
    r"radiat\w+|spread\w+|refer\w+|worse|worsen\w+|better|relie\w+|eased?|"
    r"despite|beyond|longer than|more than|over \d|after \d|within \d|"
    r"minute|minutes|hour|hours|day|days|week|weeks|"
    r"crushing|pressure-like|tearing|heavy|heaviness|severe|sharp|tight\w*|"
    r"central|left-sided|right-sided|bilateral|new|first|"
    r"unable|cannot|can't|breathless|at night|lying flat|leaning forward|"
    r"palpat\w+|inspiration|deep breath|position\w*|accompanied|with |plus "
    r")\b", re.IGNORECASE)

# Exact bare symptoms. Matching one of these as a whole entry is an error, not
# a warning: there is no reading under which a lone entry of "chest pain" in
# red_flags is correct.
BARE = {
    "chest pain", "chest pressure", "chest tightness", "shortness of breath",
    "breathlessness", "nausea", "vomiting", "sweating", "dizziness",
    "lightheadedness", "palpitations", "fatigue", "tiredness", "cough",
    "fever", "pain", "jaw pain", "arm pain", "back pain", "neck pain",
    "anxiety", "heartburn", "weakness", "numbness",
}


def words(s):
    return [w for w in re.split(r"\s+", s.strip()) if w]


def check_pair(idx, obj, registry):
    """Returns (errors, warnings) as lists of strings."""
    E, W = [], []
    def e(m): E.append(m)
    def w(m): W.append(m)

    tm = target_mismatch(obj)
    if tm:
        w(tm)

    convs = obj.get("conversations")
    if not isinstance(convs, list) or not convs:
        return ["no `conversations` list"], []

    # --- container shape -------------------------------------------------
    if convs[0].get("from") != "system":
        e("first turn is not `system`")
    elif convs[0].get("value") != SYSTEM_PROMPT:
        e("system turn is not byte-identical to pair_format.SYSTEM_PROMPT "
          "(train/serve skew)")

    expect = "human"
    for t in convs[1:]:
        if t.get("from") != expect:
            e(f"turn order broken: expected `{expect}`, got `{t.get('from')}`")
            break
        expect = "gpt" if expect == "human" else "human"
    else:
        if expect != "human":
            e("conversation does not end on an assistant turn")

    if len(convs) < 3:
        e("fewer than 3 turns (system, human, gpt)")
        return E, W

    # --- per assistant turn ----------------------------------------------
    humans = [t for t in convs if t.get("from") == "human"]
    gpts = [t for t in convs if t.get("from") == "gpt"]

    # Reference block. Keys visible to the model at the turn being answered.
    # Multi-turn pairs may re-supply context, so the union up to that point is
    # what the model could legitimately cite.
    seen_keys = []
    for h in humans:
        ks = reference_keys_in(h.get("value", ""))
        if ks is None:
            e("human turn has no [RETRIEVED CONTEXT] block")
            ks = []
        seen_keys += ks
    for k in seen_keys:
        if k not in registry:
            e(f"reference block supplies `{k}`, not in citations.csv")

    # Hard constraint 11. Union across turns, same reasoning as seen_keys: a
    # later turn can add detail a red flag may legitimately rest on.
    case_text = "\n".join(case_text_in(h.get("value", "")) for h in humans)

    for n, g in enumerate(gpts, 1):
        raw = g.get("value", "")
        tag = f"assistant turn {n}"

        if THINK.search(raw):
            e(f"{tag}: think block present. Reasoning is OFF "
              "(hard constraint 5)")

        if TODO in raw:
            e(f"{tag}: unfilled {TODO} marker")

        try:
            a = json.loads(raw)
        except json.JSONDecodeError as ex:
            e(f"{tag}: value does not parse as JSON on its own: {ex}")
            continue
        if not isinstance(a, dict):
            e(f"{tag}: assistant value is not a JSON object")
            continue

        missing = [f for f in REQUIRED_FIELDS if f not in a]
        extra = [f for f in a if f not in REQUIRED_FIELDS]
        if missing:
            e(f"{tag}: missing fields {missing}")
        if extra:
            e(f"{tag}: unexpected fields {extra} (additionalProperties is false)")

        urg = a.get("urgency")
        if urg not in URGENCIES:
            e(f"{tag}: urgency `{urg}` not one of {URGENCIES} (lowercase)")

        # Hard constraint 4. The schema cannot express it.
        fq = a.get("follow_up_questions")
        if isinstance(fq, list) and urg == "red" and fq:
            e(f"{tag}: {len(fq)} follow_up_questions on a red verdict "
              "(hard constraint 4)")

        # Hard constraint 9, plus spec section 7's stronger in-context rule.
        cites = a.get("citations")
        if isinstance(cites, list):
            for c in cites:
                if c not in registry:
                    e(f"{tag}: citation `{c}` is not in citations.csv "
                      "(invented key)")
                elif c not in seen_keys:
                    e(f"{tag}: citation `{c}` is real but was never in this "
                      "pair's reference block")
            if not seen_keys and cites:
                e(f"{tag}: reference block is `none` but citations is non-empty")

        # red_flags shape.
        rf = a.get("red_flags")
        if isinstance(rf, list):
            for entry in rf:
                if not isinstance(entry, str):
                    e(f"{tag}: red_flags entry is not a string: {entry!r}")
                    continue
                n_words = len(words(entry))
                if n_words >= RED_FLAG_MAX_WORDS:
                    e(f"{tag}: red_flag is {n_words} words, must be under "
                      f"{RED_FLAG_MAX_WORDS}: {entry!r}")
                norm = entry.strip().lower().rstrip(".")
                if norm in BARE:
                    e(f"{tag}: red_flag is a bare symptom with no "
                      f"discriminating qualifier: {entry!r}")
                elif not QUALIFIER.search(entry):
                    w(f"{tag}: red_flag carries no recognised qualifier, "
                      f"check by hand: {entry!r}")

                # Hard constraint 11. Judged against the case text only, so a
                # finding lifted out of the retrieved chunk still fails.
                absent = ungrounded_findings(entry, case_text) if case_text else []
                if absent:
                    msg = (f"{tag}: red_flag asserts {', '.join(absent)}, which "
                           f"the profile, timeline and symptoms never mention "
                           f"(hard constraint 11): {entry!r}")
                    (e if PROMOTE_GROUNDING else w)(msg)

            if urg == "red" and not rf:
                w(f"{tag}: red verdict with an empty red_flags list")
            if urg == "green" and rf:
                w(f"{tag}: green verdict carrying {len(rf)} red_flags")

        # next_steps is the IITT-to-disposition translation layer.
        ns = a.get("next_steps")
        if isinstance(ns, list) and not ns:
            e(f"{tag}: next_steps is empty. Every verdict needs a disposition")

        rat = a.get("rationale")
        if isinstance(rat, str) and not rat.strip():
            e(f"{tag}: rationale is empty")

    return E, W


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--strict", action="store_true",
                    help="promote warnings to errors")
    ap.add_argument("--quiet", action="store_true",
                    help="summary only, no per-pair detail")
    args = ap.parse_args()

    if not args.path.exists():
        sys.exit(f"no such file: {args.path}")
    registry = load_registry()

    n = 0
    bad_lines = 0
    tot_e = tot_w = 0
    pairs_with_e = pairs_with_w = 0
    dist = Counter()
    turns = Counter()

    for lineno, line in enumerate(args.path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        n += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as ex:
            bad_lines += 1
            tot_e += 1
            pairs_with_e += 1
            print(f"line {lineno}: ERROR line does not parse as JSON: {ex}")
            continue

        E, W = check_pair(lineno, obj, registry)
        if args.strict:
            E, W = E + W, []

        pid = obj.get("id", f"line{lineno}")
        convs = obj.get("conversations") or []
        turns[(len(convs) - 1) // 2] += 1
        for t in convs:
            if t.get("from") == "gpt":
                try:
                    dist[json.loads(t["value"]).get("urgency")] += 1
                except Exception:
                    pass

        tot_e += len(E)
        tot_w += len(W)
        pairs_with_e += bool(E)
        pairs_with_w += bool(W)
        if (E or W) and not args.quiet:
            print(f"\n{pid}  (line {lineno})")
            for m in E:
                print(f"  ERROR   {m}")
            for m in W:
                print(f"  WARNING {m}")

    print(f"\n{'-'*60}")
    print(f"{args.path}")
    print(f"  pairs                 : {n}")
    print(f"  exchanges per pair    : {dict(sorted(turns.items()))}")
    print(f"  urgency across turns  : {dict(dist)}")
    print(f"  pairs with errors     : {pairs_with_e}  ({tot_e} errors)")
    print(f"  pairs with warnings   : {pairs_with_w}  ({tot_w} warnings)")
    if tot_e:
        print("\nNOT FIT TO FREEZE OR TRAIN. Fix the errors.")
    elif tot_w:
        print("\nNo errors. Warnings need a human, same as a candidate chunk.")
    else:
        print("\nClean.")
    return 1 if tot_e else 0


if __name__ == "__main__":
    sys.exit(main())
