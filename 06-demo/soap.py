"""A SOAP note from a saved assessment, as plain text.

READS ONLY. It never calls the model, never retrieves, and never touches the
triage path. Everything here comes out of the saved JSON under
`06-demo/data/conversations/` and the frozen registry, so regenerating a note
gives the same text apart from its "generated" line.

THE AUDIT TRAIL IS THE POINT. Whatever a guard dropped is written into O with
its reason, never silently omitted: a clinician has to be able to see what the
system removed as well as what it kept, and a shorter list with no note is
indistinguishable from a model that said less. The same discipline as the
screen otherwise: every clinical claim carries its citation key, and the app's
own words are labelled as the app's, because they have no source to cite.

Layout, as the four sections ask for:
  S  the case text: profile, timeline and symptoms, in the patient's own words
  O  what the system observed: the chunks it retrieved with their keys, the
     escalation rules that fired, and everything the guards dropped, with why
  A  the urgency SHOWN, the rationale if it survived the raise, red flags, and
     the citations behind them
  P  the next steps as shown, and the follow-up questions
"""

import hashlib
import json
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (REPO / "02-pairs", REPO / "04-retrieval"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

WIDTH = 78

# Viraj's copy. The source of truth is DISPOSITION in static/js/answer.js: a
# note and a screen must not word the same verdict differently.
DISPOSITION = {"red": "Call emergency services now",
               "yellow": "Be seen today",
               "green": "Self-care, and the signs that change the answer"}

# What each removal means, in the words the screen uses for the same tag.
WHY = {"next_steps": "medication instruction (constraint 12)",
       "follow_up_questions": "no questions on a red (constraint 4)",
       "citations": "not in the source registry (constraint 9)"}


def _wrap(text, indent="   ", first=None):
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    return textwrap.fill(text, width=WIDTH, initial_indent=first if first is not None else indent,
                         subsequent_indent=indent)


def _source_line(meta):
    meta = meta or {}
    who = str(meta.get("attribution") or meta.get("publisher") or "?")
    return f"{re.sub(r'^\s*Source:\s*', '', who)}  retrieved {meta.get('retrieval_date') or '?'}"


def _when(stamp):
    """2026-09-19T21:14:54Z -> 21:14 UTC. Times are UTC so a note read on
    another machine is not off by an hour."""
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).strftime("%H:%M UTC")
    except ValueError:
        return str(stamp or "")


def version_info(llama_url=None, timeout=2):
    """Model, corpus and prompt identity for the header. Never raises: an
    unknown field says so rather than guessing, because a note that names the
    wrong model is worse than one that admits it could not ask."""
    out = {"model": "unknown, llama-server did not answer", "build": "",
           "corpus": "unknown", "prompt": "unknown"}
    try:
        from pair_format import REGISTRY, SYSTEM_PROMPT
        rows = REGISTRY.read_text(encoding="utf-8")
        sha = hashlib.sha256(rows.encode("utf-8")).hexdigest()[:12]
        keys = sum(1 for line in rows.splitlines()[1:] if line.strip())
        out["corpus"] = f"{keys} chunks, {REGISTRY.relative_to(REPO)} sha256 {sha}"
        out["prompt"] = (f"02-pairs/system_prompt.txt sha256 "
                         f"{hashlib.sha256(SYSTEM_PROMPT.encode('utf-8')).hexdigest()[:12]}, "
                         f"{len(SYSTEM_PROMPT)} chars")
    except Exception as e:                                  # noqa: BLE001
        out["corpus"] = f"unknown: {e}"
    if llama_url:
        try:
            with urlopen(llama_url.rstrip("/") + "/props", timeout=timeout) as r:
                props = json.load(r)
            out["model"] = Path(str(props.get("model_path") or "?")).name
            out["build"] = str(props.get("build_info") or "")
        except Exception:                                   # noqa: BLE001
            pass
    return out


