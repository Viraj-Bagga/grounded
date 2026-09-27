"""THE STEPS CALL FOR EMERGENCY CARE. Viraj's rule, 2026-09-27.

A yellow or green whose own next steps tell the person, flatly, to call
emergency services or an ambulance contradicts itself. Measured: on the
27 September demo data, 2 of 88 shown yellow and green verdicts did it, both
Dad, both "Call emergency services now" under "Be seen today". The app raises
such a verdict to RED and says why: "Raised to red: the steps call for
emergency care." It is shown like a profile raise, so constraint 16 then
strikes the model's rationale and replaces its steps with the app's own.

ONLY UNCONDITIONAL, Viraj's call the same day. 57 of those 88 carried a
safety net such as "Call 9-1-1 if it comes on at rest", which is consistent
with a yellow, not a contradiction of it. So a step raises only when a clause
tells the person to call with no condition in it (if, when, unless, should,
in case, once) and no negation before the call. "Go to the emergency
department" alone does not raise: it calls nobody.

It only ever raises, and it never touches a red or a verdict with no
urgency. Self-test: python 06-demo/selftest_steps_raise.py, which replays the
saved answers in 06-demo/fixtures/steps-raise/.
"""

import re

LEVELS = ("green", "yellow", "red")
REASON = "the steps call for emergency care"

_CALL = re.compile(
    r"\bcall(?:ing)?\b.*?\b(?:emergency services|emergency number|an? ambulance|ambulance"
    r"|9-?1-?1|999|112|108)\b", re.I)
_CONDITION = re.compile(r"\b(?:if|when|whenever|unless|should|in case|once)\b", re.I)
_NEGATION = re.compile(r"\b(?:do not|don't|dont|doesn't|no need|not need|never|without)\b", re.I)


def emergency_step(steps):
    """The first step with a clause that tells the person, with no condition,
    to call emergency services or an ambulance. None if there is none."""
    for step in steps or []:
        for clause in re.split(r"[.;]", str(step)):
            m = _CALL.search(clause)
            if m and not _CONDITION.search(clause) and not _NEGATION.search(clause[:m.start()]):
                return step
    return None


def raise_on_steps(escalation, steps):
    """`escalation`, raised to red when the steps call for emergency care.

    Takes the profile layer's escalation (02-pairs/escalation.py) and returns
    one of the same shape. A profile rule that had raised the verdict keeps
    its line, now as "at least" the level it reached."""
    final = escalation.get("final")
    if final not in ("yellow", "green"):
        return escalation
    step = emergency_step(steps)
    if step is None:
        return escalation
    fired = []
    for f in escalation.get("fired") or []:
        f = dict(f)
        if f.get("status") == "raised":
            f["status"], f["to"] = "at_least", final
        fired.append(f)
    fired.append(dict(rule="S1", kind="steps", name=REASON, action="escalate", cap="red",
                      status="raised", fact="", symptom="", keys=[], quote=step,
                      quotes=[], step=step))
    out = dict(escalation, final="red", changed=escalation.get("original") != "red", fired=fired)
    assert LEVELS.index(out["final"]) >= LEVELS.index(final), "it only ever raises"
    return out
