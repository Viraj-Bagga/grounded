---
name: Triage
description: Offline chest pain triage, read like a health worker's handset. "Triage" is a placeholder name.
colors:
  paper: "#ffffff"
  chrome: "#f2f4f7"
  well: "#eaedf2"
  ink: "#0f1318"
  ink-hover: "#2b323b"
  ink-2: "#414a56"
  ink-3: "#5c6572"
  rule: "#dce0e6"
  rule-2: "#b9c0ca"
  action: "#1f3fbf"
  action-soft: "#e5eafa"
  red: "#c8261d"
  yellow: "#f2b705"
  on-yellow: "#101418"
  green: "#1c7a43"
  hold: "#56606c"
typography:
  verdict:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.875rem"
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
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  disposition:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"kern\""
  label:
    fontFamily: "Atkinson Next, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.9375rem"
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
  control: "6px"
spacing:
  xxs: "0.25rem"
  xs: "0.375rem"
  sm: "0.5rem"
  md: "0.75rem"
  pad: "1rem"
  lg: "1.25rem"
  section: "1.75rem"
  turn: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
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
    rounded: "{rounded.control}"
    padding: "0 1rem"
    height: "2.75rem"
  button-plain-hover:
    backgroundColor: "{colors.well}"
  button-send:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    size: "3rem"
  chip-person:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0 0.75rem"
    height: "2.375rem"
  chip-person-pressed:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  source-key:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.action}"
    typography: "{typography.key}"
    rounded: "{rounded.control}"
    padding: "0 0.75rem"
    height: "2.25rem"
  input-field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 0.75rem"
    height: "3rem"
  step-numeral:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    size: "2rem"
  urgency-bar-red:
    backgroundColor: "{colors.red}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "0.75rem 1rem"
    height: "3.75rem"
  urgency-bar-yellow:
    backgroundColor: "{colors.yellow}"
    textColor: "{colors.on-yellow}"
    rounded: "{rounded.none}"
    padding: "0.75rem 1rem"
    height: "3.75rem"
  urgency-bar-green:
    backgroundColor: "{colors.green}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "0.75rem 1rem"
    height: "3.75rem"
  urgency-bar-hold:
    backgroundColor: "{colors.hold}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "0.75rem 1rem"
    height: "3.75rem"
  said-row:
    backgroundColor: "{colors.well}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "0.625rem 0.875rem 0.75rem"
---

# Design System: Triage

## Overview

**Creative North Star: "The Health Worker's Handset"**

A triage conversation set in the grammar of a field worker's phone: numbered, bold, readable with one hand in bad light. The screen is paper white with a cool grey chrome layer around it and near-black ink on top. There is one action blue and it stays small. The only saturated field on any screen is the urgency bar, a square full-width band in a WHO triage colour with the category word in heavy type. Everything else that matters (a refusal, an answer that is not grounded, something a guard removed) is carried by form and by a word, never by a fourth colour: refusal is hatched, not-grounded is dashed, removed is struck through.

The reading order is the design. The person says what is happening, and it is kept as a plain record row, not a bubble. Four steps (Retrieve, Read, Write, Check) fill in while the model works. Then the urgency bar, with any profile rule lines pinned directly under it, then numbered steps in keypad squares, then why, then red flags, questions and sources. A single "Checked" line closes each answer and opens the measurements. Density is moderate: a 45rem reading column, 70ch prose, 2.75rem tap targets.

The world refuses the chatbot bubble stack and the soft health-app card grid. There are no cards, no avatars, no gradients, no illustration, and no decorative colour.

**Key Characteristics:**
- Paper, chrome and ink, with one action blue kept to links, source keys, raise icons, step progress and focus rings.
- Triage colour only in full-width square urgency bars, and in the small history marks.
- Refusal hatched, not-grounded dashed, removed struck through with a word tag saying why.
- Atkinson Hyperlegible Next for everything read; Atkinson Hyperlegible Mono for keys, timelines and measurements.
- Square bars and record rows; 6px corners on controls only.
- Selection fills with ink, not blue.
- One drawn stroke icon set; no glyphs or emoji stand in for icons.

## Colors

