/**
 * App-logic guards on model output. Every one of these exists because a prompt
 * rule could not hold it.
 *
 * LIVES HERE FOR NOW. This was written inside the load spike because that is
 * the only RN project that exists. It belongs to the epic 5 app shell and
 * should move there with its tests when the shell is scaffolded.
 *
 * Each guard fails closed: when in doubt it drops content rather than showing
 * it. Everything dropped is returned in `dropped` so the caller can log it,
 * because a guard that silently eats output is its own kind of bug.
 */

export type Triage = {
  urgency: 'red' | 'yellow' | 'green';
  rationale: string;
  red_flags: string[];
  next_steps: string[];
  citations: string[];
  follow_up_questions: string[];
};

export type GuardReport = {
  result: Triage;
  dropped: {
    citations: string[];
    next_steps: string[];
    follow_up_questions: string[];
  };
  flagged: {next_steps: string[]};
};

/**
 * GUARD 1. Strip chat-template scaffolding before JSON.parse.
 *
 * Measured 2026-09-17 through llama.rn 0.12.9 on the simulator: `text` came
 * back as
 *
 *     <|im_start|>assistant
 *     { "urgency": "red", ... }
 *
 * so JSON.parse on the raw string throws. llama-server never showed this
 * because it splits the message before returning it, which is why nothing
 * upstream caught it. Grammar sampling constrains the JSON, not the envelope
 * around it.
 *
 * Deliberately does not regex the JSON itself. It removes known template
 * tokens and any prose before the first brace, then parses. If the remainder
 * is not valid JSON this throws, and that is correct: a malformed verdict must
 * not reach the screen as a half-parsed object.
 */
const TEMPLATE_TOKENS =
  /<\|(?:im_start|im_end|start_header_id|end_header_id|eot_id|begin_of_text|end_of_text|assistant|user|system|channel|message)\|>/g;

export function parseModelJson(raw: string): Triage {
  let s = String(raw ?? '');
  s = s.replace(TEMPLATE_TOKENS, ' ');
  // A bare role word can survive once its delimiters are gone.
  s = s.replace(/^\s*(assistant|model|system)\s*[:\n]/i, '');
  // Markdown fences, which the prompt forbids and the model sometimes emits.
  s = s.replace(/^\s*```(?:json)?/i, '').replace(/```\s*$/, '');

  const first = s.indexOf('{');
  const last = s.lastIndexOf('}');
  if (first === -1 || last === -1 || last < first) {
    throw new Error(
      `no JSON object in model output (len ${s.length}): ${s.slice(0, 120)}`,
    );
  }
  return JSON.parse(s.slice(first, last + 1)) as Triage;
}

/**
 * GUARD 2, hard constraint 12. No next_steps entry may instruct medication
 * administration.
 *
 * Measured 2026-09-17, no-chunk probe on yellow-angina: next_steps contained
 * "Administer nitroglycerin if prescribed and available". Nitroglycerin drops
 * blood pressure and is contraindicated in presentations this app cannot rule
 * out, having neither vitals nor an exam.
 *
 * THE RULE IS A BLANKET ONE: a next_step that mentions a medication or a dose
 * is dropped unless it is plainly not an instruction to take one.
 *
 * It was first written as "administration VERB pointed at a MEDICATION" and
 * that version leaked, which is worth recording. Writing the tests against real
 * outputs caught two entries with no verb in them:
 *
 *   "Over the counter analgesia as directed on the packet"
 *   "Take over-the-counter antacid or H2 blocker as directed"
 *
 * The first is the WORKED EXAMPLE in `02-pairs/system_prompt.txt`. The prompt
 * teaches a medication instruction by example, so the model will keep producing
 * them and a verb list will keep missing the phrasings nobody predicted. That
 * is the whole argument for the blanket rule in constraint 12, and it is also a
 * reason to revisit the worked example, which is Viraj's call.
 *
 * NOT dropped, deliberately:
 *   - "Bring your medications with you"       reporting or carrying, not dosing
 *   - "Tell the paramedics you take apixaban" reporting, not dosing
 *   - "Do not take nitroglycerin ..."         a prohibition is not a direction
 *     to take anything. Returned in `flagged` and kept, because whether to show
 *     a negative medication instruction is a clinical call this function should
 *     not make silently.
 */
const MEDICATION =
  /\b(aspirin|nitroglycerin|nitroglycerine|nitro|glyceryl\s+trinitrate|gtn|paracetamol|acetaminophen|tylenol|ibuprofen|advil|nurofen|naproxen|antacid|antacids|omeprazole|ranitidine|famotidine|h2\s*blocker|ppi|proton\s+pump\s+inhibitor|analgesia|analgesic|painkiller|pain\s+reliever|medication|medicine|medicines|meds|drug|drugs|tablet|tablets|pill|pills|capsule|capsules|inhaler|epipen|epinephrine|adrenaline|insulin|antihistamine|benadryl|apixaban|warfarin|statin|metformin|lisinopril|atorvastatin|beta\s*blocker|anticoagulant)\b/i;

