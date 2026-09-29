#!/usr/bin/env python3
"""App-logic guards on model output, for the llama-server path.

    python 02-pairs/guards.py          # self-test, offline, no server needed

THE DEMO SURFACE IS THE LAPTOP. Decided 2026-09-17: the demo is a web UI against
llama-server with a phone screenshot as evidence, and no live simulator
inference, because one completion in the simulator is 3 min 56 s in Release and
a judge visit is about 5 minutes. So these guards have to exist on the
llama-server path, not only in the React Native app.

This is a port of `05-app/spike-load/guards.ts` and the two must agree. They are
separate files because they run in separate languages on separate surfaces, and
that is a real drift risk. Both read their expectations from one file,
`02-pairs/guard_fixtures.json`, so a change to either implementation that breaks
a shared expectation fails that side's suite. Add new cases there, not here.

Every guard exists because a prompt rule could not hold it, and every one fails
closed. Everything removed is returned, never silently dropped.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_pairs import (contradicted_findings,  # noqa: E402
                            ungrounded_findings)

# ---------------------------------------------------------------- guard 1

# Measured 2026-09-17 through llama.rn, Debug AND Release: `text` comes back as
#     <|im_start|>assistant
#     {"urgency":"red",...}
# and a bare json.loads on that raises. llama-server splits the message before
# returning it, so this never showed under llama-server, which is exactly why it
# has to be handled at the boundary rather than assumed away: the demo now runs
# against llama-server, but the same model on a different binding prepends the
# envelope, and the app shell will hit it again.
TEMPLATE_TOKENS = re.compile(
    r"<\|(?:im_start|im_end|start_header_id|end_header_id|eot_id|"
    r"begin_of_text|end_of_text|assistant|user|system|channel|message)\|>")
LEADING_ROLE = re.compile(r"^\s*(assistant|model|system)\s*[:\n]", re.IGNORECASE)
FENCE_OPEN = re.compile(r"^\s*```(?:json)?", re.IGNORECASE)
FENCE_CLOSE = re.compile(r"```\s*$")


def parse_model_json(raw: str) -> dict:
    """Strip chat-template scaffolding, then parse. Raises on non-JSON."""
    s = TEMPLATE_TOKENS.sub(" ", str(raw or ""))
    s = LEADING_ROLE.sub("", s)
    s = FENCE_CLOSE.sub("", FENCE_OPEN.sub("", s))
    first, last = s.find("{"), s.rfind("}")
    if first == -1 or last == -1 or last < first:
        raise ValueError(f"no JSON object in model output: {s[:120]!r}")
    return json.loads(s[first:last + 1])


# ---------------------------------------------------------------- guard 2

# Hard constraint 12. Blanket rule, not a drug blacklist.
#
# It was first written as "administration VERB + MEDICATION" and that version
# leaked on two real strings with no verb in them, one of which was the worked
# example inside system_prompt.txt itself ("Over the counter analgesia as
# directed on the packet"). That line was removed from the prompt on
# 2026-09-17, but the guard must not depend on the prompt being clean.
MEDICATION = re.compile(
    r"\b(aspirin|nitroglycerin|nitroglycerine|nitro|glyceryl\s+trinitrate|gtn|"
    r"paracetamol|acetaminophen|tylenol|ibuprofen|advil|nurofen|naproxen|"
    r"antacid|antacids|omeprazole|ranitidine|famotidine|h2\s*blockers?|ppis?|"
    r"proton\s+pump\s+inhibitors?|analgesia|analgesics?|painkillers?|"
    r"pain\s+relievers?|medications?|medicines?|meds|drug|drugs|tablet|tablets|"
    r"pill|pills|capsule|capsules|inhalers?|epipens?|epinephrine|adrenaline|"
    r"insulin|antihistamines?|benadryl|apixaban|warfarin|statins?|metformin|"
    r"lisinopril|atorvastatin|beta\s*blockers?|anticoagulants?)\b", re.IGNORECASE)

DOSE = re.compile(
    r"\b\d+\s*(mg|mcg|ml|g|units?|tablets?|pills?|capsules?|puffs?|sprays?)\b",
    re.IGNORECASE)

PROHIBITION = re.compile(
    r"\b(do\s+not|don't|never|avoid|refrain\s+from|should\s+not|must\s+not)\b",
    re.IGNORECASE)

# Anchored: it must govern the sentence. "If available, chew aspirin if not
# allergic" contains allowlist-ish words late and is still an instruction.
NON_ADMIN_LEAD = re.compile(
    r"^\s*(bring|tell|inform|report|show|carry|list|mention|note|"
    r"give\s+the\s+(paramedics?|clinician|doctor|nurse))\b", re.IGNORECASE)


# ONE LINE CAN BOTH INSTRUCT AND PROHIBIT, and the prohibition used to rescue
# the whole line. Measured live 2026-09-19: "Take medication as prescribed; do
# not stop unless directed by provider" was flagged and KEPT, because "do not"
# appears in it. Constraint 12 says the instruction half is what has to go, so
# each clause is now judged on its own and any clause that instructs drops the
# whole step. Clauses split on ; and . only: a comma or "and" separates a lead
# from its object ("Bring your medications and your inhaler"), and splitting
# there would drop the second half of a line that is fine.
#
# Still escapes, knowingly: a clause whose object is a pronoun. "Do not stop
# your medication; take it as prescribed" names no medication in its second
# clause, so the lexicon cannot see it.
STEP_CLAUSE = re.compile(r"[;.]+")


def screen_next_steps(steps):
    """(kept, dropped, flagged). Flagged entries are kept for a human to judge."""
    kept, dropped, flagged = [], [], []
    for raw in steps or []:
        s = str(raw or "")
        drop = flag = False
        for clause in STEP_CLAUSE.split(s):
            if not MEDICATION.search(clause) and not DOSE.search(clause):
                continue
            if PROHIBITION.search(clause):
                flag = True          # a prohibition is a clinical call, not a dose
            elif not NON_ADMIN_LEAD.search(clause):
                drop = True          # fails closed
        if drop:
            dropped.append(s)
        else:
            if flag:
                flagged.append(s)
            kept.append(s)
    return kept, dropped, flagged


# ---------------------------------------------------------------- guard 5

# Hard constraint 11, finally enforced instead of warned about.
#
# Measured live on the demo path 2026-09-17: a case saying "heavy pressure in
# the middle of my chest ... I feel sick and I am sweating" produced
# red_flags ['crushing chest pain', 'sweating', 'nausea', 'dizziness'].
# The patient never mentioned dizziness. A milder case produced
# ['Chest pain that worsens with breathing', 'Rapid heartbeat'] for someone who
# reported neither, both lifted from CP-PERI-002, which retrieval supplies to
# nearly every query. So the demo was showing a judge findings the patient does
# not have, which is worse than showing none.
#
# This REUSES ungrounded_findings and contradicted_findings from
# validate_pairs.py rather than being a third implementation of the rule. The
# pair validator, this guard and the audit therefore cannot disagree about what
# grounded means. The TypeScript port reads the same lexicon via
# finding_lexicon.json, which export_lexicon.py generates from the same source.
#
# WHY THIS DROPS WHERE validate_pairs ONLY WARNS. In a training pair a human
# clears the warning before the pair is frozen. On the demo path there is no
# human between the model and the screen, so it has to fail closed. The dropped
# entries are returned and rendered, so a judge sees the guard working rather
# than a quietly shorter list.
#
# WHAT IT STILL CANNOT SEE: a fabricated finding for which the 20-term lexicon
# has no word. "possible pleurisy as a cause" passes. This is a floor.


def screen_red_flags(red_flags, case_text, case_present=None):
    """(kept, dropped). Drops entries asserting findings the case does not."""
    kept, dropped = [], []
    for raw in red_flags or []:
        s = str(raw or "")
        absent = ungrounded_findings(s, case_text)
        contra = contradicted_findings(s, case_text, case_present)
        if absent or contra:
            why = []
            if absent:
                why.append("not in the case: " + ", ".join(absent))
            if contra:
                why += [f"case says {c} not {b}" for _a, b, c in contra]
            dropped.append({"entry": s, "why": "; ".join(why)})
        else:
            kept.append(s)
    return kept, dropped


# ---------------------------------------------------------------- guard 3

# THE LEADING KEY OF AN ENTRY IS VALIDATED, NOT THE WHOLE STRING.
#
# Measured live 2026-09-18 on "There is a heaviness across my front and my left
# arm has gone dead", textbook ACS. The model cited
#     "CP-ACS-003: Chest pain, heaviness, or discomfort in the center ..."
# which is the right key with the chunk's line appended. Exact matching dropped
# it, the list came out empty, and the post-flight scope check refused a real
# heart attack as out of scope in 2 runs of 4, telling the user "the model
# cited nothing". The key is kept and the appended text is not: the expander
# shows the chunk's real text, and the model's copy of it is not a source.
#
# The key must LEAD the entry, after at most an opening bracket or quote,
# because the prompt writes keys as [CP-ACS-003]. It must be whole, so
# "CP-ACS-0031" is not CP-ACS-003. Prose that only mentions a key is still
# dropped, and so is any entry whose leading key does not resolve. A key cited
# twice is kept once.
LEADING_KEY = re.compile(
    r"[\[(\"'`]*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?![A-Za-z0-9_-])")


def screen_citations(citations, registry):
    """Hard constraint 9. (kept, dropped): each entry's leading key if it
    resolves, else the whole entry, dropped."""
    kept, dropped = [], []
    for raw in citations or []:
        entry = str(raw or "").strip()
        m = LEADING_KEY.match(entry)
        if m and m.group(1) in registry:
            if m.group(1) not in kept:
                kept.append(m.group(1))
        else:
            dropped.append(entry)
    return kept, dropped


# ---------------------------------------------------------------- guard 4

def screen_follow_ups(urgency, questions):
    """Hard constraint 4. No questioning round on a red."""
    qs = list(questions or [])
    if urgency == "red" and qs:
        return [], qs
    return qs, []


# ---------------------------------------------------------------- guard 6

# SCOPE. The corpus is chest pain and nothing else. 22 chunks, every one under
# topic `chest_pain`. Anything else is out of scope and must be REFUSED, not
# triaged.
#
# Found by Viraj clicking through the demo 2026-09-17. "My stomach hurts and my
# period is late", 29-year-old woman, came back as a triage verdict with an
# empty red_flags list and ZERO citations. **That presentation includes ectopic
# pregnancy, which is life-threatening and time-critical.** Retrieval had
# returned GERD, panic disorder and angina, because that is all the corpus
# contains, and the model reasoned from them anyway and called it non-urgent.
#
# Re-run the same evening it returned yellow rather than green, temperature
# being 0.2, with the rationale "Late period with stomach pain is non-urgent".
# The label is not the point and neither is its stability. A system with no
# knowledge of a condition produced a reassuring verdict about it.
#
# TWO INDEPENDENT CONDITIONS, either one refuses:
#
#   1. RELEVANCE FLOOR, checked BEFORE generating. Nothing in the corpus is
#      close enough to the query. Pre-flight because it saves 40 s of generation
#      and, more importantly, never gives the model the chance to confabulate
#      from loosely related chunks.
#
#   2. NO CITATIONS, checked after the citation guard. An empty citations list
#      means the model had nothing it was willing to ground the answer in, which
#      is exactly the case above. Viraj's observation, and it is the more robust
#      of the two because it needs no threshold.
#
# THE 2026-09-17 CALIBRATION DOES NOT REPRODUCE. Do not rely on the numbers it
# reported. They were never written to disk, which is the exact failure the
# "every eval result goes to disk" convention exists to prevent, and re-running
# the same query today gives a different answer:
#
#     "Burning behind my breastbone at night"
#         recorded 09-17 : 0.482, reported as the worst in-scope
#         measured 09-18 : 0.386, on both the dense and the hybrid scorer
#
# Both scorers agree with each other to four decimal places, so this is not a
# measurement difference. Most likely the corpus grew from 19 chunks to 22
# between the two dates. Whatever the cause, the floor's stated justification is
# not checkable, so it has been re-derived from scratch.
#
# RE-CALIBRATED 2026-09-18, 12 in-scope against 12 out-of-scope, the in-scope
# half deliberately written in plain English rather than corpus language.
# `04-retrieval/calibrate_scope.py`, re-runnable, results on disk.
#
#     worst in-scope   0.314  ("There is a heaviness across my front and my
#                               left arm has gone dead")
#     best out-scope   0.450  ("I have a sore throat and a cough")
#     gap             -0.136
#
# THE CLASSES OVERLAP. The gap is NEGATIVE, so no single threshold separates
# them and the old framing, a floor sitting safely in a gap, was an artefact of
# a sample written entirely in textbook phrasing. A floor is now a choice about
# WHICH error to make, not a boundary.
#
# Given that, the floor is set for the cheap error. Refusing a real presentation
# is catastrophic and costs a life; passing an out-of-scope query costs about 45
# seconds of generation and is then caught post-flight by the empty-citations
# condition, which needs no threshold and is the robust check of the two. The
# pre-flight floor is a latency optimisation. It is not the safety mechanism and
# must not be tuned as though it were.
#
# 0.25 CLEARS ALL 12 IN-SCOPE QUERIES, worst 0.314, with 0.064 of margin. It
# refuses 4 of 12 out-of-scope and lets 8 through to the post-flight check.
#
# It was 0.33 for part of 2026-09-18, and 0.33 still refused "There is a
# heaviness across my front and my left arm has gone dead" at 0.314. That is
# textbook ACS with radiation, scoring low only because the wording contains
# neither "chest" nor "pain", which is exactly the phrasing this product exists
# to serve. Refusing it is indefensible when a post-flight check with no
# threshold is the real guard, so the floor moved again, to 0.25.
#
# WHAT 0.25 ADMITS THAT 0.33 REFUSED, all measured:
#     0.294  "I have had a bad headache for three days"          <-- see below
#     0.291  "My tooth is killing me and the side of my face aches"
#     0.265  "My knee has been sore since I started running"
#     0.252  "I rolled my ankle playing football and it is swollen"
#
# ONE OF THOSE IS GENUINELY DANGEROUS TO TRIAGE. A three-day headache covers
# subarachnoid haemorrhage, meningitis, temporal arteritis and CO poisoning. A
# reassuring verdict on it, reasoned from chest-pain chunks, is the ectopic
# pregnancy failure again in a different body part. The other three are benign.
#
# It is NOT, however, an argument for 0.33, because the floor was never
# protecting against this class. Already through at 0.33, unchanged by this
# move: "I have been feeling really down and cannot sleep" at 0.367, which
# carries suicidality, and "My toddler has a fever and is pulling at her ear" at
# 0.341, which carries paediatric sepsis. Both are worse than the headache and
# both cleared the higher floor. A threshold on chest-pain cosine was never the
# thing keeping those out.
#
# SO THE POST-FLIGHT CHECK HAS TO HOLD, AND IT WAS TESTED RATHER THAN ASSUMED.
# All 8 out-of-scope queries that clear 0.25 were run end to end through the
# demo on 2026-09-18. SEVEN OF EIGHT WERE REFUSED post-flight, including all
# four that 0.25 newly admits and including the three-day headache.
#
# THAT WAS ONE RUN EACH, AND ONE OF THE SEVEN DOES NOT HOLD ON REPEATS. Three
# runs each later the same night: six refused 3 of 3, headache included, but
# "My tooth is killing me and the side of my face aches", 0.291, was TRIAGED
# RED 2 of 3, citing CP-PERI-002 and CP-PERI-001 by exact key, with "chest pain
# that feels sharp, gets worse with breathing" asserted as the patient's. The
# red-flag guard kept it: its lexicon has no chest-pain or pleuritic term. See
# 06-demo/results/2026-09-18-leading-key-live.txt, section C.
#
# THE ONE THAT GOT THROUGH, AND IT IS NOT ONE 0.25 ADMITTED:
#   "My toddler has a fever and is pulling at her ear", 0.341, which cleared the
#   old 0.40-era reasoning too and was passing at 0.33 as well. It was TRIAGED,
#   returning red, citing CP-PNA-001, CP-PERI-002 and CP-PERI-001, with the
#   rationale "Fever in a toddler with ear pulling is a red flag for possible
#   meningitis".
#
#   "meningitis" APPEARS IN NO CHUNK. The word is nowhere in the corpus. But
#   CP-PNA-001 really does say "Young children, older adults, and people who
#   have serious health conditions are at risk", and it lists fever, so the key
#   resolves and the citation guard is right to pass it.
#
#   THAT IS THE LIMIT OF THE POST-FLIGHT CHECK, stated plainly: it fires only
#   when the model cites NOTHING. Where the corpus holds an adjacent-but-wrong
#   chunk, the model grounds on it and sails through, and the reasoning it
#   attaches can be invented. Lowering the floor did not cause this and raising
#   it does not fix it: at 0.40 this query scores 0.341 and is refused, but that
#   is the floor catching it by luck of a number, not by knowing anything.
#
#   The red verdict happens to be the safe direction for a febrile toddler. That
#   is luck, not design. The same mechanism returns green just as easily, which
#   is what it did to the ectopic pregnancy case on 2026-09-17.
#
#   CLOSED FOR THIS QUERY, NOT IN GENERAL, 2026-09-18. The paediatric exclusion
#   below now refuses it before generation. The limit above still holds for any
#   out-of-scope subject that no categorical exclusion names.
SCOPE_FLOOR = 0.25

REFUSAL = ("This is outside what this system covers. It can only assess chest "
           "pain, and it found nothing relevant to what you described. Please "
           "seek medical advice.")


# CATEGORICAL EXCLUSION: PREGNANCY.
#
# A relevance floor cannot hold this and adjusting the floor would not help.
# Measured 2026-09-17: "30 weeks pregnant ... heartburn ... sour taste" scores
# 0.486 and "34 weeks pregnant, burning pain in the top of my stomach that will
# not go" scores 0.416, both ABOVE the 0.40 floor, both retrieving GERD chunks.
# They clear the floor precisely because they look like reflux.
#
# Third-trimester epigastric or retrosternal pain is a recognised pre-eclampsia
# warning sign. The corpus has TWO WORDS of obstetric content, "being pregnant"
# in CP-GERD-003, and they appear in a list of things that CAUSE reflux, so the
# only pregnancy-aware chunk in the corpus argues for the benign reading.
#
# Raising the floor to catch these would refuse ordinary reflux too, since the
# scores overlap. The discriminator is not similarity, it is subject matter, so
# the exclusion has to be categorical.
#
# Deliberately requires BOTH a pregnancy term and a symptom term. "I am pregnant"
# with an unrelated query is not what this is for, and a bare mention of
# pregnancy in a medication list should not refuse a chest-pain assessment.
#
# LATE OR MISSED PERIOD, added 2026-09-18 on Viraj's call. Guard 6's founding
# case, "My stomach hurts and my period is late", was never caught here, because
# PREGNANCY needed an explicit pregnancy word. That is the whole clinical point
# of an ectopic: the patient does not know she is pregnant. Forms of "late
# period", "missed period" and "period is late" now count as a pregnancy term.
#
# THE SYMPTOM SIDE HAD TO WIDEN TOO, or the new terms would have changed
# nothing. It covered the upper abdomen only, and "stomach hurts" is not "upper
# stomach", so the founding case still passed with the three phrases added. The
# whole abdomen and pelvis are in now, which also refuses lower abdominal pain in
# a patient who says she is pregnant. Same call, for the same reason as above.
#
# NOT COVERED, left for a clinical decision: bleeding, spotting, shoulder-tip
# pain or fainting with no abdominal word; "cramps" alone, which would also
# refuse leg cramps in pregnancy; "overdue", "no period", "haven't had my
# period". "My period is not late" still refuses. It fails closed.
#
# TWO DESK PHRASINGS NO LONGER REFUSE, fixed 2026-09-18. Both were ordinary
# chest pain refused as pregnancy:
#   "I was expecting it to settle"  bare `expecting` matched. It now counts
#       only in its pregnancy senses: "I'm expecting" ending a clause or
#       followed by and, but, in and the like, or "expecting a baby", "twins",
#       "my first". A transitive "expecting it to" is not a pregnancy.
#   "I am not pregnant"  `pregnan*` matched inside a denial. NOT_PREGNANT is
#       removed before the search. Uncertainty is not a denial: "not sure if I
#       am pregnant" and "don't think I'm pregnant" still refuse, and a denial
#       does not mask a late period in the same text.
PREGNANCY = re.compile(
    r"\b(pregnan\w*|trimester|\d{1,2}\s*weeks\s+(?:gone|pregnant)|"
    r"(?:i['’]?m|i\s+am|we['’]re|we\s+are|she['’]s|she\s+is)\s+expecting"
    r"(?=[ \t]*(?:[.,;:!?)\n]|$)|\s+(?:and|but|so|in|with|now|again)\b)|"
    r"expecting\s+(?:(?:a|an|another|my|our|her|their)\s+)?"
    r"(?:first|second|third|next|baby|babies|child|twins|triplets|boy|girl)|"
    r"post ?partum|post-natal|postnatal|obstetric|pre-?eclamp\w*|midwife|"
    r"late\s+periods?|missed\s+(?:\w+\s+){0,2}?periods?|"
    r"periods?(?:['’]s|\s+(?:is|was))\s+(?:\w+\s+){0,3}?late)\b",
    re.IGNORECASE)

# n't is outside the \b because it is always attached: isn't, wasn't, aren't.
NOT_PREGNANT = re.compile(
    r"(?:\b(?:not|never\s+been)|n['’]t)\s+(?:(?:currently|actually|even)\s+)?"
    r"pregnan\w*", re.IGNORECASE)

PREGNANCY_SYMPTOM = re.compile(
    r"\b(chest|retrosternal|breastbone|sternum|epigastri\w*|"
    r"stomach\w*|tumm(?:y|ies)\w*|bell(?:y|ies)\w*|abdom\w*|pelvi\w*|"
    r"under\s+(?:my\s+)?ribs|heartburn|reflux|indigestion|"
    r"short\s+of\s+breath|breathless|palpitation\w*)\b", re.IGNORECASE)

PREGNANCY_REFUSAL = (
    "This app can't assess chest or stomach symptoms during pregnancy, or when a "
    "period is late. Call your doctor, your midwife, or emergency services now.")


# CHILDREN. Decided by the selected PROFILE'S AGE since 2026-09-19, not by text.
#
# The first version, 2026-09-18, refused on a child word plus a symptom word in
# the text, and it failed in both directions. It refused adults: "my daughter
# drove me here" with crushing chest pain, and two training pairs, P0008 (aged
# 19) and P0030 (17), for mentioning a daughter. And it failed open on any
# child presentation phrased without a word from its symptom list: a panic
# attack, an asthma attack, a swallowed button battery, an allergic reaction.
#
# Now a selected profile under 16 gets PAEDIATRIC_REFUSAL as a scope notice and
# no verdict, whatever the text says. On an adult profile, a child word in the
# text refuses nothing: the page asks whether this is about someone else, and
# the user picks that person's profile or continues as themselves. Viraj's call.
# That is why child_term has no symptom half any more: it only decides whether
# to ask, so it should ask too often rather than too rarely.
#
# Every chunk is written about adults. The only paediatric content in the corpus
# is one passage in CP-PNA-001 on how pneumonia shows in babies, which is what
# the toddler case grounded on when it was triaged red with an invented
# "possible meningitis" on 2026-09-18.
#
# A child word is a child noun (baby, infant, newborn, toddler, child, kid), a
# possessive son, daughter, boy, girl or grandchild, an age under 16 in years,
# or any age given in months, weeks or days. "baby aspirin" is not a baby.
CHILD = re.compile(
    r"\b(bab(?:y|ies)(?!\s+aspirin)|infants?|newborns?|toddlers?|child|children|"
    r"kids?|(?:my|our)\s+(?:\w+\s+){0,2}?(?:son|daughter|boy|girl|grandson|"
    r"granddaughter|grandchild(?:ren)?)s?(?!-in-law))\b",
    re.IGNORECASE)

_UNITS = ("zero one two three four five six seven eight nine ten eleven twelve "
          "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
# Tens first and whole, so "twenty-five years old" is read as 25 and never as
# the "five years old" inside it.
_NUMBER = (r"\d{1,3}|(?:" + "|".join(_TENS) + r")(?:[\s-]+(?:" +
           "|".join(_UNITS[1:10]) + r"))?|" + "|".join(_UNITS) + r"|an?")

AGE_YEARS = re.compile(
    rf"\b({_NUMBER})(?:\s+and\s+a\s+half)?[\s-]*(?:years?|yrs?)[\s-]*"
    rf"(?:old|of\s+age)\b"
    r"|\b(\d{1,3})\s*(?:yo|y/o|y\.o\.?)(?!\w)"
    r"|\bage[ds]?\s*:?\s*(\d{1,3})\b", re.IGNORECASE)

AGE_INFANT = re.compile(
    rf"\b(?:{_NUMBER})[\s-]*(?:months?|weeks?|days?)[\s-]*old\b", re.IGNORECASE)

PAEDIATRIC_REFUSAL = (
    "This app can't assess children. Call a doctor or emergency services.")


def _number(s):
    s = s.lower()
    if s.isdigit():
        return int(s)
    if s in ("a", "an"):
        return 1
    return sum(10 * (_TENS.index(w) + 2) if w in _TENS else _UNITS.index(w)
               for w in re.split(r"[\s-]+", s))


def child_term(text):
    """The words in `text` that make the subject a child, or None. Asks, never
    refuses: see the block above."""
    m = CHILD.search(text) or AGE_INFANT.search(text)
    if m:
        return m.group(0)
    for m in AGE_YEARS.finditer(text):
        if _number(next(g for g in m.groups() if g)) < 16:
            return m.group(0)
    return None


def is_child_profile(profile):
    """A selected profile under 16, which gets the scope notice and no verdict."""
    age = (profile or {}).get("age")
    return isinstance(age, (int, float)) and age < 16


def excluded_subject(text):
    """(excluded, reason, message). Subject-matter exclusions the floor cannot
    catch. Pregnancy only: children are decided by profile age, not text."""
    t = str(text or "")
    preg = PREGNANCY.search(NOT_PREGNANT.sub(" ", t))
    sym = PREGNANCY_SYMPTOM.search(t)
    if preg and sym:
        return True, (f'pregnancy or a late or missed period ("{preg.group(0)}") '
                      f'with a chest or abdominal symptom ("{sym.group(0)}"), '
                      f"which the corpus has no content for"), PREGNANCY_REFUSAL
    return False, "", ""


# SUBJECT SCOPE. Refuses before generation when the text names a body part or
# complaint OUTSIDE the chest-pain territory and names NOTHING inside it.
# Added 2026-09-29 after an audit of the tuned model.
#
# WHY IT HAD TO EXIST. The post-flight check refuses a yellow or green that
# cites nothing, and on the BASE model that caught most out-of-scope queries,
# because the base cited nothing when it had nothing. The fine-tune took
# non-red answers citing nothing from 9/33 to 0/53, so the tuned model ALWAYS
# cites something, and the post-flight check stopped firing on anything.
# Measured live on the tuned model 2026-09-29, all three triaged, none refused:
#     "My knee has been swollen and stiff since I twisted it playing football
#      yesterday"                                  YELLOW, citing a DVT chunk
#     "I have had a bad headache for three days and light hurts my eyes"
#                                                  YELLOW, citing heart attack
#                                                  symptoms, its own Why saying
#                                                  the context "does not describe
#                                                  headache"
#     "My tooth is killing me and the side of my face aches"
#                                                  GREEN self-care, citing heart
#                                                  inflammation
# The floor could not catch them either: the classes overlap on cosine (see
# the calibration above), and all three clear 0.25.
#
# THE RULE, revised 2026-09-29 on Viraj's call: two tiers inside, and two
# companions rescue. Refuse when a term from OFF_TERRITORY matches, NO term from
# CORE matches, and FEWER THAN TWO different COMPANIONS match.
#
# CORE is the corpus's own ground, the presenting complaints it covers: the
# chest, heart and lungs, breathing, palpitations, reflux and swallowing, the
# upper stomach, panic. One core word keeps a text in, whatever else it says.
#
# COMPANIONS are the places heart pain spreads to (jaw, neck, arms, shoulders,
# back, front), the legs for a clot (CP-PE-001), and what a heart attack or panic
# attack comes with, from CP-ACS-003 and CP-PANIC-001 (sweating, dizziness,
# fainting, nausea, vomiting, tiredness, weakness, anxiety), plus cough. ONE companion no
# longer keeps a text in: with only one tier, "headache and feeling sick",
# "headache, stiff neck and fever", "rash on my arm" and "sprained my wrist and
# feel dizzy" all passed, because sick, neck, arm and dizzy were inside. TWO
# DIFFERENT companions do keep it in, because that is how an atypical heart
# attack reads when it names a body part the corpus does not: "My tooth hurts
# and I feel sweaty and sick" is not refused.
#
# A text that names nothing from OFF_TERRITORY is still NEVER refused, whatever
# else it says ("I suddenly feel drained and a bit queasy", "feels like an
# elephant is sitting on me"). HE01 says outright "There is no real chest pain",
# and refusing a real presentation is the catastrophic direction.
#
# OFF_TERRITORY is body parts and complaints the corpus does not cover as a
# presenting complaint. It is not "words the corpus never uses": CP-PNA-001
# lists headache and diarrhoea among the symptoms that can come WITH pneumonia.
# A pneumonia text carries breathlessness, which is core. "broke" is in, for "I
# think I broke my arm"; "broke out", as in a sweat, is not.
#
# MEASURED 2026-09-29, over 168 in-scope texts: the 22 held-out cases, all 120
# training pairs, the 3 demo presets, 1 heartburn phrasing, the 12 colloquial
# in-scope calibration queries and 10 stress phrasings of atypical heart attack,
# DVT and reflux. 165 pass. THREE STRESS PHRASINGS ARE REFUSED, the accepted
# cost of the tiers, each with one companion and one outside word:
#     "I feel faint and my vision went blurry"            faint / vision
#     "My knee and calf are swollen after a long flight"  calf / knee
#     "Pain in my left arm and my hand is tingling"       arm / hand
# None of the 22 held-out cases, 120 pairs, presets or calibration queries is
# refused. Out of scope, all 15 refused, including the two the single tier let
# through ("a rash on my arm", "a sore throat and a cough").
# It is a lexicon, and a lexicon has holes. The post-flight check and the floor
# still run after it; it adds a layer, it replaces none.
CORE_TERRITORY = re.compile(
    r"\b(chest\w*|breast\s*bone|sternum|ribs?|heart\w*|cardiac|palpitat\w*|pulse|"
    r"breath\w*|winded|out\s+of\s+puff|lungs?|pleur\w*|"
    r"indigestion|heartburn|reflux|acid\w*|swallow\w*|epigastr\w*|"
    r"upper\s+(?:stomach|belly|tummy|abdomen)|panic\w*)\b", re.IGNORECASE)

# One pattern per companion, so two words for the same thing ("sweaty",
# "sweating") count once.
COMPANIONS = tuple(re.compile(rf"\b(?:{w})\b", re.IGNORECASE) for w in (
    r"jaw\w*", r"neck", r"arms?", r"shoulders?", r"back", r"front", r"legs?",
    r"calf|calves", r"cough\w*", r"sweat\w*", r"clammy", r"dizz\w*",
    r"light[\s-]?headed\w*", r"faint\w*", r"nause\w*", r"queas\w*", r"sick",
    r"tired\w*", r"exhaust\w*", r"drained", r"fatigue\w*", r"weak\w*", r"anxi\w*",
    # Vomiting, added 2026-09-29 (Viraj's omission from the first split): one
    # companion however it is said, so "vomiting" and "threw up" count once.
    r"vomit\w*|thr(?:ow(?:s|ing)?|ew)\s+up"))

OFF_TERRITORY = re.compile(
    r"\b(head|headaches?|migraines?|eyes?|eyesight|vision|ears?|earache|"
    r"tooth|teeth|toothache|dental|gums?|face|facial|nose|sinus\w*|sore\s+throat|"
    r"skin|rash\w*|itch\w*|"
    r"knees?|ankles?|wrists?|hands?|fingers?|thumbs?|toes?|foot|feet|hips?|elbows?|"
    r"pee|peeing|urin\w*|bladder|diarrh\w*|constipat\w*|"
    r"sprain\w*|twist\w*|rolled|fractur\w*|broke(?!\s+out)|broken|break|"
    r"feeling\s+(?:really\s+|very\s+|so\s+)?(?:down|low)|low\s+mood|depress\w*|"
    r"can(?:no|['’])?t\s+sleep|insomnia)\b", re.IGNORECASE)


def companions(text):
    """The different companions `text` names, one per kind."""
    return [m.group(0) for m in (c.search(text) for c in COMPANIONS) if m]


def off_territory(text):
    """(refuse, reason). Refuses when `text` names something outside the
    chest-pain territory, nothing from its core, and fewer than two different
    companions. See the block above."""
    t = str(text or "")
    off = OFF_TERRITORY.search(t)
    if not off or CORE_TERRITORY.search(t) or len(companions(t)) >= 2:
        return False, ""
    return True, (f'the question is about "{off.group(0)}", and nothing in it '
                  f"is about the chest, heart or breathing, which is all the "
                  f"corpus covers")


def scope_check(max_cosine=None, citations=None, floor=SCOPE_FLOOR):
    """(in_scope, reason). Either condition failing refuses the whole verdict,
    except that a red is never withheld: post-flight goes through post_flight.

    Call it twice: once with max_cosine before generating, once with citations
    after the citation guard. Passing only one argument checks only that one.
    """
    if max_cosine is not None and max_cosine < floor:
        return False, (f"nothing in the corpus is relevant to this query "
                       f"(best match {max_cosine:.3f}, floor {floor:.2f})")
    if citations is not None and not citations:
        return False, ("the model cited nothing, so it had no grounded source "
                       "to reason from")
    return True, ""


# NEVER WITHHOLD A RED. Viraj's call 2026-09-18, with a condition.
#
# Measured the same night: textbook ACS, "There is a heaviness across my front
# and my left arm has gone dead", came back with citations [] and urgency RED in
# 3 runs of 30, each rationale saying "possible heart attack". The post-flight
# check withheld all three and told the patient a heart attack was out of scope.
# The 19 out-of-scope refusals measured alongside withheld green or yellow every
# time and never red, so on that data this rescues all 3 and lets none of the 19
# through.
#
# THE CONDITION: an ungrounded red is never rendered as a clean, confident red.
# Only the urgency survives. The page shows it with its disposition and
# UNGROUNDED_NOTE, and no sources panel. The rationale, red flags, next steps
# and questions are withheld, because none of them is grounded in a source.
# The caller gets them back separately; nothing is silently dropped. A yellow or
# green that cites nothing is still refused.
UNGROUNDED_NOTE = ("We couldn't match this to a source, so we're only showing the "
                   "urgency. We don't hide a possible emergency.")


def post_flight(result):
    """(action, reason, shown) once every other guard has run. action is
    "render", "refuse", or "flag": a red that cites nothing, shown as the
    urgency alone and never withheld."""
    ok, why = scope_check(citations=result.get("citations"))
    if ok:
        return "render", "", result
    if result.get("urgency") != "red":
        return "refuse", why, result
    return "flag", why, {"urgency": "red", "rationale": "", "red_flags": [],
                         "next_steps": [], "citations": [],
                         "follow_up_questions": []}


# ---------------------------------------------------------------- all four

def apply_guards(raw, registry, case_text=None, case_present=None):
    """Parse raw model text and apply every guard.

    Returns (result, dropped, flagged). `result` is safe to render.

    `case_text` is the profile, timeline and symptom text, never the retrieved
    chunk. Without it the grounding guard is skipped and that is reported in
    dropped["red_flags_skipped"], because silently not running a safety check is
    the failure mode this whole file exists to avoid.
    """
    parsed = parse_model_json(raw)
    cites_kept, cites_dropped = screen_citations(parsed.get("citations"), registry)
    steps_kept, steps_dropped, steps_flagged = screen_next_steps(parsed.get("next_steps"))
    fups_kept, fups_dropped = screen_follow_ups(
        parsed.get("urgency"), parsed.get("follow_up_questions"))

    if case_text:
        rf_kept, rf_dropped = screen_red_flags(
            parsed.get("red_flags"), case_text, case_present)
        rf_skipped = False
    else:
        rf_kept, rf_dropped = list(parsed.get("red_flags") or []), []
        rf_skipped = True

    result = dict(parsed)
    result["citations"] = cites_kept
    result["next_steps"] = steps_kept
    result["follow_up_questions"] = fups_kept
    result["red_flags"] = rf_kept
    dropped = {"citations": cites_dropped,
               "next_steps": steps_dropped,
               "follow_up_questions": fups_dropped,
               "red_flags": rf_dropped,
               "red_flags_skipped": rf_skipped}
    return result, dropped, {"next_steps": steps_flagged}


def load_registry(path=None):
    """The 22 frozen keys. Hard constraint 9's source of truth."""
    import csv
    from pathlib import Path
    p = Path(path) if path else Path(__file__).resolve().parent.parent / "01-data" / "citations.csv"
    with open(p, encoding="utf-8") as f:
        return {row["key"] for row in csv.DictReader(f)}


