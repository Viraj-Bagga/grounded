#!/usr/bin/env python3
"""Checks for the held-out eval set. Nothing here edits the set.

    python 01-data/eval/heldout-eval/check_heldout.py                 # the set itself
    python 01-data/eval/heldout-eval/check_heldout.py --pairs X.jsonl # pairs against the set

THE SET IS NEVER TRAINING DATA. Pair generation runs --pairs on every batch,
and a pair whose case text is too close to a held-out case is a leak: the
eval would then measure recall of a training example, not triage.

What it checks on the set:
  * every quoted line is verbatim in its chunk file, and every key is in the
    registry (the constraint 14 rule, applied to eval justifications);
  * the verdict mix and which conditions are covered;
  * no case trips the pregnancy exclusion or the child check, which would
    make the demo pipeline refuse it before the model ever answered;
  * every case clears the scope floor, scored the way scope_check scores it,
    on the symptoms alone;
  * which of its justifying keys blend retrieval returns in the top 3, for
    information: the eval can run on matched chunks or on retrieval;
  * overlap with every existing case text, pairs, the 09-17 eval cases and
    the demo presets, and between the held-out cases themselves.

Overlap is scored two ways, because each misses what the other catches: MiniLM
cosine on the whole text, which sees paraphrase, and word-set Jaccard, which
sees a near copy. LEAK is either one at or over its threshold.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SET = HERE / "HELDOUT-EVAL-v1.json"
# Frozen 2026-09-19 after Viraj's review. A frozen file whose bytes change is
# refused, not checked: a verdict change is a new version, never an edit.
FROZEN = {"HELDOUT-EVAL-v1.json": "6d1af06eb393d4afd2c6dc4af1669b70dbc0d6e5f46accf88b686fe3e6826035"}
sys.path.insert(0, str(REPO / "02-pairs"))
sys.path.insert(0, str(REPO / "04-retrieval"))
sys.path.insert(0, str(REPO / "01-data" / "eval"))

COS_LEAK, COS_WARN = 0.85, 0.75
JAC_LEAK = 0.50
STOP = {"a", "an", "and", "the", "i", "my", "me", "it", "is", "was", "of", "to", "in",
        "on", "for", "with", "at", "as", "but", "or", "have", "has", "had", "i've",
        "it's", "i'm", "be", "been", "this", "that", "so", "about", "when", "not", "no"}


def words(text):
    return {w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP}


def jaccard(a, b):
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def symptoms_of(human_turn):
    m = re.search(r"\[SYMPTOMS\]\n(.*?)\n\[/SYMPTOMS\]", human_turn, re.S)
    return m.group(1).strip() if m else None


def existing_texts():
    """Every case text this project has written, so a held-out case can be
    checked against all of them."""
    out = []
    for f in sorted((REPO / "02-pairs").rglob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for turn in row.get("conversations") or []:
                if turn.get("from") in ("human", "user"):
                    s = symptoms_of(turn.get("value", ""))
                    if s:
                        out.append((f"{f.name}:{row.get('id')}", s))
    from discrimination_test import CASES
    out += [(f"discrimination_test:{c['id']}", c["symptom"]) for c in CASES]
    app = REPO / "06-demo" / "static" / "js" / "app.js"
    if app.exists():
        for label, text in re.findall(r'\[\s*"([^"]+)",\s*"([^"]+)"', app.read_text(encoding="utf-8")):
            out.append((f"demo preset:{label}", text))
    return out


def load_set(path=SET):
    import hashlib
    path = Path(path)
    want = FROZEN.get(path.name)
    if want and hashlib.sha256(path.read_bytes()).hexdigest() != want:
        sys.exit(f"{path.name} is frozen and its sha256 has changed. A verdict change "
                 f"is a new version (HELDOUT-EVAL-v2.json), never an edit.")
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


class Embedder:
    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.m = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    def __call__(self, texts):
        return self.m.encode(list(texts), normalize_embeddings=True).astype("float64")


def cosines(qv, pv):
    """Query-by-pool cosine matrix. The vectors are unit length, so a dot product.

    NumPy's matmul through macOS Accelerate raises divide-by-zero, overflow and
    invalid-value warnings here with finite, correct results, in float32 and
    float64 alike: checked 2026-09-19, no NaN and every norm 1.0. The flags are
    silenced for this one product only, and the result is asserted finite, so a
    real fault still stops the check rather than scoring garbage.
    """
    import numpy as np
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        sims = qv @ pv.T
    assert np.isfinite(sims).all(), "non-finite cosine: the embeddings are broken"
    return sims


def overlap_report(queries, pool, emb, label):
    """For each (id, text) in queries, its closest text in pool, both ways."""
    sims = cosines(emb([t for _, t in queries]), emb([t for _, t in pool]))
    rows, leaks = [], 0
    for i, (qid, qt) in enumerate(queries):
        j = int(sims[i].argmax())
        cos = float(sims[i, j])
        jac_j = max(range(len(pool)), key=lambda k: jaccard(qt, pool[k][1]))
        jac = jaccard(qt, pool[jac_j][1])
        verdict = ("LEAK" if cos >= COS_LEAK or jac >= JAC_LEAK else
                   "warn" if cos >= COS_WARN else "ok")
        leaks += verdict == "LEAK"
        rows.append(f"  {qid:<14} {verdict:<5} cos {cos:.3f} ({pool[j][0]})  "
                    f"jaccard {jac:.2f} ({pool[jac_j][0]})")
    print(f"\n{label}: {leaks} leak(s) at cos >= {COS_LEAK} or jaccard >= {JAC_LEAK}")
    print("\n".join(rows))
    return leaks


def check_set(cases):
    problems = []
    registry = {r["key"] for r in csv.DictReader(open(REPO / "01-data" / "citations.csv", encoding="utf-8"))}
    chunks = {k: (REPO / "01-data" / "chunks" / f"{k}.txt").read_text(encoding="utf-8") for k in registry}

    print("== GROUNDING: every quote verbatim in its chunk, every key in the registry")
    for c in cases:
        for k in c["keys"]:
            if k not in registry:
                problems.append(f"{c['id']}: {k} is not in the registry")
            if k not in c["quotes"]:
                problems.append(f"{c['id']}: {k} is cited with no quote")
        for k, lines in c["quotes"].items():
            if k not in c["keys"]:
                problems.append(f"{c['id']}: quotes {k}, which is not in its keys")
            for line in lines:
                if k in chunks and line not in chunks[k]:
                    problems.append(f"{c['id']}: not verbatim in {k}: {line[:60]!r}")
    n_quotes = sum(len(v) for c in cases for v in c["quotes"].values())
    print(f"  {n_quotes} quotes across {len(cases)} cases: "
          f"{'all verbatim' if not problems else f'{len(problems)} PROBLEMS'}")

    from collections import Counter
    mix = Counter(c["verdict"] for c in cases)
    conds = Counter(c["condition"] for c in cases)
    print(f"\n== MIX  red {mix['red']}  yellow {mix['yellow']}  green {mix['green']}  "
          f"({', '.join(f'{100 * mix[v] / len(cases):.0f}%' for v in ('red', 'yellow', 'green'))})")
    print("  by condition: " + ", ".join(
        f"{k} {v} ({'/'.join(sorted({c['verdict'] for c in cases if c['condition'] == k}))})"
        for k, v in sorted(conds.items())))
    thin = [c["id"] for c in cases if c.get("grounding") == "thin"]
    print(f"  grounding marked thin: {', '.join(thin) or 'none'}")

    # The question this set exists to answer: does the model's verdict follow
    # the case, or the chunk? It can only tell where a prefix carries more than
    # one verdict. A single-colour prefix is scored perfectly by a model that
    # learned "this chunk means this colour".
    by_prefix = {}
    for c in cases:
        for pfx in {re.sub(r"-\d+$", "", k) for k in c["keys"]}:
            by_prefix.setdefault(pfx, Counter())[c["verdict"]] += 1
    print("\n== VERDICTS PER CITED PREFIX (a case counts under every prefix it cites)")
    for pfx, cnt in sorted(by_prefix.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
        cells = "  ".join(f"{v} {cnt[v]}" for v in ("red", "yellow", "green"))
        print(f"  {pfx:<9} {cells}  {'mixed' if len(cnt) > 1 else 'single colour'}")
    mixed = sorted(p for p, cnt in by_prefix.items() if len(cnt) > 1)
    print(f"  {len(mixed)} of {len(by_prefix)} prefixes can catch the chunk-to-colour shortcut: {', '.join(mixed)}")

    from guards import SCOPE_FLOOR, child_term, excluded_subject
    from hybrid import HybridRetriever
    r = HybridRetriever()
    print(f"\n== SCOPE (symptoms only, floor {SCOPE_FLOOR}), EXCLUSIONS, RETRIEVAL (blend, top 3)")
    for c in cases:
        cos = max(r._cosines(c["symptoms"]).values())
        excluded = excluded_subject(c["symptoms"] + "\n" + c.get("timeline", ""))[0]
        child = child_term(c["symptoms"] + "\n" + c.get("timeline", ""))
        q = c["symptoms"] + ("\n" + c["timeline"] if c.get("timeline") else "")
        got = [h[0] for h in r.search(q, 3, 0.5)]
        hit = [k for k in c["keys"] if k in got]
        if cos < SCOPE_FLOOR:
            problems.append(f"{c['id']}: below the scope floor at {cos:.3f}")
        if excluded or child:
            problems.append(f"{c['id']}: trips {'the pregnancy exclusion' if excluded else f'the child check ({child})'}")
        print(f"  {c['id']} {c['verdict']:<6} scope {cos:.3f} (+{cos - SCOPE_FLOOR:.3f})  "
              f"keys retrieved {len(hit)}/{len(c['keys'])}  top3 {got}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default=str(SET))
    ap.add_argument("--pairs", help="a pairs .jsonl to check against the held-out set")
    args = ap.parse_args()
    cases = load_set(args.set)
    emb = Embedder()
    held = [(c["id"], c["symptoms"]) for c in cases]

    if args.pairs:
        pairs = []
        for line in Path(args.pairs).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                for turn in row.get("conversations") or []:
                    if turn.get("from") in ("human", "user") and symptoms_of(turn.get("value", "")):
                        pairs.append((row.get("id"), symptoms_of(turn["value"])))
        leaks = overlap_report(pairs, held, emb, f"PAIRS in {Path(args.pairs).name} against the held-out set")
        sys.exit(1 if leaks else 0)

    problems = check_set(cases)
    leaks = overlap_report(held, existing_texts(), emb, "LEAK CHECK against every existing case text")
    inner = 0
    print("\n== WITHIN THE SET (closest other held-out case)")
    vecs = emb([t for _, t in held])
    sims = cosines(vecs, vecs)
    for i, (hid, ht) in enumerate(held):
        sims[i, i] = -1
        j = int(sims[i].argmax())
        flag = "NEAR-DUPLICATE" if sims[i, j] >= COS_LEAK else ""
        inner += bool(flag)
        print(f"  {hid} ~ {held[j][0]}  cos {sims[i, j]:.3f} {flag}")
    print(f"\nRESULT: {len(problems)} problem(s), {leaks} leak(s), {inner} near-duplicate(s) within the set")
    for p in problems:
        print("  ", p)
    sys.exit(1 if problems or leaks or inner else 0)


if __name__ == "__main__":
    main()
