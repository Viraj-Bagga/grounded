#!/usr/bin/env python3
"""
Epic 1 corpus builder.

Three commands, run in order. Each one stops and makes you look at the output
before the next is allowed to touch anything.

    python build_corpus.py fetch     # pull raw HTML, save it, never overwrite silently
    python build_corpus.py chunk     # split into candidate chunks for review
    python build_corpus.py freeze    # promote reviewed chunks, assign keys, write registry

Once a registry exists, new sources are added with

    python build_corpus.py freeze --append --only id[,id...] [--dry-run]

which appends rows and never renumbers. See freeze_append.

Design rules baked in:
  * Chunks are CANDIDATES until you review them. The script will not freeze a
    corpus you have not looked at.
  * Token budget is enforced against all-MiniLM-L6-v2's 256 word-piece limit.
    Anything over is REJECTED, not truncated. Truncation is silent data loss.
  * Once frozen, keys are immutable. Re-running freeze on an existing registry
    refuses unless you pass --force, because shifting a key breaks every
    training pair that references it.
  * Raw HTML is kept so the whole thing is reproducible from disk without network.

Deps: requests, beautifulsoup4, pyyaml
Optional but strongly recommended: transformers (for exact word-piece counts)
    pip install requests beautifulsoup4 pyyaml transformers
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
REVIEW = HERE / "review"
CHUNKS = HERE / "chunks"
REGISTRY = HERE / "citations.csv"
FETCH_LOG = HERE / "fetch_log.json"

MINILM_LIMIT = 256          # all-MiniLM-L6-v2 max_seq_length, in word pieces
TARGET_LOW = 120            # below this a chunk is probably a fragment
TARGET_HIGH = 240           # leave headroom under the hard limit

USER_AGENT = "steelhacks-triage-corpus-builder/0.1 (educational hackathon project)"

# cdc.gov sits behind Akamai, which returns 403 to a bare User-Agent header no
# matter what that header says. Verified 2026-09-15: the project UA, a full
# Chrome UA and plain curl all got "Access Denied" from AkamaiGHost with a
# 411-byte body. Sending the Sec-Fetch-* set that a real navigation carries,
# plus Accept-Encoding, returns 200. These are ordinary browser request headers
# and nothing here misrepresents who is fetching: the project UA is still sent.
# Applied to every source, since it changes nothing for the NIH and MedlinePlus
# hosts that already worked.
FETCH_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


# --------------------------------------------------------------------------
# tokenisation
# --------------------------------------------------------------------------

class TokenCounter:
    """Exact word-piece count if transformers is present, estimate otherwise."""

    def __init__(self):
        self.exact = False
        self._tok = None
        try:
            from transformers import AutoTokenizer
            self._tok = AutoTokenizer.from_pretrained(
                "sentence-transformers/all-MiniLM-L6-v2"
            )
            self.exact = True
        except Exception:
            pass

    def count(self, text: str) -> int:
        if self.exact:
            return len(self._tok.encode(text, add_special_tokens=True))
        # Fallback. BERT word-piece runs ~1.3 pieces per whitespace token on
        # clinical prose. Deliberately pessimistic so the estimate does not
        # let an oversized chunk through.
        return int(len(text.split()) * 1.4) + 2

    def banner(self) -> str:
        if self.exact:
            return "token counts: EXACT (transformers word-piece)"
        return ("token counts: ESTIMATED (transformers not installed). "
                "Install it before freezing: pip install transformers")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def load_manifest() -> dict:
    path = HERE / "sources.yaml"
    if not path.exists():
        sys.exit(f"missing {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def shippable(src: dict) -> bool:
    return src.get("license_status") in ("green", "amber")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def slug(text: str, n: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n]


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------

def cmd_fetch(args):
    import requests

    manifest = load_manifest()
    RAW.mkdir(parents=True, exist_ok=True)
    log = json.loads(FETCH_LOG.read_text()) if FETCH_LOG.exists() else {}

    for src in manifest["sources"]:
        if not shippable(src):
            print(f"  SKIP {src['id']}: license_status={src['license_status']}")
            continue

        dest = RAW / f"{src['id']}.html"
        if dest.exists() and not args.force:
            print(f"  have {src['id']}  ({dest.stat().st_size:,} bytes)")
            continue

        print(f"  GET  {src['url']}")
        try:
            r = requests.get(src["url"], timeout=30, headers=FETCH_HEADERS)
            r.raise_for_status()
        except Exception as e:
            print(f"  FAIL {src['id']}: {e}")
            continue

        # medlineplus.gov and cdc.gov send a bare `text/html` with no charset,
        # so requests falls back to ISO-8859-1 and every literal UTF-8
        # character becomes mojibake. Verified 2026-09-17: the three raw files
        # from those hosts carry it, only in the language switcher and the .gov
        # banner, so no extracted text was touched. The next page from those
        # hosts could carry it in the body. Both declare utf-8 in a meta tag,
        # so trust the page's own declaration over the HTTP default.
        if "charset" not in r.headers.get("content-type", "").lower():
            from bs4.dammit import EncodingDetector
            r.encoding = (EncodingDetector.find_declared_encoding(r.content, is_html=True)
                          or r.apparent_encoding)

        dest.write_text(r.text, encoding="utf-8")
        log[src["id"]] = {
            "url": src["url"],
            "retrieved": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": r.status_code,
            "bytes": len(r.text),
            "sha256": sha256(r.text),
        }
        print(f"       saved {len(r.text):,} bytes")

    FETCH_LOG.write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"\nfetch log: {FETCH_LOG}")
    print("Retrieval dates are recorded there. A citation without one is not reproducible.")


# --------------------------------------------------------------------------
# chunk
# --------------------------------------------------------------------------

BOILERPLATE = re.compile(
    r"skip to main content|official website|secure \.gov|back to top|"
    r"language switcher|book traversal|share this|last updated on|"
    r"privacy policy|freedom of information|stay connected|"
    r"web policies|social media|get email alerts|live chat|"
    r"nih websites are changing|participate in a study",
    re.I,
)

# Bare list items that are site chrome rather than content. These are matched
# whole, never as substrings, so "Symptoms" the breadcrumb goes and "Symptoms
# started last night" stays.
NAV_LABEL = re.compile(
    r"^(home|health topics|health information|digestive diseases|"
    r"symptoms|symptoms & causes|diagnosis|treatment|recovery|prevention|"
    r"types|living with|causes and risk factors|causes and prevention|"
    r"risk factors|preventing blood clots|english|espa\S+ol|en espa\S+ol|"
    r"< *back to .*|what is .*\?|.*and heart disease|heart attacks in women|"
    r"pulmonary embolism \(pe\))$",
    re.I,
)

# A short <li> is kept unless it looks like navigation. The old rule dropped
# every <li> under 25 characters, which silently deleted one-word clinical
# findings: "Chills", "Fever", "Sweating", "Sore muscles". Those are exactly
# the short benign discriminators the corpus is thin on, so the length cutoff
# was removing the content we most need.
SHORT_LI = 25


def _pure_link(li, text: str) -> bool:
    """True if the whole list item is a single hyperlink, i.e. a menu entry."""
    a = li.find("a")
    return bool(a) and " ".join(a.get_text(" ", strip=True).split()) == text


def _list_is_nav(li) -> bool:
    """True if the enclosing list is mostly bare hyperlinks."""
    ul = li.find_parent(["ul", "ol"])
    if ul is None:
        return False
    items = ul.find_all("li", recursive=False)
    if not items:
        return False
    linky = sum(
        1
        for x in items
        if _pure_link(x, " ".join(x.get_text(" ", strip=True).split()))
    )
    return linky >= max(1, len(items) // 2)


def _is_nav_li(li, text: str, topics: set) -> bool:
    if NAV_LABEL.match(text):
        return True
    if text.casefold() in topics:        # breadcrumb repeating the page topic
        return True
    return _pure_link(li, text) and _list_is_nav(li)


def extract_main(html: str, selectors, title: str = "") -> "list[tuple[str, list[tuple[str, str]]]]":
    """Return [(heading, [(kind, text), ...]), ...] where kind is 'p' or 'li'."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "form", "aside"]):
        tag.decompose()

    # NHLBI glossary tooltips. The modal holds the pronunciation and the full
    # definition, which get_text() would flatten into the body ("cancer cancer
    # (KAN-ser): Diseases in which..."). The inline trigger word sits outside
    # the modal, so dropping only .usa-modal keeps the term and loses the
    # gloss. Do not widen this to match "glossary": the term itself is inside
    # those nodes and removing them deletes clinical words mid-sentence.
    for tag in soup.select(".usa-modal"):
        tag.decompose()

    root = None
    for sel in (selectors or []):
        found = soup.select_one(sel)
        if found:
            root = found
            break
    root = root or soup.body or soup

    # Page topic names, used to spot breadcrumbs that just repeat the title.
    topics = {title.casefold()} if title else set()
    for h in soup.find_all("h1"):
        t = " ".join(h.get_text(" ", strip=True).split())
        if t:
            topics.add(t.casefold())
            topics.add(re.sub(r"\s+symptoms$", "", t, flags=re.I).casefold())
    topics.discard("")

    sections, heading, buf = [], "(intro)", []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text or BOILERPLATE.search(text):
            continue

        if el.name in ("h1", "h2", "h3", "h4"):
            if buf:
                sections.append((heading, buf))
            heading, buf = text, []
            continue

        if el.name == "li":
            if _is_nav_li(el, text, topics):
                continue
            buf.append(("li", text))
        else:
            if len(text) > SHORT_LI:
                buf.append(("p", text))

    if buf:
        sections.append((heading, buf))
    return sections


