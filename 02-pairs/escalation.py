#!/usr/bin/env python3
"""Deterministic profile escalation. Rules, not the model.

    python 02-pairs/escalation.py      # self-test, offline, no server needed

THE PRINCIPLE: this layer only ever RAISES urgency. It never lowers one, and a
rule that would lower a verdict is not implemented. `escalate` asserts it.

WHY RULES AND NOT THE MODEL. Beat 3, "the profile changes the answer", was cut
on 2026-09-17: the same symptom under two profiles came back red both times,
because the base model returns red for almost everything. Whether a profile fact
matters is a lookup, not a judgement, so it is done here, deterministically,
starting from the model's verdict.

EVERY RULE QUOTES ITS CHUNK, VERBATIM. `verify_grounding` checks that each quote
is really in the frozen chunk file and each key is in the registry, and the demo
server will not start if one is not. Hard constraint 14: a rule whose chunk does
not state it is not implemented. Three rules were first cited to chunks that do
not state them, and were re-keyed on 2026-09-19 on Viraj's call: R3 from
CP-ANG-001 to CP-ANG-002, R4 from CP-PE-002 to CP-PE-004 and CP-PE-001, R5 from
CP-PE-004 to CP-PE-003 and CP-PE-001.

ESCALATION IS ONE LEVEL, capped per rule: green to yellow, yellow to red. The
chunks mostly state a risk rather than an action, so one level claims the least.
R3's cap is yellow, because CP-ANG-002 says angina is a warning sign and no more.
Several rules firing together still raise one level in total, not one each.

A RULE FIRES on a structured profile fact AND a symptom asserted in the case
text: the symptoms and timeline only, never the retrieved chunks and never the
model's output (constraint 11). Symptom matching is lexical and negation-aware
per clause, so it misses phrasings it has no word for. A miss only ever means no
escalation: the model's verdict stands.

WHEN THE VERDICT IS ALREADY RED, a rule whose conditions hold is still reported,
as supporting that red. Viraj's call 2026-09-19: otherwise the base model's red
bias would hide the layer almost completely.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEVELS = ("green", "yellow", "red")
RANK = {u: i for i, u in enumerate(LEVELS)}

# ---------------------------------------------------------------- matching
#
# Clause-level, and commas split clauses. validate_pairs._negated_before does not
# split on commas, which is right for red flags and wrong here: "No real pain,
# just a vague heaviness" is exactly the presentation R1 exists for, and it must
# assert the heaviness. A cue negates a term only when it comes BEFORE the term
# in the same clause, so "Chest has not been right today" still asserts the chest.
_NEG = re.compile(r"\b(?:no|not|never|without|none|denies|denied)\b|n[’']t\b", re.I)
_SENTENCE = re.compile(r"[.;!?\n]+")
_CLAUSE = re.compile(r",|\bbut\b|\bhowever\b|\balthough\b|\bwhereas\b", re.I)


def _words(*alts):
    return re.compile(r"\b(?:" + "|".join(alts) + r")\b", re.I)


def _asserted(sentence, pattern, null=None):
    """First match of `pattern` in a clause of `sentence` that is not negated.
    `null` voids a whole clause, for "walking does not change it"."""
    for clause in _CLAUSE.split(sentence):
        if null is not None and null.search(clause):
            continue
        for m in pattern.finditer(clause):
            if not _NEG.search(clause[:m.start()]):
                return m.group(0)
    return None


def _anywhere(text, pattern, null=None):
    for s in _SENTENCE.split(text):
        hit = _asserted(s, pattern, null)
        if hit:
            return hit
    return None


def _together(text, a, b, null_b=None):
    """Words matched by `a` and `b` in the first sentence asserting both."""
    for s in _SENTENCE.split(text):
        x, y = _asserted(s, a), _asserted(s, b, null_b)
        if x and y:
            return x, y
    return None


# CP-ACS-003's list of heart attack symptoms, in patient words, plus the vague
# complaint itself. R1 and R2 need one of these AND a mild or vague marker.
CARDIAC = _words(
    r"chest", r"heav(?:y|iness)", r"pressure", r"tight(?:ness)?", r"squeez\w*",
    r"discomfort", r"ache|aching", r"pain\w*", r"arm", r"jaw", r"neck",
    r"shoulders?", r"back pain|pain in (?:my|her|his|the) back",
    r"short of breath|breathless\w*|out of breath|puffed",
    r"sweat\w*|clammy", r"tired\w*|exhausted|fatigue\w*|no energy",
    r"nause\w*|feel(?:ing)? sick|vomit\w*|indigestion",
    r"dizz\w*|light-?headed\w*|faint\w*",
    r"heart (?:racing|pounding)|racing heart|palpitations?",
    r"(?:feels?|feeling) (?:wrong|funny|odd|off|unwell)|not (?:been |feeling |felt |quite |looking )?right|unwell")

# CP-ACS-002: "without any symptoms or with very mild symptoms". Searched with no
# negation filter, because "no real pain" and "not pain as such" ARE the marker.
MILD = _words(
    r"mild(?:ly)?", r"slight(?:ly)?", r"a (?:bit|little)", r"bit of",
    r"vague(?:ly)?", r"niggle", r"twinge", r"odd", r"funny",
    r"not (?:been |feeling |felt |quite |looking )?right",
    r"(?:feels?|feeling) wrong", r"just feels?", r"no real pain",
    r"not (?:really )?pain", r"pain as such", r"hard to (?:describe|explain)",
    r"indigestion", r"off colou?r", r"under the weather",
    r"not (?:quite )?(?:myself|himself|herself)")

CHEST = _words(r"chest", r"tight(?:ness)?", r"pressure", r"heav(?:y|iness)",
               r"squeez\w*", r"band", r"angina", r"pain\w*", r"ache|aching",
               r"discomfort")
EXERTION = _words(r"walk\w*", r"climb\w*", r"stairs?", r"hills?", r"uphill",
                  r"exercis\w*", r"exert\w*", r"running|jogging|a run", r"gym",
                  r"lifting|carrying", r"rushing", r"gardening", r"cycling",
                  r"active", r"(?:going|went|go) up", r"press-?ups?")
# "Walking around does not change it" names exertion to rule it out.
EXERTION_NULL = re.compile(
    r"\b(?:does(?:n[’']t| not) (?:change|affect|make)|makes? no difference|"
    r"not related|unrelated)\b", re.I)

BREATHING = _words(r"breathe[sd]?", r"breathing", r"deep breaths?",
                   r"breath in", r"inhal\w*", r"inspiration")
# "It catches when I breathe in" is the classic patient phrasing, and missing it
# was found by the 2026-09-19 sweep's offline pre-check. "catch my breath" does
# not trip it: BREATHING needs breathe, breathing, a deep breath or breath in.
PAIN_OR_WORSE = _words(r"pain\w*", r"hurts?|hurting", r"sharp", r"stab\w*",
                       r"ache|aching", r"sore", r"worse", r"twinge\w*",
                       r"catch(?:es|ing)?")
LEG = _words(r"legs?", r"calf|calves", r"thigh")
LEG_SIGN = _words(r"swollen", r"swell\w*", r"fatter", r"bigger", r"puffy",
                  r"tender\w*", r"pain\w*", r"sore", r"ach\w*", r"hurts?",
                  r"red", r"hot", r"warm")
FATIGUE = _words(r"tired\w*", r"fatigue\w*", r"exhausted|exhaustion",
                 r"worn out", r"no energy", r"drained", r"wiped out", r"shattered")
UNEXPLAINED = _words(r"unusual(?:ly)?", r"no reason", r"for days", r"all week",
                     r"out of nowhere", r"(?:don[’']?t|do not) know why",
                     r"can(?:[’']?t|not) explain", r"since")


def _mild_cardiac(text):
    c, m = _anywhere(text, CARDIAC), MILD.search(text)
    return f'"{c}", described as "{m.group(0)}"' if c and m else None


def _exertional_chest(text):
    hit = _together(text, CHEST, EXERTION, null_b=EXERTION_NULL)
    return f'"{hit[0]}" with "{hit[1]}"' if hit else None


def _pleuritic(text):
    hit = _together(text, PAIN_OR_WORSE, BREATHING)
    return f'"{hit[0]}" on "{hit[1]}"' if hit else None


def _pleuritic_or_leg(text):
    leg = _together(text, LEG, LEG_SIGN)
    return _pleuritic(text) or (f'"{leg[0]}" {leg[1]}' if leg else None)


def _unexplained_fatigue(text):
    f, u = _anywhere(text, FATIGUE), UNEXPLAINED.search(text)
    return f'"{f}", "{u.group(0)}"' if f and u else None


# ---------------------------------------------------------------- profile facts
#
# Structured fields only. The display string is the fact as the profile states
# it, so the line under the verdict names what is actually on file.

def _condition(profile, pattern, fields=("conditions",)):
    for field in fields:
        for item in profile.get(field) or []:
            if re.search(pattern, item, re.I):
                return item
    return None


def fact_diabetes(p):
    return _condition(p, r"diabet")


def fact_older(p):
    # 70 is Viraj's cutoff. CP-ACS-002 says "older adults" and the corpus has no
    # age number anywhere.
    age = p.get("age")
    return f"age {age}" if isinstance(age, (int, float)) and age >= 70 else None


def fact_cad(p):
    return _condition(p, r"coronary (?:artery|heart) disease|angina|heart attack")


def fact_cancer(p):
    return _condition(p, r"cancer|chemo|lymphoma|leuka?emia|myeloma",
                      ("conditions", "medications"))


def fact_surgery(p):
    # CP-PE-003: "highest in the first 3 months after surgery". 13 weeks.
    s = p.get("surgery") or {}
    weeks = s.get("weeks_ago")
    if isinstance(weeks, (int, float)) and weeks <= 13:
        return f"{s.get('what', 'surgery')}, {weeks} weeks ago"
    return None


def fact_female(p):
    return "female" if str(p.get("sex", "")).lower() == "female" else None


# ---------------------------------------------------------------- the rules

RULES = [
    dict(id="R1", name="diabetes with mild or vague symptoms",
         action="escalate", cap="red", fact=fact_diabetes, symptom=_mild_cardiac,
         quotes=[("CP-ACS-002", "Silent heart attacks are more common in older "
                  "adults and in people who have high blood sugar or diabetes."),
                 ("CP-ACS-002", "Heart attacks can happen without any symptoms "
                  "or with very mild symptoms.")]),
    dict(id="R2", name="aged 70 or over with mild or vague symptoms",
         action="escalate", cap="red", fact=fact_older, symptom=_mild_cardiac,
         quotes=[("CP-ACS-002", "Silent heart attacks are more common in older "
                  "adults and in people who have high blood sugar or diabetes."),
                 ("CP-ACS-002", "Heart attacks can happen without any symptoms "
                  "or with very mild symptoms.")]),
    dict(id="R3", name="known coronary disease with chest symptoms on exertion",
         action="escalate", cap="yellow", fact=fact_cad, symptom=_exertional_chest,
         quotes=[("CP-ANG-002", "Angina can be a warning sign that you are at a "
                  "higher risk of having a heart attack.")]),
    dict(id="R4", name="cancer or chemotherapy with pain on breathing",
         action="escalate", cap="red", fact=fact_cancer, symptom=_pleuritic,
         quotes=[("CP-PE-004", "cancer and cancer treatments including "
                  "chemotherapy and surgery"),
                 ("CP-PE-001", "Shortness of breath and pain when breathing, if "
                  "you have a blood clot that travels to the lungs")]),
    dict(id="R5", name="surgery in the last 3 months with pain on breathing "
         "or a swollen or painful leg",
         action="escalate", cap="red", fact=fact_surgery, symptom=_pleuritic_or_leg,
         quotes=[("CP-PE-003", "The chance of developing a blood clot is highest "
                  "in the first 3 months after surgery and lowers with time."),
                 ("CP-PE-001", "Swollen and tender legs that are painful to the "
                  "touch"),
                 ("CP-PE-001", "Shortness of breath and pain when breathing, if "
                  "you have a blood clot that travels to the lungs")]),
    dict(id="R6", name="woman with unexplained tiredness",
         action="flag", cap=None, fact=fact_female, symptom=_unexplained_fatigue,
         quotes=[("CP-ACS-003", "Feeling unusually tired for no reason, sometimes "
                  "for days (this is more common in women)")]),
]


def verify_grounding(registry=None, chunks_dir=None):
    """Problems, empty when every rule's quote is verbatim in its chunk."""
    chunks_dir = Path(chunks_dir) if chunks_dir else ROOT / "01-data" / "chunks"
    problems = []
    for r in RULES:
        for key, quote in r["quotes"]:
            if registry is not None and key not in registry:
                problems.append(f"{r['id']}: {key} is not in the registry")
            path = chunks_dir / f"{key}.txt"
            if not path.exists():
                problems.append(f"{r['id']}: {key} has no chunk file")
            elif quote not in path.read_text(encoding="utf-8"):
                problems.append(f"{r['id']}: not verbatim in {key}: {quote[:60]!r}")
    return problems


