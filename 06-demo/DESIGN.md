---
name: Grounded
description: Offline chest pain triage, read like a health worker's handset, on Carbon's flat structure.
colors:
  paper: "#ffffff"
  chrome: "#f2f4f7"
  well: "#eaedf2"
  ink: "#0f1318"
  ink-hover: "#2b323b"
  ink-2: "#414a56"
  ink-3: "#5c6472"
  rule: "#dce0e6"
  rule-2: "#b9c0ca"
  edge: "#7b8490"
  action: "#1f3fbf"
  action-soft: "#e5eafa"
  selection: "#c7d2f4"
  red: "#c8261d"
  yellow: "#f2b705"
  on-yellow: "#101418"
  green: "#1c7a43"
  hold: "#56606c"
typography:
  verdict:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "3rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.01em"
  headline:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.3125rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  disposition:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.3125rem"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"kern\""
  field:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.35
  label:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.3
  meta:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  key:
    fontFamily: "Atkinson Mono, ui-monospace, SF Mono, Menlo, monospace"
    fontSize: "0.875rem"
    fontWeight: 700
    lineHeight: 1
  measure:
    fontFamily: "Atkinson Mono, ui-monospace, SF Mono, Menlo, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  none: "0"
spacing:
  xxs: "0.25rem"
  xs: "0.5rem"
  sm: "0.75rem"
  pad: "1rem"
  sec: "2rem"
  turn: "2.5rem"
  tap: "2.75rem"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "0 1rem"
    height: "2.75rem"
  button-primary-hover:
    backgroundColor: "{colors.ink-hover}"
  button-primary-disabled:
    backgroundColor: "{colors.rule-2}"
    textColor: "{colors.paper}"
  button-plain:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0 1rem"
    height: "2.75rem"
  button-plain-hover:
    backgroundColor: "{colors.well}"
  button-answer:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.action}"
    rounded: "{rounded.none}"
    padding: "0 0.75rem"
    height: "2.75rem"
  button-send:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    size: "2.75rem"
  source-key:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.action}"
    typography: "{typography.key}"
    rounded: "{rounded.none}"
    padding: "0 0.75rem"
    height: "2.75rem"
  input-field:
    backgroundColor: "{colors.chrome}"
    textColor: "{colors.ink}"
    typography: "{typography.field}"
    rounded: "{rounded.none}"
    padding: "0 0.75rem"
    height: "2.75rem"
  tab:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 1rem"
    height: "2.75rem"
  tab-selected:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
  switcher-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  step-numeral:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    size: "2.25rem"
  urgency-bar-red:
    backgroundColor: "{colors.red}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "1rem 1.5rem"
  urgency-bar-yellow:
    backgroundColor: "{colors.yellow}"
    textColor: "{colors.on-yellow}"
    rounded: "{rounded.none}"
    padding: "1rem 1.5rem"
  urgency-bar-green:
    backgroundColor: "{colors.green}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "1rem 1.5rem"
  urgency-bar-hold:
    backgroundColor: "{colors.hold}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "1rem 1.5rem"
  said-row:
    backgroundColor: "{colors.well}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "0.5rem 0.75rem"
---

# Design System: Grounded

## Overview

**Creative North Star: "The Health Worker's Handset"**

A triage conversation set in the grammar of a field worker's phone: numbered, bold, readable with one hand in bad light. The screen is paper white with a cool grey chrome layer around it and near-black ink on top. There is one action blue and it stays small. The only saturated field on any screen is the urgency bar, a square full-width band in a WHO triage colour with the category word in heavy type. Everything else that matters (a refusal, an answer that is not grounded, something a guard removed) is carried by form and by a word, never by a fourth colour: refusal is hatched, not-grounded is dashed, removed is struck through.

The reading order is the design. The person says what is happening, and it is kept as a plain record row, not a bubble. Four steps (Retrieve, Read, Write, Check) fill in while the model works. Then the urgency bar, with any profile rule lines pinned directly under it, then numbered steps in keypad squares, then why, then red flags, questions and sources. A single "Checked" line closes each answer and opens the measurements. Density is moderate: a 45rem reading column, 70ch prose, 44px tap targets.

The world refuses the chatbot bubble stack and the soft health-app card grid. There are no cards, no avatars, no gradients, no illustration, and no decorative colour.

### The structure is Carbon's

