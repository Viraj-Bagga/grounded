# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: a person with no clinic nearby, on a phone, checking chest pain for themselves or for someone in their household. Often worried, sometimes mid-symptom, possibly in poor light on a small or older phone. They need an urgency they can act on, and the reason for it.

Secondary: hackathon judges (SteelHacks XIII, 2026-09-19 to 20) watching that product on a laptop at an expo desk, about 5 minutes per visit. They cannot install anything. They judge whether it is a real product and whether its safety claims hold. The surface serves the person at home first; the judge watches the product (confirmed 2026-09-19).

## Product Purpose

Triage that runs on the device, offline. Symptoms go in as plain language; a WHO Interagency Integrated Triage Tool category (red, yellow, green) comes back with a disposition, next steps, red flags, sources the person can open, and follow-up questions when the answer is not red. The conversation continues over follow-up turns. Success is a correct, grounded urgency the person can act on, and a refusal instead of a guess when the question is outside what the system knows.

## Positioning

A small model on the device, wrapped in deterministic app-logic guards it cannot override. Every citation is checked against the registry of real government chunks (35 as of 2026-09-19). Red flags the case does not state are removed where the guard's lexicon can see them. Instructions to take a medication are removed. Out-of-scope questions are refused rather than answered. Profile rules only ever raise urgency, and each quotes its source line. The interface shows what the guards did.

## Operating Context

- Demo: a laptop web UI against llama-server on CPU. The phone appears only as a screenshot. A first turn takes about 15 to 55 s and a follow-up about 7 to 25 s, measured 2026-09-19 with macOS Low Power Mode off, when generation ran at about 20 tokens/s (9.5 to 10 with it on). Streaming is required to show it is working.
- Household profiles (name, age, sex, conditions, medications, recent surgery) feed deterministic escalation rules in 02-pairs/escalation.py.
- Two Claude sessions work in this repo at once. 06-demo/ is this surface.

## Capabilities and Constraints

- Stack: static HTML, CSS and vanilla JavaScript served by 06-demo/server.py (Python stdlib, no build step). Nothing from a CDN and no remote fonts at runtime: the demo must work with the laptop offline.
- The corpus is chest pain only: 35 chunks from US government sources as of 2026-09-19, when new sources were appended. Everything else is refused.
- The model is schema-constrained to triage output. People are never created or edited through chat, only through a form.
- Urgency uses the three WHO categories only. A refusal, the not-grounded note, rule lines and guard removals are never shown in a triage colour.
- A red verdict carries no follow-up questions (claude.md hard constraint 4).
- Follow-up turns reuse the first turn's retrieved chunks, and the system prompt and chunks stay byte-identical so the llama.cpp prefix cache hits.
- Undecided: the product name. A neutral placeholder stands in and is on the replacement list.

## Brand Commitments

None yet. Patient-facing copy (refusal text, rule lines, dispositions) is Viraj's and is not reworded without him. New copy written for this surface is flagged for him to put in his own voice.

## Evidence on Hand

- Frozen chunks with publisher, URL and retrieval date (35 as of 2026-09-19): 01-data/citations.csv, 04-retrieval/corpus.db.
- Demo profiles are synthetic: You, Mum, Dad, Aunt Sue, Grandpa, Maya. They are not patients.
- Measured runs in 06-demo/results/ and 01-data/eval/runs/.
- Absent, and not to be claimed: users, testimonials, clinical validation, accuracy figures.

## Product Principles

1. Urgency first. The category and what to do are readable before anything else.
2. Show the guards. What was removed, refused or raised is visible, never hidden.
3. Refuse rather than guess, and a refusal never looks like a milder verdict.
4. Grounded or flagged. Every claim traces to a source the person can open, or says it cannot.
5. Works offline, on a small phone, under stress.

## Accessibility & Inclusion

Assumed, not yet confirmed: readable under stress and in poor light, WCAG 2.2 AA contrast, large tap targets, and no meaning carried by colour alone (every urgency also has a word). English only for the MVP.