A cool neutral paper-and-ink system with a single deep blue accent and three reserved triage colours that appear only as urgency fields.

### Primary
- **Signal Blue** (action): the one accent. Links, "Add a timeline" and other text actions, source key text on citation chips and in the source sheet header, the raise arrow on a rule line that changed the verdict, the progress stripe on the working steps, focus rings and the text-field focus border. It never fills a button or marks a selection.
- **Signal Blue Wash** (action-soft): the 3px halo around a focused field, the hover fill of an outlined "Answer" button, and the saved-confirmation strip on the person form.

### Triage (reserved)
- **Emergency Red** (red, white text): RED urgency bar.
- **Signal Yellow** (yellow, near-black on-yellow text): YELLOW urgency bar.
- **Field Green** (green, white text): GREEN urgency bar.
- **Hold Slate** (hold, white text, under the hatch): the no-verdict bars (OUT OF SCOPE, NOT ASSESSED, WHO IS THIS FOR?), the child note, the Under 16 tag. Its dashed form outlines the not-grounded note. Hold is a neutral and never reads as a fourth, milder verdict.

### Neutral
- **Paper** (paper): the conversation, forms, controls, the source sheet, and the text colour on red, green and hold bars.
- **Cool Chrome** (chrome): sidebar, top bar, the profile preview panel, people-row hover. A layer around the work, never inside the answer.
- **Record Well** (well): what the person said, quiet notices, raw model output, confirm panels, hover fill on quiet controls.
- **Ink** (ink): text, pressed chips, primary buttons, the send button, step numeral borders, the brand square and status lamp.
- **Ink Lifted** (ink-hover): hover on ink-filled buttons only.
- **Ink Second** (ink-2): secondary text, meta lines, timeline text, rule quotes.
- **Ink Third** (ink-3): tertiary text, struck-through removed text, placeholder, rule ids on rule lines.
- **Hairline** (rule): section dividers, the rule-line frame, top bar and composer borders.
- **Control Line** (rule-2): borders on unpressed chips, fields, citation chips and the segmented control; disabled fill.

### Named Rules
**The One Saturated Field Rule.** On any screen the urgency bar is the only saturated field. The small red and yellow marks in the history list and the base register are the single allowed exception, because they index past bars. The base register was added to this exception on 2026-09-20, on the same grounds: a register row indexes a past bar exactly as a history row does. Nothing else on that screen carries a triage colour, not a row fill, not a count, not a tag.

**The Ink Selects Rule.** Pressed person chips, compare tabs, the sex toggle, primary buttons and send fill with ink. Blue is for pointing at something (a link, a key, a focus), never for choosing.

**The No Fourth Colour Rule.** A refusal, the not-grounded note, rule lines and guard removals are never drawn in a triage colour. They are told apart by pattern (hatch, dash, strike) and by their words.

## Typography

**Display Font:** Atkinson Hyperlegible Next, self-hosted as "Atkinson Next" (variable 200 to 800), falling back to system-ui
**Body Font:** the same family
**Label/Mono Font:** Atkinson Hyperlegible Mono, self-hosted as "Atkinson Mono", falling back to ui-monospace

**Character:** One legibility-first family built for low vision, used heavy where it must be read first and plain everywhere else. Its mono twin marks anything that is a key or a measurement, so a citation key, a timeline and a token count all look like data rather than prose.

### Hierarchy
- **Verdict** (800, 1.875rem, line-height 1, tracking 0.01em): the category word inside the urgency bar, uppercase as written (RED, YELLOW, GREEN, OUT OF SCOPE). The heaviest thing on screen.
- **Headline** (700, 1.5rem, 1.2, tracking -0.01em): page titles ("For Mum", "People", "Edit Mum").
- **Title** (700, 1.25rem, 1.25): answer section headings (What to do, Why, Red flags, Questions for you, Sources) and the brand mark (at 800).
- **Disposition** (700, 1.0625rem, 1.25): the disposition beside the verdict word.
- **Body** (400, 1.0625rem, 1.5): answers, what the person said, fields. Answer prose and the said row are capped at 70ch.
- **Label** (600 to 700, 0.9375rem): chips, field labels, preset titles, history titles, rule headings.
- **Meta** (400, 0.875rem): the "For Dad · 3:34 PM" record header, history meta, the Checked line, allowance, scope line.
- **Key** (mono 700, 0.875rem): citation keys, rule ids, A/B side tags (at 0.75rem).
- **Measure** (mono 400, 0.75rem to 0.875rem, 1.5): timelines, raw model output, the "What the model reads" block.

