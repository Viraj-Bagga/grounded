"""One turn of an assessment: guards, retrieval, the model, guards again.

A turn is either the FIRST turn, which retrieves chunks and anchors the
assessment to them, or a FOLLOW-UP, which reuses them. Everything the model
returns goes through guards.py on every turn: constraints 4, 9 and 12 are app
logic held here, because a prompt rule could not hold any of them.

WHY FOLLOW-UPS DO NOT RETRIEVE. Hard constraint 8. The prefix cache makes
prompt eval nearly free on a follow-up, and re-retrieving would throw that
away. So a follow-up resends the same system prompt, the same first-turn
message with its chunks, and every earlier answer exactly as the model wrote
it, and only the new message is read. Measured 2026-09-19 on this build of
llama-server: a repeat on the same slot re-read 15 tokens and reused 263.

WHY EACH SIDE IS PINNED TO A SLOT. The cache lives in a llama-server slot, and
the chat endpoint honours id_slot: the same request on the other slot reused
nothing. There are two slots (-np 2), enough for one compare assessment or two
single ones at once. A third active one takes the least recently used slot.

A TAKEN SLOT IS USUALLY NOT A RE-READ. This build keeps a host-memory prompt
cache (--cache-ram, 8 GiB by default) and saves a slot's state before reusing
it. Measured 2026-09-19: Dad's follow-up, after Aunt Sue's assessment took his
slot, still reused 1,805 tokens and read 37, in 1.3 s. So a re-read is never
announced in advance, which would be wrong more often than right. The page
watches the read: a follow-up that is still reading after a few seconds is
re-reading, and says so while it happens. The result then states which it was,
from what llama-server reports, so a "0 reused" is never silent.

THE LENGTH LIMIT. A slot holds 4,096 tokens (-c 8192 over -np 2). The first
turn is about 1,700 tokens in and up to a few hundred out, and each follow-up
adds its message and an answer, so an assessment allows four follow-ups, fewer
if the answers run long. The page shows the allowance from the first answer,
not when it runs out.
"""

import json
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "02-pairs"))
sys.path.insert(0, str(ROOT / "04-retrieval"))
sys.path.insert(0, str(ROOT / "01-data" / "eval"))

from guards import (PAEDIATRIC_REFUSAL, REFUSAL,  # noqa: E402
                    UNGROUNDED_NOTE, apply_guards, child_term,
                    excluded_subject, is_child_profile, post_flight,
                    scope_check, screen_follow_ups)
from escalation import RULES, escalate, rescue_refusal  # noqa: E402
from pair_format import (ASSISTANT_SCHEMA, SYSTEM_PROMPT,  # noqa: E402
                         build_human_turn)

from store import now_iso  # noqa: E402

LLAMA = "http://127.0.0.1:8080"
TOP_K = 3
# Blend weight. 0.5 is half BM25 half vector. Measured 2026-09-17 against the
# frozen keys: dense 5/9 with 3 must-not-retrieve violations, blend 6/9 with 2,
# BM25 6/9 with 1. The blend is not the best on either axis alone; it is the one
# that does not depend entirely on a single signal, and retrieval tuning was
# stopped deliberately rather than fitted to four cases.
ALPHA = 0.5

MAX_FOLLOWUPS = 4
TURN_BUDGET = 520       # tokens set aside per follow-up: its message and an answer
MAX_TOKENS = 1024
MIN_ANSWER = 300        # below this the answer could be cut off mid-JSON
# Starting guess for prompt eval, measured 2026-09-15 and 09-17 with macOS Low
# Power Mode on. With it off, 2026-09-19, a first turn read at 72 tok/s. So the
# estimate the page shows is learned from recent turns instead of trusted.
PROMPT_TOK_PER_S = 31.0


class Busy(Exception):
    """This side already has a turn running."""


class Slots:
    """Which assessment side owns each llama-server slot."""

    def __init__(self, n):
        self.n = n
        self.lock = threading.Lock()
        self.owner = [None] * n
        self.last = [0.0] * n
        self.inflight = [0] * n

    def acquire(self, key, had_slot, has_history):
        """(slot, taken). taken is True when another assessment has used this
        side's slot since its last turn, None when that cannot be known (the
        demo server restarted since), and False when the slot is still its own.
        Taken does not mean lost: see the host prompt cache above."""
        with self.lock:
            if had_slot is not None and had_slot < self.n and \
                    self.owner[had_slot] in (key, None):
                s = had_slot
                taken = False if self.owner[had_slot] == key else (None if has_history else False)
            else:
                s = min(range(self.n), key=lambda i: (self.inflight[i] > 0,
                                                       self.owner[i] is not None,
                                                       self.last[i]))
                taken = bool(has_history)
            self.owner[s] = key
            self.last[s] = time.time()
            self.inflight[s] += 1
            return s, taken

    def release(self, s):
        with self.lock:
            self.inflight[s] = max(0, self.inflight[s] - 1)
            self.last[s] = time.time()


