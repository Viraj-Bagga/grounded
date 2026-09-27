"""The caseload: who is waiting to be assessed, and who has been seen.

NAMED caseload.py, NOT queue.py. 06-demo is first on sys.path, so a
queue.py here shadows the stdlib `queue` that concurrent.futures and
multiprocessing import, and the failure lands somewhere unrelated.

A health worker in a village does not open the app to assess one person. They
arrive with a list. This is that list.

WHY THIS IS ITS OWN FILE AND NOT A FIELD ON A PERSON. `clean_person` validates
and rewrites the WHOLE person on every edit, so any field it does not know
about is dropped on the next save. Worse, the person record is what
`profile_text` reads, and that text is part of the model's cached prompt
(hard constraint: the seeded people must give byte-identical prompts). Queue
state changes many times a day and has nothing to do with triage. Keeping it in
data/queue.json means editing a person can never disturb the queue, and the
queue can never disturb the prompt.

ONE WAITING ENTRY PER PERSON. Queueing someone already waiting is not an error,
it returns the entry they already have. Marking done archives the entry rather
than deleting it, because "how many did you see today" is the base dashboard's
first question and a deleted row cannot answer it.

THE MODEL NEVER SEES ANY OF THIS. No part of an entry reaches a prompt.
"""

import json
import secrets
import threading
import time
from pathlib import Path

from store import DATA, _write_json, now_iso

HERE = Path(__file__).resolve().parent

REASON_MAX = 80


def _new_id():
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


class QueueStore:
    """data/queue.json: {"entries": [...]}, newest first when listed.

    An entry is {id, person_id, reason, added, done, done_at, conversation_id}.
    """

    def __init__(self, path=DATA / "queue.json"):
        self.path = path
        self.lock = threading.Lock()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            entries = data.get("entries")
            return entries if isinstance(entries, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, entries):
        _write_json(self.path, {"entries": entries})

    def list(self):
        """Every entry, waiting first and newest first within each group."""
        entries = self._load()
        waiting = [e for e in entries if not e.get("done")]
        done = [e for e in entries if e.get("done")]
        waiting.sort(key=lambda e: e.get("added") or "", reverse=True)
        done.sort(key=lambda e: e.get("done_at") or "", reverse=True)
        return waiting, done

    def waiting_for(self, person_id):
        return next((e for e in self._load()
                     if e.get("person_id") == person_id and not e.get("done")), None)

    def add(self, person_id, reason=""):
        """Queue a person. Returns (entry, errors). Already waiting is not an
        error: it returns the entry that is already there."""
        reason = " ".join(str(reason or "").split())
        if len(reason) > REASON_MAX:
            return None, {"reason": f"Keep the note under {REASON_MAX} characters."}
        with self.lock:
            entries = self._load()
            for e in entries:
                if e.get("person_id") == person_id and not e.get("done"):
                    return e, {}
            entry = dict(id=_new_id(), person_id=person_id, reason=reason,
                         added=now_iso(), done=False, done_at=None,
                         started_at=None, conversation_id=None)
            entries.append(entry)
            self._save(entries)
            return entry, {}

    def link(self, person_id, conversation_id):
        """Record which assessment a waiting person was seen in, without
        marking them done. Called when an assessment STARTS, so the link
        survives the page being closed and the worker only has to press one
        button later. The first assessment wins: starting a second one for the
        same waiting entry does not relabel the first."""
        with self.lock:
            entries = self._load()
            for e in entries:
                if (e.get("person_id") == person_id and not e.get("done")
                        and not e.get("conversation_id")):
                    e["conversation_id"] = conversation_id
                    self._save(entries)
                    return e
        return None

    def start(self, entry_id):
        """Mark that the worker has picked this person up.

        TAPPING ASSESS CREATES NO ASSESSMENT. The conversation is only created
        when the first message is sent, so between the tap and the typing there
        is nothing to link and the row looked untouched on a list the worker had
        just been navigated away from. This is the missing half: the entry
        records that work has started, and the assessment attaches to it later.
        """
        with self.lock:
            entries = self._load()
            for e in entries:
                if e["id"] == entry_id and not e.get("done"):
                    if not e.get("started_at"):
                        e["started_at"] = now_iso()
                        self._save(entries)
                    return e
        return None

    def unstart(self, entry_id):
        """Put a started entry back to plain waiting: it was abandoned."""
        with self.lock:
            entries = self._load()
            for e in entries:
                if e["id"] == entry_id and (e.get("started_at") or e.get("conversation_id")):
                    e["started_at"] = None
                    e["conversation_id"] = None
                    self._save(entries)
                    return e
        return None

    def unlink(self, entry_id):
        """Forget the assessment an entry was linked to, so the person goes
        back to plain waiting. Used when the assessment was ABANDONED: the
        worker tapped Assess and never sent anything. Leaving the link would
        strand the row pointing at an empty conversation forever."""
        with self.lock:
            entries = self._load()
            for e in entries:
                if e["id"] == entry_id and e.get("conversation_id"):
                    e["conversation_id"] = None
                    self._save(entries)
                    return e
        return None

    def done(self, entry_id, conversation_id=None):
        """Mark an entry seen. Idempotent: marking a done entry done again
        keeps the first done_at, because that is when they were actually seen."""
        with self.lock:
            entries = self._load()
            for e in entries:
                if e["id"] != entry_id:
                    continue
                if not e.get("done"):
                    e["done"] = True
                    e["done_at"] = now_iso()
                if conversation_id and not e.get("conversation_id"):
                    e["conversation_id"] = conversation_id
                self._save(entries)
                return e
        return None

    def remove(self, entry_id):
        with self.lock:
            entries = self._load()
            kept = [e for e in entries if e["id"] != entry_id]
            if len(kept) == len(entries):
                return False
            self._save(kept)
            return True