def _header(conv, version, now):
    who = " and ".join(s["profile"]["label"] for s in conv["sides"])
    lines = [
        "SOAP NOTE, GENERATED OFFLINE BY AN EXPERIMENTAL SYSTEM",
        "=" * WIDTH,
        _wrap("NOT A CLINICAL RECORD. No clinician has reviewed this. The urgency "
              "was produced by a small language model running on the machine that "
              "wrote this note, with "
              "no internet, constrained by app-side guards, from a corpus of public "
              "government pages about chest pain and nothing else. Anything outside "
              "that subject is refused rather than answered.", indent=""),
        "",
        f"Assessment   {conv['id']}, {conv.get('mode', 'single')}, for {who}",
        f"Generated    {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Started      {str(conv.get('created', ''))[:10]} {_when(conv.get('created'))}",
        f"Model        {version.get('model')}"
        + (f", llama.cpp {version['build']}" if version.get("build") else ""),
        "             CPU, reasoning off, schema-constrained output, no network",
        f"Corpus       {version.get('corpus')}",
        f"Prompt       {version.get('prompt')}",
    ]
    return lines


def _profile_line(p):
    bits = []
    if p.get("age") is not None:
        bits.append(f"age {p['age']}")
    if p.get("sex"):
        bits.append(str(p["sex"]))
    for field, label in (("conditions", "conditions"), ("medications", "medications")):
        if p.get(field):
            bits.append(f"{label} {', '.join(p[field])}")
    s = p.get("surgery") or {}
    if s.get("what"):
        bits.append(f"surgery {s['what']}, {s.get('weeks_ago', '?')} weeks ago")
    return "; ".join(bits) or "no profile facts recorded"


def _subjective(side):
    out = ["S  SUBJECTIVE", "   The patient's own words, in the order they were given."]
    turns = side.get("turns") or []
    if not turns:
        out.append("   Nothing was recorded for this person.")
    for t in turns:
        tag = "first" if t["n"] == 1 else f"follow-up {t['n'] - 1}"
        out.append("")
        out.append(_wrap(f'"{" ".join(str(t.get("text") or "").split())}"',
                         indent="      ", first=f"   {_when(t.get('at'))}  {tag}: "))
        if t.get("timeline"):
            out.append(_wrap(t["timeline"], indent="         ", first="      Timeline: "))
        # SPOKEN OR TYPED. A clinician reading quoted words is entitled to know
        # a machine heard them, and whether the patient corrected it. Decided
        # server-side in voice.provenance by comparing what arrived against what
        # was transcribed, so this is a fact rather than the page's claim. The
        # transcript is shown whenever it differs from the words that were sent.
        h = t.get("heard")
        if h:
            out.append(_wrap(
                f"spoken, not typed. Transcribed on this machine by whisper.cpp "
                f"{h.get('model')} in {h.get('ms', 0) / 1000:.1f} s from "
                f"{h.get('seconds')} s of speech, then "
                + ("CORRECTED by the patient before sending."
                   if h.get("edited") else "sent unchanged."),
                indent="         ", first="      Source: "))
            if h.get("edited") and h.get("heard"):
                out.append(_wrap(f'"{h["heard"]}"', indent="         ",
                                 first="      Heard as: "))
    out.append("")
    out.append("   Profile, as the model read it:")
    for line in str(side.get("profile_text") or "").splitlines():
        out.append(f"      {line}")
    return out


def _removals(t, chunk_meta):
    """Every guard removal on one turn, with its reason. Constraint 16's two
    replacements say so explicitly, because the answer above them changed."""
    ev = t.get("event") or {}
    dropped = ev.get("dropped") or {}
    raised = (ev.get("escalation") or {}).get("original")
    rows = []
    for entry in dropped.get("red_flags") or []:
        text = entry.get("entry") if isinstance(entry, dict) else entry
        why = entry.get("why") if isinstance(entry, dict) else "not grounded in the case text"
        rows.append(("red flag", text, f"{why} (constraint 11)"))
    for field in ("next_steps", "follow_up_questions", "citations"):
        for entry in dropped.get(field) or []:
            rows.append((field.replace("_", " ").rstrip("s"), entry, WHY[field]))
    for entry in dropped.get("next_steps_urgency") or []:
        rows.append(("next step", entry,
                     f"written for the model's {raised}, and a rule raised the verdict "
                     f"(constraint 16); replaced by the app's own steps, see P"))
    if dropped.get("rationale_urgency"):
        rows.append(("rationale", dropped["rationale_urgency"],
                     f"written for the model's {raised}, and a rule raised the verdict "
                     f"(constraint 16); not replaced, see the rule in O"))
    gone = {str(x) for _, x, _ in rows}
    for entry in (ev.get("flagged") or {}).get("next_steps") or []:
        if str(entry) not in gone:      # a step another guard dropped is not kept
            rows.append(("KEPT next step, flagged for a human", entry,
                         "a prohibition, not a dose (constraint 12)"))
    return rows