def stream_completion(body):
    """Yield (kind, payload) as the model produces tokens."""
    req = Request(LLAMA + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=900) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            choice = (obj.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            if delta.get("content"):
                yield "token", delta["content"]
            # Hard constraint 5: the switch is sent on every call, and if a
            # trace comes back anyway the demo should say so rather than hide it.
            if delta.get("reasoning_content"):
                yield "reasoning_leak", delta["reasoning_content"]
            if choice.get("finish_reason"):
                yield "finish", choice["finish_reason"]
            if obj.get("timings"):
                yield "timings", obj["timings"]


def watching(profile):
    """The escalation rules whose PROFILE fact holds for this person: what the
    app will watch for. Computed by the rules' own code, so the people page
    can never disagree with what the guards do."""
    out = []
    for r in RULES:
        fact = r["fact"](profile or {})
        if fact:
            out.append(dict(rule=r["id"], name=r["name"], action=r["action"],
                            cap=r["cap"], fact=fact, quote=r["quotes"][0][1],
                            keys=list(dict.fromkeys(k for k, _ in r["quotes"]))))
    return out


class Engine:
    def __init__(self, conversations, retriever, registry):
        self.conversations = conversations
        self.retriever = retriever          # callables, built at warm-up
        self.registry = registry
        self.slots = Slots(2)
        self.n_ctx = 4096
        self.prompt_rate = PROMPT_TOK_PER_S
        self._busy = set()
        self._busy_lock = threading.Lock()

    def configure_from_server(self):
        """Read slot count and context per slot from llama-server itself."""
        try:
            with urlopen(LLAMA + "/slots", timeout=3) as r:
                slots = json.load(r)
            if slots:
                self.slots = Slots(len(slots))
                self.n_ctx = int(slots[0].get("n_ctx") or self.n_ctx)
        except Exception:
            pass                            # keep the defaults; /api/health reports it
        return len(self.slots.owner), self.n_ctx

    def busy(self, cid):
        with self._busy_lock:
            return [k[1] for k in self._busy if k[0] == cid]

    def chunk_meta(self, key):
        # Through the retriever's lock: this runs on a request thread and the
        # connection belongs to whichever thread created it. See hybrid.py.
        rows = self.retriever().query(
            "select key, text, publisher, url, retrieval_date, attribution, "
            "token_count, expected_category from chunk_meta where key = ?", (key,))
        if not rows:
            return None
        return dict(zip(["key", "text", "publisher", "url", "retrieval_date",
                         "attribution", "token_count", "category"], rows[0]))

    def followups_left(self, side):
        if side["anchor"] is None:
            return MAX_FOLLOWUPS
        model_turns = sum(1 for t in side["turns"] if t.get("reached_model"))
        by_count = 1 + MAX_FOLLOWUPS - model_turns
        by_budget = (self.n_ctx - side["context_tokens"]) // TURN_BUDGET
        return max(0, min(by_count, by_budget))

    # ------------------------------------------------------------- the turn

    def run_turn(self, cid, si, text, timeline, confirmed, send):
        key = (cid, si)
        with self._busy_lock:
            if key in self._busy:
                raise Busy()
            self._busy.add(key)
        try:
            self._turn(cid, si, text, timeline, confirmed, send)
        finally:
            with self._busy_lock:
                self._busy.discard(key)

    def _record(self, cid, si, turn, llm=None, anchor=None, slot=None,
                context_tokens=None):
        """Append one turn and everything it changed, in a single write, and
        return the follow-ups left afterwards (also stored on the turn's event)."""
        left = {}

        def apply(conv):
            s = conv["sides"][si]
            s["turns"].append(turn)
            if llm:
                s["llm"].extend(llm)
            if anchor is not None and s["anchor"] is None:
                s["anchor"] = anchor
            if slot is not None:
                s["slot"] = slot
            if context_tokens is not None:
                s["context_tokens"] = context_tokens
            if not conv["title"]:
                t = " ".join(turn["text"].split())
                conv["title"] = t if len(t) <= 90 else t[:87].rstrip() + "..."
            left["n"] = self.followups_left(s)
            if isinstance(turn.get("event"), dict):
                turn["event"]["followups_left"] = left["n"]

        self.conversations.update(cid, apply)
        return left["n"]

    def _turn(self, cid, si, text, timeline, confirmed, send):
        conv = self.conversations.get(cid)
        side = conv["sides"][si]
        prof, ptext = side["profile"], side["profile_text"]
        who = {"profile": prof["label"], "profile_id": side["person_id"], "side": si}
        first = side["anchor"] is None
        n = len(side["turns"]) + 1
        t0 = time.time()

        def emit(event, payload):
            send(event, payload if event == "token" else {**who, **payload})

        def turn_record(kind, event, reached=False, **extra):
            return dict(n=n, at=now_iso(), text=text, timeline=timeline, kind=kind,
                        event=event, reached_model=reached, **extra)

        if not first and self.followups_left(side) <= 0:
            emit("full", {"message": "This assessment has used its follow-ups. "
                                     "Start a new one to keep going."})
            return

        # CHILD GUARD, by the selected profile's age, before anything else.
        # A child's profile gets the scope notice whatever the text says.
        if is_child_profile(prof):
            ev = {"message": PAEDIATRIC_REFUSAL, "categorical": True, "child": True,
                  "reason": (f"{prof['label']}'s profile says age {prof['age']}. The "
                             f"corpus is written about adults, with no paediatric "
                             f"content beyond one passage on pneumonia in babies.")}
            ev["followups_left"] = self._record(cid, si, turn_record("refused", {**who, **ev}))
            emit("refused", ev)
            return

        # A child word on an adult profile ASKS; it never refuses. Adults who
        # mention a daughter are not turned away. Viraj's call 2026-09-19; see
        # child_term in guards.py. Nothing is recorded until they answer.
        term = child_term(text + "\n" + timeline)
        if term and not confirmed:
            you = "you" if prof["label"] == "You" else prof["label"]
            emit("confirm_subject", {
                "term": term, "who": you,
                "message": (f'This mentions a child ("{term}"). If it is about them, '
                            f"choose their profile. If it is about {you}, continue.")})
            return

        # Everything the person has typed in this assessment, in order. The
        # guards judge findings against this, never against the chunks: that is
        # constraint 11. It includes turns that were refused, because the person
        # did say them.
        said = [x for t in side["turns"] for x in (t.get("timeline") or "", t["text"]) if x]
        said += [x for x in (timeline, text) if x]
        case_present = "\n".join(said)
        case_text = ptext + "\n" + case_present

        r = self.retriever()
        if first:
            query = text + ("\n" + timeline if timeline else "")
            hits = r.search(query, TOP_K, ALPHA)

            # GUARD 6, pre-flight. Checked BEFORE generating: it saves 40 s and
            # it never gives the model the chance to reason from loosely related
            # chunks, which is what produced a reassuring verdict on a possible
            # ectopic pregnancy. Subject-matter exclusion FIRST: the floor cannot
            # catch pregnancy, because those queries can score above it.
            excluded, exwhy, exmsg = excluded_subject(ptext + "\n" + case_present)
            if excluded:
                ev = {"message": exmsg, "reason": exwhy, "categorical": True}
                ev["followups_left"] = self._record(cid, si, turn_record("refused", {**who, **ev}))
                emit("refused", ev)
                return

            # SCOPE IS SCORED ON THE SYMPTOMS ALONE, NOT ON `query`, and on the
            # first turn only. The timeline is mostly "T+0:00" markers that pull
            # the embedding away from chunk space; a follow-up such as "yes,
            # worse" is too short to score at all. Measured 2026-09-18: a man
            # describing an evolving MI scored 0.489 on symptoms and 0.394 with
            # the timeline appended, and was told the system did not cover it.
            max_cos = max(r._cosines(text).values())
            in_scope, why = scope_check(max_cosine=max_cos)
            if not in_scope:
                ev = {"message": REFUSAL, "reason": why, "max_cosine": round(max_cos, 3),
                      "nearest": [h[0] for h in hits]}
                ev["followups_left"] = self._record(cid, si, turn_record("refused", {**who, **ev}))
                emit("refused", ev)
                return

            keys = [h[0] for h in hits]
            anchor = dict(keys=keys, tokens=sum(h[4] for h in hits),
                          ms=int((time.time() - t0) * 1000),
                          chunks=[{"key": h[0], "tokens": h[4],
                                   "category": h[5] or "uncategorised"} for h in hits])
            human = build_human_turn(ptext, text, keys, {k: r.text[k] for k in keys},
                                     timeline=timeline or None)
            emit("retrieved", anchor)
        else:
            # Categorical exclusions run on every turn: pregnancy can come up in
            # a follow-up as easily as in the first message.
            excluded, exwhy, exmsg = excluded_subject(ptext + "\n" + case_present)
            if excluded:
                ev = {"message": exmsg, "reason": exwhy, "categorical": True}
                ev["followups_left"] = self._record(cid, si, turn_record("refused", {**who, **ev}))
                emit("refused", ev)
                return
            anchor = side["anchor"]
            human = f"[FOLLOW-UP]\n{text}\n[/FOLLOW-UP]"
            emit("reused", {**anchor, "ms": 0})
        retrieval_ms = int((time.time() - t0) * 1000)

        # Room for the answer. A slot holds n_ctx tokens; an answer cut off by
        # max_tokens is broken JSON, so never ask for more than fits.
        est_prompt = side["context_tokens"] + len(human) // 3 + 24
        if first:
            est_prompt = (len(SYSTEM_PROMPT) + len(human)) // 3 + 24
        max_tokens = min(MAX_TOKENS, self.n_ctx - est_prompt - 32)
        if max_tokens < MIN_ANSWER:
            emit("full", {"message": "This assessment is too long for one more answer. "
                                     "Start a new one to keep going."})
            return

        slot, taken = self.slots.acquire(key=(cid, si), had_slot=side["slot"],
                                         has_history=bool(side["llm"]))
        expected = side["context_tokens"] if not first else 0
        # For the estimate only: about four characters a token. The budget
        # above uses three, which errs towards leaving room.
        new_tokens = len(human) // 4 + 24 + (len(SYSTEM_PROMPT) // 4 if first else 0)
        rate = self.prompt_rate
        emit("reading", {"slot": slot, "slot_taken": taken, "expected_reuse": expected,
                         "estimate_ms": int(new_tokens / rate * 1000),
                         "full_read_ms": int((new_tokens + expected) / rate * 1000)})

        body = {
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + side["llm"] +
                        [{"role": "user", "content": human}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "triage", "schema": ASSISTANT_SCHEMA}},
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "stream": True,
            "cache_prompt": True,
            "id_slot": slot,
            # Hard constraint 5. Every call. Nothing warns you if it is missing.
            "chat_template_kwargs": {"enable_thinking": False},
        }

        t1 = time.time()
        raw, timings, finish, ttft = [], {}, None, None
        try:
            for kind, payload in stream_completion(body):
                if kind == "token":
                    if ttft is None:
                        ttft = int((time.time() - t1) * 1000)
                    raw.append(payload)
                    emit("token", {"t": payload})
                elif kind == "reasoning_leak":
                    emit("warn", {"message": "REASONING LEAKED: enable_thinking=false "
                                             "was sent and a trace came back"})
                elif kind == "finish":
                    finish = payload
                elif kind == "timings":
                    timings = payload
        except Exception as e:
            self.slots.release(slot)
            ev = {"message": f"The model could not be reached: {e}"}
            ev["followups_left"] = self._record(cid, si, turn_record("error", {**who, **ev}))
            emit("error", ev)
            return
        self.slots.release(slot)
        emit("checking", {})                # the last token is in; the guards run now

        answer = "".join(raw)
        gen_ms = int((time.time() - t1) * 1000)
        context_tokens = sum(int(timings.get(k) or 0)
                             for k in ("prompt_n", "cache_n", "predicted_n"))
        reused = int(timings.get("cache_n") or 0)
        if int(timings.get("prompt_n") or 0) >= 200 and timings.get("prompt_per_second"):
            self.prompt_rate = 0.5 * self.prompt_rate + 0.5 * float(timings["prompt_per_second"])
        cache = {"expected": expected, "reused": reused, "read": int(timings.get("prompt_n") or 0),
                 "slot_taken": taken, "slot": slot,
                 "re_read": bool(expected and reused < expected * 0.5)}
        # The model's words go into the history exactly as written, parsed or
        # not: they are in the slot's cache, and the next turn must match them.
        llm = [{"role": "user", "content": human}, {"role": "assistant", "content": answer}]
        tc = time.time()

        # Guard 5 needs the case text and NEVER the retrieved chunk. That
        # distinction is the whole of constraint 11: the chunk says which
        # findings would be red flags, only the case says which ones this
        # patient has.
        try:
            result, dropped, flagged = apply_guards(
                answer, self.registry(), case_text=case_text, case_present=case_present)
        except Exception as e:
            why = "the answer was cut off at the token limit" if finish == "length" else str(e)
            ev = {"message": f"Could not read a verdict: {why}", "raw": answer[:400],
                  "n": n, "first": first, "cache": cache, "timings": timings}
            ev["followups_left"] = self._record(
                cid, si, turn_record("error", {**who, **ev}, reached=True, raw=answer,
                                     timings=timings),
                llm=llm, anchor=anchor, slot=slot, context_tokens=context_tokens)
            emit("error", ev)
            return

        # GUARD 6, post-flight. An empty citations list after the citation
        # guard means the model grounded the answer in nothing. A yellow or
        # green is refused. A red is never withheld: it goes out as the
        # urgency alone, flagged, and the page shows UNGROUNDED_NOTE with it.
        action, why, shown = post_flight(result)
        escalation = None
        if action == "refuse":
            # UNLESS a profile rule raises the withheld verdict to RED. Then it
            # goes out flagged, through the never-withhold-red path, with the
            # rule's line. A withheld green that would only become yellow stays
            # refused. Viraj's call 2026-09-19. See rescue_refusal.
            escalation = rescue_refusal(result.get("urgency"), prof, case_present)
            if escalation is None:
                ev = {"message": REFUSAL, "reason": why,
                      "urgency_withheld": result.get("urgency"), "gen_ms": gen_ms,
                      "n": n, "first": first, "cache": cache, "ttft_ms": ttft,
                      "timings": timings, "retrieval_ms": retrieval_ms,
                      "total_ms": int((time.time() - t0) * 1000)}
                ev["followups_left"] = self._record(
                    cid, si, turn_record("refused", {**who, **ev}, reached=True,
                                         raw=answer, timings=timings),
                    llm=llm, anchor=anchor, slot=slot, context_tokens=context_tokens)
                emit("refused", ev)
                return
            action, why, shown = post_flight(dict(result, urgency="red"))
            why += (f"; a profile rule raised the withheld {escalation['original']} "
                    f"to red, so it is shown, not refused")
        ungrounded = None
        if action == "flag":
            ungrounded = {"note": UNGROUNDED_NOTE, "reason": why,
                          "withheld": {k: result.get(k) for k in (
                              "rationale", "red_flags", "next_steps",
                              "follow_up_questions")}}
            result = shown

        # ESCALATION. Profile rules, deterministic, only ever raising, each
        # quoting its chunk. The case text is what the person typed, never the
        # chunks. See 02-pairs/escalation.py.
        if escalation is None:      # a rescued refusal arrives escalated
            escalation = escalate(result.get("urgency"), prof, case_present)
        if result.get("urgency") != escalation["final"]:
            result = dict(result, urgency=escalation["final"])
            # Constraint 4 again: a verdict raised to red asks no questions.
            kept_q, cleared = screen_follow_ups(
                result["urgency"], result.get("follow_up_questions"))
            result["follow_up_questions"] = kept_q
            dropped = dict(dropped, follow_up_questions=list(
                dropped.get("follow_up_questions") or []) + cleared)

        cites = [self.chunk_meta(k) for k in result.get("citations", [])]
        ev = {"result": result, "ungrounded": ungrounded, "escalation": escalation,
              "dropped": dropped, "flagged": flagged, "citations": [c for c in cites if c],
              "gen_ms": gen_ms, "check_ms": int((time.time() - tc) * 1000),
              "retrieval_ms": retrieval_ms, "ttft_ms": ttft,
              "total_ms": int((time.time() - t0) * 1000),
              "retrieved_tokens": anchor["tokens"], "timings": timings,
              "profile_text": ptext, "n": n, "first": first, "cache": cache}
        ev["followups_left"] = self._record(
            cid, si, turn_record("result", {**who, **ev}, reached=True, raw=answer,
                                 timings=timings),
            llm=llm, anchor=anchor, slot=slot, context_tokens=context_tokens)
        emit("result", ev)