Adapted on 2026-09-27 from an analysis of IBM's Carbon Design System, kept whole in `CARBON-REFERENCE.md`. Viraj's call: structure only.

- **Taken:** flat square geometry (every corner is 0), 1px hairlines on controls, spacing on a 4px grid, filled fields with one rule along the bottom, line tabs, and the content switcher.
- **Not taken:** IBM Plex, IBM Blue as a button fill, light display weights, and Carbon's semantic colours. Atkinson Hyperlegible stays because it was chosen for low vision. Ink stays the colour of choosing. The verdict word stays at 800. The triage colours stay ours, because Carbon's green, `#24a148`, is 3.35:1 against white text and fails AA for the disposition line; ours, `#1c7a43`, is 5.37:1.

**Key Characteristics:**
- Paper, chrome and ink, with one action blue kept to links, source keys, raise icons, step progress and focus.
- Triage colour only in full-width square urgency bars, and in the small history and register marks.
- Refusal hatched, not-grounded dashed, removed struck through with a word tag saying why.
- Atkinson Hyperlegible Next for everything read; Atkinson Hyperlegible Mono for keys, timelines and measurements.
- Square everywhere. Controls on 1px hairlines; fields filled, with a bottom rule.
- Selection fills with ink, or underlines in ink, never blue.
- One drawn stroke icon set; no glyphs or emoji stand in for icons.

## Colors

A cool neutral paper-and-ink system with a single deep blue accent and three reserved triage colours that appear only as urgency fields.

### Primary
- **Signal Blue** (action): the one accent. Links, text actions ("Add when it started", "Change base address"), source key text on citation chips and in the source sheet header, the border and text of the Answer button, the raise arrow on a rule line that changed the verdict, the progress stripe on the working steps, and focus. It never fills a button or marks a selection.
- **Signal Blue Wash** (action-soft): the hover fill of the Answer button, the current row in the sidebar, and the saved-confirmation strip.
- **Selection** (selection): behind selected text only, a deeper wash so a selection can be seen on paper; ink on it is 12.38:1.

### Triage (reserved)
- **Emergency Red** (red, white text, 5.60:1): RED urgency bar.
- **Signal Yellow** (yellow, near-black on-yellow text, 10.17:1): YELLOW urgency bar.
- **Field Green** (green, white text, 5.37:1): GREEN urgency bar.
- **Hold Slate** (hold, white text under the hatch, 6.39:1): the no-verdict bars (OUT OF SCOPE, NOT ASSESSED, WHO IS THIS FOR?), the child note, the Under 16 tag. Its dashed form outlines the not-grounded note. Hold is a neutral and never reads as a fourth, milder verdict.

### Neutral
- **Paper** (paper): the conversation, forms, controls, the source sheet, and the text colour on red, green and hold bars. Also the fill of a field that sits on a well.
- **Cool Chrome** (chrome): sidebar, top bar, the profile preview panel, and the fill of every field on paper.
- **Record Well** (well): what the person said, quiet notices, raw model output, confirm panels, hover fill on quiet controls.
- **Ink** (ink): text, primary buttons, the send button, pressed halves of a switcher, the selected tab's rule, checked boxes, step numeral borders, the brand square and status lamp.
- **Ink Lifted** (ink-hover): hover on ink-filled buttons only.
- **Ink Second** (ink-2): secondary text, meta lines, timeline text, rule quotes, unselected tabs.
- **Ink Third** (ink-3): tertiary text, struck-through removed text, placeholder, rule ids, the "None" in an empty register cell.
- **Hairline** (rule): section dividers, the rule-line frame, the line under a tab row, top bar and composer borders.
- **Control Line** (rule-2): the 1px edge of citation chips and tokens; disabled fill. Never a field's edge: it is 1.83:1 on paper.
- **Field Edge** (edge): the bottom rule of every field. 3.79:1 on paper, 3.44:1 on chrome, 3.23:1 in a well.

### Named Rules
**The One Saturated Field Rule.** On any screen the urgency bar is the only saturated field. The small red and yellow marks in the history list and the base register are the single allowed exception, because they index past bars. Nothing else carries a triage colour, not a row fill, not a count, not a tag, not an error. On 2026-09-27 two places that broke it were put back to ink: a refused line in the send-to-base log was red text, and the caseload's remove button filled red on hover.