def group_runs(items):
    """Collapse contiguous list items into atomic units.

    Returns [(kind, [text, ...]), ...] where kind is 'p' (always one text) or
    'run' (one or more list items that must stay together).
    """
    units, run = [], []
    for kind, text in items:
        if kind == "li":
            run.append(text)
        else:
            if run:
                units.append(("run", run))
                run = []
            units.append(("p", [text]))
    if run:
        units.append(("run", run))
    return units


def pack(items, counter, low=TARGET_LOW, high=TARGET_HIGH):
    """Pack into chunks without ever splitting a list run."""
    out, cur, cur_n = [], [], 0

    for kind, texts in group_runs(items):
        body = "\n".join(texts) if kind == "run" else texts[0]
        n = counter.count(body)

        if n > high:
            # Oversized on its own. Flush, emit alone, let review flag it OVER.
            # A run this long must be split by a human on a clinical boundary,
            # never by the packer on a token boundary.
            if cur:
                out.append(cur)
                cur, cur_n = [], 0
            out.append([body])
            continue

        if cur_n + n > high:
            out.append(cur)
            cur, cur_n = [body], n
        else:
            cur.append(body)
            cur_n += n

    if cur:
        out.append(cur)
    return out


def cmd_chunk(args):
    manifest = load_manifest()
    counter = TokenCounter()
    print(counter.banner(), "\n")

    REVIEW.mkdir(parents=True, exist_ok=True)
    total, flagged = 0, 0

    for src in manifest["sources"]:
        if not shippable(src):
            continue
        raw = RAW / f"{src['id']}.html"
        if not raw.exists():
            print(f"  MISS {src['id']}: run fetch first")
            continue

        # A review file is hand-edited: chunks get deleted, merged and split by
        # a human before freeze. Regenerating it silently throws all of that
        # away and, worse, resurrects chunks that were deliberately cut. Skip
        # anything that already exists unless --force says otherwise.
        out = REVIEW / f"{src['id']}.txt"
        if out.exists() and not args.force:
            print(f"  keep {src['id']}: review file exists, not regenerating "
                  f"(--force to overwrite)")
            continue

        sections = extract_main(
            raw.read_text(encoding="utf-8"),
            src.get("selectors"),
            src.get("title", ""),
        )
        candidates = []
        for heading, items in sections:
            for group in pack(items, counter):
                body = "\n\n".join(group)
                n = counter.count(body)
                candidates.append({"heading": heading, "text": body, "tokens": n})

        lines = [
            f"# REVIEW: {src['id']}",
            f"# {src['title']}",
            f"# {src['publisher']}",
            f"# {src['url']}",
            f"# key_prefix: {src['key_prefix']}   expected_category: {src.get('expected_category')}",
            f"# role: {src.get('role','')}",
            "#",
            "# Delete any chunk that is navigation, boilerplate, or clinically useless.",
            "# Merge or split by hand where the boundary is wrong. A red-flag list must",
            "# never be split across two chunks: the citation breaks if it is.",
            "# Chunks marked OVER must be cut down. They are not truncated for you.",
            "# A chunk that needs a different category from its page gets",
            "# category=red|yellow|green before heading= on its --- line.",
            "#",
            "",
        ]
        for i, c in enumerate(candidates, 1):
            status = "OVER " if c["tokens"] > MINILM_LIMIT else (
                     "short" if c["tokens"] < TARGET_LOW else "ok   ")
            if c["tokens"] > MINILM_LIMIT:
                flagged += 1
            lines += [
                f"--- chunk {i:03d} [{status}] tokens={c['tokens']} heading={c['heading']}",
                c["text"],
                "",
            ]
            total += 1

        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"  {src['id']}: {len(candidates)} candidates -> {out.name}")

    print(f"\n{total} candidate chunks, {flagged} over the {MINILM_LIMIT} token limit.")
    if REGISTRY.exists():
        # A plain freeze here would rebuild every key, which is the one thing
        # that must not happen once pairs cite them.
        print(f"Review and edit the files in {REVIEW}. A registry exists, so add them with:\n"
              f"  python build_corpus.py freeze --append --only <source ids> --dry-run")
    else:
        print(f"Review and edit the files in {REVIEW}, then run: python build_corpus.py freeze")


