"""Persistence for the demo: the household's people and the saved assessments.

Plain JSON under 06-demo/data/, written atomically (a temp file, then rename),
so a crash mid-write leaves the previous version on disk, never half a file.

PEOPLE live in one file, data/people.json. On first run it is seeded from
SEED_PEOPLE with the ids unchanged: "You" and "Dad" must still render
byte-identical prompt text to the profiles the model was always shown, and the
Mum preset picks "mum".

ASSESSMENTS live one file each, data/conversations/<id>.json. An assessment
freezes a snapshot of each person's profile when it starts, because that
profile text is part of the model's cached prompt. Editing or deleting a person
changes new assessments only, never one already under way, and a deleted
person's assessments stay in the history under the name they had.
"""

import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# THE FAMILY, as seeded. The facts the escalation rules read, structured,
# because rules must read facts rather than parse prose. Each person beyond You
# and Dad is there to show a rule on their own card: Mum R1 and R3, Aunt Sue R4,
# Grandpa R2 and R5, Maya the child scope notice. Demo data, not patients.
SEED_PEOPLE = [
    dict(id="self", label="You", age=29, sex="female", conditions=[], medications=[]),
    dict(id="mum", label="Mum", age=64, sex="female",
         conditions=["type 2 diabetes", "coronary artery disease"],
         medications=["metformin", "atorvastatin"]),
    dict(id="dad", label="Dad", age=71, sex="male",
         conditions=["atrial fibrillation", "high blood pressure"],
         medications=["apixaban 5mg twice daily", "bisoprolol"]),
    dict(id="aunt", label="Aunt Sue", age=52, sex="female",
         conditions=["breast cancer"], medications=["chemotherapy"]),
    dict(id="grandpa", label="Grandpa", age=77, sex="male",
         conditions=["high blood pressure"], medications=["amlodipine"],
         surgery=dict(what="hip replacement", weeks_ago=5)),
    dict(id="maya", label="Maya", age=6, sex="female", conditions=[], medications=[]),
]

# "NO PROFILE": a general question with nobody behind it, and the default since
# 2026-09-19. It is NOT in the store: it is never written to people.json, never
# listed on the People page, and cannot be edited or deleted. PeopleStore.get
# returns it by id so an assessment can be started for it like anyone else.
# With no age, no sex and no conditions, every escalation fact function returns
# None and no rule fires, and is_child_profile is False because age is None.
NO_PROFILE = dict(id="none", label="No profile", age=None, sex=None,
                  conditions=[], medications=[], virtual=True)

SEXES = ("female", "male")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
CONV_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def profile_text(p):
    """The [PATIENT PROFILE] block the model sees. Unchanged from the
    single-shot demo, so the seeded people give byte-identical prompts."""
    if p.get("virtual"):
        # "not given", never "none". A profile that says `medications: none` has
        # already been measured negating a symptom asserted two lines later
        # (constraint 11), and an absent profile is not a denial of anything.
        return ("age: not given, sex: not given\n"
                "conditions: not given\nmedications: not given")
    lines = [f"age: {p['age']}, sex: {p['sex']}",
             "conditions: " + (", ".join(p["conditions"]) or "none"),
             "medications: " + (", ".join(p["medications"]) or "none")]
    if p.get("surgery"):
        lines.append(f"recent surgery: {p['surgery']['what']}, "
                     f"{p['surgery']['weeks_ago']} weeks ago")
    return "\n".join(lines)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _clean_list(values, field, errors):
    if values is None:
        return []
    if isinstance(values, str):
        values = [v for v in re.split(r"[,\n]", values)]
    if not isinstance(values, list):
        errors[field] = "Should be a list."
        return []
    out, seen = [], set()
    for v in values:
        v = " ".join(str(v).split())
        if not v or v.lower() in seen:
            continue
        if len(v) > 60:
            errors[field] = "Keep each entry under 60 characters."
            continue
        seen.add(v.lower())
        out.append(v)
    if len(out) > 12:
        errors[field] = "At most 12 entries."
        out = out[:12]
    return out


def clean_person(data):
    """Validate a person from the form. Returns (person without id, errors)."""
    errors = {}
    data = data if isinstance(data, dict) else {}
    label = " ".join(str(data.get("label") or "").split())
    if not label:
        errors["label"] = "Enter a name."
    elif len(label) > 40:
        errors["label"] = "Keep the name under 40 characters."

    age = data.get("age")
    try:
        age = int(str(age).strip())
        if not 0 <= age <= 120:
            errors["age"] = "Enter an age from 0 to 120."
    except (TypeError, ValueError):
        errors["age"] = "Enter an age in whole years."
        age = None

    sex = str(data.get("sex") or "").strip().lower()
    if sex not in SEXES:
        errors["sex"] = "Choose female or male."

    person = dict(label=label, age=age, sex=sex,
                  conditions=_clean_list(data.get("conditions"), "conditions", errors),
                  medications=_clean_list(data.get("medications"), "medications", errors))

    surgery = data.get("surgery")
    if isinstance(surgery, dict) and (surgery.get("what") or surgery.get("weeks_ago") not in (None, "")):
        what = " ".join(str(surgery.get("what") or "").split())
        if not what:
            errors["surgery"] = "Say what the surgery was."
        elif len(what) > 60:
            errors["surgery"] = "Keep it under 60 characters."
        try:
            weeks = int(str(surgery.get("weeks_ago")).strip())
            if not 0 <= weeks <= 520:
                errors["surgery_weeks"] = "Enter weeks ago, from 0 to 520."
        except (TypeError, ValueError):
            errors["surgery_weeks"] = "Enter how many weeks ago, in whole weeks."
            weeks = None
        person["surgery"] = dict(what=what, weeks_ago=weeks)
    return person, errors