**The One Hidden-Text Class Rule.** Text that exists only for a screen reader uses **`.sr`**, in the field app and at base. There is no `.sr-only`: base briefly used that name and `app.css` ended up defining both, which is two names for one thing across 72 rendered places. Added 2026-09-20 after a read of the rendered HTML.

**The Announce The Outcome Rule.** Streaming is deliberately silent to assistive technology: announcing tokens reads a JSON document aloud a fragment at a time. Nothing is announced until an answer is complete, and then the outcome is announced once, through the single `#announce` live region, as the urgency word plus its disposition, because the colour is not available to a listener and "red" on its own is not an instruction. A refusal, an error and a "who is this for" question announce too.

**The Every Screen Has One h1 Rule.** Including the ones with no visible title. The new-assessment screen and an assessment are a composer and a conversation, so their `h1` is `.sr`: hidden, not absent. `aria-current="page"` marks the route you are on and is ABSENT elsewhere, never set to `"false"`.

**The Ink Selects Rule.** Primary buttons, send, the pressed half of a switcher, a checked box and the selected tab's rule are ink. Blue is for pointing at something (a link, a key, a focus), never for choosing.

**The No Fourth Colour Rule.** A refusal, the not-grounded note, rule lines and guard removals are never drawn in a triage colour. They are told apart by pattern (hatch, dash, strike) and by their words.

**The Findable Field Rule.** Every field's bottom rule is Field Edge, which stands 3:1 or better against whatever the field sits on (WCAG 1.4.11). Before 2026-09-27 fields were outlined in Control Line at 1.83:1 and could not be found in bad light. The hairline greys never mark a field.

## Typography

**Display Font:** Atkinson Hyperlegible Next, self-hosted as "Atkinson Next" (variable 200 to 800), falling back to system-ui
**Body Font:** the same family
**Label/Mono Font:** Atkinson Hyperlegible Mono, self-hosted as "Atkinson Mono", falling back to ui-monospace

**Character:** One legibility-first family built for low vision, used heavy where it must be read first and plain everywhere else. Its mono twin marks anything that is a key or a measurement, so a citation key, a timeline and a token count all look like data rather than prose.

### Hierarchy
- **Verdict** (800, 3rem, line-height 1, tracking 0.01em; 2.25rem on a phone): the category word inside the urgency bar, uppercase as written (RED, YELLOW, GREEN, OUT OF SCOPE). The heaviest thing on screen.
- **Headline** (700, 1.5rem, 1.2, tracking -0.01em): page titles ("Edit Mum", "People", "Caseload").
- **Title** (700, 1.3125rem, 1.25): answer section headings (What to do, Why, Red flags, Questions for you, Sources) and the brand mark (at 800).
- **Disposition** (700, 1.3125rem, 1.25; 1.125rem on a phone): the disposition under the verdict word, or beside it on a wide column.
- **Body** (400, 1.125rem, 1.5): answers, what the person said. Answer prose and the said row are capped at 70ch.
- **Field** (400, 1.125rem, 1.35): text inside fields. Never below 16px at any width, because iOS Safari zooms the page when a smaller field takes focus.
- **Label** (600 to 700, 1rem): tabs, field labels, preset titles, history titles, rule headings.
- **Meta** (400, 0.875rem): the "For Dad" and "3:34 PM" record header, history meta, the Checked line, allowance, scope line.
- **Key** (mono 700, 0.875rem): citation keys, rule ids, A/B side tags (at 0.75rem).
- **Measure** (mono 400, 0.75rem to 0.875rem, 1.5): timelines, raw model output, the "What the model reads" block.

The sizes above are the laptop sizes. Every size is a step of the classical typographic scale, 12, 14, 16, 18, 21, 24, 36 and 48px, approved on 2026-09-27 (ui-audit/direction.html). The tokens are named by role, `--fs-fine`, `--fs-meta`, `--fs-label`, `--fs-body`, `--fs-title`, `--fs-headline`, `--fs-disp` and `--fs-verdict`, mobile first and growing at 60rem: on a phone body and fields are 16px, section titles 18 and page titles 21; on a laptop 18, 21 and 24. Meta is 14 and labels 16 at every width. Nothing a person has to read is under 14px, except the 12px mono of counts and hashes. Until 2026-09-27 the tokens were named after the desktop pixel size each was born as (`--t-17` for the body), and phone body text was 15px. Numerals in measurements and details use tabular figures.