def escalate(urgency, profile, case_text):
    """Every rule whose profile fact and symptom both hold, and the urgency
    after raising. Never lower than `urgency`.

    `case_text` is the symptoms and timeline. Never the retrieved chunks.
    """
    fired = []
    for r in RULES:
        fact = r["fact"](profile or {})
        symptom = fact and r["symptom"](case_text or "")
        if not symptom:
            continue
        keys = list(dict.fromkeys(k for k, _ in r["quotes"]))
        fired.append(dict(rule=r["id"], name=r["name"], action=r["action"],
                          cap=r["cap"], fact=fact, symptom=symptom, keys=keys,
                          quote=r["quotes"][0][1],
                          quotes=[list(q) for q in r["quotes"]]))

    final = urgency
    if urgency in RANK:
        targets = [min(RANK[urgency] + 1, RANK[f["cap"]])
                   for f in fired if f["action"] == "escalate"]
        final = LEVELS[max([RANK[urgency]] + targets)]
        assert RANK[final] >= RANK[urgency], "the layer only ever raises"

    for f in fired:
        if f["action"] == "flag":
            f["status"] = "flag"
        elif urgency not in RANK:
            f["status"] = "noted"
        else:
            target = min(RANK[urgency] + 1, RANK[f["cap"]])
            if target > RANK[urgency] and LEVELS[target] == final:
                f["status"] = "raised"
            elif RANK[f["cap"]] >= RANK[final]:
                f["status"] = "supports"
            else:
                f["status"] = "at_least"
    return dict(original=urgency, final=final, changed=final != urgency,
                fired=fired)


