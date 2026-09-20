#!/usr/bin/env node
// Drives the demo page in headless Chrome and saves what it sees. No packages:
// Node 22's built-in WebSocket speaks the DevTools protocol directly.
//
//   node 06-demo/ui_check.mjs shots OUTDIR          static screens, desktop and phone
//   node 06-demo/ui_check.mjs flow OUTDIR           one assessment, live, with a follow-up
//   node 06-demo/ui_check.mjs compare OUTDIR        two people side by side, live
//   node 06-demo/ui_check.mjs guards OUTDIR         child profile, child word, out of scope
//   node 06-demo/ui_check.mjs people OUTDIR         add, edit and delete a person through the form
//   node 06-demo/ui_check.mjs queue OUTDIR          the caseload: add, assess, mark seen
//   node 06-demo/ui_check.mjs sync OUTDIR [BASE]     offline, queue, back in range, land at base
//   node 06-demo/ui_check.mjs base OUTDIR [BASE]     the supervisor's register on 8781
//   node 06-demo/ui_check.mjs two-tabs OUTDIR       two assessments running at once in two tabs
//   node 06-demo/ui_check.mjs drop OUTDIR           a stream that drops mid-answer, then the saved answer
//   node 06-demo/ui_check.mjs regions OUTDIR        the region packs, and the emergency-number annotation
//   node 06-demo/ui_check.mjs packs OUTDIR          a pack downloaded from the distribution node and verified
//   node 06-demo/ui_check.mjs phone OUTDIR URL      a phone on the wifi: over the network, touch, 390x844
//   node 06-demo/ui_check.mjs voice OUTDIR [URL]    the microphone, with a known WAV played into it
//   node 06-demo/ui_check.mjs reread OUTDIR CID     a follow-up after a llama-server restart
//   node 06-demo/ui_check.mjs review OUTDIR IDS     the finish review's screenshots (six ids, comma-separated)
//
// Needs the demo server on 8770 and, for the live flows, llama-server on 8080.
// Every check prints PASS or FAIL; the exit code is the number of failures.

import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
let APP = "http://127.0.0.1:8770";
const PORT = 9333;
const DESKTOP = { width: 1440, height: 900, mobile: false, deviceScaleFactor: 1 };
const PHONE = { width: 390, height: 844, mobile: true, deviceScaleFactor: 2 };
let failures = 0;
const sleep = ms => new Promise(r => setTimeout(r, ms));

function check(name, ok, detail = "") {
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail && !ok ? `  (${detail})` : ""}`);
}

// A known sentence, spoken by the OS, played into the page's microphone.
// Written here rather than checked in, because `say` produces exactly the
// 16 kHz mono 16-bit WAV that whisper.cpp wants.
const VOICE_LINE = "Heavy pressure in the middle of my chest that has not let up for almost half an hour.";
function makeSpokenWav(dir) {
  const wav = resolve(dir, "spoken.wav");
  execFileSync("/usr/bin/say", ["-v", "Samantha", "-o", wav,
    "--data-format=LEI16@16000", "--channels=1", VOICE_LINE]);
  return wav;
}

// WHY getUserMedia IS REPLACED AND CHROME'S OWN FAKE MICROPHONE IS NOT USED.
// --use-file-for-fake-audio-capture does not work in Chrome 153 headless:
// measured 2026-09-19 across both flag combinations and both sample rates, the
// page received Chrome's built-in beep every time and whisper hallucinated a
// sentence out of it ("This is also what you're supposed to do with computers
// in all air cooling"). --headless=old, which used to honour the flag, was
// removed in this version. So the audio SOURCE is substituted here and
// everything downstream of it is real: the button, MediaRecorder, the webm
// encode, decodeAudioData, the 16 kHz resample, the WAV writer, the POST,
// whisper.cpp, and what lands in the composer. What this does NOT cover is
// getUserMedia itself and the browser's permission prompt, which is the one
// thing at the desk that needs a human to have clicked Allow once.
async function installFakeMic(p, wav) {
  const b64 = readFileSync(wav).toString("base64");
  return p.eval(`(async () => {
    const bin = atob("${b64}");
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const ac = new AudioContext();
    const decoded = await ac.decodeAudioData(bytes.buffer);
    navigator.mediaDevices.getUserMedia = async () => {
      const dest = ac.createMediaStreamDestination();
      const src = ac.createBufferSource();
      src.buffer = decoded; src.connect(dest); src.start();
      return dest.stream;
    };
    return +decoded.duration.toFixed(2);
  })()`);
}

// Is anything answering the DevTools port right now?
async function debugPortUp() {
  try { await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); return true; }
  catch { return false; }
}

// WAIT FOR THE PORT TO GO QUIET BEFORE TRUSTING IT.
//
// This is the bug that produced every flaky failure on the night of
// 2026-09-19: a mode would fail its FIRST navigation with "timed out waiting
// for document.readyState", burn the full 180 s, and then pass when run on its
// own. The teardown killed Chrome and slept a flat 500 ms. When the previous
// browser took longer than that to let go of 9333, the next mode's launch()
// polled /json/version, got an answer from the DYING browser, opened a tab in
// it, and then watched that tab never load because its browser was exiting.
//
// Four of the twelve modes failed this way in one suite run, all of them at
// their first navigation and all of them for exactly 181 s. A fixed sleep
// cannot fix it, because the thing being waited for is a process exiting, not
// a duration passing. So both ends now wait on the observable condition.
async function waitForPortFree(ms = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (!(await debugPortUp())) return true;
    await sleep(100);
  }
  return false;
}

async function launch(extra = []) {
  // A browser left over from a previous mode still owns the port. Connecting
  // to it looks like success and fails 180 s later, so refuse to start until
  // it has gone.
  if (await debugPortUp() && !(await waitForPortFree())) {
    throw new Error(`something is already on the DevTools port ${PORT}. `
      + `Another ui_check is running, or one has not exited. Run one at a time.`);
  }
  // Thrown away in the finally below. Left behind, these are about 45 MB each,
  // and 73 of them filled the disk on 2026-09-19, the night before judging.
  const profile = mkdtempSync(join(tmpdir(), "ui-check-"));
  const proc = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", ...extra, "about:blank"], { stdio: "ignore" });
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
    async size(d) { await send("Emulation.setDeviceMetricsOverride", d); await send("Emulation.setTouchEmulationEnabled", { enabled: d.mobile }); },
    // A real handset, as far as the page can tell: touch events from taps and
    // a phone's user agent, not a narrow desktop window.
    async handset() {
      await send("Emulation.setEmitTouchEventsForMouse", { enabled: true, configuration: "mobile" });
      await send("Emulation.setUserAgentOverride", {
        userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
          + "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
        platform: "iPhone" });
    },
    async go(path) { await send("Page.navigate", { url: APP + path }); await page.until("document.readyState === 'complete' && !document.querySelector('.loading')"); await sleep(350); },
    async eval(expr) {
      const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(`${expr.slice(0, 80)}: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
      return r.result.value;
    },
    async until(expr, timeout = 180000, every = 200) {
      const t0 = Date.now();
      while (Date.now() - t0 < timeout) {
        if (await page.eval(`!!(${expr})`).catch(() => false)) return Date.now() - t0;
        await sleep(every);
      }
      throw new Error(`timed out waiting for ${expr}`);
    },
    click: sel => page.eval(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) throw new Error("no ${sel.replace(/"/g, "")}"); e.click(); return true; })()`),
    type: (sel, text) => page.eval(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.focus(); e.value = ${JSON.stringify(text)}; e.dispatchEvent(new Event("input", { bubbles: true })); return true; })()`),
    text: sel => page.eval(`document.querySelector(${JSON.stringify(sel)})?.innerText ?? ""`),
    count: sel => page.eval(`document.querySelectorAll(${JSON.stringify(sel)}).length`),
    async shot(file, full = false) {
      let clip;
      // Sticky bars paint at their scrolled position in a full-page capture.
      if (full) await page.eval(`(() => { const s = document.createElement("style"); s.id = "shot-static";
        s.textContent = ".top,.side,.composer,.preview{position:static!important}"; document.head.append(s); return true; })()`);
      if (full) {
        const m = await send("Page.getLayoutMetrics");
        clip = { x: 0, y: 0, width: m.cssContentSize.width, height: Math.min(m.cssContentSize.height, 6000), scale: 1 };
      }
      const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: full, ...(clip ? { clip } : {}) });
      writeFileSync(file, Buffer.from(r.data, "base64"));
      if (full) await page.eval(`document.getElementById("shot-static")?.remove() || true`);
      console.log(`      saved ${file}`);
    },
    close: () => { ws.close(); return fetch(`http://127.0.0.1:${PORT}/json/close/${t.id}`); },
  };
  return page;
}