### Named Rules
**The Mono Means Data Rule.** Mono is only for citation keys, rule ids, timelines, token and cache counts and raw model output. Never for prose, headings or labels.

**The Heavy Word Rule.** Weight 800 is reserved for the verdict word and the brand mark. Headings stop at 700.

## Layout

A single reading column, 45rem wide, centred in the main area with a 1rem gutter. From 60rem the sidebar (18.5rem) sits permanently at the left; below that it is an off-canvas drawer behind a scrim, opened from the top bar's menu button. The top bar is a phone control only: menu on the left, new assessment on the right. Who the assessment is for is one line above the composer, where the thumb already is, and it opens a picker sheet. The composer is sticky at the bottom, matches the column's left edge, and holds the allowance pips above the field.

A compare assessment uses one 64rem container for the page and the composer together, so the pair keeps one left edge. From 60rem the two answers sit side by side, each labelled with an A or B ink tag; below 60rem they stack behind A/B line tabs. The people pages use a 72rem page, and the person form puts a sticky 22rem live preview beside the fields from 60rem.

Urgency bars and the rule-line frame bleed to the screen edge below 45rem and sit inside the column above it.

### The 4px Grid
Every padding, margin and gap is a multiple of 4px, from Carbon. The steps in use are 4, 8, 12, 16, 20, 24, 28, 32 and 40px, and 64px under base's register. Below 4px only 2px survives, Carbon's own first step, as a micro offset: a tag's vertical padding, the gap between a title and its meta line, an icon nudged level with its text. Moved onto the grid on 2026-09-27, when about 120 values sat at 3, 5, 6, 7, 9, 10, 13, 14 and 18px; each went to its nearest multiple of 4, ties going up. The named layout lengths:

| Token | Phone | From 60rem | Use |
|---|---|---|---|
| `--pad` | 16px | 16px | the page gutter |
| `--page-y` | 12px | 20px | the page's own top and bottom padding |
| `--sec` | 24px | 32px | between an answer's sections |
| `--turn` | 32px | 40px | between one turn and the next, always more than a section |
| `--tap` | 44px | 44px | the floor for anything a thumb lands on |
| `--numeral` | 32px | 36px | the keypad square on a numbered step |

Two things are centred by arithmetic rather than spaced: a field's one line sits in the middle of its 44px box (`calc((var(--tap) - 1lh) / 2)`), and a numbered step's first line sits level with the middle of its numeral.

Breakpoints in use: 36rem (age and sex side by side), 40rem (two who-cards side by side), 45rem (bars stop bleeding), 60rem (sidebar, paired answers, form preview, source sheet as a side panel).

### Named Rules
**The 44px Rule.** Anything a thumb lands on is at least 44 by 44 CSS pixels, at every width: buttons, citation chips, tabs, text actions, the SOAP link, the source URL, each token's remove button, the label around a checkbox, a register title at base. A link inside a sentence is exempt, as WCAG 2.5.8 exempts it. Brought in line on 2026-09-27, when the rules check counted 59 undersized targets across the phone screens.

## Elevation & Depth

Flat. Depth comes from tone: chrome around paper, the well for what was said and for quiet panels, hairlines between sections. Shadows exist only on things that sit over the page: the open drawer on narrow screens and the source sheet, each with a dark scrim behind. Focus is a 3px action outline offset 2px on anything focusable, except where a neighbour sits flush: a field draws a 2px outline inside its box, and a tab and a preset row draw their 3px outline inside theirs.

### Shadow Vocabulary
- **Drawer lift** (`box-shadow: 0 12px 40px rgb(15 19 24 / .22)`): the sidebar when opened as a drawer.
- **Sheet lift, bottom** (`box-shadow: 0 -8px 40px rgb(15 19 24 / .25)`): the source sheet rising from the bottom on narrow screens.
- **Sheet lift, side** (`box-shadow: -8px 0 40px rgb(15 19 24 / .2)`): the source sheet as a full-height right panel from 60rem.

### Named Rules
**The Only Overlays Cast Shadows Rule.** Nothing in the page flow has a shadow. If it does not cover the page, it is flat.

## Shapes