# WAITING -> IN PROGRESS -> SEEN, and back to waiting if it was abandoned.
#
# Tapping Assess used to leave the row looking exactly as it did before, on a
# list the worker had just been navigated away from, so a person being seen
# right now was indistinguishable from one nobody had touched. Viraj's report
# 2026-09-20. The state is DERIVED from the linked assessment rather than
# stored, so it cannot go stale: see queue_view in server.py, which reconciles
# each entry against its conversation before the page is built.
def status_of(entry, failed=None):
    if entry.get("done"):
        return "seen"
    if failed:
        return "error"
    started = entry.get("started_at") or entry.get("conversation_id")
    return "in_progress" if started else "waiting"


# WHAT THE LINKED ASSESSMENT SAYS ABOUT THE PERSON. Viraj's report 2026-09-27:
# an assessment that ended in an error (the model's answer cut off at the
# token limit) marked the person SEEN, so they left the list without anyone
# having been told anything. An error is not a finished piece of work. Only a
# shown answer or a refusal is. An assessment whose turns are all errors keeps
# the person WAITING, and the row carries the error, so the worker can open it
# and try again; a later turn that finishes marks them seen as usual.
def linked_state(conv):
    """("seen", None), ("error", message) or ("open", None) for a linked
    assessment's turns."""
    turns = [t for s in (conv or {}).get("sides", []) for t in s.get("turns", [])]
    if any(t.get("kind") in ("result", "refused") for t in turns):
        return "seen", None
    errors = [t for t in turns if t.get("kind") == "error"]
    if errors:
        return "error", (errors[-1].get("event") or {}).get("message") or "The answer did not finish."
    return "open", None


def describe(entry, people_by_id, failed=None):
    """An entry with the person joined on, for the page. A person who has been
    deleted still lists: the caseload records that they were waiting. `failed`
    is the error the linked assessment ended in, if it ended in one."""
    p = people_by_id.get(entry["person_id"])
    return dict(entry, error=failed,
                label=(p or {}).get("label") or "Removed person",
                age=(p or {}).get("age"), sex=(p or {}).get("sex"),
                status=status_of(entry, failed),
                missing=p is None)


