#!/usr/bin/env python3
"""The laptop demo. Four beats, against llama-server, with the guards wired in.

    # terminal 1
    llama-server -m 03-model/base/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf \
      --jinja -np 2 -ngl 0 -c 8192 --port 8080
    # -np 2 since 2026-09-19: the side-by-side's two requests decode together,
    # 86 s against 112 at -np 1. -c 8192 keeps 4096 per slot, as before.
    # 06-demo/results/2026-09-19-compare-timing.txt
    # terminal 2
    python 06-demo/server.py          # then open http://127.0.0.1:8770

WHY THIS AND NOT THE SIMULATOR. Decided 2026-09-17: one completion in the iOS
simulator is 3 min 56 s in Release, against about 40 s here, and a judge visit is
about 5 minutes. The phone gets a screenshot as evidence that it runs on-device.
This is the surface that can answer inside a visit.

THE FOUR BEATS
  1. symptom checker flow     POST /api/triage, streamed
  2. red triage result        the urgency banner and red_flags
  3. profile escalation       family cards, and deterministic rules that only
                              raise urgency, each quoting its chunk. Compare
                              two profiles side by side. 02-pairs/escalation.py
  4. citation expander        GET /api/chunk/<key>, real text and real source

STREAMING IS NOT DECORATION. Generation runs at 9.5 to 10 tok/s on CPU, so a
200-token answer is about 20 s and a whole turn is 40 s or more. Forty seconds of
frozen screen reads as a crash at a desk. Tokens are streamed so the thing is
visibly working, and the guarded result is rendered only when the JSON is
complete, because a half-parsed verdict must never reach the screen.

EVERYTHING THE MODEL RETURNS GOES THROUGH guards.py. Constraints 4, 9 and 12
are app logic and are held here, not in the prompt, because a prompt rule could
not hold any of them.
"""

import json
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "02-pairs"))
sys.path.insert(0, str(ROOT / "04-retrieval"))
sys.path.insert(0, str(ROOT / "01-data" / "eval"))

from guards import (PAEDIATRIC_REFUSAL, REFUSAL,  # noqa: E402
                    UNGROUNDED_NOTE, apply_guards, child_term,
                    excluded_subject, is_child_profile, load_registry,
                    parse_model_json, post_flight, scope_check,
                    screen_follow_ups)
from escalation import (escalate, rescue_refusal,  # noqa: E402
                        verify_grounding)
from pair_format import (ASSISTANT_SCHEMA, SYSTEM_PROMPT,  # noqa: E402
                         build_human_turn)

LLAMA = "http://127.0.0.1:8080/v1/chat/completions"
PORT = 8770
TOP_K = 3
# Blend weight. 0.5 is half BM25 half vector. Measured 2026-09-17 against the
# frozen keys: dense 5/9 with 3 must-not-retrieve violations, blend 6/9 with 2,
# BM25 6/9 with 1. The blend is not the best on either axis alone; it is the one
# that does not depend entirely on a single signal, and retrieval tuning was
# stopped deliberately rather than fitted to four cases.
ALPHA = 0.5

# THE FAMILY. One card each on the page, and the facts the escalation rules read.
# Structured, because rules must read facts rather than parse prose.
# `profile_text` renders them for the prompt in the format the model has always
# seen, so "You" and "Dad" give byte-identical prompt text to the two profiles
# they replace. Each of the others is there to show a rule on its own card: Mum
# R1 and R3, Aunt Sue R4, Grandpa R2 and R5, Maya the child scope notice. These
# are demo data, not patients.
PROFILES = {
    "self": dict(label="You", age=29, sex="female", conditions=[], medications=[]),
    "mum": dict(label="Mum", age=64, sex="female",
                conditions=["type 2 diabetes", "coronary artery disease"],
                medications=["metformin", "atorvastatin"]),
    "dad": dict(label="Dad", age=71, sex="male",
                conditions=["atrial fibrillation", "high blood pressure"],
                medications=["apixaban 5mg twice daily", "bisoprolol"]),
    "aunt": dict(label="Aunt Sue", age=52, sex="female",
                 conditions=["breast cancer"], medications=["chemotherapy"]),
    "grandpa": dict(label="Grandpa", age=77, sex="male",
                    conditions=["high blood pressure"], medications=["amlodipine"],
                    surgery=dict(what="hip replacement", weeks_ago=5)),
    "maya": dict(label="Maya", age=6, sex="female", conditions=[], medications=[]),
}