The scale is fixed steps, not fluid: 0.75, 0.875, 0.9375, 1.0625, 1.25, 1.5 and 1.875rem. Numerals in measurements and details use tabular figures.

### Named Rules
**The Mono Means Data Rule.** Mono is only for citation keys, rule ids, timelines, token and cache counts and raw model output. Never for prose, headings or labels.

**The Heavy Word Rule.** Weight 800 is reserved for the verdict word and the brand mark. Headings stop at 700.

## Layout

A single reading column, 45rem wide (col) with 1rem side padding (pad), centred in the main area. From 60rem the sidebar (18.5rem) sits permanently at the left; below that it is an off-canvas drawer behind a scrim, opened from the top bar's menu button. The top bar is sticky, 3.5rem high, and carries the person chips as one horizontally scrolling row that snaps and fades at the right edge on narrow screens. The composer is sticky at the bottom, matches the column's left edge, and holds the allowance pips above the field.

A compare assessment uses one 64rem container (col-pair) for the page and the composer together, so the pair keeps one left edge. From 60rem the two answers sit side by side, each labelled with an A or B ink tag; below 60rem they stack behind A/B tabs styled as chips. The people pages use a 72rem page, and the person form puts a sticky 22rem live preview beside the fields from 60rem.

Urgency bars and the rule-line frame bleed to the screen edge below 45rem (negative pad margin) and sit inside the column above it. Rhythm: 0.25 to 0.75rem inside components, 1.75rem between answer sections, 2rem between turns. A turn in progress reserves most of a screen of height below the message so the answer grows downward from the top.

Breakpoints in use: 36rem (age and sex side by side), 40rem (two who-cards side by side), 45rem (bars stop bleeding), 60rem (sidebar, paired answers, form preview, source sheet as a side panel).

## Elevation & Depth

Flat. Depth comes from tone: chrome around paper, the well for what was said and for quiet panels, hairlines between sections. Shadows exist only on things that sit over the page: the open drawer on narrow screens and the source sheet, each with a dark scrim behind. Focus is a 3px action outline offset 2px on anything focusable, and fields show a 3px wash halo with a blue border.

### Shadow Vocabulary
- **Drawer lift** (`box-shadow: 0 12px 40px rgb(15 19 24 / .22)`): the sidebar when opened as a drawer.
- **Sheet lift, bottom** (`box-shadow: 0 -8px 40px rgb(15 19 24 / .25)`): the source sheet rising from the bottom on narrow screens.
- **Sheet lift, side** (`box-shadow: -8px 0 40px rgb(15 19 24 / .2)`): the source sheet as a full-height right panel from 60rem.

### Named Rules
**The Only Overlays Cast Shadows Rule.** Nothing in the page flow has a shadow. If it does not cover the page, it is flat.

## Shapes

Two shapes. Things that are records or states are square: urgency bars, the rule-line frame, the said row, history marks, the brand square, the status lamp, allowance pips, step stripes, the child note. Things you press or type into have a 6px corner: buttons, chips, fields, citation chips, keypad numerals, the segmented control, notices and panels. Small inline word tags ("removed: ...", "flagged, kept") use a 3px corner and removable condition tokens 4px. Borders on controls are 1.5px; hairlines are 1px.

Three line patterns carry state: a 135deg dark hatch (black at 24%, 6px stripe, 12px period) over hold for any no-verdict state, darker rather than lighter so white text never sits on anything lighter than hold itself (6.39:1, WCAG AA at every size); a 1.5px dashed hold border for the not-grounded note; a 1.5px strikethrough in ink-3 for anything a guard removed, always followed by a tag naming why. A dashed tag border marks a Sample profile and a dashed step stripe marks a skipped step.

## Components