if __name__ == "__main__":
    # Offline self-test against a temp file, so it never touches data/queue.json.
    import tempfile
    ok = fails = 0

    def check(name, cond):
        global ok, fails
        if cond:
            ok += 1
            print(f"  PASS  {name}")
        else:
            fails += 1
            print(f"  FAIL  {name}")

    with tempfile.TemporaryDirectory() as d:
        q = QueueStore(Path(d) / "queue.json")
        check("an empty store lists nothing", q.list() == ([], []))
        e1, err = q.add("mum", "chest tightness on the walk up")
        check("a person can be queued", bool(e1) and not err)
        check("a queued person is waiting", q.waiting_for("mum") is not None)
        e2, _ = q.add("mum", "different note")
        check("queueing twice returns the same entry, not a second one",
              e2["id"] == e1["id"] and len(q.list()[0]) == 1)
        check("the first note is kept", e2["reason"] == "chest tightness on the walk up")
        _, err = q.add("dad", "x" * (REASON_MAX + 1))
        check("an over-long note is refused", "reason" in err)
        check("a refused add queues nobody", q.waiting_for("dad") is None)
        q.add("dad", "cough")
        check("two people wait", len(q.list()[0]) == 2)
        done = q.done(e1["id"], "20260920-000000-abcdef")
        check("done moves the entry out of waiting",
              done["done"] and len(q.list()[0]) == 1 and len(q.list()[1]) == 1)
        check("done records the assessment", done["conversation_id"] == "20260920-000000-abcdef")
        first_at = done["done_at"]
        again = q.done(e1["id"], "20260920-111111-abcdef")
        check("done is idempotent and keeps the first time", again["done_at"] == first_at)
        check("done does not overwrite the assessment it was seen in",
              again["conversation_id"] == "20260920-000000-abcdef")
        check("a done person can be queued again",
              q.add("mum", "came back")[0]["id"] != e1["id"])
        check("missing entries do not mark done", q.done("nope") is None)
        q.add("grandpa", "abandoned test")
        g = q.waiting_for("grandpa")
        check("a fresh entry is waiting", status_of(g) == "waiting")
        check("start alone makes it in progress, with no assessment yet",
              status_of(q.start(g["id"])) == "in_progress"
              and q.waiting_for("grandpa")["conversation_id"] is None)
        check("unstart puts it back to waiting",
              q.unstart(g["id"]) is not None and status_of(q.waiting_for("grandpa")) == "waiting")
        check("starting an entry that does not exist is None", q.start("nope") is None)
        q.link("grandpa", "20260920-999999-cccccc")
        check("a linked entry is in progress", status_of(q.waiting_for("grandpa")) == "in_progress")
        check("unlink puts it back to waiting",
              q.unlink(g["id"]) is not None and status_of(q.waiting_for("grandpa")) == "waiting")
        check("unlinking an unlinked entry is None", q.unlink(g["id"]) is None)
        q.link("grandpa", "20260920-999999-dddddd")
        q.done(g["id"])
        check("a done entry is seen",
              status_of(next(x for x in q.list()[1] if x["id"] == g["id"])) == "seen")
        # Cleaned up: a later check counts the done list and this entry is not
        # part of what it is measuring.
        q.remove(g["id"])
        q.add("aunt", "breathless")
        linked = q.link("aunt", "20260920-222222-aaaaaa")
        check("link records the assessment without marking done",
              linked["conversation_id"] == "20260920-222222-aaaaaa" and not linked["done"])
        check("link does not relabel an entry that already has one",
              q.link("aunt", "20260920-333333-bbbbbb") is None
              and q.waiting_for("aunt")["conversation_id"] == "20260920-222222-aaaaaa")
        check("link ignores somebody who is not waiting", q.link("nobody", "x") is None)
        check("remove takes an entry out", q.remove(e1["id"]) and len(q.list()[1]) == 0)
        check("removing twice is False, not an error", q.remove(e1["id"]) is False)
        # By person_id, not by list position: two adds inside the same second
        # tie on `added` and the sort between them is not defined.
        mum_entry = q.waiting_for("mum")
        d1 = describe(mum_entry, {"mum": {"label": "Mum", "age": 64, "sex": "female"}})
        check("describe joins the person on", d1["label"] == "Mum" and d1["missing"] is False)
        d2 = describe(mum_entry, {})
        check("a deleted person still lists", d2["missing"] is True and d2["label"] == "Removed person")

        # An assessment that ended in an error does not see anyone. The
        # fixture is the real one: Dad's caseload assessment on 2026-09-27,
        # cut off at the token limit, which marked him seen.
        import json
        cut = json.loads((HERE / "fixtures" / "caseload" / "cut-off-dad.json").read_text())
        state, msg = linked_state(cut)
        check("an assessment that only errored is not seen", state == "error")
        check("its error is carried to the row", "cut off at the token limit" in (msg or ""))
        e_dad = q.waiting_for("dad")
        row = describe(e_dad, {"dad": {"label": "Dad", "age": 71, "sex": "male"}}, failed=msg)
        check("the row says error and stays waiting",
              row["status"] == "error" and not row["done"] and row["error"] == msg)
        retried = json.loads(json.dumps(cut))
        retried["sides"][0]["turns"].append({"kind": "result", "event": {}})
        check("a turn that finishes after the error marks them seen", linked_state(retried) == ("seen", None))
        refused = {"sides": [{"turns": [{"kind": "refused", "event": {}}]}]}
        check("a refusal is still a finished piece of work", linked_state(refused)[0] == "seen")
        check("nothing sent yet is still open", linked_state({"sides": [{"turns": []}]}) == ("open", None))

    print(f"\n{ok}/{ok + fails} self-tests passed.")
    raise SystemExit(1 if fails else 0)