// ------------------------------------------------------------------- flows

async function shots(out) {
  const p = await tab();
  for (const [name, d] of [["desktop", DESKTOP], ["phone", PHONE]]) {
    await p.size(d);
    await p.go("/");
    check(`${name}: new assessment shows presets`, await p.count("[data-preset]") === 3);
    await p.shot(join(out, `${name}-new.png`));
    await p.go("/people");
    check(`${name}: people list shows the household`, await p.count(".people li") >= 6);
    await p.shot(join(out, `${name}-people.png`), true);
    await p.go("/people/mum");
    await p.until("document.querySelector('.preview .w-rule')");
    check(`${name}: Mum's form shows the rules her profile turns on`,
      /R1/.test(await p.text(".preview")) && /R3/.test(await p.text(".preview")));
    await p.shot(join(out, `${name}-person-mum.png`), true);
    await p.go("/?p=maya");
    check(`${name}: Maya's empty screen says she is not assessed`, /under 16/i.test(await p.text(".kid-note")));
    await p.shot(join(out, `${name}-maya.png`));
  }
  await p.close();
}

// Send, then wait for a new outcome. Some arrive in milliseconds (a child's
// profile is refused before retrieval), so this watches for the result, not
// for the working state, which may be over before the first poll.
async function sendAndWait(p, label) {
  const t0 = Date.now();
  const before = await p.count("#thread .bar, #thread .err-panel, #thread .full");
  await p.click("#send");
  await p.until(`document.querySelectorAll("#thread .bar, #thread .err-panel, #thread .full").length > ${before}
    && !document.querySelector("[data-live] .steps4")`, 300000, 300);
  await sleep(700);
  console.log(`      ${label}: ${((Date.now() - t0) / 1000).toFixed(1)} s`);
}

async function flow(out) {
  const p = await tab();
  await p.size(DESKTOP);
  await p.go("/?p=mum");
  await p.click('[data-preset="0"]');
  // A preset's own person is a default for when nobody is picked; it never
  // overrides a person the user chose, and ?p=mum chose one.
  check("a preset keeps the person picked", /Mum/.test(await p.text("[data-for-name]")));
  check("the preset fills the composer", (await p.eval("document.querySelector('#ta').value")).length > 40);
  await p.click("#send");
  await p.until("document.querySelector('[data-live] .steps4')", 30000);
  check("the URL becomes the assessment's own", /^\/c\//.test(await p.eval("location.pathname")));
  await p.until("/tokens/.test(document.querySelector('[data-live] .steps4')?.innerText || '')", 120000);
  await p.shot(join(out, "desktop-streaming.png"));
  await p.until("[...document.querySelectorAll('[data-live]')].every(e => !e.querySelector('.steps4'))", 300000, 400);
  await p.until("!document.querySelector('[data-live]')", 60000);
  await sleep(800);
  check("a verdict bar is shown", await p.count(".bar.red, .bar.yellow, .bar.green, .bar.hold") >= 1);
  check("the checked line is shown", /Checked/.test(await p.text(".checked")));
  check("the follow-up allowance is shown before it runs out", /follow-ups left/.test(await p.text(".allow")));
  await p.shot(join(out, "desktop-answer.png"), true);
  await p.click(".checked");
  check("the checked line opens its details", !(await p.eval("document.querySelector('.details').hidden")));
  await p.shot(join(out, "desktop-answer-details.png"), true);
  await p.click(".checked");
  if (await p.count(".cite")) {
    await p.click(".cite");
    await p.until("document.querySelector('#sheet[open]')", 10000);
    check("a source chip opens the real chunk", (await p.text("#sheet-body")).length > 40);
    await p.shot(join(out, "desktop-source.png"));
    await p.click("#sheet-x");
  }
  await p.type("#ta", "It has not gone away, it has been an hour now.");
  await sendAndWait(p, "follow-up");
  const lines = await p.eval("[...document.querySelectorAll('.checked')].map(e => e.innerText)");
  check("the follow-up reports its cache reuse", /cached, read/.test(lines[lines.length - 1] || ""), lines.join(" | "));
  check("the allowance counts down", /3 follow-ups left|1 follow-up left/.test(await p.text(".allow")));
  // The clinical export reads the saved assessment: four sections, a header
  // that names the model, corpus and prompt, and the patient's own words.
  check("a finished assessment offers a SOAP note", await p.count(".export .link-a") === 1);
  const note = JSON.parse(await p.eval(`fetch(document.querySelector(".export .link-a").href)
    .then(r => r.text()).then(t => JSON.stringify({
      len: t.length,
      sections: ["S  SUBJECTIVE", "O  OBJECTIVE", "A  ASSESSMENT", "P  PLAN"].every(x => t.includes(x)),
      header: /NOT A CLINICAL RECORD/.test(t) && /sha256/.test(t) && /^Model /m.test(t),
      said: t.includes("It has not gone away, it has been an hour now."),
      keys: /CP-[A-Z]+-\\d{3}/.test(t),
      wide: t.split("\\n").some(l => l.length > 78)
    }))`));
  check("the note has its four sections and its header", note.sections && note.header, JSON.stringify(note));
  check("the note quotes the follow-up and carries citation keys", note.said && note.keys, JSON.stringify(note));
  check("the note wraps for a printed page", !note.wide && note.len > 1500, JSON.stringify(note));
  await p.shot(join(out, "desktop-followup.png"), true);
  const path = await p.eval("location.pathname");
  await p.size(PHONE);
  await p.go(path);
  await p.shot(join(out, "phone-answer.png"));
  await p.shot(join(out, "phone-answer-full.png"), true);
  await p.click("#menu");
  await sleep(400);
  check("the drawer lists this assessment", await p.count(".hist-row[aria-current=page]") === 1);
  await p.shot(join(out, "phone-drawer.png"));
  await p.close();
  return path;
}

// A compare assessment has one left edge: the record, both answers and the composer.
async function oneLeftEdge(p, where) {
  const xs = await p.eval(`(() => {
    const x = s => { const e = document.querySelector(s); return e ? Math.round(e.getBoundingClientRect().left) : null; };
    return [x("#thread .said"), x("#thread .turn.pair"), x(".composer .in")];
  })()`);
  check(`${where}: record, answers and composer share one left edge`,
    xs.every(v => v !== null) && Math.max(...xs) - Math.min(...xs) <= 1, JSON.stringify(xs));
}

async function compare(out) {
  const p = await tab();
  await p.size(DESKTOP);
  // Beat 3 is one click: from Dad, with Compare off, preset 3 alone turns Compare
  // on, sets You against Mum and sends. It is preset 3 of 3 since the cut.
  await p.go("/?p=dad");
  const t0 = Date.now();
  await p.click('[data-preset="2"]');
  await p.until("location.pathname.startsWith('/c/') && document.querySelector('[data-live]')", 30000);
  check("preset 3 turns Compare on by itself", await p.eval(`(() => {
    const t = document.querySelector("[data-for-name]").innerText.replace(/\\s+/g, " ");
    return /You\\s*A/.test(t) && /Mum\\s*B/.test(t);
  })()`) === true);
  check("preset 3 sets You against Mum", /^You\s*A\s*Mum\s*B$/.test(
    (await p.text("[data-for-name]")).trim()));
  check("preset 3 sends by itself", /^\/c\//.test(await p.eval("location.pathname")));
  await p.until(`document.querySelectorAll("#thread .bar, #thread .err-panel").length >= 2 && !document.querySelector("[data-live] .steps4")`, 300000, 300);
  await sleep(700);
  console.log(`      compare, both sides, one click: ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  check("both sides answered", await p.count(".turn.pair .side-ans .bar") === 2);
  // Constraint 16: what is SHOWN must match the urgency that is shown.
  //
  // UNTIL 2026-09-19 THIS LOOKED ONLY FOR "Raised to red". The tuned model
  // raises Mum to YELLOW, so every assertion below stopped running and the
  // check still printed "all passed": six checks where the base model ran
  // nine, and nothing said so. That is constraint 10's PEFT trap in a test
  // suite, a matcher that matches nothing reported as a pass. It now finds a
  // raise to either level and FAILS when nothing was raised at all, because
  // R1 fires on Mum on every run measured on both models.
  const raise = await p.eval(`(() => {
    const side = [...document.querySelectorAll(".side-ans")].find(s => /Raised to (red|yellow)/.test(s.innerText));
    if (!side) return null;
    return { level: side.innerText.match(/Raised to (red|yellow)/)[1],
             text: side.innerText.replace(/\\s+/g, " "),
             rescued: !!side.querySelector(".ungrounded") };
  })()`);
  check("a profile rule raised one side", raise !== null,
    "no side shows a raise, and R1 fires on Mum on every measured run");
  // A raise lands on one of three branches and the preset has taken all three
  // across the two models, so the check has to know which it is looking at.
  // GROUNDED RAISE TO RED: the model's prose is on screen, so constraint 16
  // strikes it out and replaces the steps with the app's own.
  // RESCUED RAISE TO RED: the model cited nothing, so constraint 13 shows the
  // urgency, says it is not grounded and withholds everything else. There is
  // nothing left to strike, and asserting constraint 16 here fails a page that
  // is behaving correctly.
  // RAISE TO YELLOW: constraint 16 strikes the rationale, because it argues
  // for the lower verdict, and deliberately does NOT replace the steps,
  // because there is no yellow equivalent of the three red lines. That gap is
  // recorded rather than asserted, so this check keeps passing when it is
  // closed. See the note it prints.
  if (raise && raise.rescued) {
    console.log("      the raise came through the refusal rescue: the not-grounded branch");
    check("a rescued red shows the urgency, its disposition and the not-grounded line",
      /\bRED\b/.test(raise.text) && raise.text.includes("Call emergency services now")
      && raise.text.includes("Not grounded in sources"), raise.text.slice(0, 300));
    check("a rescued red shows none of the prose the model wrote for its own verdict", await p.eval(`(async () => {
      const conv = await (await fetch("/api/conversations/" + location.pathname.split("/")[2])).json();
      const side = [...document.querySelectorAll(".side-ans")].find(s => /Raised to (red|yellow)/.test(s.innerText));
      const held = conv.sides.flatMap(s => s.turns)
        .map(t => ((t.event || {}).ungrounded || {}).withheld || {})
        .flatMap(w => [w.rationale || "", ...(w.next_steps || []), ...(w.follow_up_questions || [])])
        .filter(Boolean);
      return held.length > 0 && held.every(x => !side.innerText.includes(x)) &&
        !/What to do/.test(side.innerText) && !/Sources/.test(side.innerText);
    })()`) === true);
  } else if (raise && raise.level === "red") {
    check("a raised red shows the app's steps",
      ["Call emergency services now.", "Do not drive yourself.", "Stay where you are."].every(t => raise.text.includes(t)), raise.text.slice(0, 300));
    check("the model's own steps are shown as removed", /written for a (yellow|green)/.test(raise.text), raise.text.slice(0, 300));
  }
  // The half of constraint 16 that holds on EVERY raise, whichever level it
  // lands on and whether or not it was rescued: the model wrote its Why for
  // the verdict it gave, so a raise strikes it out whole and tags it. A
  // rescued raise has no rationale on screen to strike, so it is exempt.
  if (raise && !raise.rescued) {
    check(`a raise to ${raise.level} strikes out the model's rationale, whole and tagged`, await p.eval(`(() => {
      const side = [...document.querySelectorAll(".side-ans")].find(s => /Raised to (red|yellow)/.test(s.innerText));
      const why = [...side.querySelectorAll(".sec")].find(sec => /^Why\\b/.test(sec.innerText));
      const struck = why && why.querySelector("p.gone s");
      return !!struck && !why.querySelector("h3 + p:not(.gone)") &&
        struck.innerText.length > 80 && !struck.innerText.endsWith("…") &&
        /removed: written for a/.test(why.innerText);
    })()`) === true);
  }
  if (raise && raise.level === "yellow") {
    // KNOWN GAP, measured 2026-09-19 on the tuned model and not a failure of
    // this check: a raise to yellow keeps the steps the model wrote for its
    // green, so "Be seen today" can sit above "eat the rest of the meal".
    // Printed, not asserted, so closing it does not turn this red.
    const steps = await p.eval(`(() => {
      const side = [...document.querySelectorAll(".side-ans")].find(s => /Raised to yellow/.test(s.innerText));
      const sec = [...side.querySelectorAll(".sec")].find(x => /^What to do\\b/.test(x.innerText));
      return sec ? [...sec.querySelectorAll("li")].map(li => li.innerText.replace(/\\s+/g, " ")) : [];
    })()`);
    console.log(`      NOTE, constraint 16 gap: a raise to yellow keeps the model's own steps`);
    steps.forEach(x => console.log(`        ${x}`));
  }
  await oneLeftEdge(p, "compare");
  await p.shot(join(out, "desktop-compare.png"), true);
  const path = await p.eval("location.pathname");
  await p.size(PHONE);
  await p.go(path);
  await p.shot(join(out, "phone-compare-a.png"));
  await p.click('[data-tab="1"]');
  await sleep(200);
  await p.shot(join(out, "phone-compare-b.png"));
  await p.close();
}

