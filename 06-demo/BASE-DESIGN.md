# Base dashboard: design spec

For the instance building the base device. **Implement from this; do not design.**
Every token, shape and rule here already exists in `06-demo/DESIGN.md` and
`06-demo/static/app.css`. Where this spec adds something, it says so and says why.

Written 2026-09-20. Nothing in this file has been built.

---

## 0. What this screen is for

One person, at a clinic, deciding **who to follow up**. They did not do the
assessments. They are reading someone else's caseload, after the fact, and the
only question that matters is *which of these needs me now*.

So the screen leads with what needs a decision, not with volume. Everything
else on it exists to let the supervisor decide without opening the assessment,
and to make opening it one tap when they must.

**It is not a dashboard of charts.** No graphs, no donuts, no sparklines, no
card grid. `DESIGN.md` forbids the card grid outright, and a chart of five
assessments is decoration. This is a **register**: a tally line and a table.

---

## 1. What it reuses, and the one rule it extends

**Reuses unchanged:** every token in `:root`, the `.mk` triage mark, `.page.wide`
(72rem, as the People pages use), the sidebar and top bar, the segmented
control, the button set, the tag shapes, `h2` day headings, the drawn icon set,
the hairline rhythm.

**THE ONE SATURATED FIELD RULE IS EXTENDED, DELIBERATELY.** DESIGN.md says the
urgency bar is the only saturated field, and that "the small red and yellow
marks in the history list are the single allowed exception, because they index
past bars." **A dashboard row indexes a past bar in exactly the same way**, so
`.mk` is allowed here on the same grounds and for the same reason. Nothing else
on this screen may carry a triage colour: not a row background, not a count, not
a border, not a tag. **Viraj approved this extension on 2026-09-20 and DESIGN.md
now carries it**, in the rule itself and in the matching Don't.

**No zebra striping.** The tone system is paper, chrome, well and nothing else,
and a striped row would be a fourth tone. Rows are separated by hairlines and
lift to `--well` on hover, the same as `.hist-row`.

---

## 2. Data this needs

Everything below derives from what an assessment already carries, except four
fields the sync must add. Named here so they are not invented twice.

| field | shape | from |
|---|---|---|
| `device` | `{id, label}` | the sync. `label` is what a person named the handset. |
| `worker` | string or null | the sync, if it carries one. Null renders as nothing, not "Unknown". |
| `synced_at` | ISO 8601 | the sync |
| `reviewed` | `{at, by}` or null | set on this device by **Mark reviewed** |

Derived, no new storage: `urgency` and `ungrounded` from `side_state`, the
guard removal count from `event.dropped`, whether a profile rule fired from
`event.escalation`, `turns` and `title` from `summary()`.

### What "outstanding" means

**Outstanding = the assessment needs a human decision and has not had one.**
A single rule, so the count is never arguable:

An assessment is outstanding when `reviewed` is null **and any of**:

1. the shown urgency is **red**, including a red a profile rule raised and a red
   that rendered not-grounded;
2. the shown urgency is **yellow**;
3. it was **refused** (out of scope, not assessed, who is this for) — the system
   declined, so a person has to;
4. **a guard removed anything**, at any urgency, because the worker was shown a
   modified answer.

A **green with a clean run is not outstanding** and never enters the top
section. It is still in the register and still openable.

Marking reviewed never changes the verdict, the assessment or the SOAP note. It
records that someone looked.

---

## 3. Layout

`.page.wide` (72rem), inside the existing sidebar and top bar. Route `/base`.

```
┌ page.wide ───────────────────────────────────────────────────────┐
│  Caseload                                    [ Today | All ]     │  h1 + segmented
│  hairline                                                        │
│  12 assessed · 3 red · 5 need review · synced 14:02 from 2 devices│  tally line
│  hairline                                                        │
│                                                                  │
│  Needs review  5                                                 │  h2
│  ┌──┬──────────────────┬────────────┬────────┬─────┬──────────┐  │
│  │  │ Assessment       │ Attention  │ From   │When │          │  │  sticky head
│  ├──┼──────────────────┼────────────┼────────┼─────┼──────────┤  │
│  │R │ Heavy pressure…  │ not ground.│ Handset│14:02│ Mark     │  │
│  │  │ Mum · 62 · F     │ 2 removed  │ Asha   │     │ reviewed │  │
│  └──┴──────────────────┴────────────┴────────┴─────┴──────────┘  │
│                                                                  │
│  Reviewed  7                                                     │  h2
│  … same table, quieter …                                         │
└──────────────────────────────────────────────────────────────────┘
```

**From 60rem:** the table above.
**Below 60rem:** no table. Stacked record rows in the `.hist-row` grammar
(section 6). A squeezed six-column table on a phone is unreadable and the house
already has a list form for exactly this content.

Column widths from 60rem, in a fixed grid so rows align:

| col | width | header |
|---|---|---|
| mark | `1.75rem` | none (empty `th`, `aria-label="Urgency"`) |
| assessment | `1fr` (min 0) | Assessment |
| attention | `13rem` | Attention |
| from | `9rem` | From |
| when | `5.5rem` | When |
| action | `8.5rem` | none (empty `th`) |

---

## 4. Components

### 4.1 Page head

- `h1.pg-h` "Caseload" — existing Headline, 700 / 1.5rem.
- A **segmented control**, right-aligned on the same line from 40rem, beneath it
  below that. **A joined pair only** — `Today` / `All` — because the documented
  component is a pair and three segments is a new component. Pressed half fills
  with ink, per the Ink Selects Rule. Default `Today`.

### 4.2 Tally line

One line, hairline above and below. **Not four boxes and not a card grid.**

```
12 assessed · 3 red · 5 need review · synced 14:02 from 2 devices
```

- Figures at **700, `--t-20`, tabular figures**. Never 800: the Heavy Word Rule
  reserves that for the verdict word and the brand mark.
- Labels at 400, `--t-15`, `--ink-2`.
- Separated by the existing `·` dot in `--ink-3`.
- **"need review" is the only part in `--ink`**; the rest is `--ink-2`. That is
  how the important figure is marked, because a colour is not available to it.
- When the count is 0 it still renders, as `0 need review`. A figure that
  disappears cannot be trusted.
- `aria-live="polite"` on this line only, so a sync announces once rather than
  the whole table announcing.
- "synced 14:02 from 2 devices" is `--ink-2`; the time in mono, because it is a
  measurement. With no sync yet it reads `not synced yet`.

### 4.3 Table

Real `<table>` markup with `<th scope="col">`. It is tabular data; a div grid
would lose the row and column semantics a screen reader needs.

- **Header:** `--chrome` fill, sticky under the top bar, hairline beneath, labels
  600 / `--t-14` / `--ink-2`. Square, not rounded: it is chrome around records.
- **Row:** min-height `--tap` (2.75rem), padding `.5rem .625rem`, hairline between
  rows, hover `--well`. Square. No shadow, per the Only Overlays Cast Shadows Rule.
- **Reviewed rows** sit in the second section and set the assessment title to
  `--ink-2` instead of `--ink`. Nothing else dims: the mark, the attention tags
  and the device stay at full strength, because a supervisor re-reading a
  reviewed row needs the same facts.

### 4.4 Cells

**Mark.** The existing `.mk`, 1.5rem square, `R` / `Y` / `G`, or `.mk.hold` with
the drawn no-entry icon for a refusal. Add `title` and visually-hidden text with
the word, because the letter alone is not the verdict; DESIGN.md requires every
urgency to carry its word.

**Assessment.** Two lines.
- Line 1: the assessment title (what the person said), 600 / `--t-15`, clamped to
  two lines with the existing `-webkit-line-clamp` pattern. **This is the link**
  to `/c/<id>`, not the row (see 4.6).
- Line 2: meta, `--t-14` / `--ink-2`: the person's label, then age and sex when
  the profile has them, separated by `·`. A compare assessment shows both labels
  joined by "and", and a second `.mk` in the mark cell, stacked, exactly as the
  history list already does for a pair.

**Attention.** Zero to four tags, wrapping, using shapes that already exist. **No
triage colour.**

| condition | tag | shape |
|---|---|---|
| rendered not-grounded | `not grounded` | 1.5px dashed `--hold` border, `--ink-2` text |
| refused | `refused` | hatched hold tag, as the Under 16 tag |
| a profile rule raised it | `raised to red` / `raised to yellow` | 1px `--rule-2` box, `--ink-2` |
| guards removed n things | `n removed` | the existing removed tag, 3px, `--ink-3` |
| follow-ups were available and unused | `no follow-up` | 1px `--rule-2` box, `--ink-3` |

Nothing to say renders an em-dash in `--ink-3`, not an empty cell, so the column
never looks broken.

**From.** Two lines. Device label 600 / `--t-14` in **mono** — it is an
identifier, and the Mono Means Data Rule covers it. Worker name beneath, 400 /
`--t-14` / `--ink-2`, in the body face, because a person's name is not data.
Worker absent: the line is omitted, never filled with "Unknown".

**When.** The time, mono, tabular, `--t-14`. Today shows `14:02`. Anything older
shows `19 Sep` above `14:02` on two lines. Full ISO timestamp in `title`.

**Action.** A **Quiet button** (no border or fill, `--ink-2`, hover inks and fills
with well) reading `Mark reviewed`, full width of its cell, `--tap` high. Once
reviewed the cell shows `Reviewed 14:02` in `--t-14` / `--ink-3` with the check
icon, and no control. **Reviewing is not undoable from this screen in v1**; say
so nowhere, just do not offer it, and add it when someone asks.

### 4.5 Sections and order

Two `h2` headings, styled as the existing history `h2` (700 / `--t-14` /
`--ink-2`): `Needs review` and `Reviewed`, each followed by its count in
`--ink-3`.

