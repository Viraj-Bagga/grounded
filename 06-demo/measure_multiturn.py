#!/usr/bin/env python3
"""First turn against follow-up, measured through the demo server. Stdlib only.

    python 06-demo/measure_multiturn.py                     # all three scenarios
    python 06-demo/measure_multiturn.py --only single --followups 1
    python 06-demo/measure_multiturn.py --out 06-demo/results/<date>-<what>.txt

Runs against the demo server (8770), which runs against llama-server (8080), so
the numbers are the product path: guards, retrieval, slot pinning and all.

  single    one assessment: a first turn and its follow-ups
  parallel  two assessments at once: first turns together, then follow-ups
            together. Each must keep its own slot and its own file.
  evict     a third assessment takes a slot between two turns of another. With
            llama-server's host prompt cache the evicted one is usually restored,
            not re-read (found on this script's first run, 2026-09-19). A real
            re-read needs an empty cache: see `ui_check.mjs reread`, run after a
            llama-server restart.

Every turn's content is written out, not just its numbers: the verdict, the
steps, the citations, what the guards removed, the rule lines. A number can be
recomputed from the content; the content cannot be recomputed from a number.
"""

import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
DEMO = "http://127.0.0.1:8770"
OTHER_LLAMA = "http://127.0.0.1:8081"      # the other session's server, if running

SINGLE = ("self",
          "Burning in my chest after dinner, worse when I lie flat, with a sour taste "
          "coming up.",
          "T+0:00 began about 40 minutes after a large late meal. T+0:15 worse lying down.",
          ["It is easing now that I am sitting upright. There is no pain in my arm or jaw.",
           "I have had this before after big meals, and antacids helped last time.",
           "It has gone completely now."])
PARALLEL = [("mum", "Feeling a bit sick and sweaty after dinner, probably something I ate.", "",
             ["It has not gone away, it has been an hour now."]),
            ("dad", "I got tight in the chest going up the stairs like I sometimes do. "
                    "It went away once I sat down.", "",
             ["It happened again on the way back down."])]
EVICTOR = ("aunt", "Sharp pain in my chest when I breathe in, since this morning.", "")


def post(path, body):
    req = Request(DEMO + path, data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=30) as r:
        return json.load(r)


def get(url, timeout=5):
    with urlopen(url, timeout=timeout) as r:
        return json.load(r)


def other_busy():
    try:
        return any(s.get("is_processing") for s in get(OTHER_LLAMA + "/slots", 2))
    except Exception:
        return None                          # not running


def turn(cid, text, timeline="", side=0, confirmed=False):
    """One turn, streamed. Returns every non-token event plus client timings."""
    t0 = time.time()
    req = Request(f"{DEMO}/api/conversations/{cid}/turn",
                  data=json.dumps({"side": side, "text": text, "timeline": timeline,
                                   "confirmed_subject": confirmed}).encode(),
                  headers={"Content-Type": "application/json"})
    events, first_token, tokens, contended = [], None, 0, other_busy()
    with urlopen(req, timeout=900) as resp:
        buf = b""
        for chunk in iter(lambda: resp.read(256), b""):
            buf += chunk
            while b"\n\n" in buf:
                raw, buf = buf.split(b"\n\n", 1)
                if not raw.startswith(b"data: "):
                    continue
                ev = json.loads(raw[6:])
                if ev["event"] == "token":
                    tokens += 1
                    if first_token is None:
                        first_token = time.time() - t0
                    continue
                events.append(ev)
    final = next((e for e in reversed(events) if e["event"] in
                  ("result", "refused", "error", "full", "confirm_subject")), None)
    return dict(cid=cid, side=side, text=text, timeline=timeline, events=events,
                final=final, client_ms=int((time.time() - t0) * 1000),
                client_ttft_ms=int(first_token * 1000) if first_token else None,
                token_events=tokens, other_busy=contended)


