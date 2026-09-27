#!/usr/bin/env node
// Runs the three demo presets through the real demo path and reports what a
// judge would SEE. Not a pass/fail check: ui_check.mjs is that. This one
// measures, so it has no exit code to read and no assertions to satisfy.
//
//   node 06-demo/preset_runs.mjs OUTDIR LABEL [RUNS]
//
// LABEL names the model on 8080, because this harness cannot ask which GGUF is
// loaded without guessing. It goes in the header, so a result file says what it
// was run against.
//
// Needs the demo server on 8770 and llama-server on 8080. It drives the page in
// headless Chrome exactly as ui_check.mjs does: clicking the preset buttons a
// judge clicks, on the profile a judge would pick. Two sources per run:
//
//   the DOM        what is on the screen: the bar, the rule line, the
//                  not-grounded block, the Checked line, the source chips
//   the saved JSON what the server decided: the verdict before and after the
//                  escalation layer, every guard removal with its field, and
//                  the timings
//
// The DOM is the claim; the JSON is why. Where they disagree the DOM wins,
// because that is the thing in front of the judge.
//
// It writes assessments into 06-demo/data like any other use of the demo.
// Snapshot that directory first if the history matters.

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const APP = (process.env.FIELD_URL || "http://127.0.0.1:8770").replace(/\/+$/, "");
const PORT = 9334;                       // not ui_check's 9333, so both can run
const DESKTOP = { width: 1440, height: 900, mobile: false, deviceScaleFactor: 1 };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const out = [];
const say = s => { console.log(s); out.push(s); };

// The three beats, as a judge reaches them: the preset button, and the person
// picked before clicking it. Preset 3 is a pairing and sends by itself.
const SCENARIOS = [
  { n: 1, preset: 0, person: "self", who: "You",
    name: "Crushing chest pressure", beat: "beat 2, the red result", pair: false },
  { n: 2, preset: 1, person: "aunt", who: "Aunt Sue",
    name: "Sharp pain when breathing in", beat: "beat 3, the guards firing", pair: false },
  { n: 3, preset: 2, person: "self", who: "You vs Mum",
    name: "Indigestion (You and Mum)", beat: "beat 3, same symptom two people", pair: true },
];

async function launch() {
  const profile = mkdtempSync(join(tmpdir(), "preset-runs-"));
  const proc = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`, "--no-first-run", "--no-default-browser-check",
    "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
  for (let i = 0; i < 100; i++) {
    try { await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); proc.profile = profile; return proc; }
    catch { await sleep(100); }
  }
  throw new Error("Chrome did not start");
}

async function tab() {
  const t = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const waiting = new Map();
  ws.onmessage = m => {
    const msg = JSON.parse(m.data);
    if (msg.id && waiting.has(msg.id)) { waiting.get(msg.id)(msg); waiting.delete(msg.id); }
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const n = ++id;
    waiting.set(n, msg => msg.error ? rej(new Error(`${method}: ${msg.error.message}`)) : res(msg.result));
    ws.send(JSON.stringify({ id: n, method, params }));
  });
  await send("Page.enable");
  await send("Runtime.enable");
  const page = {
    send,
    size: d => send("Emulation.setDeviceMetricsOverride", d),
    async go(path) {
      await send("Page.navigate", { url: APP + path });
      await page.until("document.readyState === 'complete' && !document.querySelector('.loading')");
      await sleep(350);
    },
    async eval(expr) {
      const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(`${expr.slice(0, 80)}: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
      return r.result.value;
    },
    async until(expr, timeout = 300000, every = 250) {
      const t0 = Date.now();
      while (Date.now() - t0 < timeout) {
        if (await page.eval(`!!(${expr})`).catch(() => false)) return Date.now() - t0;
        await sleep(every);
      }
      throw new Error(`timed out waiting for ${expr}`);
    },
    click: sel => page.eval(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) throw new Error("no ${sel.replace(/"/g, "")}"); e.click(); return true; })()`),
    async shot(file) {
      await page.eval(`(() => { const s = document.createElement("style"); s.id = "shot-static";
        s.textContent = ".top,.side,.composer,.preview{position:static!important}"; document.head.append(s); return true; })()`);
      const m = await send("Page.getLayoutMetrics");
      const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
        clip: { x: 0, y: 0, width: m.cssContentSize.width, height: Math.min(m.cssContentSize.height, 6000), scale: 1 } });
      writeFileSync(file, Buffer.from(r.data, "base64"));
      await page.eval(`document.getElementById("shot-static")?.remove() || true`);
    },
    close: () => { ws.close(); return fetch(`http://127.0.0.1:${PORT}/json/close/${t.id}`); },
  };
  return page;
}

