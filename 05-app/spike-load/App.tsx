/**
 * Epic 5 load spike, step 2.
 *
 * Step 1 settled architecture support by reading llama.rn's vendored source.
 * This calls initLlama for the first time in the project's life. The question
 * is not quality, it is whether the binding loads a nemotron_h GGUF at all,
 * how long it takes, what it costs in memory, and what one completion costs in
 * wall clock.
 *
 * n_gpu_layers is 0 deliberately. The iOS simulator has no Metal, so CPU is
 * the demo condition and every latency number that matters is a CPU number.
 *
 * Results render on screen so a host screenshot can read them, and go to
 * console with a [SPIKE] prefix so an os_log stream can read them too. Peak
 * RSS is measured from the host by polling the app process, not from here.
 */
import React, {useEffect, useRef, useState} from 'react';
import {SafeAreaView, ScrollView, StyleSheet, Text, View} from 'react-native';
import {initLlama} from 'llama.rn';
import {MODEL_PATH} from './modelPath';
import {applyGuards} from './guards';
import {REGISTRY} from './registry';
import {SYSTEM, USER, SCHEMA, TEMPERATURE, MAX_TOKENS} from './spikePrompt';

type Line = {k: string; v: string};

// The simulator shares host networking, so the app can hand its record to a
// listener on the Mac. 127.0.0.1 resolves to the host from inside the sim.
const RESULT_SINK = 'http://127.0.0.1:8123/result';