if __name__ == "__main__":
    import pathlib

    reg = load_registry()
    fx = json.loads((pathlib.Path(__file__).resolve().parent /
                     "guard_fixtures.json").read_text(encoding="utf-8"))
    passed = failed = 0

    def check(name, cond, detail=""):
        global passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond and detail:
            print(f"        {detail}")

    for c in fx["parse"]:
        try:
            json.loads(c["raw"])
            threw = False
        except json.JSONDecodeError:
            threw = True
        check(f"parse/bare-throws: {c['name']}", threw == c["bare_parse_throws"])
        check(f"parse/guarded: {c['name']}",
              parse_model_json(c["raw"]).get("urgency") == c["urgency"])

    for c in fx["next_steps"]:
        kept, dropped, flagged = screen_next_steps(c["steps"])
        check(f"next_steps: {c['name']}",
              kept == c["kept"] and dropped == c["dropped"] and flagged == c["flagged"],
              f"kept={kept} dropped={dropped} flagged={flagged}")

    # `exclusion` names which one must fire, so the right refusal is shown.
    messages = {"pregnancy": PREGNANCY_REFUSAL}
    for c in fx.get("exclusions", []):
        got, why, msg = excluded_subject(c["text"])
        check(f"exclusion: {c['name']}",
              got == c["excluded"] and
              ("exclusion" not in c or msg == messages[c["exclusion"]]),
              f"got excluded={got} {why}")

    # A child word on an adult profile asks who this is about. It never refuses.
    for c in fx.get("child_subject", []):
        term = child_term(c["text"])
        check(f"child_subject: {c['name']}", (term is not None) == c["asks"],
              f"got {term!r}")

    for c in fx.get("child_profile", []):
        check(f"child_profile: {c['name']}",
              is_child_profile(c["profile"]) == c["child"])

    for c in fx.get("scope", []):
        ok, why = scope_check(c["max_cosine"], c["citations"])
        check(f"scope: {c['name']}", ok == c["in_scope"], f"got in_scope={ok} {why}")

    # Subject scope: the 22 held-out cases, the demo presets and the audit's
    # out-of-scope cases, each with the answer it must get.
    for c in fx.get("subject_scope", []):
        refused, why = off_territory(c["text"])
        check(f"subject_scope: {c['name']}", refused == c["refused"],
              f"got refused={refused} {why}")

    # And no training pair may be refused: they are all chest pain, written by
    # hand, in every register the pairs cover.
    pairs = Path(__file__).resolve().parent / "review" / "candidates-120.jsonl"
    hit = []
    for line in pairs.read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        h = next(x["value"] for x in p["conversations"] if x["from"] == "human")
        said = "\n".join(m.group(1) for m in re.finditer(
            r"\[(?:SYMPTOMS|SYMPTOM TIMELINE)\]\n(.*?)\n\[/", h, re.S))
        if off_territory(said)[0]:
            hit.append(p["id"])
    check("subject_scope: no training pair is refused", not hit, f"refused {hit}")

    # A flagged red must carry the urgency and nothing else the model wrote.
    for c in fx.get("post_flight", []):
        action, _, shown = post_flight(c["result"])
        bare = action != "flag" or (shown["urgency"] == "red" and not any(
            shown[k] for k in ("rationale", "red_flags", "next_steps",
                               "citations", "follow_up_questions")))
        check(f"post_flight: {c['name']}", action == c["action"] and bare,
              f"got action={action} shown={shown}")

    for c in fx.get("red_flags", []):
        kept, dropped = screen_red_flags(c["red_flags"], c["case_text"],
                                         c.get("case_present"))
        check(f"red_flags: {c['name']}",
              kept == c["kept"] and [d["entry"] for d in dropped] == c["dropped"],
              f"kept={kept} dropped={[d['entry'] for d in dropped]}")

    for c in fx["citations"]:
        kept, dropped = screen_citations(c["citations"], reg)
        check(f"citations: {c['name']}",
              kept == c["kept"] and dropped == c["dropped"],
              f"kept={kept} dropped={dropped}")

    for c in fx["follow_ups"]:
        kept, dropped = screen_follow_ups(c["urgency"], c["questions"])
        check(f"follow_ups: {c['name']}",
              kept == c["kept"] and dropped == c["dropped"],
              f"kept={kept} dropped={dropped}")

    print(f"\n{passed}/{passed + failed} self-tests passed "
          f"(fixtures shared with guards.ts).")
    raise SystemExit(0 if failed == 0 else 1)
