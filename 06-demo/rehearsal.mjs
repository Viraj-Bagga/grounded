#!/usr/bin/env node
// THE REHEARSAL. One run, in the order a judge meets it, timed and
// screenshotted at every step.
//
//   node 06-demo/rehearsal.mjs OUTDIR
//
// This is NOT a unit test and it does not assert its way to a pass. It walks
// the whole product once and reports what a five minute desk visit actually
// looks like: what each step cost in wall clock, what the screen said, and
// anything that broke. A step that fails is recorded and the rehearsal keeps
// going, because the question being asked is "what happens at the desk", and
// at the desk nothing stops to re-run.
//
// START FROM EMPTY. Clear 06-demo/data/{conversations,queue.json,sync.json,
// packs} and 06-demo/base-data first, and restart both servers, or the counts
// in steps 7 and 8 are meaningless and step 5 has nothing to download.
//
// NEEDS: llama-server on 8080 with BOTH SLOTS IDLE, the field app on 8770,
// base on 8781, and the distribution node on 8790. It checks all four and
// refuses to start otherwise, because a rehearsal that is really a
// misconfiguration is worse than no rehearsal.

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const FIELD = (process.env.FIELD_URL || "http://127.0.0.1:8770").replace(/\/+$/, "");
const BASE = "http://127.0.0.1:8781";
const NODE = "http://127.0.0.1:8790";
const PORT = 9350;
const DESKTOP = { width: 1440, height: 900, mobile: false, deviceScaleFactor: 1 };
const PHONE = { width: 390, height: 844, mobile: true, deviceScaleFactor: 2 };
const sleep = ms => new Promise(r => setTimeout(r, ms));

const OUT = process.argv[2] || "06-demo/results/rehearsal";
mkdirSync(OUT, { recursive: true });

const log = [];
const say = s => { console.log(s); log.push(s); };
const steps = [];
const broke = [];
let shotN = 0;

// ------------------------------------------------------------------ plumbing

async function portUp(url) {
  try { await fetch(url, { signal: AbortSignal.timeout(2500) }); return true; }
  catch { return false; }
}

async function launch() {
  const profile = mkdtempSync(join(tmpdir(), "rehearsal-"));
  const proc = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`, "--no-first-run", "--no-default-browser-check",
    "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
  for (let i = 0; i < 120; i++) {
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
  const p = {
    send,
    async size(d) {
      await send("Emulation.setDeviceMetricsOverride", d);
      await send("Emulation.setTouchEmulationEnabled", { enabled: d.mobile });
    },
    async goto(url) {
      await send("Page.navigate", { url });
      await p.until("document.readyState === 'complete' && !document.querySelector('.loading')", 60000);
      await sleep(400);
    },
    async eval(expr) {
      const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(`${expr.slice(0, 70)}: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
      return r.result.value;
    },
    async until(expr, timeout = 120000, every = 250) {
      const t0 = Date.now();
      while (Date.now() - t0 < timeout) {
        if (await p.eval(`!!(${expr})`).catch(() => false)) return Date.now() - t0;
        await sleep(every);
      }
      throw new Error(`timed out after ${(timeout / 1000).toFixed(0)}s waiting for ${expr.slice(0, 90)}`);
    },
    click: sel => p.eval(`(() => { const e = document.querySelector(${JSON.stringify(sel)});
      if (!e) throw new Error("nothing matches ${sel.replace(/"/g, "")}"); e.click(); return true; })()`),
    type: (sel, text) => p.eval(`(() => { const e = document.querySelector(${JSON.stringify(sel)});
      e.focus(); e.value = ${JSON.stringify(text)};
      e.dispatchEvent(new Event("input", { bubbles: true })); return true; })()`),
    text: sel => p.eval(`document.querySelector(${JSON.stringify(sel)})?.innerText ?? ""`),
    count: sel => p.eval(`document.querySelectorAll(${JSON.stringify(sel)}).length`),
    async shot(name, full = true) {
      const file = join(OUT, `${String(++shotN).padStart(2, "0")}-${name}.png`);
      if (full) await p.eval(`(() => { const s = document.createElement("style"); s.id = "shot-static";
        s.textContent = ".top,.side,.composer,.preview{position:static!important}";
        document.head.append(s); return true; })()`);
      const m = await send("Page.getLayoutMetrics");
      const clip = full
        ? { x: 0, y: 0, width: m.cssContentSize.width, height: Math.min(m.cssContentSize.height, 6000), scale: 1 }
        : undefined;
      const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: !!full, ...(clip ? { clip } : {}) });
      writeFileSync(file, Buffer.from(r.data, "base64"));
      if (full) await p.eval(`document.getElementById("shot-static")?.remove() || true`);
      return file;
    },
    close: () => { ws.close(); return fetch(`http://127.0.0.1:${PORT}/json/close/${t.id}`); },
  };
  return p;
}