async function guards(out) {
  const p = await tab();
  await p.size(DESKTOP);
  await p.go("/?p=maya");
  await p.type("#ta", "She has a pain in her chest.");
  await sendAndWait(p, "child profile");
  check("a child's profile gets NOT ASSESSED", /NOT ASSESSED/.test(await p.text(".bar.hold")));
  await p.shot(join(out, "desktop-child.png"));
  await p.go("/?p=self");
  await p.type("#ta", "My daughter has a tight chest after running.");
  await p.click("#send");
  await p.until("document.querySelector('[data-continue]')", 60000);
  check("a child word on an adult profile asks who it is for", /WHO IS THIS FOR/.test(await p.text(".bar.hold")));
  await p.shot(join(out, "desktop-who-is-this-for.png"));
  await p.go("/?p=self");
  // Not the tooth complaint: that one clears the 0.25 floor and is a documented
  // hole in constraint 13 (an adjacent chunk defeats the post-flight check).
  await p.type("#ta", "I twisted my ankle playing football and now it is swollen.");
  await sendAndWait(p, "out of scope");
  check("an out-of-scope complaint gets a hatched refusal, not a verdict",
    await p.count(".bar.hold") >= 1 && !(await p.count(".bar.red, .bar.yellow, .bar.green")));
  await p.shot(join(out, "desktop-out-of-scope.png"));
  await p.close();
}

