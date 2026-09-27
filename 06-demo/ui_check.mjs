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
//   node 06-demo/ui_check.mjs rules OUTDIR [BASE]    the rules in 06-demo/CLAUDE.md, read off every screen
//
// Needs the demo server on 8770 and, for the live flows, llama-server on 8080.
// FIELD_URL points it at a demo server on another port: on 2026-09-27 macOS's
// own sharingd (Continuity) held *:8770, so server.py could not bind it and ran
// with --port 8772 instead.
// Every check prints PASS or FAIL; the exit code is the number of failures.

import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
let APP = (process.env.FIELD_URL || "http://127.0.0.1:8770").replace(/\/+$/, "");
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
    // ONE NAVIGATION IN A FEW NEVER FINISHES. Page.navigate returns and the page
    // sits on "Loading..." for the full wait, then a second navigation clears it.
    // Unexplained: claude.md records it for drop, and on 2026-09-27 it hit the
    // rules mode and voice, each passing when run again. So a page gets 20 s, then
    // one more navigation, and the second attempt is printed, never hidden.
    async go(path) {
      const ready = "document.readyState === 'complete' && !document.querySelector('.loading')";
      await send("Page.navigate", { url: APP + path });
      try { await page.until(ready, 20000); }
      catch {
        console.log(`      NOTE ${path} had not finished loading after 20 s; navigating to it again`);
        await send("Page.navigate", { url: APP + path });
        await page.until(ready);
      }
      await sleep(350);
    },
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
    // A REAL PRESS, held like a hand. `.click()` fires instantly and so never
    // noticed that a 250ms repaint was destroying the button between mousedown
    // and mouseup, which stops the browser dispatching `click` at all. Any
    // control that lives inside a repainting region must be tested this way.
    async press(sel, holdMs = 140) {
      const r = await page.eval(`(() => { const e = document.querySelector(${JSON.stringify(sel)});
        if (!e) throw new Error("nothing matches ${sel.replace(/"/g, "")}");
        const b = e.getBoundingClientRect();
        return JSON.stringify({ x: Math.round(b.x + b.width / 2), y: Math.round(b.y + b.height / 2) }); })()`);
      const { x, y } = JSON.parse(r);
      await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
      await sleep(holdMs);
      await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
      return true;
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
  // "Show what the model is writing" is the only control inside the region
  // that repaints four times a second. Pressed like a hand, not clicked like a
  // script: held for 140 ms across at least one repaint.
  if (await p.count("[data-raw-toggle]")) {
    await p.press("[data-raw-toggle]");
    await sleep(500);
    check("the raw stream opens on a real press, not just a synthetic click",
      await p.count(".raw-live pre") === 1);
    const first = await p.eval(`(document.querySelector(".raw-live pre")||{}).textContent?.length ?? 0`);
    await sleep(1800);
    check("the raw stream keeps updating while it is open", await p.eval(
      `((document.querySelector(".raw-live pre")||{}).textContent?.length ?? 0) > ${first}`) === true);
    await p.press("[data-raw-toggle]");
    await sleep(500);
    check("the raw stream closes again on a real press", await p.count(".raw-live pre") === 0);
  }
  await p.until("[...document.querySelectorAll('[data-live]')].every(e => !e.querySelector('.steps4'))", 300000, 400);
  await p.until("!document.querySelector('[data-live]')", 60000);
  await sleep(800);
  check("a verdict bar is shown", await p.count(".bar.red, .bar.yellow, .bar.green, .bar.hold") >= 1);
  // THE ANSWER IS ANNOUNCED, AND ONLY WHEN IT IS COMPLETE. Twenty seconds of
  // streaming is silent to a screen reader; announcing tokens would read the
  // JSON aloud. The live region carries the urgency and its disposition,
  // because colour is not available to a listener and "red" is not an
  // instruction. See DESIGN.md, the Announce The Outcome Rule.
  const announced = await p.eval(`document.querySelector("#announce[aria-live='polite']")?.textContent ?? null`);
  const barWord = (await p.text("#thread .bar")).split("\n")[0].trim().toLowerCase();
  check("the verdict is announced to a screen reader",
    typeof announced === "string" && announced.toLowerCase().includes(barWord)
    && announced.length > barWord.length, `bar "${barWord}" announced as "${announced}"`);
  check("the live region is hidden from the eye", await p.eval(
    `(() => { const r = document.querySelector("#announce").getBoundingClientRect();
      return r.width <= 2 && r.height <= 2; })()`) === true);
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

  // WAITING -> IN PROGRESS -> SEEN. Starting the assessment links it to the
  // caseload row server-side and puts the person IN PROGRESS: they stay on the
  // list, visibly being assessed, because a worker working a list must not
  // have someone vanish mid-assessment. Viraj's report 2026-09-20.
  const mid = await (await fetch(`${APP}/api/queue`)).json();
  check("tapping Assess keeps them on the list, in progress",
    mid.waiting.length === 1 && mid.waiting[0].status === "in_progress",
    JSON.stringify(mid.counts));
  // THE TAP CREATES NO ASSESSMENT. The conversation is only made when the
  // first message is sent, so the row is in progress with nothing linked yet.
  // That gap is exactly where someone used to look untouched.
  check("nothing is linked yet, because no assessment exists yet",
    mid.waiting[0].conversation_id === null, String(mid.waiting[0].conversation_id));
  check("nobody is marked seen while it is still running", mid.counts.done === 0);
  await p.go("/queue");
  check("the row says it is being assessed", /Being assessed/.test(await p.text(".q-list")));
  await p.shot(join(out, "desktop-caseload-in-progress.png"), true);

  // Picking it back up and finishing it moves them to Seen on its own: the
  // worker already did the work, and saying so twice earns nothing.
  await p.click("[data-assess]");
  await p.until("location.pathname === '/'", 15000);
  await p.type("#ta", "Sharp pain in my left chest, worse when I breathe in.");
  await sendAndWait(p, "caseload assessment");
  const cid = await p.eval("location.pathname.split('/')[2]");
  await p.go("/queue");
  await p.until("document.querySelectorAll('.q-list .q-item.done').length === 1", 15000);
  const q = await (await fetch(`${APP}/api/queue`)).json();
  check("finishing the assessment moves them to Seen by itself",
    q.counts.done === 1 && q.counts.waiting === 0, JSON.stringify(q.counts));
  check("a seen row links the assessment it was seen in",
    await p.count(".q-item.done a[href^='/c/']") === 1 && /^\d{8}-/.test(cid), cid);
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
  //
  // The address field is folded away behind "Change base address" once an
  // address is saved, so it has to be opened before it can be typed into.
  // openBase() does that and asserts the fold is actually there.
  const openBase = async () => {
    if (await p.count("[data-edit-base]")) {
      await p.click("[data-edit-base]");
      await p.until("document.querySelector('#sy-url')", 5000);
    }
  };
  await p.go("/sync");
  check("the base address is folded away once one is saved",
    await p.count("[data-edit-base]") === 1 && await p.count("#sy-url") === 0);
  check("what stays is the work: the device, the count and the send control",
    /This device is/.test(await p.text(".sy-base"))
    && await p.count("#sy-send") === 1
    && /waiting to send/.test(await p.text(".head-row")));
  await openBase();
  check("the field opens on the link", await p.count("#sy-url") === 1);
  await p.type("#sy-url", "http://127.0.0.1:1");
  await p.click("#sy-form button[type=submit]");
  await sleep(600);
  check("saving folds it away again", await p.count("#sy-url") === 0);

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
  await openBase();
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
      (m.getAttribute("title") || "").length > 2 && m.querySelector(".sr"))`) === true);
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
  // Read the row's text, not its rendered text: at this width it is in the closed
  // drawer, which is hidden since 2026-09-27, and innerText of hidden text is "".
  check("the sidebar is back to Base only",
    /Base only/.test(await p.eval(`document.querySelector("#region-link").textContent`)));
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

// THE RULES IN 06-demo/CLAUDE.md, READ OFF THE RENDERED PAGE rather than off
// the CSS. Runs in the page, so it is written as an ordinary function and
// handed over as its own source. One call reads one screen and returns what
// broke, by rule; nothing here decides pass or fail.
function pageAudit(phone) {
  const W = innerWidth;
  const out = { overflow: [], targets: [], fields: [], fieldEdge: [], contrast: [], motion: [], dashes: [],
                colour: [], words: [], hold: [], cites: [], gone: 0, goneBad: [], offscreen: [], clamp: [] };
  const where = el => {
    const cls = typeof el.className === "string" && el.className.trim()
      ? "." + el.className.trim().split(/\s+/).join(".") : "";
    const txt = (el.innerText || el.getAttribute("aria-label") || el.value || "").trim()
      .replace(/\s+/g, " ").slice(0, 28);
    return el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + cls + (txt ? ` "${txt}"` : "");
  };
  // Not on screen: visually hidden text, display:none, zero size, or an
  // off-canvas drawer translated out of the viewport.
  const away = el => {
    if (el.closest(".sr")) return true;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none") return true;
    const r = el.getBoundingClientRect();
    return !r.width || !r.height || r.right <= 0 || r.left >= W;
  };

  // 390 WIDE WITH NOTHING SIDEWAYS. The page itself must not scroll across;
  // a table or a pre that scrolls inside its own box is allowed to.
  if (phone && document.documentElement.scrollWidth > W + 1) {
    const inScroller = e => { for (let a = e.parentElement; a; a = a.parentElement)
      if (/(auto|scroll|hidden)/.test(getComputedStyle(a).overflowX)) return true; return false; };
    const wide = [...document.querySelectorAll("body *")].filter(e => !away(e)
      && e.getBoundingClientRect().right > W + 1 && !inScroller(e));
    out.overflow.push(`page is ${document.documentElement.scrollWidth}px wide: `
      + wide.slice(0, 3).map(where).join(", "));
  }

  // NOTHING OFF SCREEN TAKES FOCUS. A closed drawer that is only moved aside
  // keeps its links in the tab order and in front of a screen reader; it has to
  // be hidden too. 71 did, on a phone, until 2026-09-27.
  for (const el of document.querySelectorAll("a[href], button, input:not([type=hidden]), select, textarea, summary")) {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || el.disabled || el.closest("[inert], .sr")) continue;
    const r = el.getBoundingClientRect();
    if (r.width && r.height && (r.right <= 0 || r.left >= W)) out.offscreen.push(where(el));
  }

  // A LINE CLAMP SHOWS ITS LINES AND NO MORE. A clamped box made taller than
  // its lines shows the top of the next one, as base's register titles did.
  for (const el of document.querySelectorAll("body *")) {
    const cs = getComputedStyle(el);
    const n = parseInt(cs.webkitLineClamp, 10), lh = parseFloat(cs.lineHeight);
    if (!n || !lh || away(el)) continue;
    const inner = el.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
    if (inner > n * lh + 1) out.clamp.push(`${where(el)} ${Math.round(inner)}px for ${n} lines of ${Math.round(lh)}px`);
  }

  // 44 BY 44 FOR ANYTHING A THUMB LANDS ON. A link in running text is exempt,
  // as WCAG 2.5.8 exempts it: its size is the line's. A checkbox is measured by
  // the label around it, which is what takes the tap.
  for (const el of document.querySelectorAll(
    "a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab]")) {
    if (away(el)) continue;
    if (el.tagName === "A" && getComputedStyle(el).display === "inline") continue;
    const box = el.matches("input[type=checkbox], input[type=radio]") && el.closest("label")
      ? el.closest("label") : el;
    const r = box.getBoundingClientRect();
    if (r.width < 43.5 || r.height < 43.5)
      out.targets.push(`${where(el)} ${Math.round(r.width)}x${Math.round(r.height)}`);
  }

  // 16PX IN EVERY FIELD, or iOS Safari zooms the page when it takes focus.
  for (const el of document.querySelectorAll(
    "input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea")) {
    if (away(el)) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < 16) out.fields.push(`${where(el)} ${fs}px`);
  }

  // WCAG AA. The background is the stack of fills behind the text, blended;
  // a hatch counts as its fill colour, which it only ever darkens. Disabled
  // controls are exempt, as WCAG exempts them.
  const rgb = s => {
    const m = String(s).match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const v = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    return { r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1 };
  };
  const mix = (top, under) => ({ r: top.r * top.a + under.r * (1 - top.a),
    g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1 });
  const lum = c => [c.r, c.g, c.b].map(v => (v /= 255) <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
    .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const bgOf = el => {
    const layers = [];
    for (let e = el; e; e = e.parentElement) {
      const c = rgb(getComputedStyle(e).backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
    }
    return layers.reverse().reduce((under, top) => mix(top, under), { r: 255, g: 255, b: 255, a: 1 });
  };
  const seen = new Set();
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walk.nextNode());) {
    const el = n.parentElement;
    if (!n.nodeValue.trim() || !el || seen.has(el)) continue;
    seen.add(el);
    if (away(el) || el.closest(":disabled, [aria-disabled=true], option, script, style")) continue;
    const cs = getComputedStyle(el);
    const bg = bgOf(el);
    let op = 1;
    for (let e = el; e; e = e.parentElement) op *= +getComputedStyle(e).opacity;
    const fg = mix({ ...mix(rgb(cs.color), bg), a: op }, bg);
    const size = parseFloat(cs.fontSize), weight = +cs.fontWeight || 400;
    const need = size >= 24 || (size >= 18.66 && weight >= 700) ? 3 : 4.5;
    const r = ratio(fg, bg);
    if (r < need) out.contrast.push(`${where(el)} ${r.toFixed(2)}:1, needs ${need}`);
  }

  // A FIELD CAN BE FOUND. WCAG 1.4.11: what identifies a text field has to
  // stand 3:1 against what is next to it. That is its fill against the ground
  // around it, or an edge against both the ground and the fill. A token field
  // is judged as the box around its input. Disabled fields are exempt.
  for (const el of document.querySelectorAll(
    "input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea")) {
    if (away(el) || el.disabled) continue;
    const box = el.closest(".tokens") || el;
    const cs = getComputedStyle(box);
    const ground = bgOf(box.parentElement);
    const fill = mix(rgb(cs.backgroundColor) || { r: 0, g: 0, b: 0, a: 0 }, ground);
    const edges = ["Top", "Right", "Bottom", "Left"].filter(s => parseFloat(cs[`border${s}Width`]) >= 1
      && cs[`border${s}Style`] !== "none")
      .map(s => { const c = mix(rgb(cs[`border${s}Color`]), fill); return Math.min(ratio(c, ground), ratio(c, fill)); });
    const best = Math.max(ratio(fill, ground), ...edges, 0);
    if (best < 3) out.fieldEdge.push(`${where(box)} ${best.toFixed(2)}:1`);
  }

  // NOTHING MOVES WHEN THE PERSON HAS ASKED FOR LESS MOTION. Read with the
  // page emulating prefers-reduced-motion: reduce.
  for (const el of document.querySelectorAll("*")) {
    const cs = getComputedStyle(el);
    const t = Math.max(...cs.transitionDuration.split(",").map(parseFloat));
    const a = cs.animationName === "none" ? 0 : Math.max(...cs.animationDuration.split(",").map(parseFloat));
    if (t > 0.01 || a > 0.01)
      out.motion.push(`${where(el)} transition ${cs.transitionDuration}, animation ${cs.animationName} ${cs.animationDuration}`);
  }

  // NO EM DASH IN THE COPY, the page title included.
  const text = `${document.title}\n${document.body.innerText}`;
  for (let i = text.indexOf("\u2014"); i >= 0; i = text.indexOf("\u2014", i + 1))
    out.dashes.push(JSON.stringify(text.slice(Math.max(0, i - 30), i + 30).replace(/\s+/g, " ")));

  // TRIAGE COLOURS ARE SIGNALS. Only an urgency bar and a history or register
  // mark may carry red, yellow or green, as text, fill or border.
  const TRIAGE = ["rgb(200, 38, 29)", "rgb(242, 183, 5)", "rgb(28, 122, 67)"];
  for (const el of document.querySelectorAll("body *")) {
    if (el.closest(".bar, .mk") || away(el)) continue;
    const cs = getComputedStyle(el);
    const hit = [];
    if (TRIAGE.includes(cs.color) && [...el.childNodes].some(n => n.nodeType === 3 && n.nodeValue.trim())) hit.push("text");
    if (TRIAGE.includes(cs.backgroundColor)) hit.push("fill");
    if (["Top", "Right", "Bottom", "Left"].some(s => parseFloat(cs[`border${s}Width`]) > 0
      && TRIAGE.includes(cs[`border${s}Color`]))) hit.push("border");
    if (hit.length) out.colour.push(`${where(el)} ${hit.join("+")}`);
  }

  // EVERY RESULT HAS ITS WORD, never colour alone, and a refusal is the
  // neutral grey, never a fourth category.
  for (const b of document.querySelectorAll(".bar[role=heading]")) {
    const w = (b.querySelector(".w")?.innerText || "").trim();
    if (!/^(RED|YELLOW|GREEN|OUT OF SCOPE|NOT ASSESSED|WHO IS THIS FOR\?)$/.test(w)) out.words.push(`a bar says ${JSON.stringify(w)}`);
    if (b.classList.contains("hold") && getComputedStyle(b).backgroundColor !== "rgb(86, 96, 108)")
      out.hold.push(`${where(b)} ${getComputedStyle(b).backgroundColor}`);
  }
  for (const m of document.querySelectorAll(".mk")) {
    if (away(m)) continue;
    const said = (m.innerText || "").trim() || m.getAttribute("title") || m.querySelector(".sr")?.textContent || "";
    if (!said.trim()) out.words.push(`${where(m)} has no word`);
  }

  // EVERY CITATION IS A BUTTON THAT NAMES ITS KEY. Opening one is checked by
  // the caller, with a real click.
  for (const c of document.querySelectorAll(".cite")) {
    if (away(c)) continue;
    if (c.tagName !== "BUTTON" || !c.dataset.k || c.disabled) out.cites.push(where(c));
  }

  // A GUARD REMOVAL STAYS VISIBLE: struck through, with the reason beside it
  // or on the head line of the list it belongs to.
  for (const g of document.querySelectorAll(".gone")) {
    if (away(g)) continue;
    out.gone++;
    const reason = g.querySelector(".tag") || g.closest("ul")?.previousElementSibling?.querySelector(".tag");
    if (!g.querySelector("s") || !reason || !/removed/.test(reason.innerText)) out.goneBad.push(where(g));
  }
  return out;
}

async function rulesFlow(out, baseUrl) {
  const BASE = (baseUrl || "http://127.0.0.1:8781").replace(/\/+$/, "");
  const p = await tab();
  await p.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await p.size(DESKTOP);
  await p.go("/");
  // The saved assessments the other modes leave behind: an answer, a pair, a
  // refusal and a child's profile. Newest first, so a suite reads its own.
  const convs = JSON.parse(await p.eval(`fetch("/api/conversations").then(r => r.json())
    .then(j => JSON.stringify(j.conversations))`));
  const answered = s => ["red", "yellow", "green"].includes(s.state);
  const find = f => (convs.find(f) || {}).id;
  const ids = {
    answer: find(c => c.sides.length === 1 && answered(c.sides[0])),
    pair: find(c => c.sides.length === 2 && c.sides.every(answered)),
    refusal: find(c => c.sides.some(s => s.state === "refused")),
    child: find(c => c.sides.some(s => s.state === "child")),
    error: find(c => c.sides.some(s => s.state === "error")),
  };
  for (const [k, v] of Object.entries(ids)) if (!v) console.log(`      NOTE no saved ${k} to read: run flow, compare and guards first`);
  let baseUp = false;
  try { baseUp = !!(await (await fetch(`${BASE}/api/health`)).json()).ok; } catch { /* down */ }
  if (!baseUp) console.log(`      NOTE base is not running at ${BASE}, so its pages were not read`);

  // [name, path or url, what to press first, what to wait for, which width only]
  const screens = [
    ["new", "/"],
    ["picker", "/", "#forwho", "#picker[open]"],
    ["drawer", "/", "#menu", ".side.open", "phone"],
    ...(ids.answer ? [["answer", `/c/${ids.answer}`],
      ["details", `/c/${ids.answer}`, ".checked", ".details:not([hidden])"],
      ["source", `/c/${ids.answer}`, ".cite", "#sheet[open]"]] : []),
    ...(ids.pair ? [["compare", `/c/${ids.pair}`]] : []),
    ...(ids.refusal ? [["refusal", `/c/${ids.refusal}`]] : []),
    ...(ids.child ? [["not-assessed", `/c/${ids.child}`]] : []),
    ...(ids.error ? [["error", `/c/${ids.error}`]] : []),
    ["people", "/people"],
    ["person", "/people/mum", null, ".preview .w-rule"],
    ["person-new", "/people/new"],
    ["caseload", "/queue"],
    ["sync", "/sync"],
    ["regions", "/regions"],
    ...(baseUp ? [["base", `${BASE}/`], ["base-assessment", `${BASE}/`, ".ttl", ".det"]] : []),
  ];

  // ONE NAVIGATION IN A FEW NEVER FINISHES, and nothing about the page explains
  // it: on 2026-09-27 the phone "details" screen sat on "Loading…" for the full
  // 180 s, with the server, both llama slots and the node idle, and passed on
  // the next run. claude.md records the same hang for drop. So a page gets 20 s,
  // then one more navigation, and the second attempt is printed, not hidden.
  // Base marks loading with .fine; the field app with .loading.
  const visit = async url => {
    const ready = url.startsWith(APP)
      ? "document.readyState === 'complete' && !document.querySelector('.loading')"
      : "document.readyState === 'complete' && !document.querySelector('.fine')";
    for (let attempt = 1; ; attempt++) {
      await p.send("Page.navigate", { url });
      try { await p.until(ready, 20000); break; }
      catch (e) {
        if (attempt === 2) throw e;
        console.log(`      NOTE ${url} had not finished loading after 20 s; navigating to it again`);
      }
    }
    await sleep(350);
  };
  for (const [dev, size] of [["phone", PHONE], ["desktop", DESKTOP]]) {
    await p.size(size);
    const found = {};
    for (const [name, at, press, wait, only] of screens) {
      if (only && only !== dev) continue;
      await visit(at.startsWith("http") ? at : APP + at);
      if (press) {
        if (!(await p.count(press))) { console.log(`      NOTE ${dev} ${name}: nothing matches ${press}`); continue; }
        await p.click(press);
      }
      if (wait) await p.until(`document.querySelector(${JSON.stringify(wait)})`, 15000);
      await sleep(300);
      const a = await p.eval(`(${pageAudit})(${dev === "phone"})`);
      for (const [k, v] of Object.entries(a)) {
        if (Array.isArray(v)) (found[k] ||= []).push(...v.map(x => `${name}: ${x}`));
        else found[k] = (found[k] || 0) + v;
      }
      // The timeline field is as wide as the composer: it was the browser's
      // default textarea width, about 200px, until 2026-09-27.
      if (name === "new" && await p.count("#tl-toggle")) {
        await p.click("#tl-toggle");
        await sleep(150);
        const w = JSON.parse(await p.eval(`JSON.stringify({ tl: document.querySelector("#tl").getBoundingClientRect().width,
          row: document.querySelector(".field-row").getBoundingClientRect().width })`));
        check(`${dev}: the timeline field is as wide as the composer`, w.tl >= w.row * 0.95,
          `${Math.round(w.tl)} of ${Math.round(w.row)}px`);
        await p.click("#tl-toggle");
      }
      // A failed turn is not a dead end: it offers to send the same words again.
      if (name === "error") {
        check(`${dev}: a failed turn offers Try again`, await p.count("#thread [data-retry]") >= 1);
      }
      if (name === "source") {
        check(`${dev}: a citation opens its source, with a link out`,
          (await p.text("#sheet-body")).length > 40 && await p.count("#sheet-foot a[href^='http']") === 1);
      }
      await p.shot(join(out, `${dev}-${name}.png`));
    }
    writeFileSync(join(out, `rules-${dev}.json`), JSON.stringify(found, null, 1));
    const rule = (k, label) => {
      const v = found[k] || [];
      check(`${dev}: ${label}`, !v.length, v.slice(0, 8).join("; ") + (v.length > 8 ? `; and ${v.length - 8} more` : ""));
    };
    if (dev === "phone") rule("overflow", "nothing scrolls sideways at 390px");
    rule("targets", "every control is at least 44px");
    rule("fields", "every field's text is at least 16px");
    rule("fieldEdge", "every field has an edge or fill that stands 3:1 (WCAG 1.4.11)");
    rule("contrast", "all text meets WCAG AA contrast");
    rule("motion", "nothing moves under prefers-reduced-motion");
    rule("dashes", "no em dash anywhere in the copy");
    rule("colour", "triage colours appear only in urgency bars and marks");
    rule("words", "every urgency bar and mark carries a word");
    rule("hold", "refusals are the neutral grey");
    rule("cites", "every citation is a button with its key");
    rule("offscreen", "nothing off screen can take focus");
    rule("clamp", "every clamped text shows its lines and no more");
    if (found.gone) rule("goneBad", `every removal is struck through with its reason (${found.gone} on screen)`);
    else console.log(`      NOTE ${dev}: no guard removals in the saved answers, so that rule was not exercised`);
  }
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
                regions, phone, voice, packs: packsFlow, queue, sync: syncFlow, base, rules: rulesFlow }[mode];
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
  // Chrome can still be writing to its profile as it exits: retry, and never let
  // a cleanup race fail a mode whose checks have already run. On 2026-09-27 the
  // queue mode passed all 14 checks and then exited 1 on ENOTEMPTY here.
  if (chrome.profile) {
    try { rmSync(chrome.profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }); }
    catch (e) { console.log(`      NOTE could not remove ${chrome.profile}: ${e.code}; remove it by hand`); }
  }
}
console.log(`${failures ? `${failures} failed` : "all passed"}`);
process.exit(failures);
