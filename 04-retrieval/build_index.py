#!/usr/bin/env python3
"""Epic 4. Embed the frozen chunks and build a sqlite-vec index.

    python 04-retrieval/build_index.py            # build
    python 04-retrieval/build_index.py --verify   # rebuild nothing, check what exists

Output: 04-retrieval/corpus.db, a sqlite database with one vec0 virtual table
and one metadata table, keyed by citation key.

THE 256 WORD-PIECE CEILING IS CHECKED HERE, NOT ASSUMED. Hard constraint 2:
all-MiniLM-L6-v2 truncates at 256 word-pieces and anything past the cut is
silently invisible to retrieval. The freeze already enforces it, so this should
never fire, but "should never fire" is exactly the check worth having, because
the failure mode is silence rather than an error. Chunks are embedded one at a
time with the tokenizer's own count asserted first.

EVERY CHUNK IS VERIFIED AGAINST ITS FROZEN HASH before it is embedded. The
registry carries chunk_sha256 and the keys are immutable per hard constraint 1.
If a chunk file has drifted from what was frozen, the index would quietly encode
text that no training pair refers to, so this refuses rather than proceeding.
"""

import argparse
import csv
import hashlib
import sqlite3
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "01-data"
CHUNKS = DATA / "chunks"
REGISTRY = DATA / "citations.csv"
DB = HERE / "corpus.db"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIM = 384
MAX_WORDPIECES = 256    # hard constraint 2


def load_registry():
    with open(REGISTRY, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def chunk_sha(text: str) -> str:
    """Matches build_corpus.py: first 16 hex chars of the sha256 of the text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def serialize_f32(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="inspect an existing corpus.db instead of building")
    args = ap.parse_args()

    import sqlite_vec
    from sentence_transformers import SentenceTransformer

    if args.verify:
        if not DB.exists():
            sys.exit(f"no {DB}, run without --verify first")
        db = sqlite3.connect(DB)
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        n = db.execute("select count(*) from chunk_meta").fetchone()[0]
        v = db.execute("select count(*) from chunk_vec").fetchone()[0]
        tot = db.execute("select sum(token_count) from chunk_meta").fetchone()[0]
        print(f"{DB.name}: {n} metadata rows, {v} vectors, {tot} tokens total")
        for row in db.execute(
                "select key, token_count, length(text) from chunk_meta order by key"):
            print(f"  {row[0]:<16} {row[1]:>4} tokens  {row[2]:>5} chars")
        return

    rows = load_registry()
    print(f"registry: {len(rows)} keys")

    # Verify every chunk against its frozen hash BEFORE embedding anything.
    texts, keys = [], []
    for r in rows:
        p = CHUNKS / f"{r['key']}.txt"
        if not p.exists():
            sys.exit(f"missing chunk file for {r['key']}")
        text = p.read_text(encoding="utf-8").strip()
        got = chunk_sha(text)
        if got != r["chunk_sha256"]:
            sys.exit(f"{r['key']} has drifted from the freeze: "
                     f"registry {r['chunk_sha256']}, file {got}. "
                     f"Keys are immutable (hard constraint 1); do not re-embed "
                     f"until this is explained.")
        keys.append(r["key"])
        texts.append(text)
    print(f"all {len(keys)} chunks match their frozen sha256")

    print(f"loading {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)
    tok = model.tokenizer

    # Hard constraint 2, checked with the model's own tokenizer.
    over = []
    for k, t in zip(keys, texts):
        n = len(tok.encode(t, add_special_tokens=True))
        if n > MAX_WORDPIECES:
            over.append((k, n))
    if over:
        print("\nREJECTED, over the 256 word-piece ceiling. Constraint 2 says "
              "reject, never truncate:")
        for k, n in over:
            print(f"  {k}: {n} word-pieces")
        sys.exit(1)
    widest = max((len(tok.encode(t, add_special_tokens=True)), k)
                 for k, t in zip(keys, texts))
    print(f"word-piece ceiling OK, widest is {widest[1]} at {widest[0]}/{MAX_WORDPIECES}")

    print("embedding ...")
    vecs = model.encode(texts, normalize_embeddings=True,
                        show_progress_bar=False, convert_to_numpy=True)
    assert vecs.shape == (len(keys), DIM), f"unexpected shape {vecs.shape}"

    if DB.exists():
        DB.unlink()
    db = sqlite3.connect(DB)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.execute(f"create virtual table chunk_vec using vec0("
               f"key text primary key, embedding float[{DIM}])")
    db.execute("""create table chunk_meta (
        key text primary key, topic text, subtopic text, expected_category text,
        publisher text, url text, retrieval_date text, attribution text,
        token_count integer, chunk_sha256 text, text text)""")

    by_key = {r["key"]: r for r in rows}
    for k, t, v in zip(keys, texts, vecs):
        r = by_key[k]
        db.execute("insert into chunk_vec(key, embedding) values (?, ?)",
                   (k, serialize_f32(v.tolist())))
        db.execute("insert into chunk_meta values (?,?,?,?,?,?,?,?,?,?,?)",
                   (k, r["topic"], r["subtopic"], r["expected_category"],
                    r["publisher"], r["url"], r["retrieval_date"],
                    r["attribution"], int(r["token_count"]), r["chunk_sha256"], t))
    db.commit()

    n = db.execute("select count(*) from chunk_meta").fetchone()[0]
    tot = db.execute("select sum(token_count) from chunk_meta").fetchone()[0]
    print(f"\nwrote {DB}")
    print(f"  {n} chunks, {tot} tokens total, mean {tot / n:.0f}")
    print(f"  embedding dim {DIM}, normalized, so L2 distance ranks the same "
          f"as cosine")


if __name__ == "__main__":
    main()