class PeopleStore:
    def __init__(self, path=DATA / "people.json"):
        self.path = path
        self.lock = threading.Lock()

    def _load(self):
        if not self.path.exists():
            _write_json(self.path, {"people": SEED_PEOPLE})
        return json.loads(self.path.read_text(encoding="utf-8"))["people"]

    def list(self):
        with self.lock:
            return self._load()

    def get(self, pid):
        if pid == NO_PROFILE["id"]:
            return dict(NO_PROFILE)
        return next((p for p in self.list() if p["id"] == pid), None)

    def _new_id(self, label, existing):
        base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:32] or "person"
        pid = base
        while pid in existing:
            pid = f"{base}-{secrets.token_hex(2)}"
        return pid

    def create(self, data):
        person, errors = clean_person(data)
        if errors:
            return None, errors
        with self.lock:
            people = self._load()
            person = dict(id=self._new_id(person["label"], {p["id"] for p in people}), **person)
            people.append(person)
            _write_json(self.path, {"people": people})
        return person, {}

    def update(self, pid, data):
        if pid == NO_PROFILE["id"]:
            return None, {"id": "No profile cannot be edited."}
        person, errors = clean_person(data)
        if errors:
            return None, errors
        with self.lock:
            people = self._load()
            for i, p in enumerate(people):
                if p["id"] == pid:
                    people[i] = dict(id=pid, **person)
                    _write_json(self.path, {"people": people})
                    return people[i], {}
        return None, {"id": "No such person."}

    def delete(self, pid):
        if pid == NO_PROFILE["id"]:
            return False
        with self.lock:
            people = self._load()
            kept = [p for p in people if p["id"] != pid]
            if len(kept) == len(people):
                return False
            _write_json(self.path, {"people": kept})
            return True


class ConversationStore:
    """One JSON file per assessment.

    Two sides of a compare assessment stream at the same time and both write
    to the same file, so every change goes through update(): lock, re-read
    from disk, apply, write. A side never saves a stale copy it loaded before
    the other side finished.
    """

    def __init__(self, root=DATA / "conversations"):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks = {}
        self._guard = threading.Lock()

    def _lock(self, cid):
        with self._guard:
            return self._locks.setdefault(cid, threading.Lock())

    def path(self, cid):
        if not CONV_ID_RE.match(cid or ""):
            raise KeyError(cid)
        return self.root / f"{cid}.json"

    def create(self, people):
        cid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
        conv = dict(id=cid, created=now_iso(), updated=now_iso(),
                    mode="compare" if len(people) == 2 else "single", title="",
                    sides=[dict(person_id=p["id"], profile=p, profile_text=profile_text(p),
                                slot=None, anchor=None, llm=[], turns=[],
                                context_tokens=0) for p in people])
        with self._lock(cid):
            _write_json(self.path(cid), conv)
        return conv

    def get(self, cid):
        try:
            p = self.path(cid)
        except KeyError:
            return None
        if not p.exists():
            return None
        with self._lock(cid):
            return json.loads(p.read_text(encoding="utf-8"))

    def update(self, cid, fn):
        """Apply fn(conv) to the file as it is on disk right now, and save."""
        with self._lock(cid):
            p = self.path(cid)
            conv = json.loads(p.read_text(encoding="utf-8"))
            fn(conv)
            conv["updated"] = now_iso()
            _write_json(p, conv)
            return conv

    def summaries(self):
        out = []
        for p in sorted(self.root.glob("*.json"), reverse=True):
            try:
                conv = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not any(s["turns"] for s in conv["sides"]):
                continue                    # created, never sent: not an assessment yet
            out.append(summary(conv))
        out.sort(key=lambda s: s["updated"], reverse=True)
        return out


def side_state(side):
    """What the history row shows for one side: its latest shown outcome."""
    for turn in reversed(side["turns"]):
        ev = turn.get("event") or {}
        kind = turn.get("kind")
        if kind == "result":
            return dict(state=(ev.get("result") or {}).get("urgency"),
                        ungrounded=bool(ev.get("ungrounded")))
        if kind == "refused":
            return dict(state="child" if ev.get("child") else "refused", ungrounded=False)
        if kind == "error":
            return dict(state="error", ungrounded=False)
    return dict(state=None, ungrounded=False)


def summary(conv):
    return dict(id=conv["id"], title=conv["title"], created=conv["created"],
                updated=conv["updated"], mode=conv["mode"],
                turns=max(len(s["turns"]) for s in conv["sides"]),
                sides=[dict(person_id=s["person_id"], label=s["profile"]["label"],
                            **side_state(s)) for s in conv["sides"]])