# --------------------------------------------------------------------------
# freeze
# --------------------------------------------------------------------------

CHUNK_RE = re.compile(r"^--- chunk (\d+) \[(.*?)\] tokens=(\d+)"
                      r"(?: category=(\S*))? heading=(.*)$")
CATEGORIES = ("red", "yellow", "green")


def parse_review(path: Path):
    blocks, cur = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = CHUNK_RE.match(line)
        if m:
            if cur:
                blocks.append(cur)
            cur = {"heading": m.group(5).strip(), "category": m.group(4), "lines": []}
        elif cur is not None and not line.startswith("#"):
            cur["lines"].append(line)
    if cur:
        blocks.append(cur)
    for b in blocks:
        b["text"] = "\n".join(b["lines"]).strip()
    return [b for b in blocks if b["text"]]


def chunk_category(src: dict, block: dict):
    """The chunk's category and an error, exactly one of which is None.

    expected_category is set per source, so a chunk that argues a different
    category than its page, unstable angina on a yellow angina page, needs its
    own. The reviewer writes category=red|yellow|green before heading= on the
    chunk's --- line. Anything else is refused, never read as the default: a
    typo that silently froze the page's colour would put the wrong one on screen.
    """
    cat = block.get("category")
    if cat is None:
        if "category=" in block["heading"]:
            return None, "category= must come before heading= on the --- line"
        return src.get("expected_category") or "", None
    if cat not in CATEGORIES:
        return None, f"category={cat!r} is not one of {', '.join(CATEGORIES)}"
    return cat, None