def profile_text(p):
    """The [PATIENT PROFILE] block the model sees."""
    lines = [f"age: {p['age']}, sex: {p['sex']}",
             "conditions: " + (", ".join(p["conditions"]) or "none"),
             "medications: " + (", ".join(p["medications"]) or "none")]
    if p.get("surgery"):
        lines.append(f"recent surgery: {p['surgery']['what']}, "
                     f"{p['surgery']['weeks_ago']} weeks ago")
    return "\n".join(lines)


# BUILT EAGERLY AT STARTUP, NOT LAZILY ON FIRST REQUEST.
#
# Lazy init was a crash, not an inefficiency. Measured 2026-09-17: two
# concurrent first requests both entered the `is None` branch, both constructed
# a HybridRetriever, both loaded all-MiniLM-L6-v2, and **the process died**,
# leaving a loky semaphore behind and every in-flight request returning zero
# bytes. A judge double-clicking Assess would have killed the demo server.
#
# The lock below is belt and braces. The real fix is that `warm_up()` runs
# before the socket is listening, so no request can find these unset and there
# is no race to lose. It also moves the 9 s MiniLM load off the first query,
# which was showing up as a slow first answer.
_retriever = None
_registry = None
_init_lock = threading.Lock()


def retriever():
    global _retriever
    if _retriever is None:
        with _init_lock:
            if _retriever is None:          # re-check inside the lock
                from hybrid import HybridRetriever
                _retriever = HybridRetriever()
    return _retriever


def registry():
    global _registry
    if _registry is None:
        with _init_lock:
            if _registry is None:
                _registry = load_registry()
    return _registry


def warm_up():
    """Build everything before serving, so a first request cannot race. Refuses
    to start if any escalation rule's quote is not verbatim in its chunk."""
    problems = verify_grounding(registry())
    if problems:
        raise SystemExit("escalation rules are not grounded:\n  " +
                         "\n  ".join(problems))
    r = retriever()
    r.search("warm up the encoder and the index", 1, 0.5)
    return r


def chunk_meta(key):
    r = retriever()
    # Through the retriever's lock: this runs on a request thread and the
    # connection belongs to whichever thread created it. See hybrid.py.
    rows = r.query(
        "select key, text, publisher, url, retrieval_date, attribution, "
        "token_count, expected_category from chunk_meta where key = ?", (key,))
    if not rows:
        return None
    row = rows[0]
    return dict(zip(["key", "text", "publisher", "url", "retrieval_date",
                     "attribution", "token_count", "category"], row))


def build_prompt(profile_text, symptoms, timeline, keys, texts):
    return build_human_turn(profile_text, symptoms, keys, texts,
                            timeline=timeline or None)


