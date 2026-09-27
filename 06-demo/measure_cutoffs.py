"""How often an answer is cut off at the token limit, and how long answers run.

    python 06-demo/measure_cutoffs.py OUTFILE LABEL [RUNS] [FIELD_URL]

Drives the demo server's own API, exactly as the page does: start an
assessment for one person, send one turn, read the saved result. Two runs at a
time, because llama-server has two slots. Every raw answer is saved beside
OUTFILE as JSON lines, so a loop can be read and not just counted.

Written 2026-09-27 for Viraj's report that Dad's and Aunt Sue's answers were
cut off at the token limit in 4 of 72 and 3 of 26 turns. The two scenarios are
the texts that produced those: Dad's hill (the two-tabs check and the
rehearsal's caseload) and the Aunt Sue preset.
"""

import json
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCENARIOS = [
    ("dad", "Dad, the hill",
     "Tight chest when I walk up the hill, it eased when I stopped.", ""),
    ("aunt", "Aunt Sue, the preset",
     "Sharp pain in my left chest, worse when I breathe in. It eases if I sit up and lean forward. "
     "Walking around does not change it.",
     "T+0:00 began at rest. T+0:10 worse on deep breath. T+1:30 unchanged, no relation to exertion."),
]


def call(url, body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def one(app, pid, text, timeline):
    t0 = time.time()
    conv = json.loads(call(f"{app}/api/conversations", {"person_ids": [pid]}))
    call(f"{app}/api/conversations/{conv['id']}/turn", {"side": 0, "text": text, "timeline": timeline})
    saved = json.loads(call(f"{app}/api/conversations/{conv['id']}"))
    turn = saved["sides"][0]["turns"][-1]
    ev = turn.get("event") or {}
    raw = turn.get("raw") or ""
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    timings = turn.get("timings") or ev.get("timings") or {}
    return {"cid": conv["id"], "kind": turn.get("kind"), "message": ev.get("message"),
            "tokens": timings.get("predicted_n"), "secs": round(time.time() - t0, 1),
            "shown": (ev.get("result") or {}).get("urgency"),
            "model": ((ev.get("escalation") or {}).get("original")),
            "steps": len((parsed or {}).get("next_steps") or []) if parsed else None,
            "cut_off": turn.get("kind") == "error" and "token limit" in (ev.get("message") or ""),
            "raw": raw}


def main():
    out = Path(sys.argv[1])
    label = sys.argv[2]
    runs = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    app = (sys.argv[4] if len(sys.argv) > 4 else "http://127.0.0.1:8770").rstrip("/")
    health = json.loads(call(f"{app}/api/health"))
    lines = [f"# cut-offs and answer length, {label}",
             f"# date   {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"# path   this script -> {app} (06-demo/server.py) -> llama-server, {health.get('slots')} slots",
             f"# runs   {runs} per scenario, two at a time, each a fresh assessment", ""]
    raws = []
    for pid, name, text, tl in SCENARIOS:
        with ThreadPoolExecutor(max_workers=2) as pool:
            rs = list(pool.map(lambda _: one(app, pid, text, tl), range(runs)))
        ok = [r["tokens"] for r in rs if r["kind"] == "result" and r["tokens"]]
        cut = sum(r["cut_off"] for r in rs)
        shown = {}
        for r in rs:
            k = r["shown"] or ("CUT OFF" if r["cut_off"] else r["kind"])
            shown[k] = shown.get(k, 0) + 1
        lines += [f"{name}: {cut}/{runs} cut off at the token limit",
                  f"  answers that finished: {len(ok)}, tokens median {int(statistics.median(ok)) if ok else '-'}, "
                  f"max {max(ok) if ok else '-'}",
                  f"  shown: {', '.join(f'{k} {v}' for k, v in sorted(shown.items()))}",
                  f"  steps the model wrote per answer: {sorted(r['steps'] for r in rs if r['steps'] is not None)}"]
        for r in rs:
            lines.append(f"    {r['cid']}  {r['kind']:7}  model {str(r['model']):6} shown {str(r['shown']):6} "
                         f"{str(r['tokens']):>5} tok  {r['secs']:5.1f} s" + ("  CUT OFF" if r["cut_off"] else ""))
            raws.append(dict(r, scenario=name))
        lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    out.with_suffix(".jsonl").write_text("".join(json.dumps(r) + "\n" for r in raws))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