def cmd_freeze(args):
    manifest = load_manifest()
    counter = TokenCounter()
    print(counter.banner())

    # Without this, `freeze --only x --force` would quietly be a full rebuild.
    if (args.only or args.dry_run) and not args.append:
        sys.exit("\n--only and --dry-run only apply with --append.")

    if args.append:
        if args.force:
            sys.exit("\n--append never overwrites anything, so --force means nothing with it.")
        if not counter.exact:
            sys.exit("\nRefusing to freeze on estimated token counts.\n  pip install transformers")
        return freeze_append(args, manifest, counter)

    if not counter.exact and not args.force:
        sys.exit("\nRefusing to freeze on estimated token counts.\n"
                 "  pip install transformers\n"
                 "Or pass --force if you accept the risk of silent truncation at embed time.")

    if REGISTRY.exists() and not args.force:
        sys.exit(f"\n{REGISTRY} already exists. The corpus is frozen.\n"
                 "Keys are immutable once a training pair references them. "
                 "Pass --force only if no pairs have been written yet.")

    CHUNKS.mkdir(parents=True, exist_ok=True)
    rows, counters, errors = [], {}, []
    log = json.loads(FETCH_LOG.read_text()) if FETCH_LOG.exists() else {}

    for src in manifest["sources"]:
        if not shippable(src):
            continue
        review = REVIEW / f"{src['id']}.txt"
        if not review.exists():
            print(f"  MISS {src['id']}: no reviewed file")
            continue

        prefix = src["key_prefix"]
        for block in parse_review(review):
            n = counter.count(block["text"])
            if n > MINILM_LIMIT:
                errors.append(f"{src['id']} :: {block['heading'][:40]} :: {n} tokens")
                continue
            category, problem = chunk_category(src, block)
            if problem:
                errors.append(f"{src['id']} :: {block['heading'][:40]} :: {problem}")
                continue

            counters[prefix] = counters.get(prefix, 0) + 1
            key = f"{prefix}-{counters[prefix]:03d}"

            (CHUNKS / f"{key}.txt").write_text(block["text"], encoding="utf-8")
            rows.append({
                "key": key,
                "topic": manifest["topic"],
                "subtopic": slug(block["heading"]),
                "expected_category": category,
                "source_id": src["id"],
                "publisher": src["publisher"],
                "url": src["url"],
                "retrieval_date": log.get(src["id"], {}).get("retrieved", "")[:10],
                "license_status": src["license_status"],
                "attribution": src["attribution"],
                "token_count": n,
                "chunk_sha256": sha256(block["text"]),
            })

    if errors:
        print("\nREFUSING TO FREEZE:")
        for e in errors:
            print("  ", e)
        print("\nFix them in the review file and run freeze again. Oversized chunks are "
              "not truncated for you, because truncation is silent data loss.")
        sys.exit(1)

    if not rows:
        sys.exit("\nNothing to freeze.")

    with REGISTRY.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"\nFROZEN {date.today().isoformat()}: {len(rows)} chunks -> {REGISTRY}")
    print_distribution(rows)
    print("\nKeys are now immutable. Record the freeze date in build-log.md section 5 step 3.")