def stream_completion(body):
    """Yield (kind, payload) as the model produces tokens."""
    req = Request(LLAMA, data=json.dumps(body).encode(),
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
            if obj.get("timings"):
                yield "timings", obj["timings"]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE / "static"), **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"  {self.address_string()} {fmt % args}\n")

    def _json(self, obj, code=200):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/api/health":
            ok, detail = True, "llama-server reachable"
            try:
                with urlopen("http://127.0.0.1:8080/health", timeout=3) as r:
                    r.read()
            except Exception as e:
                ok, detail = False, f"llama-server unreachable: {e}"
            return self._json({"ok": ok, "detail": detail,
                               "profiles": [dict(id=k, child=is_child_profile(v),
                                                 **v)
                                            for k, v in PROFILES.items()]})
        if self.path.startswith("/api/chunk/"):
            key = self.path.rsplit("/", 1)[-1]
            # Constraint 9 again, at the expander. A key that does not resolve
            # must never open a panel, even if something upstream let it through.
            if key not in registry():
                return self._json({"error": f"{key} is not in the registry"}, 404)
            return self._json(chunk_meta(key))
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/triage":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")

        symptoms = (req.get("symptoms") or "").strip()
        timeline = (req.get("timeline") or "").strip()
        pkey = req.get("profile") if req.get("profile") in PROFILES else "self"
        prof = PROFILES[pkey]
        ptext = profile_text(prof)
        who = {"profile": prof["label"], "profile_id": pkey}
        if not symptoms:
            return self._json({"error": "no symptoms given"}, 400)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def send(event, payload):
            if event != "token":        # every panel knows whose verdict it is
                payload = {**who, **payload}
            self.wfile.write(f"data: {json.dumps({'event': event, **payload})}\n\n"
                             .encode())
            self.wfile.flush()

        try:
            t0 = time.time()
            # CHILD GUARD, by the selected profile's age, before anything else.
            # A child's profile gets the scope notice whatever the text says.
            if is_child_profile(prof):
                send("refused", {
                    "message": PAEDIATRIC_REFUSAL, "categorical": True,
                    "child": True,
                    "reason": (f"{prof['label']}'s profile says age {prof['age']}."
                               f" The corpus is written about adults, with no "
                               f"paediatric content beyond one passage on "
                               f"pneumonia in babies.")})
                return
            # A child word on an adult profile ASKS; it never refuses. Adults who
            # mention a daughter are no longer turned away. Viraj's call
            # 2026-09-19; see child_term in guards.py.
            term = child_term(symptoms + "\n" + timeline)
            if term and not req.get("confirmed_subject"):
                you = "you" if prof["label"] == "You" else prof["label"]
                send("confirm_subject", {
                    "term": term, "who": you,
                    "message": (f'This mentions a child ("{term}"). If it is about '
                                f"them, choose their profile. If it is about "
                                f"{you}, continue.")})
                return

            r = retriever()
            query = symptoms + ("\n" + timeline if timeline else "")
            hits = r.search(query, TOP_K, ALPHA)

            # GUARD 6, pre-flight. Checked BEFORE generating: it saves 40 s and
            # it never gives the model the chance to reason from loosely related
            # chunks, which is what produced a reassuring verdict on a possible
            # ectopic pregnancy.
            # Subject-matter exclusion FIRST: pregnancy, including a late or
            # missed period. The floor cannot catch it, because those queries
            # can score above it. Children are handled above, by profile age.
            excluded, exwhy, exmsg = excluded_subject(ptext + "\n" + query)
            if excluded:
                send("refused", {"message": exmsg, "reason": exwhy,
                                 "categorical": True})
                return

            # SCOPE IS SCORED ON THE SYMPTOMS ALONE, NOT ON `query`.
            #
            # Retrieval keeps the timeline: onset and progression are real
            # signal for WHICH chunk. Scope does not, because the timeline is
            # mostly "T+0:00" markers and structural tokens, and averaging them
            # into a sentence embedding pulls it away from chunk space without
            # saying anything about topic.
            #
            # Measured 2026-09-18, and this was a live refusal, not a
            # hypothetical. "Chest got tight walking up the hill to my car ...
            # Sat on the wall. It has not shifted, it has been half an hour now"
            # scored 0.489 on symptoms and 0.394 with the timeline appended, so
            # a man describing an evolving MI in ordinary English was told the
            # system does not cover it.
            #
            # The floor was always a symptoms-only number. claude.md records
            # "worst in-scope 0.482" from the 09-17 calibration, which is within
            # rounding of the 0.489 above measured symptoms-only. The floor was
            # calibrated one way and applied another; this aligns them.
            max_cos = max(r._cosines(symptoms).values())
            in_scope, why = scope_check(max_cosine=max_cos)
            if not in_scope:
                send("refused", {"message": REFUSAL, "reason": why,
                                 "max_cosine": round(max_cos, 3),
                                 "nearest": [h[0] for h in hits]})
                return
            keys = [h[0] for h in hits]
            texts = {k: r.text[k] for k in keys}
            retrieved_tokens = sum(h[4] for h in hits)
            send("retrieved", {
                "keys": keys, "tokens": retrieved_tokens,
                "ms": int((time.time() - t0) * 1000),
                "chunks": [{"key": h[0], "tokens": h[4],
                            "category": h[5] or "uncategorised"} for h in hits],
            })

            human = build_prompt(ptext, symptoms, timeline, keys, texts)
            body = {
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": human}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "triage",
                                                    "schema": ASSISTANT_SCHEMA}},
                "temperature": 0.2,
                "max_tokens": 1024,
                "stream": True,
                # Hard constraint 5. Every call. Nothing warns you if it is missing.
                "chat_template_kwargs": {"enable_thinking": False},
            }

            t1 = time.time()
            raw, timings = [], {}
            for kind, payload in stream_completion(body):
                if kind == "token":
                    raw.append(payload)
                    send("token", {"t": payload})
                elif kind == "reasoning_leak":
                    send("warn", {"message": "REASONING LEAKED: enable_thinking"
                                             "=false was sent and a trace came back"})
                elif kind == "timings":
                    timings = payload

            text = "".join(raw)
            gen_ms = int((time.time() - t1) * 1000)

            # Guard 5 needs the case text and NEVER the retrieved chunk. That
            # distinction is the whole of constraint 11: the chunk says which
            # findings would be red flags, only the case says which ones this
            # patient has.
            case_present = "\n".join(x for x in (timeline, symptoms) if x)
            case_text = ptext + "\n" + case_present
            try:
                result, dropped, flagged = apply_guards(
                    text, registry(), case_text=case_text,
                    case_present=case_present)
            except Exception as e:
                send("error", {"message": f"could not parse a verdict: {e}",
                               "raw": text[:400]})
                return

            # GUARD 6, post-flight. An empty citations list after the citation
            # guard means the model grounded the answer in nothing. A yellow or
            # green is refused. A red is never withheld: it goes out as the
            # urgency alone, flagged, and the page shows UNGROUNDED_NOTE with it.
            action, why, shown = post_flight(result)
            escalation = None
            if action == "refuse":
                # UNLESS a profile rule raises the withheld verdict to RED. Then
                # it goes out flagged, through the never-withhold-red path, with
                # the rule's line. A withheld green that would only become
                # yellow stays refused. Viraj's call 2026-09-19: a refusal that
                # hides a yellow the rules would raise is the same failure class
                # as withholding a red. See rescue_refusal.
                escalation = rescue_refusal(result.get("urgency"), prof,
                                            case_present)
                if escalation is None:
                    send("refused", {"message": REFUSAL, "reason": why,
                                     "urgency_withheld": result.get("urgency"),
                                     "gen_ms": gen_ms})
                    return
                action, why, shown = post_flight(dict(result, urgency="red"))
                why += (f"; a profile rule raised the withheld "
                        f"{escalation['original']} to red, so it is shown, not "
                        f"refused")
            ungrounded = None
            if action == "flag":
                ungrounded = {"note": UNGROUNDED_NOTE, "reason": why,
                              "withheld": {k: result.get(k) for k in (
                                  "rationale", "red_flags", "next_steps",
                                  "follow_up_questions")}}
                result = shown

            # ESCALATION. Profile rules, deterministic, only ever raising, each
            # quoting its chunk. The case text is symptoms and timeline, never
            # the chunks. See 02-pairs/escalation.py.
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

            cites = [chunk_meta(k) for k in result.get("citations", [])]
            send("result", {
                "result": result,
                "ungrounded": ungrounded,
                "escalation": escalation,
                "dropped": dropped,
                "flagged": flagged,
                "citations": [c for c in cites if c],
                "gen_ms": gen_ms,
                "total_ms": int((time.time() - t0) * 1000),
                "retrieved_tokens": retrieved_tokens,
                "timings": timings,
                "profile_text": ptext,
            })
        except Exception as e:  # never leave the page hanging on a dead server
            try:
                send("error", {"message": str(e)})
            except Exception:
                pass


def main():
    (HERE / "static").mkdir(exist_ok=True)
    print("warming up: registry, index and encoder ...")
    warm_up()
    print(f"demo on http://127.0.0.1:{PORT}")
    print(f"  llama-server expected at {LLAMA}")
    print(f"  retrieval: top-{TOP_K}, blend alpha={ALPHA}")
    print(f"  registry: {len(registry())} citation keys")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