One shape: square. Every corner is 0, Carbon's flat geometry: urgency bars, the rule-line frame, the said row, marks, buttons, chips, fields, tabs, keypad numerals, the switcher, notices, panels, tags, tokens, and the source sheet as it rises. Before 2026-09-27 controls had 6px corners and tags 3px.

Lines are 1px. A control's edge is a 1px hairline (ink for a plain button, a switcher and a numeral; Control Line for a citation chip and a token; action for the Answer button). A field has no edge but its bottom rule in Field Edge. The only lines thicker than 1px carry meaning: the 3px stripe on a working step, the 3px ink rule under a selected tab, and the three state patterns.

Three line patterns carry state: a 135deg dark hatch (black at 24%, 6px stripe, 12px period) over hold for any no-verdict state, darker rather than lighter so white text never sits on anything lighter than hold itself (6.39:1, WCAG AA at every size); a 1.5px dashed hold border for the not-grounded note; a 1.5px strikethrough in ink-3 for anything a guard removed, always followed by a tag naming why. A dashed tag border marks a Sample profile and a dashed step stripe marks a skipped step.

## Motion

Motion is only ever feedback on a state change: the urgency bar develops left to right in two hard steps over 180ms, the drawer slides in over 160ms, the Checked chevron turns 90deg, the microphone pulses while it records, and a pack's download bar fills.

### Named Rules
**The Less Motion Rule.** Under `prefers-reduced-motion: reduce` every transition and animation lands on its end state at once. It is one rule at the top of `app.css`, not one per component, so a new animation cannot forget it. Before 2026-09-27 only the bar and the microphone honoured it.

## Components

### Buttons
Blunt and filled with ink; there is no blue button.
- **Shape:** square, 44px least height, 700 weight.
- **Primary:** ink fill, paper text, 0 1rem padding ("Save changes", "Continue as ..."). Hover lifts to ink-hover. Disabled fills with rule-2.
- **Plain:** paper fill, 1px ink border, ink text ("New assessment", "Delete Mum", "Switch to ..."). Hover fills with well.
- **Quiet:** no border or fill, ink-2 text; hover inks the text and fills with well ("Cancel").
- **Send:** a 44px ink square with the drawn up-arrow; disabled fills with rule-2 while a turn runs.
- **Microphone:** a 44px ghost square beside the field: no border, ink-2 icon, well on hover. Recording fills it with action and it widens to carry the seconds.
- **Answer:** Carbon's tertiary button and the one outlined-blue control: 1px action border and action text, beside each follow-up question, 44px tall.
- **Text action:** blue 700 text with no box ("Add when it started", "Show what the model is writing"), underlined on hover, in a 44px row.

### Tabs and the switcher
- **Line tabs:** the A/B tabs of a comparison below 60rem. A hairline runs under the row; each tab is 44px, ink-2 at 600 with its mono A or B tag; the selected tab turns ink at 700 and stands on a 3px ink rule. They are real tabs: `aria-selected`, a roving tabindex, arrow keys, and `role="tabpanel"` on each side.
- **Content switcher:** the sex toggle on the person form and Today/All at base. One 1px ink frame split by a 1px ink line; the pressed half fills with ink.

### Chips
- **Citation chip:** paper, 1px rule-2 border, 44px; an ink-3 mono index, the key in blue mono 700, the short publisher in ink-2. Hover turns the border blue. Opens the source sheet.
- **Token:** a condition or medication on the person form. A 44px paper chip framed by an inset 1px rule-2 outline, with a 44px remove button.

### Inputs / Fields
- **Style:** Carbon's filled field. Chrome fill on paper, paper fill on a well; no edge but a 1px bottom rule in Field Edge; square; 44px least height; 0.75rem side padding; Field type. The composer field grows to 10rem. Placeholder in ink-3.
- **Focus:** a 2px action outline drawn inside the box.
- **Error:** the same 2px outline in ink, and a bold line with the alert icon. No red is used for form errors. Focus wins while the field is being fixed.
- **Disabled (busy composer):** the field and send are disabled while a turn runs, the field's rule disappears, and a status line above says why. That line, "Writing the answer. You can add more once it's done.", is Viraj's wording (2026-09-19). Its placeholder, "Waiting for the answer to finish", is still surface copy for him to confirm.
- **Checkbox:** square, ticked in ink, inside a 44px label.