Within **Needs review**, fixed order, not sortable in v1: **red, then refused,
then yellow, then green-with-removals**, and newest first inside each band. A
supervisor reads top to bottom and stops when they run out of time, so the order
has to be the priority order.

Within **Reviewed**, newest first, grouped by day with the existing day `h2`
("Today", "Yesterday", then the date) when the window is `All`.

**Columns are not sortable and there are no filters beyond Today/All.** Say it
by omission. Sorting a five-row register is a feature nobody asked for.

### 4.6 The nested-control problem, solved explicitly

**The row is not a link.** The assessment title is an `<a>` to `/c/<id>`; the
action cell holds a `<button>`. A row that is an anchor with a button inside it
is invalid and unusable by keyboard. Hovering anywhere on the row still fills it
with `--well`, so it reads as one target even though it is two.

### 4.7 New arrivals never move a row under the reader

When a sync brings new assessments while the screen is open, **do not insert
them**. Show a single full-width quiet bar above the first section:

> `3 new since you opened this` — with a `Show` text action in the action blue.

Rows merge only when it is pressed. A supervisor reaching for **Mark reviewed**
must not have the table reorder under their finger. This is the same instinct as
the composer disabling send while a turn runs.

---

## 5. Empty states

Four, and they are different states, not one message. All copy below is
**surface copy for Viraj to put in his own voice**, per the house convention.

**No device has ever synced.** The primary case on a fresh base device.
> **No device has synced to this one yet.**
> A handset syncs its caseload when it is back in range. Assessments appear here
> when it does.

**Devices have synced, nothing in the window.** With `Today` selected:
> **Nothing assessed today.**
> The last sync was 19 Sep at 16:40, from Handset A. Choose All to see earlier
> assessments.

**Nothing outstanding.** The good case, and it should read as finished rather
than as empty. Replaces the `Needs review` table only; the `Reviewed` section
stays.
> **Nothing needs review.** All 12 assessments today have been looked at.

Render it in a `--well` panel with the existing check icon, **not** in green.
The No Fourth Colour Rule holds: completion is told by words and a check, not by
a triage colour.

**Nothing reviewed yet.** The `Reviewed` section with an empty list simply does
not render its heading. An empty section heading is noise.

---

## 6. Below 60rem

The table is replaced, not squeezed. Each assessment is a record row on the
`.hist-row` grid: `1.375rem` mark column, `1fr` content, `.5rem` gap, hairline
between rows, hover `--well`.

```
┌────┬──────────────────────────────────────────┐
│ R  │ Heavy pressure in the middle of my chest │  600, 2-line clamp, the link
│    │ Mum · 62 · F · 14:02                     │  meta, ink-2
│    │ Handset A · Asha                         │  device mono, worker body
│    │ [not grounded] [2 removed]               │  tags, wrapping
│    ├──────────────────────────────────────────┤
│    │ Mark reviewed                            │  full-width quiet button, 2.75rem
└────┴──────────────────────────────────────────┘
```

- The tally line wraps to two lines and keeps its order.
- The segmented control goes full width under the `h1`.
- The sticky table header does not exist here; the `h2` section headings carry
  the structure instead.
- Nothing may overflow sideways at 390px. The existing check asserts this on
  other pages and should assert it here.

---

## 7. Accessibility and motion

- Real table semantics from 60rem; a list below it. Do not fake either.
- Every `.mk` carries the urgency word as visually-hidden text.
- `aria-live="polite"` on the tally line only.
- The new-arrivals bar is a `role="status"`.
- Focus: the existing 3px action outline offset 2px. Row hover is not focus.
- Contrast: every combination here is one the system already ships. `--ink-3` on
  `--paper` is used for tertiary text elsewhere and is not used for anything a
  supervisor must read to make a decision.
- No animation on the table. If a "developing" treatment is ever wanted on a new
  row, gate it behind `prefers-reduced-motion` like `.bar.develop`.

---

## 8. One new icon

The set has no device glyph. Draw it on the existing 24px grid, 1.75 stroke,
round caps and joins, `currentColor`, added to `icons.js` as `device`:

```js
device: '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M10.5 18.5h3"/>',
```

A handset outline with a speaker line. It appears in the tally line before the
device count and in the phone layout before the device name. **Nothing else new
is drawn.** `check`, `flag`, `alert`, `info`, `none` and `people` already cover
the rest.

---

## 9. What this spec deliberately leaves out

- **Charts of any kind.** Five assessments do not need a graph, and the card grid
  a chart would sit in is forbidden.
- **Per-worker or per-device performance.** A supervisor screen that ranks health
  workers is a different product with a different ethics problem, and nobody
  asked for it.
- **Undo on Mark reviewed.** Add it when someone asks for it.
- **Sortable columns and filters beyond Today/All.**
- **Editing an assessment from here.** The base reads the caseload; it does not
  rewrite what a worker was shown in the field.
- **Any change to the assessment page itself.** A row links to `/c/<id>`, which
  already renders the whole thing including the guards and the SOAP note.
