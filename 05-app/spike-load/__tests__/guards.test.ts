/**
 * Every fixture here is a REAL string a run produced, with the run file named.
 * Invented test data would have passed the first version of the medication
 * guard; the real outputs did not, which is the point.
 */
import {
  applyGuards,
  parseModelJson,
  screenCitations,
  screenFollowUps,
  screenNextSteps,
  screenRedFlags,
} from '../guards';

// 22 frozen keys. Only the ones the tests touch are listed.
const REGISTRY = new Set([
  'CP-ACS-001', 'CP-ACS-002', 'CP-ACS-003',
  'CP-ANG-001', 'CP-ANG-002',
  'CP-GERD-001', 'CP-GERD-002',
  'CP-PERI-002', 'CP-PLEU-001', 'CP-DIFF-001',
]);

// Shared with 02-pairs/guards.py. A change to either implementation that breaks
// a shared expectation fails that side's suite. Add cases to the JSON, not here.
// The copy in this directory exists because Metro cannot resolve outside the
// project root; `npm run sync-fixtures` refreshes it from 02-pairs.
import fixtures from '../guard_fixtures.json';

describe('shared fixtures, parity with 02-pairs/guards.py', () => {
  it.each(fixtures.parse.map(c => [c.name, c] as const))(
    'parse: %s', (_n, c: any) => {
      let threw = false;
      try { JSON.parse(c.raw); } catch { threw = true; }
      expect(threw).toBe(c.bare_parse_throws);
      expect(parseModelJson(c.raw).urgency).toBe(c.urgency);
    });

  it.each(fixtures.next_steps.map(c => [c.name, c] as const))(
    'next_steps: %s', (_n, c: any) => {
      const {kept, dropped, flagged} = screenNextSteps(c.steps);
      expect(kept).toEqual(c.kept);
      expect(dropped).toEqual(c.dropped);
      expect(flagged).toEqual(c.flagged);
    });

  it.each(fixtures.red_flags.map(c => [c.name, c] as const))(
    'red_flags: %s', (_n, c: any) => {
      const {kept, dropped} = screenRedFlags(c.red_flags, c.case_text, c.case_present);
      expect(kept).toEqual(c.kept);
      expect(dropped.map((d: any) => d.entry)).toEqual(c.dropped);
    });

  it.each(fixtures.citations.map(c => [c.name, c] as const))(
    'citations: %s', (_n, c: any) => {
      const {kept, dropped} = screenCitations(c.citations, REGISTRY);
      expect(kept).toEqual(c.kept);
      expect(dropped).toEqual(c.dropped);
    });

  it.each(fixtures.follow_ups.map(c => [c.name, c] as const))(
    'follow_ups: %s', (_n, c: any) => {
      const {kept, dropped} = screenFollowUps(c.urgency, c.questions);
      expect(kept).toEqual(c.kept);
      expect(dropped).toEqual(c.dropped);
    });
});

describe('guard 1: chat-template prefix', () => {
  // 2026-09-17-load-spike-step2.txt, through llama.rn on the simulator.
  it('strips <|im_start|>assistant, which JSON.parse cannot survive', () => {
    const raw = '<|im_start|>assistant\n{"urgency":"red","rationale":"x"}';
    expect(() => JSON.parse(raw)).toThrow(); // the bug, stated
    expect(parseModelJson(raw).urgency).toBe('red');
  });

  it('leaves clean JSON alone', () => {
    expect(parseModelJson('{"urgency":"green"}').urgency).toBe('green');
  });

  it('handles markdown fences the prompt forbids', () => {
    expect(parseModelJson('```json\n{"urgency":"yellow"}\n```').urgency)
      .toBe('yellow');
  });

  it('throws rather than half-parsing garbage', () => {
    expect(() => parseModelJson('the model refused')).toThrow(/no JSON object/);
  });
});