// WHAT IS ON THE SCREEN. One entry per side, read off the rendered answer, not
// off the model's JSON. `.turn.pair` holds two `.side-ans`; a single assessment
// is one `.turn`, which is treated as one side so both shapes read the same.
const SCRAPE = `(() => {
  const txt = e => (e ? e.innerText.replace(/\\u00a0/g, " ").trim() : "");
  const turn = [...document.querySelectorAll("#thread .turn")].pop();
  const sides = turn.querySelectorAll(".side-ans").length
    ? [...turn.querySelectorAll(".side-ans")] : [turn];
  return sides.map(s => {
    const bar = s.querySelector(".bar");
    return {
      who: txt(s.querySelector(".who")) || null,
      bar: bar ? (bar.className.match(/bar (\\w+)/) || [])[1] : null,
      barText: txt(bar).replace(/\\n+/g, " / "),
      rules: [...s.querySelectorAll(".rules .rule")].map(e => txt(e).replace(/\\n+/g, " / ")),
      rulesText: txt(s.querySelector(".rules")).replace(/\\n+/g, " / "),
      ungrounded: !!s.querySelector(".ungrounded"),
      ungroundedText: txt(s.querySelector(".ungrounded")).replace(/\\n+/g, " / "),
      checked: txt(s.querySelector(".checked")).replace(/\\n+/g, " / "),
      cites: [...s.querySelectorAll(".sources .cite")].map(e => e.dataset.k),
      sections: [...s.querySelectorAll(".sec h3")].map(txt),
      struck: [...s.querySelectorAll(".gone")].map(e => txt(e).replace(/\\n+/g, " ").slice(0, 150)),
      error: txt(s.querySelector(".err-panel")).replace(/\\n+/g, " / ") || null,
      full: txt(s),
    };
  });
})()`;

function guardLines(ev) {
  // Every removal the guards made, field by field, with the reason the field
  // name carries. Empty fields are not printed: a run with nothing removed
  // should say so in one line, not in eight.
  const why = {
    citations: "citation not in the registry (c9)",
    red_flags: "finding not grounded in the case text (c11)",
    next_steps: "instructs medication (c12)",
    follow_up_questions: "questions cleared off a red (c4)",
    rationale_urgency: "rationale written for the model's lower verdict (c16)",
    next_steps_urgency: "steps written for the model's lower verdict (c16)",
  };
  const d = ev.dropped || {};
  const lines = [];
  for (const [field, items] of Object.entries(d)) {
    const list = Array.isArray(items) ? items : (items ? [items] : []);
    for (const x of list) {
      lines.push(`      - ${field}: ${JSON.stringify(String(x)).slice(0, 160)}`);
    }
    if (list.length) lines.push(`        why: ${why[field] || field}`);
  }
  for (const [field, items] of Object.entries(ev.flagged || {})) {
    for (const f of items || []) {
      lines.push(`      ~ FLAGGED, kept in ${field}: ${JSON.stringify(String(f)).slice(0, 160)}`);
    }
  }
  return lines;
}