def describe(t):
    """The content of one turn, as lines."""
    f = t["final"] or {}
    ev = {e["event"]: e for e in t["events"]}
    rd = ev.get("reading", {})
    tm = f.get("timings") or {}
    cache = f.get("cache") or {}
    out = [f"  person {f.get('profile')}  side {t['side']}  turn {f.get('n')} "
           f"({'first' if f.get('first') else 'follow-up'})  -> {f.get('event')}",
           f"  said: {t['text']}" + (f"  [timeline: {t['timeline']}]" if t["timeline"] else "")]
    if "retrieved" in ev:
        out.append(f"  retrieved {ev['retrieved']['keys']} ({ev['retrieved']['tokens']} tokens, "
                   f"{ev['retrieved']['ms']} ms)")
    if "reused" in ev:
        out.append(f"  reused {ev['reused']['keys']} (no retrieval)")
    if rd:
        out.append(f"  reading: slot {rd.get('slot')}, slot taken since last turn="
                   f"{rd.get('slot_taken', rd.get('evicted'))}, expected reuse "
                   f"{rd.get('expected_reuse')} tokens, estimate {rd.get('estimate_ms')} ms "
                   f"(full re-read {rd.get('full_read_ms')} ms)")
    if tm:
        out.append(f"  timings: read {tm.get('prompt_n')} tok in {tm.get('prompt_ms', 0):.0f} ms, "
                   f"reused {tm.get('cache_n')}, wrote {tm.get('predicted_n')} tok in "
                   f"{tm.get('predicted_ms', 0):.0f} ms ({tm.get('predicted_per_second', 0):.1f}/s)")
    out.append(f"  wall: server {f.get('total_ms')} ms, client {t['client_ms']} ms, "
               f"first token at {t['client_ttft_ms']} ms; re_read={cache.get('re_read')}; "
               f"follow-ups left {f.get('followups_left')}; other llama busy={t['other_busy']}")
    r = f.get("result") or {}
    if r:
        out.append(f"  urgency {r.get('urgency')}"
                   + (f" (model said {f['escalation']['original']})"
                      if f.get("escalation") and f["escalation"].get("changed") else ""))
        out.append(f"  why: {r.get('rationale')}")
        out.append(f"  red flags: {r.get('red_flags')}")
        out.append(f"  next steps: {r.get('next_steps')}")
        out.append(f"  questions: {r.get('follow_up_questions')}")
        out.append(f"  citations: {r.get('citations')}")
        if f.get("ungrounded"):
            out.append(f"  NOT GROUNDED: {f['ungrounded']['reason']}")
        for rule in (f.get("escalation") or {}).get("fired", []):
            out.append(f"  rule {rule['rule']} {rule['status']}: {rule['fact']} with {rule['symptom']}")
        drop = f.get("dropped") or {}
        removed = {k: v for k, v in drop.items() if v}
        out.append(f"  removed by guards: {removed or 'nothing'}")
    elif f.get("event") in ("refused", "error", "full"):
        out.append(f"  message: {f.get('message')}")
        out.append(f"  reason: {f.get('reason')}")
    return out


def scenario_single(log, followups):
    pid, text, tl, fus = SINGLE
    cid = post("/api/conversations", {"person_ids": [pid]})["id"]
    log(f"\n== single: one assessment ({cid})")
    rows = [turn(cid, text, tl)]
    for fu in fus[:followups]:
        rows.append(turn(cid, fu))
    for t in rows:
        log(*describe(t))
    return rows