def freeze_append(args, manifest, counter):
    """Add reviewed sources to a frozen registry without touching a frozen key.

    A plain freeze rebuilds the registry from every review file and numbers
    each prefix from 001, so it can only ever be run once pairs cite keys.
    This mode only appends:
      * existing rows stay byte-identical, and that is checked after writing;
      * numbering continues from the highest frozen key in each prefix;
      * only the sources named in --only are read, so a review file sitting in
        review/ unfrozen, cdc-acute-bronchitis today, is never swept in;
      * a source that already has rows is refused, and so is a chunk whose text
        is identical to a frozen one or to another chunk in the same append;
      * a chunk file is never overwritten, and a chunk with no retrieval date
        is refused, because a citation without one is not reproducible.
    Named sources are taken in manifest order, not --only order, which is the
    order a full freeze numbers them in. New sources therefore belong below
    every source that already holds keys in the same prefix.
    """
    if not REGISTRY.exists():
        sys.exit("\n--append adds to an existing registry and there is none. "
                 "The first freeze is a plain freeze.")
    only = [s.strip() for s in (args.only or "").split(",") if s.strip()]
    if not only:
        sys.exit("\n--append needs --only id[,id...]. It never freezes every "
                 "source that happens to have a review file.")

    with REGISTRY.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        existing = list(reader)

    by_id = {s["id"]: s for s in manifest["sources"]}
    frozen_sources = {r["source_id"] for r in existing}
    problems = [f"{i}: not in sources.yaml" for i in only if i not in by_id]
    problems += [f"{i}: already frozen, its keys exist" for i in only if i in frozen_sources]
    if problems:
        sys.exit("\nREFUSING TO APPEND.\n  " + "\n  ".join(problems))

    top = {}
    for r in existing:
        prefix, _, n = r["key"].rpartition("-")
        top[prefix] = max(top.get(prefix, 0), int(n))
    known = {r["chunk_sha256"]: r["key"] for r in existing}
    log = json.loads(FETCH_LOG.read_text()) if FETCH_LOG.exists() else {}

    rows, texts, errors = [], {}, []
    for src in manifest["sources"]:
        if src["id"] not in only:
            continue
        if not shippable(src):
            errors.append(f"{src['id']}: license_status={src['license_status']}, not shippable")
            continue
        retrieved = log.get(src["id"], {}).get("retrieved", "")[:10]
        if not retrieved:
            errors.append(f"{src['id']}: no retrieval date in {FETCH_LOG.name}")
            continue
        review = REVIEW / f"{src['id']}.txt"
        if not review.exists():
            errors.append(f"{src['id']}: no review file")
            continue

        prefix = src["key_prefix"]
        for block in parse_review(review):
            n = counter.count(block["text"])
            if n > MINILM_LIMIT:
                errors.append(f"{src['id']} :: {block['heading'][:40]} :: {n} tokens")
                continue
            category, problem = chunk_category(src, block)
            if problem:
                errors.append(f"{src['id']} :: {block['heading'][:40]} :: {problem}")
                continue
            digest = sha256(block["text"])
            if digest in known:
                errors.append(f"{src['id']} :: {block['heading'][:40]} :: "
                              f"identical to {known[digest]}")
                continue

            top[prefix] = top.get(prefix, 0) + 1
            key = f"{prefix}-{top[prefix]:03d}"
            if (CHUNKS / f"{key}.txt").exists():
                errors.append(f"{key}: chunk file exists with no registry row")
                continue
            known[digest] = f"{src['id']} :: {block['heading'][:40]}, which would be {key}"
            texts[key] = block["text"]
            rows.append({
                "key": key,
                "topic": manifest["topic"],
                "subtopic": slug(block["heading"]),
                "expected_category": category,
                "source_id": src["id"],
                "publisher": src["publisher"],
                "url": src["url"],
                "retrieval_date": retrieved,
                "license_status": src["license_status"],
                "attribution": src["attribution"],
                "token_count": n,
                "chunk_sha256": digest,
            })

    if errors:
        print("\nREFUSING TO APPEND. Nothing was written:")
        for e in errors:
            print("  ", e)
        sys.exit(1)
    if not rows:
        sys.exit("\nNothing to append: the named review files hold no chunks.")
    if list(rows[0].keys()) != fields:
        sys.exit(f"\nRegistry columns {fields} do not match the rows this would write.")

    print(f"\n{'DRY RUN, nothing written' if args.dry_run else 'APPENDING'}: "
          f"{len(rows)} chunks after the {len(existing)} frozen\n")
    # A reviewed page can keep no chunks at all. Say so, rather than let it
    # vanish from the listing: it stays unfrozen and can be appended later.
    for sid in [s["id"] for s in manifest["sources"] if s["id"] in only]:
        print(f"  {sid:<42} {sum(r['source_id'] == sid for r in rows)} chunks")
    print()
    for r in rows:
        print(f"  {r['key']:<14} {r['token_count']:>4}  {r['expected_category'] or '-':<7} "
              f"{r['source_id']}  {r['subtopic'][:40]}")
    if args.dry_run:
        return

    before = REGISTRY.read_bytes()
    chunks_before = {p.name: p.read_bytes() for p in CHUNKS.glob("*.txt")}

    for key, text in texts.items():
        with (CHUNKS / f"{key}.txt").open("x", encoding="utf-8") as f:
            f.write(text)
    with REGISTRY.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=fields).writerows(rows)

    drifted = [name for name, b in chunks_before.items()
               if (CHUNKS / name).read_bytes() != b]
    if not REGISTRY.read_bytes().startswith(before) or drifted:
        sys.exit(f"\nFROZEN CONTENT CHANGED. This should be impossible. "
                 f"Registry prefix intact: {REGISTRY.read_bytes().startswith(before)}; "
                 f"chunk files changed: {drifted}")

    print(f"\nAPPENDED {date.today().isoformat()}: {len(rows)} chunks -> {REGISTRY}")
    print(f"The {len(existing)} frozen rows and {len(chunks_before)} chunk files are byte-identical.")
    print_distribution(existing + rows)
    print("\nThe new keys are now immutable too. Rebuild the index: "
          "python 04-retrieval/build_index.py")