// A step times itself, records what it found, and never stops the rehearsal.
async function step(n, title, fn) {
  const t0 = Date.now();
  say(`\n${"─".repeat(72)}\nSTEP ${n}. ${title}`);
  let note = "";
  try {
    note = (await fn()) || "";
  } catch (e) {
    note = `BROKE: ${e.message}`;
    broke.push(`step ${n} (${title}): ${e.message}`);
  }
  const secs = (Date.now() - t0) / 1000;
  steps.push({ n, title, secs, broke: note.startsWith("BROKE") });
  for (const line of String(note).split("\n")) if (line) say(`    ${line}`);
  say(`    ⏱  ${secs.toFixed(1)} s`);
  return secs;
}

// What the page is showing for one answer, as a judge would read it.
const READ_SIDES = `(() => {
  const txt = e => (e ? e.innerText.replace(/\\u00a0/g, " ").trim() : "");
  const turn = [...document.querySelectorAll("#thread .turn")].pop();
  if (!turn) return [];
  const sides = turn.querySelectorAll(".side-ans").length
    ? [...turn.querySelectorAll(".side-ans")] : [turn];
  return sides.map(s => {
    const bar = s.querySelector(".bar");
    return {
      who: txt(s.querySelector(".who")) || null,
      bar: bar ? (bar.className.match(/bar (\\w+)/) || [])[1] : null,
      barText: txt(bar).replace(/\\n+/g, " / "),
      rule: txt(s.querySelector(".rules")).replace(/\\n+/g, " / ").slice(0, 140),
      ungrounded: !!s.querySelector(".ungrounded"),
      // Since the overhaul (2026-09-27) a source shows its publisher; the key
      // rides on the button, and the answer's own sources are under Sources.
      cites: [...s.querySelectorAll(".sources .cite")].map(e => e.dataset.k),
      checked: txt(s.querySelector(".checked")).replace(/\\n+/g, " / "),
    };
  });
})()`;

// ---------------------------------------------------------------- the rehearsal

const T0 = Date.now();
say("=".repeat(72));
say("REHEARSAL: one end-to-end run in the state a judge meets");
say("=".repeat(72));
say(`date    ${new Date().toISOString()}`);
say(`out     ${OUT}`);

for (const [name, url] of [["llama-server", `${FIELD}/api/health`], ["field", `${FIELD}/api/health`],
                           ["base", `${BASE}/api/health`], ["pack node", `${NODE}/packs`]]) {
  if (!(await portUp(url))) {
    say(`\nREFUSING TO START: ${name} is not answering at ${url}`);
    process.exit(2);
  }
}
const slots = await (await fetch("http://127.0.0.1:8080/slots")).json().catch(() => null);
if (slots && slots.some(s => s.is_processing)) {
  say("\nREFUSING TO START: an llama-server slot is already processing. Restart it.");
  process.exit(2);
}
const startState = {
  field: await (await fetch(`${FIELD}/api/sync`)).json(),
  base: await (await fetch(`${BASE}/api/dashboard`)).json(),
};
say(`start   field: ${startState.field.pending.length} pending, ${startState.field.sent} already sent`);
say(`        base:  ${startState.base.counts.assessments} assessments, ${startState.base.counts.devices} devices`);
say(`        slots: ${slots ? slots.map(s => `${s.id}:${s.is_processing ? "busy" : "idle"}`).join(" ") : "?"}`);

