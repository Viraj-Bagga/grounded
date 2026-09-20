#!/usr/bin/env python3
"""THE PROMPT DOES NOT MOVE. Offline, no server, no model.

    .venv/bin/python 06-demo/selftest_profile_text.py

WHY THIS FILE EXISTS. `profile_text` builds the [PATIENT PROFILE] block the
model reads, and that block is part of the prompt llama-server caches. The
seeded household has to keep producing BYTE-IDENTICAL prompt text, because
every latency number, every recorded run and every demo beat was measured
against those exact bytes.

Patient records grew on 2026-09-20: a patient ID, a medication schedule,
history notes, who last saw them and when. None of that is clinical input to
triage, and none of it may reach the model. The danger is not that someone
adds a field on purpose; it is that someone makes `medications` richer, since
`profile_text` joins that list into a line. So the expected strings below are
written out in full rather than computed, and the tests add every record field
at once and demand the prompt come back the same.

If this fails, DO NOT update the expected strings to match. The prompt moved,
and everything measured against it is now measuring something else.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from store import NO_PROFILE, SEED_PEOPLE, clean_person, profile_text  # noqa: E402

# Written out, not generated. A generated expectation would move with the code
# it is supposed to pin.
EXPECTED = {
    "self": "age: 29, sex: female\nconditions: none\nmedications: none",
    "mum": ("age: 64, sex: female\n"
            "conditions: type 2 diabetes, coronary artery disease\n"
            "medications: metformin, atorvastatin"),
    "dad": ("age: 71, sex: male\n"
            "conditions: atrial fibrillation, high blood pressure\n"
            "medications: apixaban 5mg twice daily, bisoprolol"),
    "aunt": ("age: 52, sex: female\n"
             "conditions: breast cancer\n"
             "medications: chemotherapy"),
    "grandpa": ("age: 77, sex: male\n"
                "conditions: high blood pressure\n"
                "medications: amlodipine\n"
                "recent surgery: hip replacement, 5 weeks ago"),
    "maya": "age: 6, sex: female\nconditions: none\nmedications: none",
}

NO_PROFILE_TEXT = ("age: not given, sex: not given\n"
                   "conditions: not given\nmedications: not given")

# Every record field at once, on top of a real person.
RECORDS = {
    "patient_id": "CHW-2026-0041",
    "medication_schedule": {"metformin": "500mg twice daily with food",
                            "atorvastatin": "20mg at night"},
    "history_notes": "Seen at the clinic in March for chest tightness on exertion. "
                     "ECG normal. Advised to return if it changes.",
    "last_seen_by": "Dr Amara Okafor, district clinic",
    "last_seen_on": "2026-08-14",
}

ok = fails = 0


def check(name, cond, detail=""):
    global ok, fails
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fails += 1
        print(f"  FAIL  {name}{chr(10) + '        ' + detail if detail else ''}")


print("the seeded household's prompt text, byte for byte")
for p in SEED_PEOPLE:
    got = profile_text(p)
    want = EXPECTED[p["id"]]
    check(f"{p['label']} ({p['id']})", got == want,
          f"got:  {got!r}\n        want: {want!r}")

check("No profile says 'not given', never 'none'",
      profile_text(NO_PROFILE) == NO_PROFILE_TEXT, repr(profile_text(NO_PROFILE)))

print("\nrecord fields do not reach the prompt")
for p in SEED_PEOPLE:
    before = profile_text(p)
    after = profile_text({**p, **RECORDS})
    check(f"{p['label']}: every record field added, prompt unchanged",
          after == before, f"before: {before!r}\n        after:  {after!r}")

print("\nthe fields survive validation, and still do not reach the prompt")
raw = dict(label="Test", age=64, sex="female",
           conditions=["type 2 diabetes"], medications=["metformin"], **RECORDS)
person, errors = clean_person(raw)
check("a person with every record field validates", not errors, repr(errors))
check("the patient ID is kept", person.get("patient_id") == "CHW-2026-0041")
check("the medication schedule is kept as its own field",
      person.get("medication_schedule") == RECORDS["medication_schedule"])
check("history notes are kept", person.get("history_notes") == RECORDS["history_notes"])
check("who last saw them is kept", person.get("last_seen_by") == RECORDS["last_seen_by"])
check("when they were last seen is kept", person.get("last_seen_on") == "2026-08-14")

check("MEDICATIONS IS STILL A LIST OF STRINGS",
      person["medications"] == ["metformin"], repr(person.get("medications")))
check("the schedule did not leak into the prompt",
      profile_text(person) == "age: 64, sex: female\nconditions: type 2 diabetes\n"
                              "medications: metformin",
      repr(profile_text(person)))
check("no record value appears anywhere in the prompt",
      not any(str(v) in profile_text(person) for v in
              ["CHW-2026-0041", "500mg twice daily with food", "Dr Amara Okafor", "2026-08-14"]),
      repr(profile_text(person)))

print("\nbad record values are refused, and refusing does not change the prompt")
_, errs = clean_person(dict(label="T", age=30, sex="male", conditions=[], medications=[],
                            last_seen_on="14/08/2026"))
check("a malformed date is refused", "last_seen_on" in errs, repr(errs))
_, errs = clean_person(dict(label="T", age=30, sex="male", conditions=[], medications=[],
                            history_notes="x" * 601))
check("over-long notes are refused", "history_notes" in errs, repr(errs))
p2, errs = clean_person(dict(label="T", age=30, sex="male", conditions=[], medications=[],
                             medication_schedule={"  ": "  ", "aspirin": "75mg daily"}))
check("blank schedule rows are dropped, real ones kept",
      not errs and p2.get("medication_schedule") == {"aspirin": "75mg daily"}, repr(p2.get("medication_schedule")))

print(f"\n{ok}/{ok + fails} self-tests passed.")
raise SystemExit(1 if fails else 0)