def run_parallel(jobs):
    out = [None] * len(jobs)

    def work(i, job):
        out[i] = turn(*job)
    threads = [threading.Thread(target=work, args=(i, j)) for i, j in enumerate(jobs)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return out


def scenario_parallel(log):
    cids = [post("/api/conversations", {"person_ids": [p[0]]})["id"] for p in PARALLEL]
    log(f"\n== parallel: two assessments at once ({cids[0]}, {cids[1]})")
    first = run_parallel([(cid, p[1], p[2]) for cid, p in zip(cids, PARALLEL)])
    follow = run_parallel([(cid, p[3][0]) for cid, p in zip(cids, PARALLEL)])
    for t in first + follow:
        log(*describe(t))
    # Isolation: each file holds only its own person and its own words.
    for cid, p in zip(cids, PARALLEL):
        conv = get(f"{DEMO}/api/conversations/{cid}")
        side = conv["sides"][0]
        said = [t["text"] for t in side["turns"]]
        ok = side["person_id"] == p[0] and said == [p[1], p[3][0]] and side["model_turns"] == 2
        log(f"  isolation {cid}: person {side['person_id']}, turns {said}, model turns "
            f"{side['model_turns']}, slot {side['slot']} -> {'OK' if ok else 'FAILED'}")
    return cids, first + follow


def scenario_evict(log, cids):
    victims = {get(f"{DEMO}/api/conversations/{c}")["sides"][0]["slot"]: c for c in cids}
    cid = post("/api/conversations", {"person_ids": [EVICTOR[0]]})["id"]
    log(f"\n== evict: a third assessment ({cid}) takes a slot")
    t3 = turn(cid, EVICTOR[1], EVICTOR[2])
    slot = next((e for e in t3["events"] if e["event"] == "reading"), {}).get("slot")
    victim = victims.get(slot)
    log(*describe(t3))
    log(f"  took slot {slot}, which belonged to {victim}")
    after = turn(victim, "Now I also feel a little dizzy.")
    log(*describe(after))
    return [t3, after]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["single", "parallel", "evict", "all"], default="all")
    ap.add_argument("--followups", type=int, default=2)
    ap.add_argument("--out")
    args = ap.parse_args()
    lines = []

    def log(*ls):
        for l in ls:
            print(l, flush=True)
            lines.append(l)

    health = get(DEMO + "/api/health")
    try:
        power = subprocess.run(["pmset", "-g"], capture_output=True, text=True).stdout
        low = next((l.split()[-1] for l in power.splitlines() if "lowpowermode" in l), "?")
    except Exception:
        low = "?"
    log(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} multi-turn latency, through the demo server",
        f"config: llama-server -np {health['slots']} -c {health['slots'] * health['n_ctx']} "
        f"-ngl 0 (CPU), {health['n_ctx']} tokens per slot; demo 06-demo/server.py; "
        f"temperature 0.2, reasoning off, schema on",
        f"index: {health['sources']} chunks; macOS low power mode {low}; "
        f"other llama-server (8081) busy at start: {other_busy()}",
        "each turn: what was said, what was retrieved or reused, the slot, the timings, "
        "and the guarded content")

    rows = []
    if args.only in ("single", "all"):
        rows += scenario_single(log, args.followups)
    if args.only in ("parallel", "evict", "all"):
        cids, r = scenario_parallel(log)
        rows += r
        if args.only in ("evict", "all"):
            rows += scenario_evict(log, cids)

    def stat(kind):
        pick = [t for t in rows if t["final"] and t["final"].get("timings") and
                bool(t["final"].get("first")) == (kind == "first")]
        return pick
    log("\n== first turn against follow-up (turns that reached the model)")
    for kind in ("first", "follow-up"):
        for t in stat(kind):
            f, tm = t["final"], t["final"]["timings"]
            log(f"  {kind:<9} {f['profile']:<9} read {tm.get('prompt_n'):>5} reused "
                f"{tm.get('cache_n'):>5} read-time {tm.get('prompt_ms', 0) / 1000:6.1f} s  "
                f"wrote {tm.get('predicted_n'):>4} in {tm.get('predicted_ms', 0) / 1000:5.1f} s  "
                f"total {f.get('total_ms', 0) / 1000:6.1f} s  re_read={f['cache'].get('re_read')}")
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nwritten to {args.out}")


if __name__ == "__main__":
    main()