// THE CASELOAD, end to end and offline: add somebody, see them waiting, assess
// them, come back, mark them seen. No model call is needed for any of it, which
// is the point: the list is the health worker's, not the model's.
async function queue(out) {
  const p = await tab();
  await p.size(DESKTOP);
  // Start from a known state so a re-run does not pile up rows.
  const before = await (await fetch(`${APP}/api/queue`)).json();
  for (const e of [...before.waiting, ...before.done]) {
    await fetch(`${APP}/api/queue/${e.id}`, { method: "DELETE" });
  }
  await p.go("/queue");
  check("an empty caseload says so", /Nobody is waiting/.test(await p.text("#main")));
  await p.shot(join(out, "desktop-caseload-empty.png"), true);

  await p.eval(`(() => { const s = document.querySelector("#q-who");
    s.value = "aunt"; s.dispatchEvent(new Event("change", { bubbles: true })); return true; })()`);
  await p.type("#q-why", "short of breath since this morning");
  await p.click("#q-add button[type=submit]");
  await p.until("document.querySelectorAll('.q-list .q-item').length === 1", 10000);
  check("a person can be added to the caseload", /Aunt Sue/.test(await p.text(".q-list")));
  check("the note they were added with is shown",
    /short of breath since this morning/.test(await p.text(".q-list")));
  check("the sidebar says how many are waiting", /1 waiting/.test(await p.text("#queue-link")));
  await p.shot(join(out, "desktop-caseload.png"), true);

  // The same person cannot be queued twice from the screen that lists them.
  check("somebody already waiting is not offered again",
    !(await p.eval(`[...document.querySelectorAll("#q-who option")].some(o => o.value === "aunt")`)));

  await p.click("[data-assess]");
  await p.until("location.pathname === '/'", 10000);
  check("Assess opens a new assessment for that person",
    /Aunt Sue/.test(await p.text("[data-for-name]")), await p.text("[data-for-name]"));

  // Starting the assessment is what links it to the caseload row, server-side,
  // so the link survives the tab closing. It must NOT mark anybody seen.
  await p.type("#ta", "Sharp pain in my left chest, worse when I breathe in.");
  await sendAndWait(p, "caseload assessment");
  const cid = await p.eval("location.pathname.split('/')[2]");
  const q = await (await fetch(`${APP}/api/queue`)).json();
  check("starting an assessment links it to the caseload row",
    q.waiting.length === 1 && q.waiting[0].conversation_id === cid, JSON.stringify(q.counts));
  check("starting an assessment does NOT mark them seen", q.counts.done === 0);

  await p.go("/queue");
  await p.click("[data-seen]");
  await p.until("document.querySelectorAll('.q-list .q-item.done').length === 1", 10000);
  check("Mark seen moves them out of waiting",
    /Nobody is waiting/.test(await p.text("#main")));
  check("a seen row links the assessment it was seen in",
    await p.count(".q-item.done a[href^='/c/']") === 1);
  check("the sidebar count goes back to empty", /Empty/.test(await p.text("#queue-link")));
  await p.shot(join(out, "desktop-caseload-seen.png"), true);
  await p.size(PHONE);
  await p.go("/queue");
  await p.shot(join(out, "phone-caseload.png"), true);
  await p.close();
}

// SEND TO BASE, the whole demo sentence: assess with base unreachable, watch it
// queue, then reach base and watch it land with its hash.
//
// "Unreachable" is a dead PORT, not a stopped process. A check that has to
// stop and start another server is a check nobody runs; pointing the device at
// 127.0.0.1:1 exercises exactly the same code path in sync.post.
async function syncFlow(out, baseUrl) {
  const BASE = (baseUrl || "http://127.0.0.1:8781").replace(/\/+$/, "");
  let up = true;
  try { await fetch(`${BASE}/api/health`); } catch { up = false; }
  if (!up) {
    check(`base is running at ${BASE}`, false, "start it: python 06-demo/base_server.py");
    return;
  }
  const p = await tab();
  await p.size(DESKTOP);

  // OFFLINE. Point the device at a port nothing is listening on.
  await p.go("/sync");
  await p.type("#sy-url", "http://127.0.0.1:1");
  await p.click("#sy-form button[type=submit]");
  await sleep(600);

  // Assess somebody while "out of range". The triage itself must not care.
  await p.go("/?p=dad");
  await p.type("#ta", "Tight chest when I walk up the hill, it eased when I stopped.");
  await sendAndWait(p, "assessment with base unreachable");
  const cid = await p.eval("location.pathname.split('/')[2]");
  check("an assessment works with base unreachable", /^\d{8}-/.test(cid), cid);

  await p.go("/sync");
  check("the new assessment is waiting to send",
    (await p.text("#main")).includes("waiting to send")
    && await p.count(".sy-list .sy-row") >= 1);
  check("the sidebar says how many are waiting to send",
    /to send/.test(await p.text("#sync-link")), await p.text("#sync-link"));
  await p.shot(join(out, "desktop-sync-waiting.png"), true);

  await p.click("#sy-send");
  await p.until("/not reachable/.test(document.querySelector('.sy-log')?.innerText || '')", 30000);
  check("an unreachable base is reported, and nothing is lost",
    /Nothing was lost/.test(await p.text(".sy-log")), await p.text(".sy-log"));
  const stillThere = await (await fetch(`${APP}/api/sync`)).json();
  check("nothing was marked sent while base was unreachable",
    stillThere.pending.some(x => x.id === cid));
  await p.shot(join(out, "desktop-sync-offline.png"), true);

  // BACK IN RANGE.
  await p.type("#sy-url", BASE);
  await p.click("#sy-form button[type=submit]");
  await sleep(600);
  await p.click("#sy-send");
  await p.until("/sent/.test(document.querySelector('.sy-log')?.innerText || '')", 120000);
  await p.until("!document.querySelector('#sy-send[disabled]') || /All sent|Nothing to send/.test(document.querySelector('#main').innerText)", 120000);
  await sleep(500);
  const log = await p.text(".sy-log");
  check("the flush reports each assessment landing", /Landed at base|already had/.test(log), log.slice(0, 300));
  await p.shot(join(out, "desktop-sync-sent.png"), true);

  // AT BASE. The assessment is there, and it carried its citations and the
  // guard actions with it, because base stores the field device's own bytes.
  const got = await (await fetch(`${BASE}/api/assessments/${cid}`)).json();
  check("base received that exact assessment", got && got.assessment && got.assessment.id === cid);
  check("base verified it against the sha256 it arrived with",
    typeof got.sha256 === "string" && got.sha256.length === 64);
  const dash = await (await fetch(`${BASE}/api/dashboard`)).json();
  const rowAt = dash.assessments.find(r => r.id === cid);
  check("the dashboard lists it under the device that sent it",
    !!rowAt && !!rowAt.device && rowAt.device === got.device.id);
  check("the verdict at base is the one the field device showed",
    !!rowAt && rowAt.sides.length === 1 && ["red", "yellow", "green", "refused"].includes(rowAt.sides[0].state),
    JSON.stringify(rowAt && rowAt.sides));

  // A SECOND FLUSH MUST BE A NO-OP. This is what makes a flaky link safe.
  const after = await (await fetch(`${APP}/api/sync`)).json();
  check("nothing is left waiting after a successful send",
    !after.pending.some(x => x.id === cid), JSON.stringify(after.pending.map(x => x.id)));

  // INTEGRITY. Base must refuse content that does not match its own digest.
  const tampered = JSON.parse(JSON.stringify(got));
  tampered.assessment.sides[0].turns[0].text = "TAMPERED: the pain has gone away";
  const r = await fetch(`${BASE}/api/receive`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tampered) });
  const refused = await r.json();
  check("base REFUSES a bundle whose content does not match its sha256",
    r.status === 422 && (refused.problems || []).some(x => /sha256 does not match/.test(x)),
    JSON.stringify(refused).slice(0, 200));

  await p.size(PHONE);
  await p.go("/sync");
  await p.shot(join(out, "phone-sync.png"), true);
  await p.close();
}