### Buttons
Blunt and filled with ink; there is no blue button.
- **Shape:** 6px corners, 2.75rem minimum height, 700 weight.
- **Primary:** ink fill, paper text, 0 1rem padding ("Save changes", "Continue as ..."). Hover lifts to ink-hover. Disabled fills with rule-2.
- **Plain:** paper fill, 1.5px ink border, ink text ("New assessment", "Delete Mum", "Switch to ..."). Hover fills with well.
- **Quiet:** no border or fill, ink-2 text; hover inks the text and fills with well ("Cancel").
- **Send:** a 3rem ink square with the drawn up-arrow; disabled fills with rule-2 while a turn runs.
- **Answer:** the one outlined-blue control, a 2.25rem 1.5px action-bordered button beside each follow-up question.
- **Text action:** blue 700 text with no box ("Add a timeline", "Show what the model is writing"), underlined on hover.

### Chips
- **Person chip:** 2.375rem, paper fill, 1.5px rule-2 border, ink-2 label at 600. Hover inks the label and border. Pressed fills with ink and paper text. In compare mode each pressed chip carries an A or B mono tag set paper on ink.
- **Tool chip:** Compare and add, ink text, same shape; pressed fills with ink. A 1px vertical divider separates people from tools.
- **Citation chip:** paper, rule-2 border, 2.25rem; an ink-3 mono index, the key in blue mono 700, the short publisher in ink-2. Hover turns the border blue. Opens the source sheet.

### Inputs / Fields
- **Style:** 3rem, paper, 1.5px rule-2 border, 6px corners, 1.0625rem body text; the composer field grows to 10rem. Placeholder in ink-3.
- **Focus:** blue border plus a 3px action-soft halo, no outline.
- **Error:** the border goes to 2px ink and a bold line with the alert icon appears. No red is used for form errors.
- **Disabled (busy composer):** the field and send are disabled while a turn runs, with a status line above saying why. That line, "Writing the answer. You can add more once it's done.", is Viraj's wording (2026-09-19). Its placeholder, "Waiting for the answer to finish", is still surface copy for him to confirm.
- **Segmented control:** a joined pair in one 1.5px rule-2 frame; the pressed half fills with ink.
- **Token field:** conditions and medications as well-filled 4px tokens with a drawn close button, inside a field-styled frame.

### Navigation
- **Sidebar:** chrome. The brand square and name at the top, a plain "New assessment" button, the history list grouped by day, People and the model status lamp at the foot. A history row is a column of 1.5rem triage marks (R, Y, G letters, or the hatched hold mark with the drawn no-entry icon), a two-line clamped title and a meta line of person, verdict word and time.
- **Top bar:** chrome, sticky, person chips across the top. On narrow screens the menu, compare and compose actions are 2.75rem icon buttons, and a pressed icon button fills with ink.

### Urgency Bar (signature)
A square full-width field, at least 3.75rem, holding the verdict word at 800 and the disposition at 700. Red, yellow and green for the three WHO categories; hatched hold for OUT OF SCOPE, NOT ASSESSED and WHO IS THIS FOR?. It is exposed as a level-2 heading. On arrival it develops left to right in two hard steps over 180ms, and not at all under reduced motion. The disposition strings are Viraj's copy and are recorded here as he wrote them, not as system copy to vary: "Call emergency services now", "Be seen today", "Self-care, and the signs that change the answer". The refusal and not-assessed messages beneath the bar are also his.

### Rule Lines (signature)
Pinned directly under the bar in a hairline frame with no top border, so they read as part of the verdict. Each line has a drawn icon (blue raise arrow when the rule raised the verdict, ink-3 check-circle when it supports it, flag when it only flags), a bold head ("Raised to red" or "Raised to yellow", "Backs up this red", "At least yellow", "Flagged"), the profile fact and symptom, the quoted source line in ink-2 with curly quotes, and a citation chip with the rule id in mono. The wording of rule lines is Viraj's.

### Said Row
What the person said, as a record: a square well row across the column with "For Dad · 3:34 PM" in meta, the words in body, and an optional timeline in mono with a bold "Timeline" label. Never a bubble, never right-aligned.

