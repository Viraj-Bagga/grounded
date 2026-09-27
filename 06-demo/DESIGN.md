---
version: 1
name: Grounded, on paper
description: "The field app and base as built on 27 September 2026 (option B of ui-audit/overhaul.html). Warm white paper, charcoal ink, hairlines at most. Hierarchy comes from space, size and weight. The interface is monochrome: colour belongs to triage and to nothing else, and every verdict also says its word."

colors:
  paper: "#fbfbfa"
  chrome: "#f4f3f0"
  well: "#f0efeb"
  surface: "#ffffff"
  ink: "#1f2123"
  ink-2: "#4a4c4f"
  ink-3: "#646360"
  rule: "#e9e8e4"
  rule-2: "#dcdad4"
  edge: "#86847e"
  soft: "#ebeae5"
  red-ink: "#b3261e"
  red-dot: "#d33a2c"
  red-tint: "#fdebec"
  yellow-ink: "#7a5000"
  yellow-dot: "#e5a800"
  yellow-tint: "#fbf3db"
  green-ink: "#2f6b3a"
  green-dot: "#3f8f4e"
  green-tint: "#edf3ec"
  hold-ink: "#5f5e5b"
  hold-tint: "#efeeea"

typography:
  disposition:
    fontFamily: ui-serif, New York, Iowan Old Style, Georgia
    fontSize: 36px phone, 46px laptop, never more than 10% of the answer's width
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: -0.02em
  page-title:
    fontFamily: the serif
    fontSize: 26px phone, 32px laptop
    fontWeight: 500
  verdict-word:
    fontFamily: Atkinson Hyperlegible Next
    fontSize: 14px
    fontWeight: 700
    letterSpacing: 0.08em
    textTransform: uppercase
  step:
    fontSize: 17px phone, 19px laptop
    lineHeight: 1.45
  body:
    fontFamily: Atkinson Hyperlegible Next
    fontSize: 16px phone, 17px laptop
    lineHeight: 1.5
  label:
    fontSize: 16px
  meta:
    fontSize: 14px
  section-label:
    fontSize: 14px
    fontWeight: 500
    color: ink-3
  fine:
    fontSize: 12px
    use: counts, times, hashes and keys, in Atkinson Hyperlegible Mono

rounded:
  control: 8px
  panel: 12px
  pill: 999px
  dot: 50%

spacing:
  base: 4px
  gutter: 20px phone, 24px laptop
  between-parts-of-an-answer: 32px phone, 36px laptop
  between-turns: 48px phone, 56px laptop
  tap: 44px
---

# Grounded, on paper

Built 27 September 2026 from option B of `ui-audit/overhaul.html`, which Viraj
picked over a dark Linear-style option. It replaced the square, black-bordered
Carbon look (in git history before `33b2771`). Everything here is in
`06-demo/static/app.css` and `06-demo/base-static/base.css`, and the house
rules in `06-demo/CLAUDE.md` still hold.

## The rules

1. **Monochrome.** Ink on warm white. There is no accent colour: links, focus
   rings, the send button, selected rows and the microphone are ink. The old
   `--action` tokens still exist and are set to ink, so every rule that used
   them reads the same.
2. **Colour is triage and nothing else.** Red, yellow and green appear only in
   a verdict (its word, its dot and its tint) and in the history and register
   dots. A refusal, a not-grounded note, a guard removal and a rule line are
   never in a triage colour. `ui_check.mjs` fails the build if one is.
3. **Never colour alone.** Every verdict says its word: RED, YELLOW, GREEN,
   OUT OF SCOPE, NOT ASSESSED. Every dot carries its word in a title and in
   hidden text.
4. **Hierarchy from space, size and weight.** Hairlines (`rule`, 1px) at most.
   No heavy borders, no boxed buttons, no square number boxes, no drop shadows
   except the soft one under an open drawer or sheet.
5. **One glance.** The result reads verdict, then what to do; everything else
   is one tap away, closed.

## Type

Atkinson Hyperlegible Next for everything read, self-hosted in
`static/fonts`, because it tells I, l and 1 apart in a drug name or a key.
Its mono twin for counts, times, hashes and keys. The disposition and page
titles are the system serif (New York on Apple devices, Georgia elsewhere):
nothing to download, so the app stays offline. Base has no access to the field
app's font files and uses the system sans with the same serif.