// BASE, the supervisor's register. Runs against base on 8781, which is a
// SEPARATE process: nothing here touches the field app, and base being down is
// reported as base being down rather than as a field failure.
async function base(out, baseUrl) {
  const BASE = (baseUrl || "http://127.0.0.1:8781").replace(/\/+$/, "");
  let health = null;
  try { health = await (await fetch(`${BASE}/api/health`)).json(); } catch { /* down */ }
  if (!health || !health.ok) {
    check(`base is running at ${BASE}`, false, "start it: python 06-demo/base_server.py");
    return;
  }
  const d0 = await (await fetch(`${BASE}/api/dashboard`)).json();
  if (!d0.assessments.length) {
    check("base has at least one assessment to show", false,
      "run the sync check first: node 06-demo/ui_check.mjs sync OUT");
    return;
  }
  const p = await tab();
  const at = async path => {
    await p.send("Page.navigate", { url: BASE + path });
    await p.until("document.readyState === 'complete' && !document.querySelector('.fine')", 30000);
    await sleep(500);
  };

  await p.size(DESKTOP);
  await at("/");
  check("base leads with a tally line, not a card grid",
    await p.count(".tally") === 1 && await p.count(".tile") === 0);
  // Six columns per table, and there is one table per section.
  check("the register is a real table with column headers", await p.eval(`(() => {
    const tables = [...document.querySelectorAll(".wide-only .reg")];
    return tables.length >= 1 && tables.every(t => t.querySelectorAll("thead th").length === 6);
  })()`) === true, String(await p.count(".wide-only .reg thead th")));
  check("it splits into Needs review and Reviewed",
    /Needs review/.test(await p.text("#main")));
  // The spec's colour rule: the urgency marks are the ONLY saturated thing.
  check("every urgency mark carries its word, not just a letter",
    await p.eval(`[...document.querySelectorAll(".reg .mk")].every(m =>
      (m.getAttribute("title") || "").length > 2 && m.querySelector(".sr-only"))`) === true);
  check("no tag carries a triage colour", await p.eval(`(() => {
    const bad = ["rgb(200, 38, 29)", "rgb(242, 183, 5)", "rgb(28, 122, 67)"];
    return [...document.querySelectorAll(".tg")].every(t => {
      const s = getComputedStyle(t);
      return !bad.includes(s.backgroundColor) && !bad.includes(s.color);
    });
  })()`) === true);
  await p.shot(join(out, "desktop-base-register.png"), true);

  // Needs review is read top to bottom by someone who runs out of time, so red
  // must come before yellow whatever the clock says.
  // A COMPARE ROW CARRIES TWO MARKS, so the row's band is the worst of them,
  // exactly as the page computes it. Reading only the first mark scores a
  // green-beside-yellow row as green and fails a page that is sorted right.
  check("Needs review is in priority order, red before yellow", await p.eval(`(() => {
    const rows = [...document.querySelectorAll(".wide-only .reg")][0].querySelectorAll("tbody tr");
    const one = m => m.classList.contains("red") ? 0 : m.classList.contains("hold") ? 1
      : m.classList.contains("yellow") ? 2 : 3;
    const band = r => Math.min(...[...r.querySelectorAll(".mk")].map(one));
    const bands = [...rows].map(band);
    return bands.every((b, i) => i === 0 || bands[i - 1] <= b) ? true : bands.join(",");
  })()`) === true);

  const before = await p.count("[data-review]");
  await p.click("[data-review]");
  await p.until(`document.querySelectorAll("[data-review]").length < ${before}`, 10000);
  check("Mark reviewed moves a row out of Needs review", true);
  check("a reviewed row says when it was reviewed",
    /Reviewed \d\d:\d\d/.test(await p.text("#main")), (await p.text("#main")).slice(0, 200));
  // It must change the record and NOT the assessment.
  const rowNow = (await (await fetch(`${BASE}/api/dashboard`)).json())
    .assessments.find(r => r.reviewed);
  check("reviewing is recorded at base", !!rowNow && !!rowNow.reviewed.at);
  const bundle = await (await fetch(`${BASE}/api/assessments/${rowNow.id}`)).json();
  check("reviewing does not change the assessment's verified digest",
    bundle.sha256 === rowNow.sha256 && bundle.sha256.length === 64);
  await p.shot(join(out, "desktop-base-reviewed.png"), true);

  await p.click("[data-win='all']");
  await sleep(400);
  check("the Today/All control switches window",
    await p.eval(`document.querySelector("[data-win='all']").getAttribute("aria-pressed") === "true"`) === true);

  // One assessment, read-only, with what base can and cannot show.
  await p.click(".ttl");
  await p.until("/^\\/a\\//.test(location.pathname)", 10000);
  await sleep(600);
  const det = await p.text("#main");
  check("an assessment opens read-only at base", /Assessment/.test(det));
  check("it carries the citation keys", await p.count(".key") >= 1 || /Nothing cited/.test(det));
  check("it says plainly that base holds no corpus",
    /Base holds no corpus/.test(det) || /Nothing cited/.test(det), det.slice(0, 300));
  check("it shows the verified digest it arrived with", /verified sha256 [0-9a-f]{64}/.test(det));
  await p.shot(join(out, "desktop-base-assessment.png"), true);

  // Below 60rem the table is REPLACED, not squeezed.
  await p.size(PHONE);
  await at("/");
  check("the table is not rendered on a phone",
    await p.eval(`getComputedStyle(document.querySelector(".wide-only")).display`) === "none");
  check("records are rendered instead", await p.count(".rec") >= 1);
  check("nothing overflows sideways at 390px",
    await p.eval("document.documentElement.scrollWidth <= window.innerWidth"),
    String(await p.eval("document.documentElement.scrollWidth")));
  await p.shot(join(out, "phone-base-register.png"), true);
  await p.close();
}

// Adds, then deletes, one throwaway person. It finds that person by exact name
// through the API and will not delete anyone from the seeded household: an
// earlier version matched "Sam" by substring, hit the "Sample" tag on You, and
// deleted You (restored from the seed, 2026-09-19).
const SEEDED = new Set(["self", "mum", "dad", "aunt", "grandpa", "maya"]);

async function people(out) {
  const p = await tab();
  const name = `Test Person ${Math.random().toString(36).slice(2, 6)}`;
  await p.size(DESKTOP);
  await p.go("/people/new");
  await p.click("button[type=submit]");
  await sleep(400);
  check("an empty form names what is missing", /Enter a name/.test(await p.text(".form")));
  await p.type("#f-label", name);
  await p.type("#f-age", "58");
  await p.click('[data-sex="male"]');
  await p.type("#f-conditions", "type 2 diabetes");
  await p.eval("document.querySelector('#f-conditions').dispatchEvent(new Event('change'))");
  await p.until("/R1/.test(document.querySelector('.preview')?.innerText || '')", 10000);
  check("the preview shows the rule the new condition turns on", true);
  await p.shot(join(out, "desktop-person-new.png"), true);
  await p.click("button[type=submit]");
  await p.until("location.pathname === '/people'", 10000);
  const made = (await (await fetch(`${APP}/api/people`)).json()).people.filter(x => x.label === name);
  check("the new person is saved and listed", made.length === 1 && (await p.text(".people")).includes(name));
  // The chip row is gone; a new person has to reach the picker instead.
  await p.go("/");
  await p.click("#forwho");
  await p.until("document.querySelector('#picker[open]')", 5000);
  check("the new person is offered in the picker", (await p.text("#picker-body")).includes(name));
  await p.click("#picker-x");
  await p.go("/people");
  const id = made[0] && made[0].id;
  if (!id || SEEDED.has(id)) throw new Error(`refusing to delete ${id}: not the throwaway person`);
  await p.go(`/people/${id}`);
  await p.click("[data-del]");
  await p.shot(join(out, "desktop-person-delete.png"), true);
  await p.click("[data-del-yes]");
  await p.until("location.pathname === '/people'", 10000);
  const after = (await (await fetch(`${APP}/api/people`)).json()).people.map(x => x.id);
  check("the deleted person is gone, and only them", !after.includes(id) && [...SEEDED].every(x => after.includes(x)), after.join(","));
  await p.close();
}

async function twoTabs(out) {
  const a = await tab(), b = await tab();
  await a.size(DESKTOP); await b.size(DESKTOP);
  await a.go("/?p=dad"); await b.go("/?p=grandpa");
  await a.type("#ta", "Tight chest when I walk up the hill, it eased when I stopped.");
  await b.type("#ta", "Bit of a niggle in my chest, honestly it is nothing.");
  await Promise.all([sendAndWait(a, "tab A, Dad"), sendAndWait(b, "tab B, Grandpa")]);
  const [pa, pb] = [await a.eval("location.pathname"), await b.eval("location.pathname")];
  check("the two tabs hold two different assessments", pa !== pb && pa.startsWith("/c/") && pb.startsWith("/c/"));
  const [ca, cb] = await Promise.all([pa, pb].map(x => fetch(`${APP}/api/conversations/${x.slice(3)}`).then(r => r.json())));
  check("each assessment kept its own person and words",
    ca.sides[0].person_id === "dad" && cb.sides[0].person_id === "grandpa" &&
    /hill/.test(ca.sides[0].turns[0].text) && /niggle/.test(cb.sides[0].turns[0].text));
  await a.type("#ta", "It came back when I climbed the stairs.");
  await b.type("#ta", "Now it is spreading to my left arm.");
  await Promise.all([sendAndWait(a, "tab A follow-up"), sendAndWait(b, "tab B follow-up")]);
  const [la, lb] = [await a.eval("[...document.querySelectorAll('.checked')].pop()?.innerText"),
    await b.eval("[...document.querySelectorAll('.checked')].pop()?.innerText")];
  check("both follow-ups reused their own cache", /cached, read/.test(la) && /cached, read/.test(lb), `${la} | ${lb}`);
  await a.shot(join(out, "desktop-tab-a.png"), true);
  await b.shot(join(out, "desktop-tab-b.png"), true);
  await a.close(); await b.close();
}

