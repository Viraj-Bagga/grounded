#!/usr/bin/env python3
"""Apply authored pair content to scaffolded slots.

    python 02-pairs/fill_pairs.py <content.py> [--file review/candidates-60.jsonl]

The content file is a plain Python module defining PAIRS, a dict keyed by slot
id. Each value is {profile, symptoms, answer} and optionally {timeline} and
{turns} for multi-turn slots.

WHY A SEPARATE APPLIER. The slot decides the mechanics: which chunks, which
register, which category, how many turns. The content file decides only what a
clinician has to decide. Keeping them apart means re-scaffolding never destroys
authored text and authored text never silently changes a chunk list.

It refuses to write a pair whose citations are not a subset of the slot's
reference_keys, because that is hard constraint 9 failing at authoring time
rather than at inference time, and it is the cheapest place to catch it.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pair_format import SYSTEM_PROMPT, build_human_turn, load_chunk_texts


def load_content(path):
    spec = importlib.util.spec_from_file_location("content", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PAIRS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("content")
    ap.add_argument("--file", default=str(HERE / "review" / "candidates-60.jsonl"))
    args = ap.parse_args()

    texts = load_chunk_texts()
    pairs = load_content(args.content)
    path = Path(args.file)
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_id = {r["id"]: r for r in rows}

    unknown = [k for k in pairs if k not in by_id]
    if unknown:
        sys.exit(f"content references slots that do not exist: {unknown}")

    applied = 0
    for pid, c in pairs.items():
        r = by_id[pid]
        keys = r["reference_keys"]
        for turn in c.get("turns", [c]):
            cites = set(turn["answer"].get("citations") or [])
            stray = cites - set(keys)
            if stray:
                sys.exit(f"{pid}: cites {sorted(stray)} which is not in its "
                         f"reference_keys {keys}. Constraint 9, caught at "
                         f"authoring time.")
            if turn["answer"]["urgency"] == "red" and turn["answer"].get("follow_up_questions"):
                sys.exit(f"{pid}: red verdict carrying follow_up_questions. "
                         f"Hard constraint 4.")

        convs = [{"from": "system", "value": SYSTEM_PROMPT}]
        turns = c.get("turns", [c])
        for i, t in enumerate(turns):
            convs.append({"from": "human", "value": build_human_turn(
                c["profile"], t["symptoms"], keys if i == 0 else keys, texts,
                timeline=t.get("timeline"))})
            convs.append({"from": "gpt",
                          "value": json.dumps(t["answer"], ensure_ascii=False)})
        r["conversations"] = convs
        r["filled"] = True
        applied += 1

    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                    encoding="utf-8")
    total = sum(1 for r in rows if r.get("filled"))
    print(f"applied {applied}, now {total}/{len(rows)} filled")


if __name__ == "__main__":
    main()