const chrome = await launch();
const p = await tab();
const verdicts = [];

try {
  // 1 ------------------------------------------------------------------------
  await step(1, "The empty screen, desktop and phone", async () => {
    await p.size(DESKTOP);
    await p.goto(`${FIELD}/`);
    const presets = await p.count("[data-preset]");
    const f1 = await p.shot("empty-desktop");
    await p.size(PHONE);
    await p.goto(`${FIELD}/`);
    const f2 = await p.shot("empty-phone");
    await p.size(DESKTOP);
    return `${presets} presets offered\nhistory: ${(await p.text(".hist-empty")) || "(not empty)"}\n${f1}\n${f2}`;
  });

  // 2 ------------------------------------------------------------------------
  const PRESETS = [
    { i: 0, who: "self", label: "Crushing chest pressure (You)", pair: false },
    { i: 1, who: "aunt", label: "Sharp pain breathing in (Aunt Sue)", pair: false },
    { i: 2, who: "self", label: "Indigestion (You and Mum)", pair: true },
  ];
  for (const pr of PRESETS) {
    await step(`2.${pr.i + 1}`, `Preset: ${pr.label}`, async () => {
      await p.goto(`${FIELD}/?p=${pr.who}`);
      const t0 = Date.now();
      await p.click(`[data-preset="${pr.i}"]`);
      if (pr.pair) await p.until("location.pathname.startsWith('/c/') && document.querySelector('[data-live]')", 30000);
      else await p.click("#send");
      const want = pr.pair ? 2 : 1;
      await p.until(`document.querySelectorAll("#thread .bar, #thread .err-panel").length >= ${want}
        && !document.querySelector("[data-live]")`, 300000, 300);
      await sleep(700);
      const secs = (Date.now() - t0) / 1000;
      const sides = await p.eval(READ_SIDES);
      const cid = await p.eval("location.pathname.split('/')[2]");
      verdicts.push({ label: pr.label, cid, sides, secs });
      const f = await p.shot(`preset-${pr.i + 1}`);
      return sides.map(s => `${(s.who || "answer").padEnd(8)} ${String(s.bar).toUpperCase().padEnd(7)} `
        + `"${s.barText}"${s.ungrounded ? "  [not grounded]" : ""}`
        + `\n         sources: ${s.cites.join(", ") || "none"}`
        + (s.rule ? `\n         rule: ${s.rule}` : "")
        + `\n         ${s.checked}`).join("\n")
        + `\n  click to answer: ${secs.toFixed(1)} s\n${f}`;
    });
  }

  // 3 ------------------------------------------------------------------------
  await step(3, "A follow-up on the Aunt Sue assessment", async () => {
    const target = verdicts[1];
    await p.goto(`${FIELD}/c/${target.cid}`);
    const before = await p.count("#thread .bar, #thread .err-panel");
    await p.type("#ta", "It is worse when I lie down, and I feel breathless now.");
    const t0 = Date.now();
    await p.click("#send");
    await p.until(`document.querySelectorAll("#thread .bar, #thread .err-panel").length > ${before}
      && !document.querySelector("[data-live]")`, 300000, 300);
    await sleep(700);
    const secs = (Date.now() - t0) / 1000;
    const lines = await p.eval(`[...document.querySelectorAll('.checked')].map(e => e.innerText.replace(/\\n+/g, " / "))`);
    const sides = await p.eval(READ_SIDES);
    const f = await p.shot("follow-up");
    return `answer: ${String(sides[0]?.bar).toUpperCase()} "${sides[0]?.barText}"`
      + `\ncache: ${lines[lines.length - 1]}`
      + `\n  follow-up: ${secs.toFixed(1)} s\n${f}`;
  });

  // 4 ------------------------------------------------------------------------
  await step(4, "Open a citation and confirm the chunk resolves", async () => {
    if (!(await p.count(".sources .cite"))) return "BROKE: no source on screen to click";
    await p.click(".sources [data-fold]");
    const key = await p.eval(`document.querySelector(".sources .cite").dataset.k`);
    await p.click(".sources .cite");
    await p.until("document.querySelector('#sheet[open]')", 15000);
    await sleep(400);
    const body = await p.text("#sheet-body");
    const head = await p.text("#sheet");
    const f = await p.shot("citation");
    await p.click("#sheet-x");
    return `clicked ${key}\nchunk text: ${body.length} chars, "${body.slice(0, 110).replace(/\n/g, " ")}…"`
      + `\nsource line: ${head.split("\n").filter(l => /NHLBI|MedlinePlus|Retrieved|http/i.test(l)).join(" · ").slice(0, 160)}`
      + `\n${f}`;
  });

  // 5 ------------------------------------------------------------------------
  await step(5, "Download a regional pack and confirm the integrity check", async () => {
    await p.goto(`${FIELD}/regions`);
    const f0 = await p.shot("packs-before");
    const before = await (await fetch(`${FIELD}/api/regions`)).json();
    const target = before.regions.find(r => !(r.pack || {}).installed_sha256);
    if (!target) return `BROKE: every pack is already installed, nothing to download`;
    const t0 = Date.now();
    await p.click(`[data-install="${target.id}"]`);
    await p.until(`!document.querySelector('[data-install="${target.id}"]')
      || /verified|Installed/i.test(document.body.innerText)`, 120000, 300);
    await sleep(1200);
    const secs = (Date.now() - t0) / 1000;
    const after = await (await fetch(`${FIELD}/api/regions`)).json();
    const now = after.regions.find(r => r.id === target.id).pack || {};
    // THE INTEGRITY CHECK, INDEPENDENTLY: ask the NODE what it published and
    // compare against what this device computed from the bytes on its own
    // disk. Reading both numbers from the same side would prove nothing.
    // The node namespaces its packs: packs.py's node_id() maps a region id to
    // "regional-<id>". Looking it up by the bare region id finds nothing and
    // reports a MISMATCH that is really a lookup bug, which is what this did
    // on its first run.
    const idx = await (await fetch(`${NODE}/packs`)).json();
    const offered = (idx.packs || []).find(x => x.id === `regional-${target.id}` || x.id === target.id) || {};
    const shown = await p.text("#main");
    const f = await p.shot("packs-after");
    return `downloaded ${target.id} (${(target.pack || {}).size} bytes) in ${secs.toFixed(1)} s`
      + `\ninstalled sha256, recomputed from this device's files: ${(now.installed_sha256 || "MISSING").slice(0, 32)}…`
      + `\nnode published:                                        ${String(offered.pack_sha256 || "?").slice(0, 32)}…`
      + `\nINTEGRITY: ${now.installed_sha256 && now.installed_sha256 === offered.pack_sha256 ? "MATCH" : "MISMATCH"}`
      + `\nper-file sha256 lines on screen: ${(shown.match(/sha256/gi) || []).length}`
      + `\n${f0}\n${f}`;
  });

  // 6 ------------------------------------------------------------------------
  await step(6, "The caseload: add someone, assess them, mark them seen", async () => {
    await p.goto(`${FIELD}/queue`);
    await p.eval(`(() => { const s = document.querySelector("#q-who");
      s.value = "dad"; s.dispatchEvent(new Event("change", { bubbles: true })); return true; })()`);
    await p.type("#q-why", "chest tightness on the walk up from the field");
    await p.click("#q-add button[type=submit]");
    await p.until("document.querySelectorAll('.q-list .q-item').length >= 1", 15000);
    const added = await p.text(".q-list");
    const f1 = await p.shot("caseload-waiting");

    await p.click("[data-assess]");
    await p.until("location.pathname === '/'", 15000);
    await p.type("#ta", "Tight chest walking up the hill, it eased when I stopped.");
    const t0 = Date.now();
    await p.click("#send");
    await p.until(`document.querySelectorAll("#thread .bar, #thread .err-panel").length >= 1
      && !document.querySelector("[data-live]")`, 300000, 300);
    await sleep(700);
    const secs = (Date.now() - t0) / 1000;
    const sides = await p.eval(READ_SIDES);
    const cid = await p.eval("location.pathname.split('/')[2]");
    verdicts.push({ label: "Caseload: Dad", cid, sides, secs });

    await p.goto(`${FIELD}/queue`);
    const linked = (await (await fetch(`${FIELD}/api/queue`)).json()).waiting[0];
    await p.click("[data-seen]");
    await p.until("document.querySelectorAll('.q-list .q-item.done').length >= 1", 15000);
    const q = await (await fetch(`${FIELD}/api/queue`)).json();
    const f2 = await p.shot("caseload-seen");
    return `added Dad: ${added.split("\n").slice(0, 2).join(" · ")}`
      + `\nassessed: ${String(sides[0]?.bar).toUpperCase()} in ${secs.toFixed(1)} s`
      + `\nlinked to the caseload row automatically: ${linked && linked.conversation_id === cid ? "yes" : "NO"}`
      + `\nafter Mark seen: ${q.counts.waiting} waiting, ${q.counts.done_today} seen today`
      + `\n${f1}\n${f2}`;
  });

  // 7 ------------------------------------------------------------------------
  let sent = 0;
  await step(7, "Sync to base and confirm what arrives", async () => {
    await p.goto(`${FIELD}/sync`);
    const pend = await (await fetch(`${FIELD}/api/sync`)).json();
    const f0 = await p.shot("sync-before");
    const t0 = Date.now();
    await p.click("#sy-send");
    await p.until(`/sent|not reachable|REFUSED/.test(document.querySelector('.sy-log')?.innerText || '')`, 120000, 250);
    await p.until(`!document.querySelector('#sy-send[disabled]')
      || /All sent|Nothing to send/.test(document.querySelector('#main').innerText)`, 120000, 300);
    await sleep(600);
    const secs = (Date.now() - t0) / 1000;
    const logTxt = await p.text(".sy-log");
    const after = await (await fetch(`${FIELD}/api/sync`)).json();
    const b = await (await fetch(`${BASE}/api/dashboard`)).json();
    sent = pend.pending.length;
    const f = await p.shot("sync-after");
    return `${pend.pending.length} waiting to send before\n`
      + logTxt.split("\n").map(l => `  ${l}`).join("\n")
      + `\nstill waiting after: ${after.pending.length}`
      + `\nbase now holds: ${b.counts.assessments} assessments from ${b.counts.devices} device(s)`
      + `\n${secs.toFixed(1)} s to send ${pend.pending.length}\n${f0}\n${f}`;
  });

  // 8 ------------------------------------------------------------------------
  await step(8, "The base register, and do the counts match what was sent", async () => {
    await p.size(DESKTOP);
    await p.goto(`${BASE}/`);
    const tally = await p.text(".tally");
    const b = await (await fetch(`${BASE}/api/dashboard`)).json();
    const f1 = await p.shot("base-register");
    await p.size(PHONE);
    await p.goto(`${BASE}/`);
    const f2 = await p.shot("base-phone");
    await p.size(DESKTOP);

    // What the field device thinks it sent, against what base is holding.
    const fieldNow = await (await fetch(`${FIELD}/api/sync`)).json();
    const match = b.counts.assessments === sent && fieldNow.pending.length === 0;
    const mine = new Set(verdicts.map(v => v.cid));
    const atBase = new Set(b.assessments.map(a => a.id));
    const missing = [...mine].filter(x => !atBase.has(x));
    return `tally: ${tally.replace(/\n/g, " ")}`
      + `\nfield sent ${sent}, base holds ${b.counts.assessments}: ${match ? "MATCH" : "MISMATCH"}`
      + `\nevery assessment made in this rehearsal is at base: ${missing.length === 0 ? "yes" : `NO, missing ${missing.join(", ")}`}`
      + `\nred ${b.counts.red}, yellow ${b.counts.yellow}, green ${b.counts.green}, refused ${b.counts.refused}`
      + `\nneeds review ${b.counts.needs_review}, still waiting in the field ${b.counts.waiting_in_field}`
      + `\n${f1}\n${f2}`;
  });

  // 9 ------------------------------------------------------------------------
  await step(9, "Download a SOAP note", async () => {
    const target = verdicts[1];
    await p.goto(`${FIELD}/c/${target.cid}`);
    if (!(await p.count(".export .link-a"))) return "BROKE: no SOAP link on a finished assessment";
    const href = await p.eval(`document.querySelector(".export .link-a").href`);
    const t0 = Date.now();
    const note = await p.eval(`fetch(${JSON.stringify(href)}).then(r => r.text())`);
    const secs = (Date.now() - t0) / 1000;
    const file = join(OUT, "soap-note.txt");
    writeFileSync(file, note);
    const flat = note.replace(/\s+/g, " ");
    const has = s => flat.includes(s);
    const f = await p.shot("soap-link");
    return `${note.length} chars in ${secs.toFixed(1)} s, saved ${file}`
      + `\nsections: ${["S  SUBJECTIVE", "O  OBJECTIVE", "A  ASSESSMENT", "P  PLAN"].filter(x => note.includes(x)).length} of 4`
      + `\nheader names the model and the corpus: ${has("sha256") && /^Model /m.test(note) ? "yes" : "NO"}`
      + `\nsays it is not a clinical record: ${/NOT A CLINICAL RECORD/i.test(note) ? "yes" : "NO"}`
      + `\ncarries citation keys: ${/CP-[A-Z]+-\d{3}/.test(note) ? "yes" : "NO"}`
      + `\ncarries what the guards removed: ${/removed/i.test(note) ? "yes" : "no removals on this one"}`
      + `\n${f}`;
  });
} finally {
  await p.close().catch(() => {});
  chrome.kill();
  for (let i = 0; i < 100; i++) {
    if (!(await portUp(`http://127.0.0.1:${PORT}/json/version`))) break;
    await sleep(100);
  }
  if (chrome.profile) rmSync(chrome.profile, { recursive: true, force: true });
}

