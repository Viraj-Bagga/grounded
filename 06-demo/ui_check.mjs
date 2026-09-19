#!/usr/bin/env node
// Drives the demo page in headless Chrome and saves what it sees. No packages:
// Node 22's built-in WebSocket speaks the DevTools protocol directly.
//
//   node 06-demo/ui_check.mjs shots OUTDIR          static screens, desktop and phone
//   node 06-demo/ui_check.mjs flow OUTDIR           one assessment, live, with a follow-up
//   node 06-demo/ui_check.mjs compare OUTDIR        two people side by side, live
//   node 06-demo/ui_check.mjs guards OUTDIR         child profile, child word, out of scope
//   node 06-demo/ui_check.mjs people OUTDIR         add, edit and delete a person through the form
//   node 06-demo/ui_check.mjs two-tabs OUTDIR       two assessments running at once in two tabs
//   node 06-demo/ui_check.mjs reread OUTDIR CID     a follow-up after a llama-server restart
//   node 06-demo/ui_check.mjs review OUTDIR IDS     the finish review's screenshots (six ids, comma-separated)
//
// Needs the demo server on 8770 and, for the live flows, llama-server on 8080.
// Every check prints PASS or FAIL; the exit code is the number of failures.

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const APP = "http://127.0.0.1:8770";
const PORT = 9333;
const DESKTOP = { width: 1440, height: 900, mobile: false, deviceScaleFactor: 1 };
const PHONE = { width: 390, height: 844, mobile: true, deviceScaleFactor: 2 };
let failures = 0;
const sleep = ms => new Promise(r => setTimeout(r, ms));

function check(name, ok, detail = "") {
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail && !ok ? `  (${detail})` : ""}`);
}

async function launch() {
  const profile = mkdtempSync(join(tmpdir(), "ui-check-"));
  const proc = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
  for (let i = 0; i < 100; i++) {
    try { await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); return proc; }
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
    check(`${name}: new assessment shows presets`, await p.count("[data-preset]") === 5);
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
  await p.click('[data-preset="4"]');
  check("the Mum preset selects Mum", /Mum/.test(await p.text("#chips [aria-pressed=true]")));
  check("the preset fills the composer", await p.eval(
    "document.querySelector('#ta').value === document.querySelector('[data-preset=\"4\"] .snip').textContent"));
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
  check("the allowance counts down", /3 follow-ups left|Last follow-up/.test(await p.text(".allow")));
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
  await p.go("/?p=self");
  await p.click("[data-compare]");
  await p.click('[data-preset="4"]');
  check("compare with the Mum preset picks You and Mum", await p.count("#chips .chip .ab") === 2);
  await sendAndWait(p, "compare, both sides");
  check("both sides answered", await p.count(".turn.pair .side-ans .bar") === 2);
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
  check("the new person gets a chip", (await p.text("#chips")).includes(name));
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
  await p.until("/Re-reading this whole assessment/.test(document.querySelector('[data-live]')?.innerText || '')", 60000, 250);
  check("a slow read says it is re-reading, while it happens", true);
  await p.shot(join(out, "desktop-rereading.png"));
  await p.until(`document.querySelectorAll("#thread .checked").length >= 2 && !document.querySelector("[data-live] .steps4")`, 300000, 400);
  await sleep(700);
  const last = await p.eval("[...document.querySelectorAll('.checked')].pop().innerText");
  check("the answer says it re-read everything, and why", /re-read/.test(last) && /memory of this assessment/.test(last), last);
  await p.shot(join(out, "desktop-reread-answer.png"));
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
  await p.click('[data-preset="3"]');
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

const [mode, out = ".", arg, arg2] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const chrome = await launch();
try {
  const run = { shots, flow, compare, guards, people, "two-tabs": twoTabs, reread, review }[mode];
  if (!run) throw new Error(`unknown mode ${mode}`);
  await run(out, arg, arg2);
} catch (e) {
  failures++;
  console.log(`FAIL  ${e.message}`);
} finally {
  chrome.kill();
}
console.log(`${failures ? `${failures} failed` : "all passed"}`);
process.exit(failures);