def rescue_refusal(withheld, profile, case_text):
    """The escalation to show INSTEAD of a post-flight refusal, or None.

    Only when a rule raises the withheld verdict to RED. It then goes out through
    the never-withhold-red path: flagged as not grounded, with the rule's quoted
    line. A withheld green that a rule would only raise to yellow stays refused,
    because a non-red that cites nothing is still refused.

    Viraj's call 2026-09-19: a refusal that hides a yellow the rules would raise
    is the same failure class as withholding a red. Measured the same day, on the
    sweep's 99 runs, 11 of the model's 14 non-red verdicts were refused before
    the layer ran. This takes raises from 3 of 99 to 10. None of the 7 recorded
    out-of-scope phrasings fires a rule on any adult profile, so the risk of
    triaging an out-of-scope complaint this way is constructed, not measured.
    """
    e = escalate(withheld, profile, case_text)
    return e if e["changed"] and e["final"] == "red" else None


if __name__ == "__main__":
    import json
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from guards import load_registry

    fx = json.loads((Path(__file__).resolve().parent /
                     "escalation_fixtures.json").read_text(encoding="utf-8"))
    passed = failed = 0

    def check(name, cond, detail=""):
        global passed, failed
        passed += bool(cond)
        failed += not cond
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond and detail:
            print(f"        {detail}")

    problems = verify_grounding(load_registry())
    check("grounding: every rule quote is verbatim in its chunk, every key in "
          "the registry", not problems, "; ".join(problems))

    P = fx["profiles"]
    for c in fx["fires"]:
        got = [f["rule"] for f in escalate("green", P[c["profile"]], c["text"])["fired"]]
        check(f"fires: {c['name']}", got == c["rules"], f"got {got}")

    for c in fx["escalation"]:
        out = escalate(c["urgency"], P[c["profile"]], c["text"])
        status = {f["rule"]: f["status"] for f in out["fired"]}
        check(f"escalation: {c['name']}",
              out["final"] == c["final"] and status == c["status"],
              f"got final={out['final']} status={status}")

    for c in fx.get("rescue", []):
        got = rescue_refusal(c["withheld"], P[c["profile"]], c["text"])
        check(f"rescue: {c['name']}",
              (got is not None) == c["rescued"] and (got is None or got["final"] == "red"),
              f"got {got and (got['original'], got['final'])}")

    # The principle, over every fixture at every starting urgency.
    lowered = [(c["name"], u) for c in fx["fires"] + fx["escalation"]
               for u in LEVELS
               if RANK[escalate(u, P[c["profile"]], c["text"])["final"]] < RANK[u]]
    check("never lowers: every fixture at green, yellow and red", not lowered,
          f"lowered: {lowered}")

    print(f"\n{passed}/{passed + failed} self-tests passed.")
    raise SystemExit(0 if failed == 0 else 1)