// A follow-up on an assessment whose cache is gone: run it after restarting
// llama-server, so the re-read is real. The notice must show while it happens
// and the answer must say why afterwards.
async function reread(out, cid) {
  const p = await tab();
  await p.size(DESKTOP);
  await p.go(`/c/${cid}`);
  await p.type("#ta", "It has come back again, just now.");
  await p.click("#send");
  await p.until("/lost this conversation and is re-reading/.test(document.querySelector('[data-live]')?.innerText || '')", 60000, 250);
  check("a slow read says it is re-reading, while it happens", true);
  await p.shot(join(out, "desktop-rereading.png"));
  await p.until(`document.querySelectorAll("#thread .checked").length >= 2 && !document.querySelector("[data-live] .steps4")`, 300000, 400);
  await sleep(700);
  const last = await p.eval("[...document.querySelectorAll('.checked')].pop().innerText");
  check("the answer says it re-read everything, and why", /re-read/.test(last) && /lost this conversation/.test(last), last);
  await p.shot(join(out, "desktop-reread-answer.png"));
  await p.close();
}

// The regional add-on packs. They are not wired into retrieval, so the page
// must say so, and a cited US chunk that says 9-1-1 must carry the region's
// own number rather than be hidden.
async function regions(out) {
  const p = await tab();
  await p.size(DESKTOP);
  await p.go("/regions");
  const names = await p.text(".packs");
  check("the region page lists the packs", /Base corpus only/.test(names) && /India/.test(names)
    && /Sub-Saharan Africa/.test(names), names.slice(0, 160));
  check("it says retrieval does not change", /do not\s+change the answers/i.test(await p.text("#main .notice"))
    && /Unchanged\. The model still reads the base corpus only\./.test(names));
  check("it states the licence and that it is not for commercial use",
    /CC BY-NC-SA 3\.0 IGO/.test(names) && /Not for commercial use/.test(names));
  check("it gives the region's emergency number", /\b108\b/.test(names)
    && /no single number: local emergency services/.test(names));
  await p.shot(join(out, "desktop-regions.png"), true);
  // A pack has to be ON THIS DEVICE before it can be chosen, since 2026-09-19:
  // an uninstalled card offers Download, not "Use this region". Pull it first
  // if it is not here, which is also what a person would have to do.
  if (await p.count('[data-install="india"]')) {
    await p.click('[data-install="india"]');
    await p.until(`document.querySelector("#pack-india .dl.ok")`, 60000, 100);
    check("india installs from the distribution node before it can be chosen",
      /every one hashed from disk against the manifest/.test(await p.text("#pack-india .dl.ok")));
  }
  await p.click('[data-region="india"]');
  await sleep(300);
  check("choosing a region marks it active", await p.eval(
    `[...document.querySelectorAll('.pack.on')].map(e => e.innerText).join(' ').includes('India')`));
  check("the sidebar says which region is on", /India/.test(await p.text("#region-link")));
  await p.shot(join(out, "desktop-regions-india.png"), true);

  // The annotation, on a real cited chunk. One assessment, then the first
  // cited key whose text names 9-1-1.
  await p.go("/?p=self");
  await p.click('[data-preset="0"]');
  await sendAndWait(p, "assessment for a citation");
  const key = await p.eval(`(async () => {
    const keys = [...document.querySelectorAll("#thread .cite")].map(b => b.dataset.k);
    for (const k of keys) {
      const c = await fetch("/api/chunk/" + k).then(r => r.ok ? r.json() : null).catch(() => null);
      if (c && /\\b9-?1-?1\\b/.test(c.text)) return k;
    }
    return null;
  })()`);
  if (!key) {
    check("a cited chunk names 9-1-1, so the annotation can be checked", true, "none cited this run");
    console.log("      no cited chunk names 9-1-1 in this run, annotation not exercised");
  } else {
    await p.click(`#thread .cite[data-k="${key}"]`);
    await p.until("document.querySelector('#sheet[open]')", 10000);
    const foot = await p.text("#sheet-foot");
    check("a US chunk that says 9-1-1 carries the region's number", /9-1-1/.test(foot)
      && /\b108\b/.test(foot) && /shown unchanged/.test(foot), `${key}: ${foot.slice(0, 200)}`);
    await p.shot(join(out, "desktop-region-annotation.png"));
    await p.click("#sheet-x");
  }
  await p.size(PHONE);
  await p.go("/regions");
  await p.shot(join(out, "mobile-regions.png"), true);

  // PUT IT BACK. The region is remembered in localStorage per origin, so this
  // check used to leave India selected in whatever browser ran it, and the
  // sidebar would still say so days later. A check that changes persistent app
  // state and walks away is how a demo ends up showing a region nobody chose.
  await p.click('[data-region=""]');
  await sleep(300);
  check("the check leaves the base corpus selected, as it found it",
    await p.eval(`(localStorage.getItem("region") || "") === ""`));
  check("the sidebar is back to Base only", /Base only/.test(await p.text("#region-link")));
  await p.close();
}

