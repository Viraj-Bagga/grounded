#!/usr/bin/env python3
"""Score a model against the frozen 22-case held-out set.

    llama-server -m ./03-model/base/<file>.gguf --jinja -np 2 -ngl 0 -c 4096 --port 8080
    python 01-data/eval/heldout-eval/score_heldout.py --label base --runs 3

One completion per case per run. Nothing here edits the set, and the set's
sha256 is checked before anything runs: a changed file is refused, not scored.

WHAT IS HELD CONSTANT. Both models see the byte-identical prompt: the frozen
system prompt at 02-pairs/system_prompt.txt, the human turn built by
pair_format.build_human_turn, and the same chunks in the same order. Sampling is
the demo's: temperature 0.2, the demo's ASSISTANT_SCHEMA through --json-schema,
max_tokens 1024, and hard constraint 5's enable_thinking=false on every call,
with reasoning_content checked empty on every reply. The only thing that differs
between two invocations of this script is the GGUF the server has open.

--chunks matched (default) gives each case its own justifying keys from the set.
--chunks retrieval runs the demo's blend retriever instead. Matched is the
default because the question this answers is whether the MODEL's verdict follows
the case, and retrieval variance is a second variable. discrimination_test.py
already showed the verdict does not move when the chunks change (matched versus
red-only were verdict-identical), so matched is the established control here.

EVERY COMPLETION IS WRITTEN TO DISK, raw, next to the report. Working
convention: save the content, not the summary. A count of red flags with no text
cannot answer "was that finding actually in the patient" later.
"""

import argparse
import collections
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SET = HERE / "HELDOUT-EVAL-v1.json"
FROZEN_SHA = "6d1af06eb393d4afd2c6dc4af1669b70dbc0d6e5f46accf88b686fe3e6826035"

sys.path.insert(0, str(REPO / "02-pairs"))
sys.path.insert(0, str(REPO / "04-retrieval"))
sys.path.insert(0, str(REPO / "06-demo"))

from pair_format import (ASSISTANT_SCHEMA, SYSTEM_PROMPT,  # noqa: E402
                         build_human_turn, load_chunk_texts, load_registry)
from store import profile_text  # noqa: E402

URGENCIES = ("red", "yellow", "green")
# The demo's numbers, so the eval runs the shipping config and not a variant.
TEMPERATURE = 0.2
MAX_TOKENS = 1024
TOP_K = 3
ALPHA = 0.5


def load_set(path):
    raw = Path(path).read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    if got != FROZEN_SHA:
        raise SystemExit(f"{path} is not the frozen set.\n  expected {FROZEN_SHA}\n  got      {got}\n"
                         "A verdict change is a new version, never an edit.")
    return json.loads(raw)["cases"]


def build_turns(cases, mode):
    """case id -> (human turn, keys shown). Built once, reused by every run."""
    text = load_chunk_texts()
    out = {}
    retriever = None
    if mode == "retrieval":
        from hybrid import HybridRetriever
        retriever = HybridRetriever()
    for c in cases:
        if mode == "matched":
            keys = list(c["keys"])
        else:
            q = c["symptoms"] + ("\n" + c["timeline"] if c.get("timeline") else "")
            keys = [h[0] for h in retriever.search(q, TOP_K, ALPHA)]
        human = build_human_turn(profile_text(c["profile"]), c["symptoms"], keys,
                                 {k: text[k] for k in keys},
                                 timeline=c.get("timeline") or None)
        out[c["id"]] = (human, keys)
    return out