def _objective(side, chunk_meta):
    out = ["O  OBJECTIVE", "   What the system did, and what it removed."]
    anchor = side.get("anchor") or {}
    keys = anchor.get("keys") or []
    out.append("")
    if keys:
        out.append(_wrap(f"Retrieved on the first turn, {len(keys)} chunks, "
                         f"{anchor.get('tokens', '?')} tokens, reused unchanged on every "
                         f"follow-up, with no re-retrieval:", first="   "))
        for k in keys:
            meta = chunk_meta(k) or {}
            out.append(f"      {k}  {_source_line(meta)}")
            if meta.get("url"):
                out.append(f"         {meta['url']}")
    else:
        out.append("   Nothing was retrieved: the assessment was refused before that.")

    for t in side.get("turns") or []:
        ev = t.get("event") or {}
        esc = ev.get("escalation") or {}
        fired = esc.get("fired") or []
        rows = _removals(t, chunk_meta)
        head = f"   Turn {t['n']} ({_when(t.get('at'))})"
        if t.get("kind") == "refused":
            out += ["", f"{head}: REFUSED, no verdict given.",
                    _wrap(ev.get("reason") or "?", indent="         ", first="      Reason: "),
                    _wrap(ev.get("message") or "", indent="         ",
                          first="      Shown to the patient: ")]
            continue
        if not fired and not rows:
            out += ["", f"{head}: no rule fired, nothing removed."]
            continue
        out += ["", f"{head}:"]
        for f in fired:
            verb = {"raised": f"RAISED {esc.get('original')} to {esc.get('final')}",
                    "supports": f"supports this {esc.get('final')}",
                    "at_least": f"supports at least {f.get('cap')}",
                    "flag": "flag only, no change"}.get(f.get("status"), f.get("status"))
            out.append(_wrap(f"{verb}. Profile fact: {f.get('fact')}. "
                             f"In the case text: {f.get('symptom')}.",
                             indent="         ", first=f"      Rule {f['rule']}: "))
            for key, quote in (f.get("quotes") or [[k, f.get("quote")] for k in f.get("keys") or []]):
                out.append(_wrap(f'"{quote}"', indent="            ", first=f"         {key}: "))
        for kind, text, why in rows:
            label = kind if kind.startswith("KEPT") else f"Removed {kind}"
            out.append(_wrap(f'"{" ".join(str(text).split())}"',
                             indent="            ", first=f"      {label}: "))
            out.append(_wrap(why, indent="            ", first="         why: "))
    return out


def _last_answer(side):
    for t in reversed(side.get("turns") or []):
        if t.get("kind") in ("result", "refused"):
            return t
    return None