### Navigation
- **Sidebar:** chrome. The brand square and "Grounded" at the top, a plain "New assessment" button, the history list grouped by day, then Caseload, Send to base, People and Region as 44px rows, and the model status lamp at the foot. A history row is a column of 1.5rem triage marks (R, Y, G letters, or the hatched hold mark with the drawn no-entry icon), a two-line clamped title and a meta line of person, verdict word and time.
- **Top bar:** chrome, sticky, below 60rem only: the menu and new-assessment icon buttons, 44px each.
- **Drawer:** below 60rem the sidebar slides in over a scrim. Closed, it is hidden as well as moved aside, so none of its links can take focus or be read out; its visibility flips only after the 160ms slide. Until 2026-09-27 its 71 links took focus off screen.

### Urgency Bar (signature)
A square full-width field, and the one loud thing on the screen: the verdict word at 800, 36px on a phone and 48 on a laptop, with the disposition at 700 under it. They share one line once the answer's own column is 34rem wide; that is a container query on the turn, so each side of a comparison follows its own width. 16px of padding, 24 at the sides when it runs on one line. 36px on a phone was kept after a fold measurement on iPhone 15 (results/2026-09-27-direction-2-band/fold.txt): the first step stays on the first screen in every state without a rule line, and where a rule line pushes it under the composer it does so at 30px too. Red, yellow and green for the three WHO categories; hatched hold for OUT OF SCOPE, NOT ASSESSED and WHO IS THIS FOR?. It is exposed as a level-2 heading. On arrival it develops left to right in two hard steps over 180ms, and not at all under reduced motion. The disposition strings are Viraj's copy and are recorded here as he wrote them, not as system copy to vary: "Call emergency services now", "Be seen today", "Self-care, and the signs that change the answer". The refusal and not-assessed messages beneath the bar are also his.

### Rule Lines (signature)
Pinned directly under the bar in a hairline frame with no top border, so they read as part of the verdict. Each line has a drawn icon (blue raise arrow when the rule raised the verdict, ink-3 check-circle when it supports it, flag when it only flags), a bold head ("Raised to red" or "Raised to yellow", "Backs up this red", "At least yellow", "Flagged"), the profile fact and symptom, the quoted source line in ink-2 with curly quotes, and a citation chip with the rule id in mono. The wording of rule lines is Viraj's.

### Said Row
What the person said, as a record: a square well row across the column with who on the left and when on the right in meta ("For Dad", "3:34 PM"), two facts rather than one string joined by a dot, the words in body, and an optional timeline in mono with a bold "Timeline" label. Never a bubble, never right-aligned.

### Working Steps
Four equal columns, Retrieve, Read, Write, Check, each topped by a 3px stripe: rule when waiting, a blue and wash dashed stripe while running, solid blue when done, dashed and greyed when skipped. A sub-line under each gives the count or time. The raw model stream stays hidden behind a "Show what the model is writing" text action. A slow re-read shows a well notice with the info icon; its wording, "The model lost this conversation and is re-reading it.", is Viraj's (2026-09-19), and the answer's summary line says "The model lost this conversation and re-read it." afterwards.

### Keypad Numerals
Numbered steps sit beside a square with a 1px ink border and a bold numeral, 32px on a phone and 36px from 60rem. "What to do" is always numbered this way.

### Removed, Flagged, Not Grounded
- **Removed:** the entry struck through in ink-3, followed by a small square tag "removed: " plus the reason. Several removed citations share one "removed" head line and are clipped to a line each.
- **Flagged, kept:** the same tag shape appended to a kept step.
- **Not grounded:** a 1.5px dashed hold box headed "Not grounded in sources" in bold, placed under the bar and any rule lines; no sections follow except removals and the reason.

### Checked Line
A full-width text button, 44px at least, above a hairline: check icon, "Checked", total time, read and cached tokens, tokens written, and "n removed" in bold, separated by small square ink-3 dots, with a chevron that turns 90deg over 160ms when opened. It expands a definition list of Retrieve, Read, Write, Check, Total and Slot, what the guards removed, the raw output, and a fine line on the run conditions.

### Profile Tags
- **Under 16:** a small hatched hold tag, bold 0.75rem.
- **Sample:** a small dashed ink-3 tag on seeded demo people ("Sample" in the list, "Sample profile" on the who-card). The list note, "Sample profiles are made up for this demo.", is Viraj's wording (2026-09-19). The two labels are surface copy for him to confirm.
- **Rule id:** mono bold 0.75rem in a 1px rule-2 box.

