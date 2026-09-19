#!/usr/bin/env python3
"""BM25 over the 22 frozen chunks, and a blend with the vector score.

    python 04-retrieval/hybrid.py "sharp pain worse when I breathe in"
    python 04-retrieval/hybrid.py --alpha 0.0 "..."      # pure BM25
    python 04-retrieval/hybrid.py --alpha 1.0 "..."      # pure vector

WHY. Measured 2026-09-17: dense retrieval over this corpus returns CP-PERI-002
for 10 out of 10 queries and never returns 13 of the 22 chunks. The cause looks
like register, not chunk size: the queries are symptom reports in a patient's
voice, most chunks are explanatory prose, and the only chunks that retrieve are
the ones written as symptom lists. Keyword matching attacks that directly,
because "jaw" and "sweating" are the same tokens in both registers even when the
sentences around them are not.

NO CORPUS CHANGE. BM25 is computed from the chunk text already in corpus.db.
Nothing is re-chunked, re-frozen, or re-keyed, so hard constraint 1 is untouched.

BLENDING TWO SCORES THAT ARE NOT ON THE SAME SCALE. Cosine here sits roughly in
0.0 to 0.8; BM25 is unbounded and depends on corpus statistics. Blending them raw
would make alpha meaningless, so both are min-max normalized across the 22 chunks
PER QUERY before mixing. That makes alpha a real mixing weight and makes a result
at alpha 0.5 mean "half each", but it also means the scores are ranks within one
query and are not comparable across queries. Do not display them as confidence.
"""

import argparse
import math
import threading
import re
import sqlite3
import struct
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "corpus.db"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Small and deliberate. A long stoplist would strip clinically loaded words.
STOP = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can",
    "could", "did", "do", "does", "for", "from", "had", "has", "have", "how",
    "i", "if", "in", "into", "is", "it", "its", "me", "my", "no", "not", "of",
    "on", "or", "other", "our", "out", "over", "she", "so", "some", "such",
    "than", "that", "the", "their", "them", "then", "there", "these", "they",
    "this", "to", "up", "was", "were", "what", "when", "which", "while", "who",
    "will", "with", "would", "you", "your", "am", "any", "also", "may", "more",
    "most", "much", "very", "get", "gets", "got", "like", "just", "about",
}

TOKEN = re.compile(r"[a-z]+")


def tokenize(text: str):
    """Lowercase, letters only, stopped, and crudely singularised.

    The plural strip matters more than it looks: the corpus says "heart attack
    symptoms" and a patient says "my symptom", "arms" against "arm". Without it
    those are different terms. It is deliberately dumb, no stemmer, because a
    stemmer would also collapse words a clinician would want kept apart.
    """
    out = []
    for w in TOKEN.findall(text.lower()):
        # Single letters are always junk here and they were actively harmful.
        # The case timelines are written "T+0:00 central chest pressure began",
        # so every timestamp contributed a bare "t" to the query, four of them
        # on red-acs. That matched the "t" that falls out of "don't" in the
        # chunks, and BM25 scored it as a real term. CP-ACS-005 rose on that
        # alone. Found 2026-09-17 while diagnosing why the blend picked it.
        if len(w) < 2 or w in STOP:
            continue
        if len(w) > 3 and w.endswith("es") and not w.endswith("ses"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


class BM25:
    """Standard Okapi BM25. 22 documents, so everything is computed eagerly."""

    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.n = len(self.docs)
        self.len = [len(d) for d in self.docs]
        self.avglen = sum(self.len) / self.n if self.n else 0.0
        self.tf = [Counter(d) for d in self.docs]
        df = Counter()
        for d in self.docs:
            for t in set(d):
                df[t] += 1
        # +1 inside the log keeps idf non-negative for terms in every document,
        # which matters here: with 22 documents a common term like "chest"
        # otherwise goes negative and actively penalises a good match.
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5))
                    for t, c in df.items()}

    def scores(self, query: str):
        q = tokenize(query)
        out = []
        for i in range(self.n):
            s = 0.0
            for t in q:
                if t not in self.tf[i]:
                    continue
                f = self.tf[i][t]
                denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avglen)
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / denom
            out.append(s)
        return out