function report(sc, run, dom, conv, wall) {
  say(`\n  RUN ${run}  ${sc.name}  (${wall.toFixed(1)} s wall, one click to answer)`);
  const turns = (conv.sides || []).map(s => (s.turns || [])[0]).filter(Boolean);
  turns.forEach((t, i) => {
    const d = dom[i] || {};
    const ev = t.event || {};
    const person = (conv.sides[i].profile || {}).label || d.who || `side ${i}`;
    say(`    ${person}`);
    say(`      SCREEN: ${d.bar ? d.bar.toUpperCase() : "no bar"}  "${d.barText}"`);
    if (t.kind === "refused") {
      say(`      REFUSED: ${ev.reason || ev.message || "?"}`);
      if (ev.urgency_withheld) say(`      withheld verdict: ${ev.urgency_withheld}`);
      if (ev.max_cosine !== undefined) say(`      max cosine ${ev.max_cosine} against the 0.25 floor`);
      say(`      grounded: n/a, nothing was shown`);
    } else if (t.kind === "error") {
      say(`      ERROR: ${ev.message || "?"}`);
    } else {
      const e = ev.escalation || {};
      const model = e.original || (ev.result || {}).urgency;
      say(`      model said ${model}, shown ${((ev.result || {}).urgency) || "?"}` +
          (e.changed ? `  (RAISED by the profile layer)` : ""));
      say(`      grounded: ${ev.ungrounded ? "NO, flagged not-grounded" : "yes"}` +
          `, ${d.cites.length} source chip(s)${d.cites.length ? ": " + d.cites.join(", ") : ""}`);
      const fired = e.fired || [];
      if (!fired.length) say(`      rules: none fired`);
      for (const f of fired) {
        say(`      rule ${f.rule} ${f.status.toUpperCase()}: ${f.name}`);
        say(`        fact "${f.fact}" + symptom "${f.symptom}"  -> ${f.keys.join(", ")}`);
      }
      if (d.rulesText) say(`      rule line on screen: "${d.rulesText.slice(0, 200)}"`);
      if (ev.ungrounded) say(`      not-grounded line: "${d.ungroundedText.slice(0, 160)}"`);
      const g = guardLines(ev);
      say(`      guards removed: ${g.length ? "" : "nothing"}`);
      g.forEach(l => say(l));
      if (d.struck.length) say(`      struck through on screen: ${d.struck.length} block(s)`);
      say(`      sections shown: ${d.sections.join(", ") || "none"}`);
      say(`      timing: retrieval ${ev.retrieval_ms} ms, first token ${ev.ttft_ms} ms, ` +
          `generate ${ev.gen_ms} ms, guards ${ev.check_ms} ms, total ${ev.total_ms} ms`);
      const ti = ev.timings || {};
      if (ti.predicted_per_second) {
        say(`      rates: prompt ${(ti.prompt_per_second || 0).toFixed(1)} tok/s, ` +
            `generate ${ti.predicted_per_second.toFixed(1)} tok/s, ` +
            `${ti.predicted_n} tokens out, ${ev.retrieved_tokens} tokens of chunk in`);
      }
    }
    if (d.checked) say(`      checked line: "${d.checked.slice(0, 200)}"`);
  });
  return turns.map((t, i) => ({
    person: (conv.sides[i].profile || {}).label,
    kind: t.kind,
    bar: (dom[i] || {}).bar,
    model: ((t.event || {}).escalation || {}).original || ((t.event || {}).result || {}).urgency,
    shown: ((t.event || {}).result || {}).urgency,
    raised: !!((t.event || {}).escalation || {}).changed,
    ungrounded: !!(t.event || {}).ungrounded,
    cites: (dom[i] || {}).cites || [],
    rules: (((t.event || {}).escalation || {}).fired || []).map(f => `${f.rule}:${f.status}`),
    removed: guardLines(t.event || {}).filter(l => l.startsWith("      - ")).length,
    secs: ((t.event || {}).total_ms || 0) / 1000,
  }));
}

