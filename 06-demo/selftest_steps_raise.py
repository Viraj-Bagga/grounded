"""Self-test for steps_raise.py, on the saved answers where it happened.

    python 06-demo/selftest_steps_raise.py

The fixtures are real assessments from the 27 September demo data, copied
before the data was reset: two yellows whose steps said "Call emergency
services now", and one whose only call was conditional.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "02-pairs"))
from steps_raise import emergency_step, raise_on_steps, REASON  # noqa: E402

fails = []


def check(name, ok):
    if not ok:
        fails.append(name)
    print(("ok    " if ok else "FAIL  ") + name)


def first_turn(fixture):
    conv = json.loads((HERE / "fixtures" / "steps-raise" / fixture).read_text())
    return conv["sides"][0]["turns"][0]["event"]


# The saved answers.
for fx, raises in [("20260927-165457-66f910.json", True),   # yellow, "Call emergency services now"
                   ("20260927-163627-4d8a6b.json", True),   # the same, beside "Call 9-1-1 if ..."
                   ("20260927-143822-4d6d49.json", False)]: # yellow, "... now if the tightness ..."
    ev = first_turn(fx)
    r, esc = ev["result"], ev["escalation"]
    out = raise_on_steps(esc, r["next_steps"])
    if raises:
        check(f"{fx}: a {r['urgency']} whose steps say call now is raised to red",
              out["final"] == "red" and out["changed"])
        s1 = [f for f in out["fired"] if f.get("kind") == "steps"]
        check(f"{fx}: it is shown like a raise, with the reason",
              len(s1) == 1 and s1[0]["status"] == "raised" and s1[0]["name"] == REASON)
    else:
        check(f"{fx}: a conditional call does not raise", out == esc)

# The edges, one line each.
cases = [
    (["Call emergency services now"], True),
    (["Call an ambulance."], True),
    (["Go to the emergency department"], False),
    (["Go to the emergency department", "Rest"], False),
    (["Call 9-1-1 if the pain comes back at rest"], False),
    (["Call emergency services now if you become breathless"], False),
    (["You do not need to call an ambulance"], False),
    (["Call your GP today"], False),
    (["Rest now; call emergency services"], True),
    (["Seek assessment if it happens again"], False),
]
for steps, expect in cases:
    check(f"{steps!r} {'raises' if expect else 'does not raise'}", bool(emergency_step(steps)) == expect)

# Only ever raises: a red, or no urgency, comes back untouched.
red = {"original": "red", "final": "red", "changed": False, "fired": []}
check("a red is never touched", raise_on_steps(red, ["Call emergency services now"]) is red)
none = {"original": None, "final": None, "changed": False, "fired": []}
check("no urgency is never touched", raise_on_steps(none, ["Call emergency services now"]) is none)
# A profile raise to yellow stays on the page, as "at least yellow".
prof = {"original": "green", "final": "yellow", "changed": True,
        "fired": [{"rule": "R1", "status": "raised", "cap": "red"}]}
out = raise_on_steps(prof, ["Call emergency services now"])
check("a profile raise under it becomes at least yellow",
      out["final"] == "red" and out["fired"][0]["status"] == "at_least" and out["fired"][0]["to"] == "yellow")

n = len(fails)
print(f"{n} failed" if n else f"{3 * 2 - 1 + len(cases) + 3}/{3 * 2 - 1 + len(cases) + 3} self-tests passed.")
sys.exit(1 if n else 0)
