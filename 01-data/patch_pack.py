"""
PATCH for build_corpus.py

Problem: now that one-line <li> items survive extraction, a symptom list is a run
of short paragraphs. pack() is greedy and boundary-blind, so it will split a list
across two chunks whenever the budget runs out mid-run. That breaks hard
constraint 4: a red-flag list must never be split across two chunks, because the
citation stops resolving to the whole finding.

Fix: tag each item with its source element kind, then treat a contiguous run of
list items under one heading as a single atomic unit. A run either fits in the
current chunk or starts a new one. It is never cut in half. A run that exceeds
the ceiling on its own is surfaced as OVER for a human to split deliberately,
which is the only safe way to split a clinical list.

Two functions change. Everything else stays as is, including the nav-detection
rule that replaced the length cutoff.
"""

# ---------------------------------------------------------------------------
# REPLACE extract_main
# ---------------------------------------------------------------------------
# Only the return shape changes: items become (kind, text) instead of bare text.
# KEEP whatever nav-detection logic is currently filtering <li>. It slots into
# the marked line below unchanged.

def extract_main(html: str, selectors) -> "list[tuple[str, list[tuple[str, str]]]]":
    """Return [(heading, [(kind, text), ...]), ...] where kind is 'p' or 'li'."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "form", "aside"]):
        tag.decompose()

    root = None
    for sel in (selectors or []):
        found = soup.select_one(sel)
        if found:
            root = found
            break
    root = root or soup.body or soup

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
            if is_nav_item(el, text):      # <-- your existing nav check goes here
                continue
            buf.append(("li", text))
        else:
            if len(text) > 25:
                buf.append(("p", text))

    if buf:
        sections.append((heading, buf))
    return sections


# ---------------------------------------------------------------------------
# REPLACE pack
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CALLER CHANGE in cmd_chunk
# ---------------------------------------------------------------------------
# extract_main now yields (kind, text) tuples, so the loop variable name is the
# only thing that changes. pack() handles the rest.
#
#     for heading, items in sections:
#         for group in pack(items, counter):
#             body = "\n\n".join(group)
#
# Note the join stays "\n\n" between units. Items inside a run are joined with a
# single "\n" in pack(), which keeps a symptom list reading as a list rather than
# as a wall of one-line paragraphs.