// ---------------------------------------------------------------- the verdict

const total = (Date.now() - T0) / 1000;
say(`\n${"=".repeat(72)}\nWHAT A DESK VISIT COSTS\n${"=".repeat(72)}`);
for (const s of steps) {
  say(`  ${String(s.n).padEnd(5)} ${s.title.slice(0, 48).padEnd(50)} ${s.secs.toFixed(1).padStart(6)} s${s.broke ? "   BROKE" : ""}`);
}
say(`  ${"".padEnd(5)} ${"TOTAL".padEnd(50)} ${total.toFixed(1).padStart(6)} s  (${(total / 60).toFixed(1)} min)`);

const model = steps.filter(s => String(s.n).startsWith("2") || s.n === 3 || s.n === 6)
  .reduce((a, s) => a + s.secs, 0);
say(`\n  of which the model: ${model.toFixed(1)} s across 5 generations (3 presets, 1 follow-up, 1 caseload)`);
say(`  everything else:    ${(total - model).toFixed(1)} s`);

say(`\nVERDICTS SHOWN`);
for (const v of verdicts) {
  say(`  ${v.label.padEnd(36)} ${v.sides.map(s => `${s.who || ""} ${String(s.bar).toUpperCase()}`).join(" | ")}  ${v.secs.toFixed(1)} s`);
}

say(`\nWHAT BROKE`);
if (!broke.length) say("  nothing");
else for (const b of broke) say(`  ${b}`);

say(`\n${shotN} screenshots in ${OUT}`);
writeFileSync(join(OUT, "rehearsal.txt"), log.join("\n") + "\n");
console.log(`\nsaved ${join(OUT, "rehearsal.txt")}`);
process.exit(broke.length ? 1 : 0);