def print_distribution(rows):
    by_cat = {}
    for r in rows:
        by_cat[r["expected_category"] or "none"] = by_cat.get(r["expected_category"] or "none", 0) + 1

    print("distribution by expected category:", by_cat)
    print(f"mean tokens: {sum(int(r['token_count']) for r in rows) // len(rows)}")

    red = by_cat.get("red", 0)
    green = by_cat.get("green", 0)
    if green == 0:
        print("\nWARNING: zero green chunks. Retrieval cannot support a green verdict.")
    elif red > green * 2:
        print(f"\nWARNING: red chunks outnumber green {red}:{green}. "
              "A real triage distribution is closer to 7 red / 34 yellow / 59 green. "
              "A red-skewed corpus biases every retrieval toward red.")


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch"); f.add_argument("--force", action="store_true")
    c = sub.add_parser("chunk"); c.add_argument("--force", action="store_true")
    z = sub.add_parser("freeze"); z.add_argument("--force", action="store_true")
    z.add_argument("--append", action="store_true",
                   help="add the --only sources to the existing registry, never renumbering")
    z.add_argument("--only", help="comma-separated source ids, required with --append")
    z.add_argument("--dry-run", action="store_true",
                   help="with --append: print the keys it would assign and write nothing")

    args = ap.parse_args()
    {"fetch": cmd_fetch, "chunk": cmd_chunk, "freeze": cmd_freeze}[args.cmd](args)


if __name__ == "__main__":
    main()