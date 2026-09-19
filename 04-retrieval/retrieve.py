#!/usr/bin/env python3
"""Epic 4. Query the sqlite-vec index.

    python 04-retrieval/retrieve.py "burning in my chest after dinner"
    python 04-retrieval/retrieve.py --k 5 "sharp pain worse when I breathe in"

Library use:
    from retrieve import Retriever
    r = Retriever()
    hits = r.search("...", k=3)          # [(key, distance, token_count, text)]

WHY TOKENS ARE REPORTED ON EVERY QUERY. Hard constraint 7: chunk size is a
latency decision, not a tidiness one. Prompt eval runs at 30 to 32 tok/s on CPU
under llama-server, which is the decided demo surface, so every 100 tokens of
retrieved context costs about 3.1 s on a cold turn. A top-3 that happens to
select the three longest chunks is a materially slower demo than one that does
not, and the only way to see that coming is to print it.

Distances are L2 over normalized embeddings, so smaller is closer and the
ranking is identical to cosine. They are NOT similarities; do not report them
as a confidence.
"""

import argparse
import sqlite3
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "corpus.db"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Measured 2026-09-15 under llama-server with -ngl 0 on the M4, and re-confirmed
# as the demo surface 2026-09-17. Used only to turn a token count into a number
# a human can act on.
PROMPT_EVAL_TOK_PER_S = 31.0


def serialize_f32(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class Retriever:
    def __init__(self, db_path=DB, model_name=MODEL_NAME):
        import sqlite_vec
        from sentence_transformers import SentenceTransformer
        if not Path(db_path).exists():
            raise FileNotFoundError(
                f"{db_path} not found. Run build_index.py first.")
        # check_same_thread=False for the same reason as hybrid.py: this class
        # is CLI-only today, and the next person to import it into a threaded
        # server would otherwise hit "SQLite objects created in a thread can
        # only be used in that same thread" on their SECOND request, not their
        # first. Costs nothing here and removes the trap.
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        self.model = SentenceTransformer(model_name)

    def embed(self, text: str):
        return self.model.encode([text], normalize_embeddings=True,
                                 convert_to_numpy=True)[0]

    def search(self, query: str, k: int = 3):
        """Top-k by L2 over normalized embeddings. Smaller distance is closer."""
        q = serialize_f32(self.embed(query).tolist())
        rows = self.db.execute(
            """select v.key, v.distance, m.token_count, m.text, m.expected_category
               from chunk_vec v join chunk_meta m on m.key = v.key
               where v.embedding match ? and k = ?
               order by v.distance""",
            (q, k)).fetchall()
        return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+")
    ap.add_argument("--k", type=int, default=3)
    args = ap.parse_args()
    query = " ".join(args.query)

    r = Retriever()
    hits = r.search(query, args.k)
    total = sum(h[2] for h in hits)
    print(f"query: {query!r}\n")
    for key, dist, toks, text, cat in hits:
        print(f"  {key:<16} d={dist:.4f}  {toks:>4} tok  "
              f"[{cat or 'uncategorised'}]")
        print(f"      {text[:110].replace(chr(10), ' ')}...")
    print(f"\n  retrieved {total} tokens across {len(hits)} chunks, "
          f"about {total / PROMPT_EVAL_TOK_PER_S:.1f} s of prompt eval "
          f"at {PROMPT_EVAL_TOK_PER_S:.0f} tok/s")


if __name__ == "__main__":
    main()