Body is 16px on a phone. Nothing a person must read is under 14px except the
12px mono of counts. Fields are 16px or more so iOS never zooms.

## Colour

| token | value | use |
|---|---|---|
| paper | #fbfbfa | the page |
| chrome | #f4f3f0 | the sidebar |
| well | #f0efeb | quiet panels, chips, pills, the segmented control |
| surface | #ffffff | fields, region cards, the lifted segment |
| ink / ink-2 / ink-3 | #1f2123 / #4a4c4f / #646360 | text; ink-3 is 5.2:1 or better on every ground and tint |
| rule / rule-2 | #e9e8e4 / #dcdad4 | hairlines |
| edge | #86847e | a field's 1px edge, 3:1 or better against paper and sidebar (WCAG 1.4.11) |
| soft | #ebeae5 | hover and the row you are on |

Each verdict has three: an **ink** for its word (AA on its tint), a brighter
**dot**, and a pale **tint** behind the whole verdict. Red #b3261e / #d33a2c /
#fdebec; yellow #7a5000 / #e5a800 / #fbf3db; green #2f6b3a / #3f8f4e /
#edf3ec. A refusal is **hold**: #5f5e5b on #efeeea, with a ring instead of a
dot, so it cannot read as a fourth category.

## The result

Top to bottom:

1. **What was said**: who and when in small grey type, the words in ink-2 at
   18px. No panel.
2. **The verdict**: one 12px-radius tint panel. The word with its dot, then
   the disposition in the serif, then any rule line in words ("Raised to red:
   breast cancer on Aunt Sue's profile, with "Sharp" on "breathe"", or "Raised
   to red: the steps call for emergency care."). No rule number.
3. **What to do**: plain grey numerals in a column, no boxes. A step that only
   repeats the disposition is not shown again.
4. **Questions**, when there are any, each with a text-style Answer button.
5. **The guard line**, whenever a guard removed anything: "N items removed by
   safety checks". It opens to each removal, struck through, its reason under
   it.
6. **Closed rows**, hairline-separated, name on the left, preview beside it,
   a plus that turns to a cross: **Why** (first two lines; opened, the rule's
   quoted source line, the model's original reason struck out on a raise, red
   flags), **Sources** (publisher names; opened, each source is a row of
   publisher and the chunk's opening words that opens the chunk and its page),
   **Checked** (every measurement of the turn; opened, the full breakdown).
7. **Download the SOAP note**.

A refusal: the grey panel, the message at step size, and a closed Why row
previewing "No verdict: Grounded only covers chest pain." (a plain
out-of-scope refusal only).

## The sidebar

The name in the serif, New assessment as a quiet row with a plus, then one
line per assessment: a 7px dot per person (filled for a verdict, a ring for
none), the title in 14px regular ink-2, the time in 12px. The row you are on
is ink on `soft`. The foot links are quiet rows; the model status is a 6px
dot and one fine line.

## Controls

- **Primary button**: ink fill, white text, 8px radius.
- **Secondary button**: well fill, ink text, no border.
- **Text buttons** (Answer, Show, Try again in context): no fill until hover.
- **Fields**: white, 1px edge, 8px radius (12px for the composer), focus is a
  2px ink outline.
- **Segmented control**: a well with the chosen segment lifted onto white.
- **Chips and tags**: soft pills in `well`; Under 16 in the hold tint.
- **Sheets**: bottom sheet with 16px top corners on a phone, a right-hand
  panel on a laptop. The source sheet is titled by publisher, with the key and
  size beside it in mono.

## Motion

Only feedback on a state change: the verdict fades up 4px over 240ms, the
drawer slides, a fold's plus turns 45 degrees. Under prefers-reduced-motion
all of it lands at once.

## Checked by the suite

`node 06-demo/ui_check.mjs rules` audits every screen on phone and desktop:
44px targets, 16px fields, AA contrast, field edges, no sideways scroll, no
motion under reduce, no em dash, no rule number shown by default, triage
colours only in verdicts and dots, a word on every verdict and mark, refusals
grey, every citation a button with its key, every removal struck with a
reason.