// A dose pattern is itself enough: "5mg twice daily" is dosing whatever the
// noun turns out to be.
const DOSE = /\b\d+\s*(mg|mcg|ml|g|units?|tablets?|pills?|capsules?|puffs?|sprays?)\b/i;

const PROHIBITION = /\b(do\s+not|don't|never|avoid|refrain\s+from|should\s+not|must\s+not)\b/i;

// Must GOVERN the sentence, so it is anchored. "If available, chew aspirin if
// not allergic" contains an allowlist-ish word late in the clause and is still
// an instruction to chew aspirin.
const NON_ADMIN_LEAD =
  /^\s*(bring|tell|inform|report|show|carry|list|mention|note|give\s+the\s+(paramedics?|clinician|doctor|nurse))\b/i;

export function screenNextSteps(steps: string[]): {
  kept: string[];
  dropped: string[];
  flagged: string[];
} {
  const kept: string[] = [];
  const dropped: string[] = [];
  const flagged: string[] = [];
  for (const raw of steps ?? []) {
    const s = String(raw ?? '');
    if (!MEDICATION.test(s) && !DOSE.test(s)) {
      kept.push(s); // says nothing about a medication at all
      continue;
    }
    if (PROHIBITION.test(s)) {
      flagged.push(s);
      kept.push(s);
      continue;
    }
    if (NON_ADMIN_LEAD.test(s)) {
      kept.push(s);
      continue;
    }
    dropped.push(s); // fails closed
  }
  return {kept, dropped, flagged};
}

/**
 * GUARD 5, hard constraint 11. Drop red_flags the case text does not support.
 *
 * Measured live on the demo path 2026-09-17: a case saying "heavy pressure in
 * the middle of my chest ... I feel sick and I am sweating" produced
 * red_flags ['crushing chest pain','sweating','nausea','dizziness']. The
 * patient never mentioned dizziness.
 *
 * THE LEXICON IS NOT DEFINED HERE. It is generated from validate_pairs.py by
 * export_lexicon.py into finding_lexicon.json, which this reads, so a clinical
 * term is added in exactly one place. Editing the JSON by hand puts this port
 * out of step with the Python one and with the audit.
 *
 * validate_pairs.py only WARNS on this, because a human clears a warning before
 * a training pair is frozen. Here there is no human between the model and the
 * screen, so it fails closed.
 */
import lexicon from './finding_lexicon.json';

const NEG_CUE = new RegExp(
  `\\b(${lexicon.negation_cues.map(c => c.replace(/ /g, '\\s+')).join('|')})\\b`, 'i');
const CLAUSE = /[.;:!?]|\bbut\b|\bhowever\b|\balthough\b|\bwhereas\b/gi;

function mentions(text: string, phrase: string): boolean {
  return new RegExp(`\\b${phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ /g, '\\s+')}\\b`, 'i')
    .test(text);
}

function negatedBefore(text: string, phrase: string): boolean {
  const pat = new RegExp(
    `\\b${phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ /g, '\\s+')}\\b`, 'gi');
  let m: RegExpExecArray | null, found = false;
  while ((m = pat.exec(text)) !== null) {
    found = true;
    const before = text.slice(0, m.index);
    CLAUSE.lastIndex = 0;
    let start = 0, b: RegExpExecArray | null;
    while ((b = CLAUSE.exec(before)) !== null) start = b.index + b[0].length;
    if (!NEG_CUE.test(before.slice(start))) return false;
  }
  return found;
}

function assertedPoles(text: string, axis: string): string[] {
  const out: string[] = [];
  const poles = (lexicon.contradiction_axes as any)[axis];
  for (const [pole, phrases] of Object.entries(poles as Record<string, string[]>)) {
    for (const p of phrases) {
      if (!mentions(text, p)) continue;
      if (negatedBefore(text, p)) continue;
      out.push(pole);
      break;
    }
  }
  return out;
}

/** Findings the entry asserts that the case text never mentions. */
export function ungroundedFindings(entry: string, caseText: string): string[] {
  return Object.entries(lexicon.finding_synonyms as Record<string, string[]>)
    .filter(([, variants]) =>
      variants.some(v => mentions(entry, v)) &&
      !variants.some(v => mentions(caseText, v)))
    .map(([canon]) => canon);
}

/** Axes where the entry asserts the opposite pole to the case. */
export function contradictedFindings(
  entry: string, caseText: string, casePresent?: string,
): [string, string, string][] {
  const out: [string, string, string][] = [];
  for (const axis of Object.keys(lexicon.contradiction_axes)) {
    const src = casePresent !== undefined &&
      (lexicon.present_only_axes as string[]).includes(axis) ? casePresent : caseText;
    const said = new Set(assertedPoles(entry, axis));
    const inCase = new Set(assertedPoles(src, axis));
    if (!said.size || !inCase.size) continue;
    for (const pole of said)
      for (const other of inCase)
        if (pole !== other) out.push([axis, pole, other]);
  }
  return out;
}

export function screenRedFlags(
  redFlags: string[], caseText: string, casePresent?: string,
): {kept: string[]; dropped: {entry: string; why: string}[]} {
  const kept: string[] = [];
  const dropped: {entry: string; why: string}[] = [];
  for (const raw of redFlags ?? []) {
    const s = String(raw ?? '');
    const absent = ungroundedFindings(s, caseText);
    const contra = contradictedFindings(s, caseText, casePresent);
    if (absent.length || contra.length) {
      const why = [
        ...(absent.length ? [`not in the case: ${absent.join(', ')}`] : []),
        ...contra.map(([, said, inCase]) => `case says ${inCase} not ${said}`),
      ].join('; ');
      dropped.push({entry: s, why});
    } else {
      kept.push(s);
    }
  }
  return {kept, dropped};
}

/**
 * GUARD 3, hard constraint 9. Every citation key must resolve against
 * citations.csv.
 *
 * The model invents keys. Measured 2026-09-15 with no chunks in context:
 * CP-RISK-014 and MED-ANTICOAG-007, neither of which exists. Measured again
 * 2026-09-17 under prompt change set B, in a new shape: it emitted
 * "profile (CAD, nitroglycerin)" and "timeline (exertional onset, resolved
 * with rest)" as citation keys, which are not keys at all.
 *
 * A judge clicking a citation that does not resolve is worse than showing no
 * citations, so this drops rather than renders.
 *
 * THE LEADING KEY IS VALIDATED, NOT THE WHOLE STRING. Measured live 2026-09-18
 * on textbook ACS: the model cited "CP-ACS-003: Chest pain, heaviness, or
 * discomfort ...", the right key with the chunk's line appended. Exact matching
 * dropped it, the list came out empty, and the post-flight scope check refused
 * a real heart attack as out of scope in 2 runs of 4. The key is kept and the
 * appended text is not, because the expander shows the chunk's real text.
 *
 * The key must lead, after at most an opening bracket or quote (the prompt
 * writes keys as [CP-ACS-003]), and must be whole: "CP-ACS-0031" is not
 * CP-ACS-003. Prose that only mentions a key is still dropped. A key cited
 * twice is kept once. Same rule as screen_citations in 02-pairs/guards.py.
 */
const LEADING_KEY = /^[[("'`]*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?![A-Za-z0-9_-])/;

export function screenCitations(
  citations: string[],
  registry: ReadonlySet<string>,
): {kept: string[]; dropped: string[]} {
  const kept: string[] = [];
  const dropped: string[] = [];
  for (const raw of citations ?? []) {
    const entry = String(raw ?? '').trim();
    const key = LEADING_KEY.exec(entry)?.[1];
    if (key && registry.has(key)) {
      if (!kept.includes(key)) kept.push(key);
    } else {
      dropped.push(entry);
    }
  }
  return {kept, dropped};
}

/**
 * GUARD 4, hard constraint 4. follow_up_questions must be empty on a red.
 *
 * A red verdict means call for emergency help now; there is no questioning
 * round. The schema cannot express this. Measured 2026-09-17 under prompt
 * change set A: yellow-angina returned red carrying two follow-up questions,
 * the first breach in the project's recorded history, introduced by a prompt
 * edit that was fixing something else. That is the argument for holding it
 * here rather than in the prompt.
 */
export function screenFollowUps(
  urgency: string,
  questions: string[],
): {kept: string[]; dropped: string[]} {
  if (urgency === 'red' && (questions?.length ?? 0) > 0) {
    return {kept: [], dropped: [...questions]};
  }
  return {kept: questions ?? [], dropped: []};
}

/** Parse raw model text and apply every guard. */
export function applyGuards(
  raw: string,
  registry: ReadonlySet<string>,
): GuardReport {
  const parsed = parseModelJson(raw);
  const cites = screenCitations(parsed.citations ?? [], registry);
  const steps = screenNextSteps(parsed.next_steps ?? []);
  const fups = screenFollowUps(parsed.urgency, parsed.follow_up_questions ?? []);
  return {
    result: {
      ...parsed,
      citations: cites.kept,
      next_steps: steps.kept,
      follow_up_questions: fups.kept,
    },
    dropped: {
      citations: cites.dropped,
      next_steps: steps.dropped,
      follow_up_questions: fups.dropped,
    },
    flagged: {next_steps: steps.flagged},
  };
}