### Source Sheet
A native dialog: a square bottom sheet up to 85dvh on narrow screens, a full-height 28rem right panel from 60rem. Sticky header with the key in blue mono at 1.0625rem, token count and a close button; the chunk text at line-height 1.55; a footer with publisher, the URL as a 44px link, retrieval date and source line in meta.

### A Failed Turn
An ink-bordered panel, never red: the alert icon and "The answer did not finish.", the words the screen-reader announcement already used, then the reason, then a plain **Try again** button that sends the same words and timeline again. Only the last turn of a side offers it, and not while anything is being written. It used to stop at "Something went wrong". "Try again" is surface copy for Viraj.

### Clinical Export
Under the last answer, above the composer: a hairline rule, then one action link, 44px tall, and a muted line of explanation beside it, wrapping under it on a phone. It is the only link in the conversation that leaves the page, and it downloads rather than navigates. Added 2026-09-19. Its copy, "Download the SOAP note" and "Plain text, for a clinician. It shows what the guards removed and why.", is surface copy for Viraj to put in his own voice.

### Base
The supervisor's register on its own port, with its own copy of these tokens in `base-static/base.css`. The same square shapes, 1px hairlines and 4px grid. A register cell with nothing in it says "None" in ink-3; it was an em dash until 2026-09-27. "None" is surface copy for Viraj to confirm. A register title clamps at two lines on an inner span, and its link reaches 12px above and below the words, so it is a 44px target without a gap under it; a min-height on the clamped box itself showed the top of a third line.

## Do's and Don'ts

### Do:
- **Do** open every answer with the urgency bar, then rule lines, then "What to do" as numbered keypad steps, then Why, Red flags, Questions for you, Sources, and the Checked line.
- **Do** give every urgency its word as well as its colour; the bar always says RED, YELLOW, GREEN or its no-verdict word.
- **Do** fill selected and primary controls with ink, and keep blue to links, source keys, raise icons, step progress and focus.
- **Do** mark every guard removal in place with a strikethrough and a tag that names the reason.
- **Do** set citation keys, rule ids, timelines and measurements in Atkinson Mono.
- **Do** keep every corner square and every control edge 1px.
- **Do** put every padding, margin and gap on the 4px grid.
- **Do** make anything a thumb lands on 44 by 44, and every field's text 16px or more.
- **Do** give every field a bottom rule in Field Edge.
- **Do** draw new icons on the existing 24px grid at 1.75 stroke with round caps and joins, in currentColor.
- **Do** self-host every font and asset; nothing loads from a CDN.

### Don't:
- **Don't** put a triage colour anywhere except the urgency bar, the history marks and the base register's marks.
- **Don't** render a refusal, a not-grounded answer, a rule line or a removal in red, yellow or green, or style a refusal so it could pass for a milder verdict.
- **Don't** put what the person said in a chat bubble, or align it right.
- **Don't** group answer sections into cards or a card grid.
- **Don't** fill a button or a selected state with blue.
- **Don't** round a corner. Even 4px breaks the flat geometry.
- **Don't** mark a field with a hairline grey; rule and rule-2 cannot be found in bad light.
- **Don't** add shadows to anything that does not cover the page.
- **Don't** add motion that ignores reduced motion, or motion that is not feedback.
- **Don't** use an em dash anywhere in the copy, page titles included.
- **Don't** use emoji or text glyphs as icons.
- **Don't** reword the dispositions, refusal messages or rule lines; they are Viraj's copy.
- **Don't** show the raw model stream by default.

## Checked, not remembered

`node 06-demo/ui_check.mjs rules OUTDIR` reads these rules off every rendered screen, at 390px and 1440px, with reduced motion on: nothing sideways at 390px, every control 44px, every field's text 16px, every field findable at 3:1, all text AA, nothing moving under reduced motion, no em dash, triage colours only in bars and marks, a word on every bar and mark, refusals in hold, every citation a button that opens its source, every removal struck with its reason, nothing off screen able to take focus, every clamped text showing its lines and no more, the timeline field as wide as the composer, and a failed turn offering Try again. `bash 06-demo/suite.sh OUTDIR` runs it last, after the other twelve modes and the offline self-tests, and `bash 06-demo/pw_shots.sh OUTDIR` takes the screenshots that close a batch.