### Working Steps
Four equal columns, Retrieve, Read, Write, Check, each topped by a 4px stripe: rule when waiting, a blue and wash dashed stripe while running, solid blue when done, dashed and greyed when skipped. A mono-free sub-line under each gives the count or time. The raw model stream stays hidden behind a "Show what the model is writing" text action. A slow re-read shows a well notice with the info icon; its wording, "The model lost this conversation and is re-reading it.", is Viraj's (2026-09-19), and the answer's summary line says "The model lost this conversation and re-read it." afterwards.

### Keypad Numerals
Numbered steps and presets sit beside a 2rem square with a 1.5px ink border, 6px corners and a bold numeral. "What to do" is always numbered this way.

### Removed, Flagged, Not Grounded
- **Removed:** the entry struck through in ink-3, followed by a small bordered tag "removed: " plus the reason. Several removed citations share one "removed" head line and are clipped to a line each.
- **Flagged, kept:** the same tag shape appended to a kept step.
- **Not grounded:** a 1.5px dashed hold box headed "Not grounded in sources" in bold, placed under the bar and any rule lines; no sections follow except removals and the reason.

### Checked Line
A full-width text button above a hairline: check icon, "Checked", total time, read and cached tokens, tokens written, and "n removed" in bold, separated by small ink-3 dots, with a chevron that turns 90deg over 160ms when opened. It expands a definition list of Retrieve, Read, Write, Check, Total and Slot, what the guards removed, the raw output, and a fine line on the run conditions.

### Profile Tags
- **Under 16:** a small hatched hold tag, bold 0.75rem.
- **Sample:** a small dashed ink-3 tag on seeded demo people ("Sample" in the list, "Sample profile" on the who-card). The list note, "Sample profiles are made up for this demo.", is Viraj's wording (2026-09-19). The two labels are surface copy for him to confirm.
- **Rule id:** mono bold 0.75rem in a 1px rule-2 box.

### Source Sheet
A native dialog: a bottom sheet up to 85dvh on narrow screens, a full-height 28rem right panel from 60rem. Sticky header with the key in blue mono at 1.0625rem, token count and a close button; the chunk text at line-height 1.6; a footer with publisher, URL, retrieval date and source line in meta.

### Clinical Export

Under the last answer, above the composer: a hairline rule, then one action link in the action blue and a
muted line of explanation beside it, wrapping under it on a phone. It is the only link in the conversation
that leaves the page, and it downloads rather than navigates. Added 2026-09-19. Its copy, "Download the SOAP
note" and "Plain text, for a clinician. It shows what the guards removed and why.", is surface copy for
Viraj to put in his own voice.

## Do's and Don'ts

### Do:
- **Do** open every answer with the urgency bar, then rule lines, then "What to do" as numbered keypad steps, then Why, Red flags, Questions for you, Sources, and the Checked line.
- **Do** give every urgency its word as well as its colour; the bar always says RED, YELLOW, GREEN or its no-verdict word.
- **Do** fill selected and primary controls with ink (#0f1318 family), and keep blue to links, source keys, raise icons, step progress and focus rings.
- **Do** mark every guard removal in place with a strikethrough and a tag that names the reason.
- **Do** set citation keys, rule ids, timelines and measurements in Atkinson Mono.
- **Do** keep controls at a 2.75rem minimum height and answer prose at 70ch or less.
- **Do** draw new icons on the existing 24px grid at 1.75 stroke with round caps and joins, in currentColor.
- **Do** self-host every font and asset; nothing loads from a CDN.

### Don't:
- **Don't** put a triage colour anywhere except the urgency bar, the history marks and the base register's marks.
- **Don't** render a refusal, a not-grounded answer, a rule line or a removal in red, yellow or green, or style a refusal so it could pass for a milder verdict.
- **Don't** put what the person said in a chat bubble, or align it right.
- **Don't** group answer sections into rounded cards or a card grid.
- **Don't** fill a button or a selected state with blue.
- **Don't** add shadows to anything that does not cover the page.
- **Don't** use emoji or text glyphs as icons.
- **Don't** reword the dispositions, refusal messages or rule lines; they are Viraj's copy.
- **Don't** show the raw model stream by default.