// A stream that drops mid-answer, as two did once on 2026-09-19 with the server
// still finishing and saving both. The page's stream reader is made to fail
// after a few reads; the server is untouched. The page must say the answer is
// still being written, then show the saved answer without a reload.
async function drop(out) {
  const p = await tab();
  await p.size(DESKTOP);
  await p.go("/?p=self");
  await p.eval(`(() => {
    const read = ReadableStreamDefaultReader.prototype.read;
    let n = 0;
    ReadableStreamDefaultReader.prototype.read = function () {
      return ++n > 4 ? Promise.reject(new TypeError("network error")) : read.call(this);
    };
    return true;
  })()`);
  const t0 = Date.now();
  await p.click('[data-preset="0"]');
  await p.click("#send");
  await p.until("document.querySelector('#busy-note')", 120000, 250);
  check("a dropped stream says the answer is still being written", /Still writing/.test(await p.text("#busy-note")));
  check("the composer waits while it is written", await p.eval("document.querySelector('#send').disabled"));
  await p.shot(join(out, "desktop-dropped.png"));
  await p.until(`document.querySelector("#thread .bar") && !document.querySelector("#busy-note")`, 300000, 500);
  console.log(`      dropped, then saved: ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  check("the saved answer appears without a reload", await p.count("#thread .bar") === 1);
  await p.shot(join(out, "desktop-dropped-answer.png"), true);
  await p.close();
}

// A PHONE ON THE SAME WIFI, over the network rather than loopback, with touch
// and a handset user agent. The phone is a SCREEN: the model runs on the
// laptop, and the page has to say so rather than let "this device" be read as
// the phone. Everything here is what a thumb actually does.
async function phone(out, base) {
  if (base) APP = base.replace(/\/+$/, "");
  const p = await tab();
  await p.size(PHONE);
  await p.handset();
  await p.go("/");
  check("the page loads over the network, not loopback", !/127\.0\.0\.1|localhost/.test(APP), APP);
  check("the browser reports a coarse pointer, so the page takes the touch path",
    await p.eval('matchMedia("(pointer: coarse)").matches'));
  const scope = await p.text(".scope");
  check("it says the model runs on the laptop, not on this phone",
    /the model runs on the laptop, not on this phone/i.test(scope)
    && !/runs on this device/.test(scope), scope);
  check("that line is on the first screen, not below the composer", await p.eval(`(() => {
    const r = document.querySelector(".scope").getBoundingClientRect();
    const c = document.querySelector(".composer").getBoundingClientRect();
    return r.top > 0 && r.bottom <= c.top + 1;
  })()`));
  check("nothing overflows sideways at 390px",
    await p.eval("document.documentElement.scrollWidth <= window.innerWidth + 1"),
    await p.eval("document.documentElement.scrollWidth + ' vs ' + window.innerWidth"));
  await p.shot(join(out, "phone-new.png"));

  await p.click("#menu");
  await sleep(350);
  check("the drawer opens on the menu button",
    await p.eval("document.querySelector('#side').classList.contains('open') && !document.querySelector('#scrim').hidden"));
  check("the drawer covers the page rather than squeezing it",
    await p.eval("document.querySelector('#side').getBoundingClientRect().left <= 0"));
  await p.shot(join(out, "phone-drawer.png"));
  await p.click("#scrim");
  await sleep(350);
  check("it closes again on the scrim",
    await p.eval("!document.querySelector('#side').classList.contains('open')"));

  // Who this is for sits above the composer now, not across the top bar.
  check("the top bar is the menu and a new assessment, nothing else", await p.eval(
    "document.querySelectorAll('.top button, .top a').length === 2 && !document.querySelector('#chips')"));
  check("it opens on nobody, so a typed question carries no profile",
    /No profile/.test(await p.text("[data-for-name]")));
  check("the who-line is above the composer and within reach", await p.eval(`(() => {
    const f = document.querySelector("#forwho").getBoundingClientRect();
    const c = document.querySelector(".composer").getBoundingClientRect();
    return f.top >= c.top - 1 && f.bottom <= window.innerHeight;
  })()`));
  await p.click("#forwho");
  await p.until("document.querySelector('#picker[open]')", 5000);
  await sleep(250);
  check("the picker opens as a bottom sheet, full width", await p.eval(`(() => {
    const r = document.querySelector("#picker").getBoundingClientRect();
    return Math.abs(r.width - window.innerWidth) < 2 && Math.abs(r.bottom - window.innerHeight) < 2;
  })()`));
  check("it offers Compare and every person", await p.eval(
    "!!document.querySelector('#picker-body [data-compare]') && document.querySelectorAll('#picker-body [data-person]').length >= 7"));
  await p.shot(join(out, "phone-picker.png"));
  await p.click('#picker-body [data-person="mum"]');
  await sleep(300);
  check("picking a person closes the sheet and names them", await p.eval("!document.querySelector('#picker').open")
    && /Mum/.test(await p.text("[data-for-name]")));

  await p.click('[data-preset="0"]');
  check("a preset fills the composer", (await p.eval("document.querySelector('#ta').value")).length > 20);
  check("the composer sits at the bottom of the screen, in reach", await p.eval(
    "(r => Math.abs(r.bottom - window.innerHeight) < 2)(document.querySelector('.composer').getBoundingClientRect())"));
  await sendAndWait(p, "phone, one answer");
  check("the answer came back on the phone", await p.count("#thread .bar") === 1);
  await p.shot(join(out, "phone-answer.png"), true);

  if (await p.count("#thread .cite")) {
    await p.click("#thread .cite");
    await p.until("document.querySelector('#sheet[open]')", 10000);
    await sleep(300);
    check("a source opens as a bottom sheet, full width", await p.eval(`(() => {
      const r = document.querySelector("#sheet").getBoundingClientRect();
      return Math.abs(r.width - window.innerWidth) < 2 && Math.abs(r.bottom - window.innerHeight) < 2
        && r.height > 200;
    })()`));
    check("the sheet shows the chunk and its source", (await p.text("#sheet-body")).length > 80
      && /http/.test(await p.text("#sheet-foot")));
    await p.shot(join(out, "phone-sheet.png"));
    await p.click("#sheet-x");
    await sleep(250);
    check("the sheet closes", await p.eval("!document.querySelector('#sheet').open"));
  } else {
    check("a source chip was there to open", false, "this answer cited nothing");
  }

  // Compare: one tap makes the beat, and on a phone the two sides are tabs.
  await p.go("/");
  await p.click('[data-preset="2"]');
  await p.until(`document.querySelectorAll("#thread .bar, #thread .err-panel").length >= 2
    && !document.querySelector("[data-live] .steps4")`, 300000, 300);
  await sleep(600);
  check("compare answers both sides on the phone too", await p.count(".turn.pair .side-ans .bar") === 2);
  check("the two sides are A/B tabs at this width", await p.count(".turn.pair .tabs [data-tab]") === 2
    && await p.eval("getComputedStyle(document.querySelector('.turn.pair .tabs')).display !== 'none'"));
  check("side A is the one showing", await p.eval(
    "!document.querySelectorAll('.turn.pair .side-ans')[0].hidden && document.querySelectorAll('.turn.pair .side-ans')[1].hidden"));
  await p.shot(join(out, "phone-compare-a.png"));
  await p.click('.turn.pair .tabs [data-tab="1"]');
  await sleep(300);
  check("tapping B switches to the other person", await p.eval(
    "document.querySelectorAll('.turn.pair .side-ans')[0].hidden && !document.querySelectorAll('.turn.pair .side-ans')[1].hidden"));
  check("still nothing overflowing sideways",
    await p.eval("document.documentElement.scrollWidth <= window.innerWidth + 1"));
  await p.shot(join(out, "phone-compare-b.png"));
  await p.close();
}

// The finish review's screenshots: the surface as a visitor meets it, and every
// state the reviewer asked to see. IDs are saved assessments in data/.
async function review(out, ids) {
  const [single, pair, ungrounded, child, green, guardsId] = ids.split(",");
  const p = await tab();
  await p.size(DESKTOP);
  await p.go(`/c/${single}`);
  await p.shot(join(out, "desktop.png"));
  await p.shot(join(out, "desktop-full.png"), true);
  await p.click(".cite");
  await p.until("document.querySelector('#sheet[open]')", 10000);
  await sleep(250);
  await p.shot(join(out, "desktop-sheet.png"));
  await p.click("#sheet-x");
  await p.go(`/c/${pair}`);
  await oneLeftEdge(p, "review compare");
  await p.shot(join(out, "desktop-compare.png"), true);
  await p.go(`/c/${ungrounded}`);
  await p.shot(join(out, "desktop-ungrounded.png"), true);
  await p.go(`/c/${child}`);
  await p.shot(join(out, "desktop-child.png"));
  await p.go(`/c/${green}`);
  await p.shot(join(out, "desktop-green.png"), true);
  await p.go(`/c/${guardsId}`);
  await p.shot(join(out, "desktop-guards.png"), true);
  await p.go("/?p=mum");
  await p.shot(join(out, "desktop-new.png"));
  await p.go("/people");
  await p.shot(join(out, "desktop-people.png"), true);
  await p.go("/people/mum");
  await p.until("document.querySelector('.preview .w-rule')");
  await p.shot(join(out, "desktop-person.png"), true);
  await p.go("/?p=aunt");
  await p.click('[data-preset="1"]');
  await p.click("#send");
  await p.until("/tokens/.test(document.querySelector('[data-live] .steps4')?.innerText || '')", 180000);
  await p.shot(join(out, "desktop-live.png"));
  await p.click("[data-raw-toggle]");
  await sleep(1200);
  await p.shot(join(out, "desktop-live-raw.png"));
  await p.until(`!document.querySelector("[data-live] .steps4") && document.querySelector("#thread .bar")`, 300000, 400);
  await sleep(800);
  await p.shot(join(out, "desktop-live-result.png"), true);
  await p.size(PHONE);
  await p.go(`/c/${single}`);
  await p.shot(join(out, "mobile.png"));
  await p.shot(join(out, "mobile-full.png"), true);
  await p.go("/?p=mum");
  await p.shot(join(out, "mobile-new.png"));
  await p.go(`/c/${pair}`);
  await p.shot(join(out, "mobile-compare.png"));
  await p.go("/people");
  await p.shot(join(out, "mobile-people.png"), true);
  await p.go("/people/mum");
  await p.until("document.querySelector('.preview .w-rule')");
  await p.shot(join(out, "mobile-person.png"), true);
  await p.go(`/c/${single}`);
  await p.click("#menu");
  await sleep(400);
  await p.shot(join(out, "mobile-drawer.png"));
  await p.close();
}

// THE MICROPHONE, END TO END. Chrome's fake capture device plays a known WAV
// into a real getUserMedia, so this exercises MediaRecorder, the 16 kHz
// resample, /api/transcribe and whisper.cpp, not a stub. What it is really
// here to prove is the safety property: voice FILLS THE BOX AND NEVER
// ASSESSES. With a URL it checks the other half, that over the wifi the button
// is absent with a reason rather than present and broken.
async function voice(out, url) {
  if (url) APP = url;
  const p = await tab();
  await p.size(url ? PHONE : DESKTOP);
  if (url) await p.handset();
  await p.go("/");

  if (url) {
    // A plain http address on the wifi is not a secure context, so
    // navigator.mediaDevices does not exist there. Measured 2026-09-19.
    check("no microphone over the wifi", await p.count("#mic") === 0);
    const why = await p.text("#heard-slot");
    check("the page says why, in one line", /only works on the laptop/i.test(why)
      && why.split("\n").filter(Boolean).length === 1, why);
    await p.shot(join(out, "voice-phone-no-mic.png"));
    await p.close();
    return;
  }

  check("the composer offers a microphone", await p.count("#mic") === 1);
  const spoken = await installFakeMic(p, makeSpokenWav(out));
  console.log(`      speaking ${spoken} s into the page`);
  await p.click("#mic");
  await p.until("document.querySelector('#mic.on')", 10000);
  check("tapping starts recording", await p.count("#mic.on") === 1);
  check("send is closed while recording", await p.eval("document.querySelector('#send').disabled"));
  await p.shot(join(out, "voice-recording.png"));
  await sleep(spoken * 1000 + 900);       // let the whole sentence play through
  await p.click("#mic");
  await p.until("document.querySelector('#ta').value.length > 20", 60000);

  const said = await p.eval("document.querySelector('#ta').value");
  check("the words land in the composer", /middle of my chest/i.test(said), said);
  check("nothing was sent", await p.eval("location.pathname") === "/");
  check("no answer started", await p.count("[data-live]") === 0);
  const heard = await p.text("#heard-slot");
  check("the transcription time is shown", /Heard in [\d.]+ s/.test(heard), heard);
  check("it says to check the words", /Read it before you send/.test(heard), heard);
  await p.shot(join(out, "voice-transcript.png"));

  // Correcting it is the whole point of putting it in the box, so the line
  // says when it happened and the SOAP note keeps what was originally heard.
  await p.eval(`(() => { const e = document.querySelector("#ta");
    e.focus(); e.value += " It spread to my jaw.";
    e.dispatchEvent(new Event("input", { bubbles: true })); return true; })()`);
  await sleep(250);
  const edited = await p.text("#heard-slot");
  check("editing is recorded", /then edited/.test(edited), edited);
  await p.shot(join(out, "voice-edited.png"));

  await sendAndWait(p, "spoken assessment");
  await p.until("[...document.querySelectorAll('[data-live]')].every(e => !e.querySelector('.steps4'))", 300000, 400);
  await p.until("!document.querySelector('[data-live]')", 60000);
  await sleep(800);
  const line = await p.text(".checked");
  check("the checked line says it was heard", /heard [\d.]+ s/.test(line), line);
  await p.click(".checked");
  const details = await p.text(".details");
  check("the details panel has a Heard row",
    /Heard/.test(details) && /on this machine/.test(details), details.slice(0, 240));
  check("the details panel records the correction",
    /edited before sending/.test(details), details.slice(0, 240));
  await p.shot(join(out, "voice-answer-details.png"), true);

  // And the clinical export, which is the reason it rides on the turn at all.
  const note = await p.eval(`fetch(document.querySelector(".export .link-a").href).then(r => r.text())`);
  // The note is wrapped to a column, so a sentence can straddle a line break.
  // Match against the collapsed text, never the laid-out text.
  const flat = note.replace(/\s+/g, " ");
  check("the SOAP note says the symptoms were spoken", /spoken, not typed/.test(flat));
  check("the SOAP note records the correction", /CORRECTED by the patient before sending/.test(flat));
  check("the SOAP note keeps what was heard", /Heard as: "/.test(flat));
  check("the SOAP note names the model and the time",
    /whisper\.cpp base\.en-q5_1 in [\d.]+ s from [\d.]+ s of speech/.test(flat), flat.slice(0, 400));
  writeFileSync(join(out, "voice-soap.txt"), note);
  console.log(`      saved ${join(out, "voice-soap.txt")}`);
  await p.close();
}

// A PACK CROSSING FROM THE NODE TO THIS DEVICE. Needs the distribution node
// on 8790 (python 07-distribute/server.py) and at least one pack not yet
// installed here; clear them with: rm -rf 06-demo/data/packs
//
// The download itself is over in well under a second, because the regional
// packs are kilobytes and the node is on loopback. What this really checks is
// that the page shows WHERE the pack is at each step and keeps the evidence:
// every file hashed from disk against the manifest, and the pack digest
// recomputed from the files. Retrieval must still say it is unchanged.
async function packsFlow(out) {
  const p = await tab();
  await p.size(DESKTOP);
  await p.go("/regions");

  const notices = await p.eval(`[...document.querySelectorAll("#main .notice")].map(e => e.innerText).join(" | ")`);
  check("the page names the distribution node", /distribution node at http/.test(notices), notices.slice(0, 200));
  check("the node is reachable", await p.count(".node-dot.on") === 1,
    "start it with: python 07-distribute/server.py");

  const base = await p.eval(`document.querySelector(".packs .pack").innerText`);
  check("the base corpus offers no download", !/Download/.test(base) && /always installed/.test(base),
    base.slice(0, 160));

  const target = await p.eval(`(() => {
    const b = document.querySelector("[data-install]");
    return b ? { id: b.dataset.install, label: b.innerText } : null;
  })()`);
  if (!target) {
    check("a pack is available to download", false, "every pack is already installed; rm -rf 06-demo/data/packs");
    await p.close();
    return;
  }
  check("an uninstalled pack offers a download with its size",
    /^Download\s·\s[\d.]+ (B|kB|MB|GB)$/.test(target.label.trim()), target.label);
  check("and its card says the pack is on the node, not here",
    /on the node, not on this device yet/.test(await p.text(`#pack-${target.id}`)));
  await p.shot(join(out, "packs-before.png"), true);

  await p.click(`[data-install="${target.id}"]`);
  await p.until(`document.querySelector("#pack-${target.id} .dl.ok")`, 60000, 100);
  const panel = await p.text(`#pack-${target.id} .dl.ok`);
  check("the card says it is installed here, with the file count and size",
    /Installed on this device/.test(panel) && /\d+ files/.test(panel), panel.slice(0, 200));
  check("and that every file was hashed from disk against the manifest",
    /every one hashed from disk against the manifest/.test(panel), panel.slice(0, 200));
  check("and shows the pack digest", /pack_sha256 [0-9a-f]{24}/.test(panel), panel.slice(0, 200));
  check("the button becomes Use this region",
    /Use this region/.test(await p.text(`#pack-${target.id} .pack-act`)));
  check("retrieval still says it is unchanged",
    /Unchanged\. The model still reads the base corpus only\./.test(await p.text(`#pack-${target.id}`)));
  await p.shot(join(out, "packs-installed.png"), true);

  await p.click(`#pack-${target.id} [data-region]`);
  await sleep(400);
  check("an installed pack can then be made active",
    await p.count(`#pack-${target.id}.on`) === 1);
  check("the sidebar follows", !/Base only/.test(await p.text("#region-link")));
  await p.shot(join(out, "packs-active.png"), true);

  // Put it back, the way the regions check now does.
  await p.click('.packs .pack [data-region=""]');
  await sleep(300);
  check("and the base corpus can be chosen again",
    (await p.eval(`localStorage.getItem("region") || ""`)) === "");

  // A reload proves it is on disk and not in the page's head.
  await p.go("/regions");
  check("the install survives a reload",
    /Installed on this device/.test(await p.text(`#pack-${target.id}`)));
  await p.close();
}

const [mode, out = ".", arg, arg2] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
// Only the voice check needs an AudioContext that runs without a click.
// Every other check launches with no media flags at all, exactly as before.
const chrome = await launch(mode === "voice"
  ? ["--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required"] : []);
try {
  const run = { shots, flow, compare, guards, people, "two-tabs": twoTabs, reread, review, drop,
                regions, phone, voice, packs: packsFlow, queue, sync: syncFlow, base }[mode];
  if (!run) throw new Error(`unknown mode ${mode}`);
  await run(out, arg, arg2);
} catch (e) {
  failures++;
  console.log(`FAIL  ${e.message}`);
} finally {
  chrome.kill();
  // Wait for the browser to actually let go of the DevTools port, not for an
  // arbitrary 500 ms. See waitForPortFree: the flat sleep is what made the
  // next mode in a suite attach to a dying browser. Chrome also writes its
  // profile out as it exits, so this is the same wait for both purposes.
  await waitForPortFree();
  if (chrome.profile) rmSync(chrome.profile, { recursive: true, force: true });
}
console.log(`${failures ? `${failures} failed` : "all passed"}`);
process.exit(failures);