def call(endpoint, human, timeout):
    body = {
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": human}],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "triage", "schema": ASSISTANT_SCHEMA}},
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "cache_prompt": True,
        # Hard constraint 5. Every call. Nothing warns you if it is missing.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t0 = time.time()
    r = requests.post(endpoint, json=body, timeout=timeout)
    r.raise_for_status()
    d = r.json()
    ch = d["choices"][0]
    return {
        "content": ch["message"]["content"],
        "reasoning_content": ch["message"].get("reasoning_content"),
        "finish_reason": ch["finish_reason"],
        "usage": d.get("usage"),
        "wall_s": round(time.time() - t0, 2),
        "timings": d.get("timings"),
    }


def leading_key(entry, registry):
    """Hard constraint 9: the key at the START of the entry, whole, after at
    most an opening bracket. Only the key counts; appended prose is dropped."""
    import re
    m = re.match(r"^\s*\[?\s*([A-Z]+-[A-Z]+-\d+)\b", entry or "")
    if not m:
        return None
    return m.group(1) if m.group(1) in registry else None


def score_one(args, case, human, keys, registry, run_idx):
    try:
        res = call(args.endpoint, human, args.timeout)
    except Exception as e:                                   # noqa: BLE001
        return {"id": case["id"], "run": run_idx, "error": f"{type(e).__name__}: {e}"}
    rec = {"id": case["id"], "run": run_idx, "expected": case["verdict"],
           "condition": case["condition"], "keys_shown": keys, **res}
    try:
        ans = json.loads(res["content"])
    except json.JSONDecodeError as e:
        rec["got"] = None
        rec["parse_error"] = str(e)
        return rec
    rec["answer"] = ans
    rec["got"] = ans.get("urgency")
    cited = [leading_key(x, registry) for x in ans.get("citations", [])]
    rec["valid_citations"] = sorted({k for k in cited if k})
    rec["citation_entries"] = ans.get("citations", [])
    # Constraint 13's post-flight condition, scored but not applied: a yellow or
    # green that cites nothing is refused on the demo path, a red never is.
    rec["would_refuse"] = (not rec["valid_citations"]) and rec["got"] in ("yellow", "green")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="base | tuned-120pairs, for the report only")
    ap.add_argument("--gguf", default="", help="the model file the server has open, for the header")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--chunks", choices=("matched", "retrieval"), default="matched")
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/v1/chat/completions")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--concurrency", type=int, default=2, help="match the server's -np")
    ap.add_argument("--out", default="", help="path stem; .jsonl and .txt are written")
    ap.add_argument("--set", default=str(SET))
    args = ap.parse_args()

    cases = load_set(args.set)
    registry = load_registry()
    turns = build_turns(cases, args.chunks)
    by_id = {c["id"]: c for c in cases}

    stem = Path(args.out) if args.out else \
        REPO / "01-data" / "eval" / "runs" / f"heldout-{args.label}-{args.chunks}"
    stem.parent.mkdir(parents=True, exist_ok=True)
    raw_path = stem.with_suffix(".jsonl")

    prompt_sha = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:8]
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    print(f"label {args.label}  gguf {args.gguf or '(not given)'}  chunks {args.chunks}  "
          f"runs {args.runs}  prompt sha {prompt_sha}", flush=True)

    jobs = [(c, r) for r in range(1, args.runs + 1) for c in cases]
    records = []
    t0 = time.time()
    with raw_path.open("w", encoding="utf-8") as fh, \
            ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = [pool.submit(score_one, args, c, *turns[c["id"]], registry, r) for c, r in jobs]
        for i, f in enumerate(futs, 1):
            rec = f.result()
            records.append(rec)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            mark = "ok " if rec.get("got") == rec.get("expected") else "MISS"
            print(f"  [{i:3}/{len(jobs)}] {rec['id']} run{rec['run']} "
                  f"{mark} expected {rec.get('expected')} got {rec.get('got')} "
                  f"cited {len(rec.get('valid_citations', []))} "
                  f"{rec.get('wall_s', '?')}s{'  ' + rec['error'] if 'error' in rec else ''}",
                  flush=True)
    elapsed = time.time() - t0

    leaked = [r["id"] for r in records if r.get("reasoning_content")]
    errors = [r for r in records if "error" in r or r.get("got") is None]

    lines = []
    def w(s=""):
        lines.append(s)
        print(s)

    w()
    w("=" * 78)
    w(f"HELD-OUT SCORE  label={args.label}  chunks={args.chunks}  runs={args.runs}")
    w(f"started {started}  elapsed {elapsed / 60:.1f} min")
    w(f"gguf            {args.gguf or '(not given)'}")
    w(f"set             {Path(args.set).name} sha {FROZEN_SHA[:16]}")
    w(f"system prompt   02-pairs/system_prompt.txt sha {prompt_sha}")
    w(f"sampling        temperature {TEMPERATURE}, schema on, enable_thinking=false, "
      f"max_tokens {MAX_TOKENS}")
    w(f"reasoning leaks {len(leaked)}  (constraint 5: must be 0)")
    w(f"errors/unparsed {len(errors)}")
    w(f"raw completions {raw_path}")
    w("=" * 78)

    good = [r for r in records if r.get("got")]
    correct = sum(1 for r in good if r["got"] == r["expected"])
    w()
    w(f"OVERALL, per completion: {correct}/{len(good)} = {correct / len(good) * 100:.1f}%")

    # Majority vote per case: the verdict the model gave most often over the runs.
    majority = {}
    for cid in by_id:
        got = [r["got"] for r in records if r["id"] == cid and r.get("got")]
        majority[cid] = collections.Counter(got).most_common(1)[0][0] if got else None
    maj_correct = sum(1 for cid, v in majority.items() if v == by_id[cid]["verdict"])
    w(f"OVERALL, majority of {args.runs} per case: {maj_correct}/{len(by_id)} = "
      f"{maj_correct / len(by_id) * 100:.1f}%")

    stable = sum(1 for cid in by_id
                 if len({r["got"] for r in records if r["id"] == cid and r.get("got")}) == 1)
    w(f"cases that gave the same verdict all {args.runs} runs: {stable}/{len(by_id)}")

    w()
    w("PER CASE")
    w(f"  {'id':<5} {'cond':<9} {'exp':<7} " +
      " ".join(f"{'run' + str(i):<7}" for i in range(1, args.runs + 1)) +
      "  cites(valid/entries)   refused?")
    for c in cases:
        rs = sorted([r for r in records if r["id"] == c["id"]], key=lambda r: r["run"])
        cells = []
        for r in rs:
            g = r.get("got") or "ERR"
            cells.append(f"{g + ('' if g == c['verdict'] else '*'):<7}")
        cites = "/".join(str(x) for x in
                         (sum(len(r.get("valid_citations", [])) for r in rs),
                          sum(len(r.get("citation_entries", [])) for r in rs)))
        refused = sum(1 for r in rs if r.get("would_refuse"))
        w(f"  {c['id']:<5} {c['condition']:<9} {c['verdict']:<7} " + " ".join(cells) +
          f"  {cites:<20}   {refused}/{len(rs)}")
    w("  * = wrong. cites is valid keys / citation entries, summed over the runs.")
    w("  refused? = runs this would have been refused post-flight, constraint 13")
    w("    (a yellow or green that cites nothing; a red is never withheld).")

    w()
    w("CONFUSION, per completion (rows expected, columns given)")
    w(f"  {'':<8}" + "".join(f"{u:>8}" for u in URGENCIES) + f"{'total':>8}")
    for exp in URGENCIES:
        row = [sum(1 for r in good if r["expected"] == exp and r["got"] == g) for g in URGENCIES]
        w(f"  {exp:<8}" + "".join(f"{n:>8}" for n in row) + f"{sum(row):>8}")
    dist = collections.Counter(r["got"] for r in good)
    w(f"  {'given':<8}" + "".join(f"{dist.get(u, 0):>8}" for u in URGENCIES) +
      f"{len(good):>8}")

    w()
    w("PER CONDITION, per completion")
    w(f"  {'condition':<10} {'cases':>5} {'n':>4} {'correct':>8} {'acc':>7}   verdicts given")
    for cond in sorted({c["condition"] for c in cases}):
        rs = [r for r in good if r["condition"] == cond]
        n_cases = sum(1 for c in cases if c["condition"] == cond)
        ok = sum(1 for r in rs if r["got"] == r["expected"])
        dist = collections.Counter(r["got"] for r in rs)
        w(f"  {cond:<10} {n_cases:>5} {len(rs):>4} {ok:>8} "
          f"{ok / len(rs) * 100 if rs else 0:>6.1f}%   " +
          ", ".join(f"{k} {v}" for k, v in sorted(dist.items())))

    w()
    w("PER EXPECTED VERDICT, per completion")
    for exp in URGENCIES:
        rs = [r for r in good if r["expected"] == exp]
        ok = sum(1 for r in rs if r["got"] == exp)
        w(f"  {exp:<7} {ok:>3}/{len(rs):<3} = {ok / len(rs) * 100 if rs else 0:5.1f}%")

    w()
    w("GROUNDING (constraint 13's post-flight condition, scored not applied)")
    nonred = [r for r in good if r["got"] in ("yellow", "green")]
    red = [r for r in good if r["got"] == "red"]
    w(f"  non-red answers citing nothing that resolves: "
      f"{sum(1 for r in nonred if not r['valid_citations'])}/{len(nonred)}"
      f"  -> would be refused")
    w(f"  red answers citing nothing that resolves:     "
      f"{sum(1 for r in red if not r['valid_citations'])}/{len(red)}"
      f"  -> shown as a flagged red")

    if leaked:
        w()
        w(f"WARNING reasoning_content came back non-empty on: {sorted(set(leaked))}")
    if errors:
        w()
        w("ERRORS / UNPARSED")
        for r in errors:
            w(f"  {r['id']} run{r['run']}: {r.get('error') or r.get('parse_error')}")

    txt = stem.with_suffix(".txt")
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwritten: {txt}\n         {raw_path}")


if __name__ == "__main__":
    main()