const [dir = ".", label = "unlabelled", runsArg = "3"] = process.argv.slice(2);
const RUNS = Number(runsArg);
mkdirSync(dir, { recursive: true });
const chrome = await launch();
const summary = [];
try {
  const health = await (await fetch(`${APP}/api/health`)).json();
  say(`# The three demo presets through the real demo path`);
  say(`#`);
  say(`# date    ${new Date().toISOString()}`);
  say(`# model   ${label}   (on llama-server at 127.0.0.1:8080)`);
  say(`# path    headless Chrome -> 06-demo/server.py on 8770 -> llama-server on 8080`);
  say(`# corpus  ${health.sources} chunks, registry ${health.registry}, topics ${health.topics.join(", ")}`);
  say(`# server  ${health.slots} slots of ${health.n_ctx} tokens`);
  say(`# runs    ${RUNS} per preset, each a fresh assessment, one click to send`);
  say(`# NOTE    SCREEN is what the page rendered. Everything under it is the`);
  say(`#         saved assessment, which is why the page rendered it.`);

  const p = await tab();
  await p.size(DESKTOP);
  for (const sc of SCENARIOS) {
    say(`\n${"=".repeat(78)}`);
    say(`PRESET ${sc.n}: ${sc.name}   on ${sc.who}   (${sc.beat})`);
    say(`${"=".repeat(78)}`);
    for (let run = 1; run <= RUNS; run++) {
      await p.go(`/?p=${sc.person}`);
      const t0 = Date.now();
      await p.click(`[data-preset="${sc.preset}"]`);
      if (sc.pair) {
        // The pairing sends by itself: one click is the whole beat.
        await p.until("location.pathname.startsWith('/c/') && document.querySelector('[data-live]')", 30000);
      } else {
        await p.click("#send");
      }
      const want = sc.pair ? 2 : 1;
      await p.until(`document.querySelectorAll("#thread .bar, #thread .err-panel, #thread .full").length >= ${want}
        && !document.querySelector("[data-live] .steps4") && !document.querySelector("[data-live]")`);
      await sleep(800);
      const wall = (Date.now() - t0) / 1000;
      const cid = await p.eval("location.pathname.split('/')[2]");
      const conv = await (await fetch(`${APP}/api/conversations/${cid}`)).json();
      const dom = await p.eval(SCRAPE);
      summary.push({ preset: sc.n, run, sides: report(sc, run, dom, conv, wall), wall });
      const shot = join(dir, `preset${sc.n}-run${run}.png`);
      await p.shot(shot);
      say(`      saved ${shot}   assessment ${cid}`);
    }
  }
  await p.close();

  say(`\n${"=".repeat(78)}`);
  say(`SUMMARY, what a judge sees`);
  say(`${"=".repeat(78)}`);
  for (const sc of SCENARIOS) {
    const rows = summary.filter(s => s.preset === sc.n);
    say(`\nPRESET ${sc.n}: ${sc.name}`);
    for (const r of rows) {
      for (const s of r.sides) {
        const shown = s.kind === "refused" ? "REFUSED" : (s.bar || "?").toUpperCase();
        say(`  run ${r.run}  ${(s.person || "").padEnd(8)} ${shown.padEnd(8)}` +
            ` model=${String(s.model || "-").padEnd(7)}` +
            ` ${s.raised ? "RAISED " : "       "}` +
            ` ${s.ungrounded ? "not-grounded" : "grounded    "}` +
            ` cites=${s.cites.length} removed=${s.removed}` +
            ` rules=${s.rules.join(",") || "-"}  ${s.secs.toFixed(1)}s`);
      }
    }
    const all = rows.flatMap(r => r.sides);
    const tally = {};
    for (const s of all) {
      const k = `${s.person}: ${s.kind === "refused" ? "REFUSED" : (s.bar || "?").toUpperCase()}`;
      tally[k] = (tally[k] || 0) + 1;
    }
    say(`  tally: ${Object.entries(tally).map(([k, v]) => `${k} ${v}/${rows.length}`).join("   ")}`);
    const secs = rows.map(r => r.wall);
    say(`  wall clock, click to both answers: ${secs.map(s => s.toFixed(1)).join(", ")} s`);
  }
} catch (e) {
  say(`\nFAILED: ${e.stack || e.message}`);
} finally {
  chrome.kill();
  await sleep(500);
  if (chrome.profile) rmSync(chrome.profile, { recursive: true, force: true });
  writeFileSync(join(dir, "report.txt"), out.join("\n") + "\n");
  console.log(`\nsaved ${join(dir, "report.txt")}`);
}