export default function App() {
  const [lines, setLines] = useState<Line[]>([]);
  const [done, setDone] = useState(false);
  const [sent, setSent] = useState('');

  // Mirrors every push so the POSTed record carries the whole run, including
  // the fields the screen cuts off. A ref, not a plain object: push triggers a
  // re-render, and a per-render object would leave the effect writing into a
  // stale one. It happens to work through the effect's closure, which is
  // exactly the kind of accident that breaks when someone adds a dependency.
  const recordRef = useRef<Record<string, any>>({
    captured_at: new Date().toISOString(),
  });

  const push = (k: string, v: string) => {
    console.log(`[SPIKE] ${k}: ${v}`);
    recordRef.current[k] = v;
    setLines(prev => [...prev, {k, v}]);
  };

  useEffect(() => {
    let ctx: any = null;
    (async () => {
      try {
        push('model_path', MODEL_PATH);

        // LOAD
        const t0 = Date.now();
        ctx = await initLlama({
          model: MODEL_PATH,
          n_gpu_layers: 0, // simulator has no Metal; CPU is the demo condition
          n_ctx: 4096,
          use_mlock: false,
        });
        const loadMs = Date.now() - t0;
        push('LOADED', 'yes');
        push('load_ms', String(loadMs));
        push('load_s', (loadMs / 1000).toFixed(1));

        // What did it actually load? If the arch mapping were wrong this is
        // where it would show, rather than in a clean-looking failure.
        try {
          const m = ctx.model || {};
          push('n_params', String(m.nParams ?? m.n_params ?? 'unknown'));
          push('n_embd', String(m.nEmbd ?? m.n_embd ?? 'unknown'));
          push('desc', String(m.desc ?? 'unknown'));
          if (m.metadata && m.metadata['general.architecture']) {
            push('arch', String(m.metadata['general.architecture']));
          }
        } catch (e: any) {
          push('model_info_error', String(e?.message ?? e));
        }

        // ONE COMPLETION, demo shape.
        const c0 = Date.now();
        const res = await ctx.completion({
          messages: [
            {role: 'system', content: SYSTEM},
            {role: 'user', content: USER},
          ],
          response_format: {
            type: 'json_schema',
            json_schema: {name: 'triage', schema: SCHEMA},
          },
          temperature: TEMPERATURE,
          n_predict: MAX_TOKENS,
          // Hard constraint 5: reasoning OFF, and it has to be asked for on
          // every call. Nothing warns you if it is missing.
          chat_template_kwargs: {enable_thinking: false},
        });
        const compMs = Date.now() - c0;

        push('completion_ms', String(compMs));
        push('completion_s', (compMs / 1000).toFixed(1));
        const tim = res.timings || {};
        push('prompt_n', String(tim.prompt_n ?? 'n/a'));
        push('prompt_ms', String(Math.round(tim.prompt_ms ?? 0)));
        push('prompt_tok_per_s', String((tim.prompt_per_second ?? 0).toFixed(1)));
        push('predicted_n', String(tim.predicted_n ?? 'n/a'));
        push('predicted_tok_per_s', String((tim.predicted_per_second ?? 0).toFixed(2)));
        push('reasoning_content_len', String((res.reasoning_content || '').length));

        // The four app-logic guards, run against real model output rather than
        // only against fixtures. Guard 1 is load-bearing here: llama.rn returns
        // the chat-template header on the front of `text`, so a bare
        // JSON.parse throws.
        const raw = String(res.text ?? '');
        push('raw_head', raw.slice(0, 60));
        try {
          JSON.parse(raw);
          push('bare_JSON_parse', 'succeeded (no template prefix this time)');
        } catch (e: any) {
          push('bare_JSON_parse', `THREW: ${String(e?.message ?? e).slice(0, 80)}`);
        }
        try {
          const {result, dropped, flagged} = applyGuards(raw, REGISTRY);
          push('guarded_urgency', result.urgency);
          push('guarded_citations', JSON.stringify(result.citations));
          push('guarded_next_steps', JSON.stringify(result.next_steps));
          push('guarded_follow_ups', JSON.stringify(result.follow_up_questions));
          push('dropped_citations', JSON.stringify(dropped.citations));
          push('dropped_next_steps', JSON.stringify(dropped.next_steps));
          push('dropped_follow_ups', JSON.stringify(dropped.follow_up_questions));
          push('flagged_next_steps', JSON.stringify(flagged.next_steps));
        } catch (e: any) {
          push('GUARDS_FAILED', String(e?.message ?? e));
        }
        push('text', raw.slice(0, 500));
        recordRef.current.raw_text_full = raw; // the screen truncates; the file must not
        setDone(true);
      } catch (e: any) {
        push('FAILED', String(e?.message ?? e));
        setDone(true);
      } finally {
        // Results must not live only on a screen. The first Release run lost
        // its dropped_* fields below the fold, and a simulator screenshot
        // cannot be scrolled from the host. There is no filesystem API here
        // (see modelPath.ts), so the host listener writes the file:
        //   python 05-app/spike-load/collect_results.py
        try {
          await fetch(RESULT_SINK, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(recordRef.current),
          });
          setSent('sent to ' + RESULT_SINK);
        } catch (e: any) {
          // Never fail the run over the sink. The screen is still the fallback.
          setSent('POST failed, screen only: ' + String(e?.message ?? e));
        }
        // Leave the context alive; releasing it would move the RSS peak the
        // host poller is trying to catch.
      }
    })();
  }, []);

  return (
    <SafeAreaView style={styles.root}>
      <Text style={styles.h1}>llama.rn load spike{done ? ' [DONE]' : ' [running]'}</Text>
      {sent ? <Text style={styles.sent}>{sent}</Text> : null}
      <ScrollView>
        {lines.map((l, i) => (
          <View key={i} style={styles.row}>
            <Text style={styles.k}>{l.k}</Text>
            <Text style={styles.v}>{l.v}</Text>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: '#0b0b0d', paddingHorizontal: 12},
  h1: {color: '#7ef0a0', fontSize: 15, fontWeight: '700', paddingVertical: 8},
  row: {marginBottom: 6},
  sent: {color: '#f0c674', fontSize: 11, fontFamily: 'Menlo', paddingBottom: 6},
  k: {color: '#8ab4f8', fontSize: 11, fontFamily: 'Menlo'},
  v: {color: '#e8e8ea', fontSize: 12, fontFamily: 'Menlo'},
});