def minmax(xs):
    lo, hi = min(xs), max(xs)
    if hi - lo < 1e-12:
        return [0.0] * len(xs)
    return [(x - lo) / (hi - lo) for x in xs]


def serialize_f32(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class HybridRetriever:
    def __init__(self, db_path=DB, model_name=MODEL_NAME):
        import sqlite_vec
        from sentence_transformers import SentenceTransformer
        if not Path(db_path).exists():
            raise FileNotFoundError(f"{db_path} not found. Run build_index.py.")
        # check_same_thread=False plus a lock, because the demo server is a
        # ThreadingHTTPServer and hands each request its own thread while this
        # retriever is a module-level singleton. Without it the FIRST query
        # succeeds, creating the connection on that thread, and the SECOND one
        # dies with "SQLite objects created in a thread can only be used in that
        # same thread". A judge asks more than one question, so this was
        # demo-fatal and it only appears on the second request. Found 2026-09-17.
        #
        # The lock is not optional with check_same_thread=False: it disables
        # Python's check, it does not make the connection concurrent.
        self._lock = threading.Lock()
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        rows = self.db.execute(
            "select key, token_count, text, expected_category from chunk_meta "
            "order by key").fetchall()   # __init__, single-threaded, no lock needed
        self.keys = [r[0] for r in rows]
        self.toks = {r[0]: r[1] for r in rows}
        self.text = {r[0]: r[2] for r in rows}
        self.cat = {r[0]: r[3] for r in rows}
        self.model = SentenceTransformer(model_name)
        self.bm25 = BM25([r[2] for r in rows])

    def _cosines(self, query):
        q = serialize_f32(
            self.model.encode([query], normalize_embeddings=True,
                              convert_to_numpy=True)[0].tolist())
        # Ask for every chunk so the blend sees the whole corpus, not a
        # pre-filtered top-k. With 22 chunks that is free.
        with self._lock:
            rows = self.db.execute(
                "select key, distance from chunk_vec where embedding match ? and k = ?",
                (q, len(self.keys))).fetchall()
        d = dict(rows)
        # normalized embeddings: cos = 1 - d^2/2
        return {k: 1.0 - (d[k] ** 2) / 2.0 for k in self.keys}

    def query(self, sql, params=()):
        """Thread-safe read. Everything outside __init__ must go through this."""
        with self._lock:
            return self.db.execute(sql, params).fetchall()

    def search(self, query: str, k: int = 3, alpha: float = 0.5):
        """alpha 1.0 = vector only, 0.0 = BM25 only, 0.5 = half each."""
        cos = self._cosines(query)
        bm = dict(zip(self.keys, self.bm25.scores(query)))
        cos_n = dict(zip(self.keys, minmax([cos[x] for x in self.keys])))
        bm_n = dict(zip(self.keys, minmax([bm[x] for x in self.keys])))
        blended = {x: alpha * cos_n[x] + (1 - alpha) * bm_n[x] for x in self.keys}
        order = sorted(self.keys, key=lambda x: -blended[x])[:k]
        return [(x, blended[x], cos[x], bm[x], self.toks[x], self.cat[x])
                for x in order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--alpha", type=float, default=0.5)
    args = ap.parse_args()
    r = HybridRetriever()
    hits = r.search(" ".join(args.query), args.k, args.alpha)
    print(f"query: {' '.join(args.query)!r}   alpha={args.alpha}\n")
    for key, sc, cos, bm, toks, cat in hits:
        print(f"  {key:<16} blend={sc:.3f}  cos={cos:.3f}  bm25={bm:.2f}  "
              f"{toks:>4} tok  [{cat or 'uncategorised'}]")
    print(f"\n  {sum(h[4] for h in hits)} tokens retrieved")


if __name__ == "__main__":
    main()