describe('guard 2: constraint 12, no medication administration', () => {
  it('drops the measured nitroglycerin instruction', () => {
    // 2026-09-17-no-chunk-angina.txt
    const {kept, dropped} = screenNextSteps([
      'Call emergency services immediately',
      'Administer nitroglycerin if prescribed and available',
      'Monitor for recurrence or worsening symptoms',
    ]);
    expect(dropped).toEqual(['Administer nitroglycerin if prescribed and available']);
    expect(kept).toHaveLength(2);
  });

  it('drops the measured aspirin instruction', () => {
    // 2026-09-17-format3-probe.txt, red-acs
    const {dropped} = screenNextSteps([
      'Call emergency services immediately',
      'Do not drive yourself to the hospital',
      'If available, chew aspirin if not allergic',
    ]);
    expect(dropped).toEqual(['If available, chew aspirin if not allergic']);
  });

  it('drops the measured antacid instruction, which has no dangerous drug in it', () => {
    // 2026-09-17-format3-probe.txt, green-gerd
    const {dropped, kept} = screenNextSteps([
      'Take over-the-counter antacid or H2 blocker as directed',
      'Avoid large meals, caffeine, and alcohol',
      'Elevate head of bed if symptoms recur at night',
    ]);
    expect(dropped).toHaveLength(1);
    expect(kept).toEqual([
      'Avoid large meals, caffeine, and alcohol',
      'Elevate head of bed if symptoms recur at night',
    ]);
  });

  it("drops the worked example's own analgesia line, which has no verb", () => {
    // 02-pairs/system_prompt.txt. The prompt teaches this by example.
    const {dropped} = screenNextSteps([
      'Rest, ice, compression and elevation for the first 48 hours',
      'Over the counter analgesia as directed on the packet',
      'Seek assessment if unable to bear weight after 48 hours or if numbness develops',
    ]);
    expect(dropped).toEqual(['Over the counter analgesia as directed on the packet']);
  });

  it('keeps reporting and carrying, which are not dosing', () => {
    const {kept, dropped} = screenNextSteps([
      'Bring your medications with you',
      'Tell the paramedics you take apixaban',
    ]);
    expect(dropped).toEqual([]);
    expect(kept).toHaveLength(2);
  });

  it('flags a prohibition and keeps it, rather than deciding silently', () => {
    // 2026-09-17-format3-postfix.txt, yellow-angina
    const {kept, dropped, flagged} = screenNextSteps([
      'Do not take nitroglycerin if unsure of exact dose or timing',
    ]);
    expect(dropped).toEqual([]);
    expect(flagged).toHaveLength(1);
    expect(kept).toHaveLength(1);
  });

  it('drops a bare dose even with no drug name', () => {
    expect(screenNextSteps(['Give 300 mg now']).dropped).toHaveLength(1);
  });
});

describe('guard 3: constraint 9, citation keys must resolve', () => {
  it('drops the measured pseudo-keys from prompt change set B', () => {
    // 2026-09-17-format3-rule3.txt, yellow-angina
    const {kept, dropped} = screenCitations(
      ['CP-ANG-001', 'CP-ANG-002',
       'profile (CAD, nitroglycerin)',
       'timeline (exertional onset, resolved with rest)'],
      REGISTRY,
    );
    expect(kept).toEqual(['CP-ANG-001', 'CP-ANG-002']);
    expect(dropped).toHaveLength(2);
  });

  it('drops the measured invented keys from 2026-09-15', () => {
    const {kept, dropped} = screenCitations(
      ['CP-RISK-014', 'MED-ANTICOAG-007'], REGISTRY);
    expect(kept).toEqual([]);
    expect(dropped).toEqual(['CP-RISK-014', 'MED-ANTICOAG-007']);
  });

  it('keeps a wholly valid list untouched', () => {
    expect(screenCitations(['CP-ACS-001', 'CP-ACS-003'], REGISTRY).kept)
      .toEqual(['CP-ACS-001', 'CP-ACS-003']);
  });
});

describe('guard 4: constraint 4, no questions on a red', () => {
  it('clears the measured breach from prompt change set A', () => {
    // 2026-09-17-format3-postfix.txt, yellow-angina came back red WITH these
    const {kept, dropped} = screenFollowUps('red', [
      'Is the chest tightness recurring or worsening?',
      'Have you taken nitroglycerin today?',
    ]);
    expect(kept).toEqual([]);
    expect(dropped).toHaveLength(2);
  });

  it('leaves questions on a yellow alone', () => {
    const qs = ['Any vomiting blood or black tarry stools?'];
    expect(screenFollowUps('yellow', qs).kept).toEqual(qs);
  });
});

describe('applyGuards end to end', () => {
  it('cleans a red verdict carrying all four defects at once', () => {
    const raw =
      '<|im_start|>assistant\n' +
      JSON.stringify({
        urgency: 'red',
        rationale: 'Central pressure at rest beyond 20 minutes.',
        red_flags: ['Chest pressure radiating to jaw'],
        next_steps: [
          'Call emergency services immediately',
          'Administer nitroglycerin if prescribed and available',
        ],
        citations: ['CP-ACS-001', 'profile (CAD, nitroglycerin)'],
        follow_up_questions: ['Have you taken nitroglycerin today?'],
      });

    const {result, dropped} = applyGuards(raw, REGISTRY);

    expect(result.urgency).toBe('red');
    expect(result.next_steps).toEqual(['Call emergency services immediately']);
    expect(result.citations).toEqual(['CP-ACS-001']);
    expect(result.follow_up_questions).toEqual([]);
    expect(dropped.next_steps).toHaveLength(1);
    expect(dropped.citations).toEqual(['profile (CAD, nitroglycerin)']);
    expect(dropped.follow_up_questions).toHaveLength(1);
    // red_flags are untouched: grounding is constraint 11 and is not a
    // string-matching job. See audit_grounding.py.
    expect(result.red_flags).toHaveLength(1);
  });
});