def _assessment(side, chunk_meta):
    out = ["A  ASSESSMENT"]
    t = _last_answer(side)
    if t is None:
        return out + ["   No answer was recorded."]
    ev = t.get("event") or {}
    if t.get("kind") == "refused":
        return out + [
            "   No triage category was given. The system refused this as outside",
            "   what it covers, and withheld the verdict the model produced"
            + (f" ({ev['urgency_withheld']})." if ev.get("urgency_withheld") else "."),
            _wrap(ev.get("reason") or "?", indent="      ", first="   Reason: ")]

    r = ev.get("result") or {}
    esc = ev.get("escalation") or {}
    u = str(r.get("urgency") or "?")
    out.append(f"   Urgency shown: {u.upper()} (WHO Interagency Integrated Triage Tool).")
    out.append(f"   Disposition: {DISPOSITION.get(u, '?')}. The app's words, not the model's.")
    if esc.get("changed"):
        rules = ", ".join(f["rule"] for f in esc.get("fired") or [] if f.get("status") == "raised")
        out.append(_wrap(f"The model gave {esc.get('original')}. Profile rule {rules} raised it to "
                         f"{esc.get('final')}; the rule and its source line are in O.", first="   "))
    if ev.get("ungrounded"):
        out.append("")
        out.append(_wrap(f"NOT GROUNDED: {(ev['ungrounded'] or {}).get('note') or ''}", first="   "))
        out.append(_wrap("Only the urgency is shown. The rationale, red flags and steps the "
                         "model wrote were withheld, because none of them is grounded in a source.",
                         first="   "))
    out.append("")
    if r.get("rationale"):
        out.append("   Rationale, the model's own words:")
        out.append(_wrap(r["rationale"], indent="      "))
    elif (ev.get("dropped") or {}).get("rationale_urgency"):
        out.append(_wrap(f"Rationale: withheld. The model wrote it for its own "
                         f"{esc.get('original')} and a rule raised the verdict, so it argues "
                         f"against the urgency above. It is quoted in full in O.", first="   "))
    else:
        out.append("   Rationale: none recorded.")
    out.append("")
    flags = r.get("red_flags") or []
    if flags:
        out.append("   Red flags, as stated by the model and kept by the grounding guard:")
        for f in flags:
            out.append(_wrap(f, indent="         ", first="      - "))
    else:
        out.append("   Red flags: none stated.")
    out.append("")
    cites = ev.get("citations") or []
    if cites:
        out.append("   Citations behind this answer. Every key resolves in the registry:")
        for c in cites:
            out.append(f"      {c.get('key')}  {_source_line(c)}")
            if c.get("url"):
                out.append(f"         {c['url']}")
    else:
        out.append("   Citations: none. Nothing in this answer is grounded in a source.")
    earlier = [t2 for t2 in side.get("turns") or [] if t2.get("kind") == "result"][:-1]
    if earlier:
        seq = ", ".join(f"turn {t2['n']} "
                        f"{((t2.get('event') or {}).get('result') or {}).get('urgency', '?')}"
                        for t2 in earlier)
        out += ["", _wrap(f"Earlier turns in this assessment: {seq}.", first="   ")]
    return out


def _plan(side):
    out = ["P  PLAN"]
    t = _last_answer(side)
    if t is None or t.get("kind") != "result":
        return out + ["   None. No verdict was given, so the system gave no steps.",
                      "   The refusal message it showed is in O."]
    ev = t.get("event") or {}
    r = ev.get("result") or {}
    if ev.get("ungrounded"):
        out.append("   Withheld with the rest of the answer: see A. Only the urgency and its")
        out.append("   disposition were shown to the patient.")
        return out
    steps = r.get("next_steps") or []
    replaced = bool((ev.get("dropped") or {}).get("next_steps_urgency"))
    if steps:
        out.append("   Next steps, as shown to the patient:")
        for i, s in enumerate(steps, 1):
            out.append(_wrap(s, indent="         ", first=f"      {i}. "))
        if replaced:
            out.append("")
            out.append(_wrap("These are the app's own steps, not the model's, because a profile "
                             "rule raised the verdict. They carry no citation for the same reason "
                             "the disposition does not. What the model wrote is in O.", first="   "))
    else:
        out.append("   Next steps: none given.")
    out.append("")
    qs = r.get("follow_up_questions") or []
    if qs:
        out.append("   Follow-up questions the system asked:")
        for q in qs:
            out.append(_wrap(q, indent="         ", first="      - "))
    elif ((ev.get("dropped") or {}).get("follow_up_questions")):
        out.append("   Follow-up questions: none. A red asks none, and the ones the model")
        out.append("   wrote are in O.")
    else:
        out.append("   Follow-up questions: none.")
    return out


def note(conv, chunk_meta, version=None, now=None):
    """The whole note, as plain text. One SOAP block per person, so a compare
    assessment gives two, each complete on its own."""
    version = version or {}
    now = now or datetime.now(timezone.utc)
    lines = _header(conv, version, now)
    for side in conv.get("sides") or []:
        p = side.get("profile") or {}
        lines += ["", "=" * WIDTH,
                  f"PATIENT  {p.get('label', '?')}",
                  _wrap(_profile_line(p), indent="         ", first="         "),
                  "=" * WIDTH, ""]
        lines += _subjective(side) + [""]
        lines += _objective(side, chunk_meta) + [""]
        lines += _assessment(side, chunk_meta) + [""]
        lines += _plan(side)
    lines += ["", "=" * WIDTH,
              _wrap("Everything above is read from the saved assessment. Citation keys resolve "
                    "in 01-data/citations.csv, whose sha256 is in the header. The system has no "
                    "knowledge outside that corpus, and this note is not a diagnosis.", indent="")]
    return "\n".join(lines).rstrip() + "\n"
