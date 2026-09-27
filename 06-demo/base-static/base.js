// BASE, the supervisor's register. Built from 06-demo/BASE-DESIGN.md.
//
// ONE PERSON, AT A CLINIC, DECIDING WHO TO FOLLOW UP. They did not do these
// assessments. So the screen leads with what needs a decision, not with volume:
// a tally line and a table, never a card grid and never a chart.
//
// IT RECOMPUTES NOTHING. Every verdict, citation, rule and guard removal came
// out of the assessment a field device saved and sent, so what a supervisor
// reads is what the health worker read.
//
// ONE DEVIATION FROM THE SPEC, FORCED BY BASE BEING A SEPARATE PROCESS. The
// spec has a row link to /c/<id>, which is the field app's own assessment page.
// Base runs on its own port and may be on a different device entirely, so it
// links to its own read-only view instead. Base has the assessment bytes but
// NOT the corpus, so that view shows citation KEYS and says plainly that the
// chunk text lives on the device that did the assessment.

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// The drawn set, on the existing 24px grid, 1.75 stroke. `device` is the one
// new glyph BASE-DESIGN.md section 8 allows; the rest are copies of icons.js.
const P = {
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  none: '<circle cx="12" cy="12" r="8"/><path d="M6.4 6.4l11.2 11.2"/>',
  device: '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M10.5 18.5h3"/>',
  back: '<path d="m15 6-6 6 6 6"/>',
};
const icon = n => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${P[n]}</svg>`;

const WORD = { red: "red", yellow: "yellow", green: "green", refused: "out of scope",
               child: "not assessed", error: "error" };
const LETTER = { red: "R", yellow: "Y", green: "G" };

const dt = iso => (iso ? new Date(iso) : null);
const hhmm = iso => dt(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
const isToday = iso => {
  const t = new Date(); t.setHours(0, 0, 0, 0);
  return dt(iso) >= t;
};
// Today shows the time. Anything older shows the day above it, on two lines.
const whenCell = iso => iso
  ? (isToday(iso) ? `<span class="t">${esc(hhmm(iso))}</span>`
    : `<span class="d">${esc(dt(iso).toLocaleDateString([], { day: "numeric", month: "short" }))}</span><span class="t">${esc(hhmm(iso))}</span>`)
  : `<span class="t none-mark">None</span>`;

// Every mark carries its word as visually hidden text and in its title: the
// dot alone is not the verdict. Since the overhaul of 2026-09-27 it is a dot,
// filled for a verdict and a ring for none, with no letter.
function mk(state) {
  const l = LETTER[state];
  const word = WORD[state] || "no answer";
  return l
    ? `<span class="mk ${esc(state)}" title="${esc(word)}"><span class="sr">${esc(word)}</span></span>`
    : `<span class="mk hold" title="${esc(word)}">${icon("none")}<span class="sr">${esc(word)}</span></span>`;
}

// Zero to four tags, no triage colour anywhere.
function attention(r) {
  const t = [];
  for (const s of r.sides) {
    if (s.ungrounded) t.push(`<span class="tg dashed">not grounded</span>`);
    if (s.state === "refused" || s.state === "child") t.push(`<span class="tg hatched">refused</span>`);
    if (s.raised) t.push(`<span class="tg box">raised to ${esc(s.state || "")}</span>`);
    if (s.removed) t.push(`<span class="tg removed">${s.removed} removed</span>`);
  }
  return t.length ? t.join("") : `<span class="none-mark">None</span>`;
}

const people = r => r.sides.map(s => esc(s.label)).join(" and ");
const said = r => {
  const s = (r.sides[0] && r.sides[0].said) || r.title || "Untitled";
  return esc(s);
};

function fromCell(r) {
  return `<span class="dev">${esc(r.device_label || r.device)}</span>` +
    (r.worker ? `<span class="wk">${esc(r.worker)}</span>` : "");
}

function actionCell(r) {
  return r.reviewed
    ? `<span class="done">${icon("check")}Reviewed ${esc(hhmm(r.reviewed.at))}</span>`
    : `<button class="btn quiet" type="button" data-review="${esc(r.id)}">Mark reviewed</button>`;
}

// ------------------------------------------------------------- the table

function tableHTML(rows) {
  return `<table class="reg">
    <thead><tr>
      <th scope="col" class="c-mk"><span class="sr">Urgency</span></th>
      <th scope="col" class="c-as">Assessment</th>
      <th scope="col" class="c-at">Attention</th>
      <th scope="col" class="c-fr">From</th>
      <th scope="col" class="c-wh">When</th>
      <th scope="col" class="c-ac"><span class="sr">Action</span></th>
    </tr></thead>
    <tbody>${rows.map(r => `<tr${r.reviewed ? ' class="seen"' : ""}>
      <td class="c-mk">${r.sides.map(s => mk(s.state)).join("")}</td>
      <td class="c-as"><a href="/a/${esc(r.id)}" data-link class="ttl"><span class="clamp">${said(r)}</span></a>
        <span class="meta">${people(r)}</span></td>
      <td class="c-at">${attention(r)}</td>
      <td class="c-fr">${fromCell(r)}</td>
      <td class="c-wh" title="${esc(r.updated || "")}">${whenCell(r.updated)}</td>
      <td class="c-ac">${actionCell(r)}</td>
    </tr>`).join("")}</tbody>
  </table>`;
}

// Below 60rem the table is REPLACED, not squeezed, on the .hist-row grammar.
function listHTML(rows) {
  return `<ul class="recs">${rows.map(r => `<li class="rec${r.reviewed ? " seen" : ""}">
    <div class="rm">${r.sides.map(s => mk(s.state)).join("")}</div>
    <div class="rc">
      <a href="/a/${esc(r.id)}" data-link class="ttl"><span class="clamp">${said(r)}</span></a>
      <span class="meta">${people(r)} · ${esc(r.updated ? hhmm(r.updated) : "")}</span>
      <span class="meta dev-line">${icon("device")}<span class="dev">${esc(r.device_label || r.device)}</span>${r.worker ? ` · ${esc(r.worker)}` : ""}</span>
      <span class="tags">${attention(r)}</span>
      <span class="act">${actionCell(r)}</span>
    </div>
  </li>`).join("")}</ul>`;
}

const section = rows => `<div class="wide-only">${tableHTML(rows)}</div>
  <div class="narrow-only">${listHTML(rows)}</div>`;

// Needs review is read top to bottom by someone who will run out of time, so
// the order is the priority order, not the clock.
const BAND = { red: 0, refused: 1, child: 1, error: 1, yellow: 2, green: 3 };
// A SIDE THAT NEVER ANSWERED SORTS WITH THE REFUSALS, NOT WITH THE GREENS.
// It renders the same hold mark a refusal does, and it needs a person for the
// same reason: the system produced nothing, so someone has to. Falling through
// to the green band buried a half-finished compare at the bottom of the list,
// which the base check caught on 2026-09-20.
const bandOf = state => BAND[state] ?? 1;
function priority(a, b) {
  const band = r => Math.min(...r.sides.map(s => bandOf(s.state)));
  return band(a) - band(b) || String(b.updated || "").localeCompare(String(a.updated || ""));
}

// The arrivals bar, built in place so the rest of the page keeps its focus,
// its scroll position and its hover.
function showNewBar(n) {
  let bar = document.querySelector(".newbar");
  const label = `${n} new since you opened this`;
  if (bar) {
    bar.firstChild.textContent = ` ${label} `;
    return;
  }
  bar = document.createElement("p");
  bar.className = "newbar";
  bar.setAttribute("role", "status");
  bar.append(` ${label} `);
  const btn = document.createElement("button");
  btn.className = "link-btn";
  btn.type = "button";
  btn.dataset.show = "";
  btn.textContent = "Show";
  btn.onclick = mergeNew;
  bar.append(btn);
  const first = document.querySelector("#main h2");
  if (first) first.before(bar); else $("#main").append(bar);
}

function mergeNew() {
  S.held = S.pendingData || S.held;
  S.note = 0;
  S.pendingData = null;
  S.seen = new Set(S.held.assessments.map(r => r.id));
  render(S.held);
}

// ------------------------------------------------------------- the page

const S = { window: "today", seen: null, held: null, note: 0 };

function inWindow(r) {
  return S.window === "all" || isToday(r.updated);
}

function tally(d, rows) {
  const c = d.counts;
  const n = rows.length;
  const red = rows.filter(r => r.sides.some(s => s.state === "red")).length;
  const need = rows.filter(r => r.outstanding).length;
  const bits = [
    `<b>${n}</b> assessed`,
    `<b>${red}</b> red`,
    `<b>${need}</b> need review`,
    c.last_sync
      ? `synced ${esc(hhmm(c.last_sync))} from <b>${c.devices}</b> ${icon("device")}${c.devices === 1 ? "device" : "devices"}`
      : `no sync yet`,
  ];
  return `<p class="tally" aria-live="polite">${bits.join(" <span class=sep>·</span> ")}</p>`;
}

function emptyAll(d) {
  return `<div class="well-panel">
    <h2 class="eh">No device has synced to this one yet.</h2>
    <p>A handset syncs its caseload when it is back in range. Assessments appear here when it does.</p>
  </div>`;
}

function emptyWindow(d) {
  const last = d.counts.last_sync;
  return `<div class="well-panel">
    <h2 class="eh">Nothing assessed today.</h2>
    <p>${last ? `The last sync was ${esc(dt(last).toLocaleDateString([], { day: "numeric", month: "short" }))} at ${esc(hhmm(last))}.` : ""}
      Choose All to see earlier assessments.</p>
  </div>`;
}

function render(d) {
  const all = d.assessments;
  const rows = all.filter(inWindow);
  const needs = rows.filter(r => r.outstanding).sort(priority);
  const seen = rows.filter(r => !r.outstanding)
    .sort((a, b) => String(b.updated || "").localeCompare(String(a.updated || "")));

  const head = `<div class="pg-head">
      <h1>Caseload</h1>
      <div class="seg" role="group" aria-label="Window">
        <button type="button" data-win="today" aria-pressed="${S.window === "today"}">Today</button>
        <button type="button" data-win="all" aria-pressed="${S.window === "all"}">All</button>
      </div>
    </div>
    ${tally(d, rows)}`;

  // New arrivals never move a row under the reader.
  const bar = S.note > 0 ? `<p class="newbar" role="status">
      ${S.note} new since you opened this
      <button class="link-btn" type="button" data-show>Show</button></p>` : "";

  let body;
  if (!all.length) body = emptyAll(d);
  else if (!rows.length) body = emptyWindow(d);
  else {
    const needsBlock = needs.length
      ? `<h2>Needs review <span class="n">${needs.length}</span></h2>${section(needs)}`
      : `<h2>Needs review <span class="n">0</span></h2>
         <div class="well-panel done-panel">${icon("check")}
           <div><b>Nothing needs review.</b>
           <p>All ${rows.length} assessment${rows.length === 1 ? "" : "s"}
             ${S.window === "today" ? "today" : "here"} have been looked at.</p></div></div>`;
    // An empty Reviewed section does not render its heading at all.
    const seenBlock = seen.length
      ? `<h2>Reviewed <span class="n">${seen.length}</span></h2>${section(seen)}` : "";
    body = needsBlock + seenBlock;
  }
  $("#main").innerHTML = head + bar + body;
  bind();
}

function bind() {
  document.querySelectorAll("[data-win]").forEach(b => {
    b.onclick = () => { S.window = b.dataset.win; render(S.held); };
  });
  document.querySelectorAll("[data-review]").forEach(b => {
    b.onclick = async () => {
      b.disabled = true;
      try {
        S.held = await (await fetch(`/api/assessments/${encodeURIComponent(b.dataset.review)}/review`,
          { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
        S.seen = new Set(S.held.assessments.map(r => r.id));
        render(S.held);
      } catch { b.disabled = false; }
    };
  });
  const show = document.querySelector("[data-show]");
  if (show) show.onclick = mergeNew;
}

// IS THE READER ACTUALLY DOING SOMETHING RIGHT NOW.
//
// BASE-DESIGN.md 4.7 says new arrivals must never move a row under the
// reader's finger, and it was implemented by holding EVERY arrival behind a
// bar. Measured 2026-09-20: base saw an arrival in under 2 s and still showed
// a 44-row table and a tally reading 44, so the closing beat of the demo,
// "wifi on and it appears at base", showed a thin grey line and a stale count.
// The rule's concern is real but it only applies while someone is mid-action.
// So: arrivals land immediately when nobody is reaching for anything, and are
// held behind the bar only when a control here has focus or the pointer is
// over a row. Viraj's call.
function readerIsBusy() {
  const a = document.activeElement;
  const focused = a && a !== document.body && a.closest
    && a.closest("#main") && a.matches("button, a, input, select, [tabindex]");
  const hovered = !!document.querySelector(".reg tbody tr:hover, .rec:hover, .newbar:hover");
  return !!(focused || hovered);
}

async function load(first) {
  let d;
  try { d = await (await fetch("/api/dashboard")).json(); }
  catch (e) {
    if (first) $("#main").innerHTML = `<div class="well-panel"><p>Base could not read its own store: ${esc(e.message)}</p></div>`;
    return;
  }
  const ids = new Set(d.assessments.map(r => r.id));
  if (!S.seen) {                       // first paint: everything is "already there"
    S.seen = ids; S.held = d; S.note = 0;
    return render(d);
  }
  const fresh = [...ids].filter(id => !S.seen.has(id));
  if (fresh.length && readerIsBusy()) {
    // Only now: something is under the reader's hand, so nothing moves.
    S.pendingData = d;
    S.note = fresh.length;
    // INSERTED, NOT RE-RENDERED. Re-rendering to show the bar destroyed the
    // focused button it was protecting, so focus fell to the body and the very
    // next poll decided the reader was idle and merged anyway: the hold lasted
    // one tick and then did the thing it exists to prevent. The bar is now
    // built and placed on its own, and nothing else on the page is touched.
    showNewBar(S.note);
    return;
  }
  // It arrives: the row, the counts and the tally together, so the page never
  // says 44 while holding 45.
  S.seen = ids;
  S.held = d;
  S.note = 0;
  S.pendingData = null;
  render(d);
}

// ------------------------------------------------------- one assessment

// ONE TURN, WHOLE. The detail page shows EVERY turn, not just the last: a
// follow-up must not hide the rule that raised the first answer or the lines
// the guards took out of it. Same reason the register row now sums across
// turns. See base_server.row().
function turnHTML(t, n, total) {
  const ev = t.event || {};
  const res = ev.result || {};
  const dropped = ev.dropped || {};
  const e = ev.escalation || {};
  const state = res.urgency || (t.kind === "refused" ? "refused" : t.kind === "error" ? "error" : null);
  const removedRows = Object.entries(dropped).flatMap(([field, v]) =>
    (Array.isArray(v) ? v : (v ? [v] : [])).map(x =>
      `<li><b>${esc(field)}</b> <s>${esc(typeof x === "string" ? x : JSON.stringify(x)).slice(0, 220)}</s></li>`));
  return `<div class="turn-block">
    <h3 class="turn-h">${total > 1 ? `Turn ${n} of ${total}` : "The answer"}
      ${mk(state)} <span class="wordy">${esc(WORD[state] || "no answer")}</span></h3>
    ${n > 1 && t.text ? `<blockquote class="saidq small">${esc(t.text)}</blockquote>` : ""}
    ${ev.ungrounded ? `<p class="tg dashed inline">not grounded in sources</p>` : ""}
    ${ev.message && t.kind !== "result" ? `<p>${esc(ev.message)}</p>` : ""}
    ${(e.fired || []).map(f => `<p class="rulep"><b>${esc(f.status === "raised" ? `Raised to ${e.final}` : "Rule " + f.rule)}</b>:
      ${esc(f.fact)} with ${esc(f.symptom)}<br><span class="q">“${esc(f.quote)}”</span>
      <span class="keys">${(f.keys || []).map(k => `<span class="key">${esc(k)}</span>`).join("")}</span></p>`).join("")}
    ${res.rationale ? `<h4>Why</h4><p>${esc(res.rationale)}</p>` : ""}
    ${(res.red_flags || []).length ? `<h4>Red flags</h4><ul>${res.red_flags.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    ${(res.next_steps || []).length ? `<h4>What to do</h4><ol>${res.next_steps.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
    ${(res.citations || []).length
      ? `<h4>Sources</h4><p class="keys">${res.citations.map(k => `<span class="key">${esc(k)}</span>`).join("")}</p>`
      : ""}
    ${removedRows.length ? `<h4>Removed by the guards before it was shown</h4>
      <ul class="removed">${removedRows.join("")}</ul>` : ""}
  </div>`;
}

function detail(b) {
  const a = b.assessment;
  const sides = a.sides.map(s => {
    const turns = (s.turns || []).filter(t => ["result", "refused", "error"].includes(t.kind));
    const state = turns.length ? (() => {
      const l = turns[turns.length - 1];
      return (l.event && l.event.result && l.event.result.urgency)
        || (l.kind === "refused" ? "refused" : l.kind === "error" ? "error" : null);
    })() : null;
    const removed = turns.reduce((n, t) => n + Object.values((t.event || {}).dropped || {})
      .reduce((m, v) => m + (Array.isArray(v) ? v.length : (v ? 1 : 0)), 0), 0);
    return `<section class="det">
      <h2>${esc((s.profile || {}).label || "?")} ${mk(state)} <span class="wordy">${esc(WORD[state] || "no answer")}</span>
        ${turns.length > 1 ? `<span class="tag">${turns.length} turns</span>` : ""}
        ${removed ? `<span class="tag">${removed} removed in total</span>` : ""}</h2>
      ${turns.map((t, i) => turnHTML(t, i + 1, turns.length)).join("")}
      <p class="fine">Base holds no corpus, so the chunk text is not here. It is on the device
        that did the assessment, behind these keys.</p>
    </section>`;
  }).join("");

  const first = (a.sides[0] && a.sides[0].turns && a.sides[0].turns[0]) || {};
  $("#main").innerHTML = `
    <p><a class="link-btn" href="/" data-link>${icon("back")}All assessments</a></p>
    <div class="pg-head"><h1>Assessment</h1></div>
    <blockquote class="saidq">${esc(first.text || "")}
      ${first.timeline ? `<span class="tl">${esc(first.timeline)}</span>` : ""}</blockquote>
    ${sides}
    <p class="sha">from ${esc(b.device.label || b.device.id)}${b.device.worker ? ` · ${esc(b.device.worker)}` : ""}
      · assessment ${esc(a.id)}<br>verified sha256 ${esc(b.sha256)}
      ${b.synced_at ? `<br>arrived here ${esc(new Date(b.synced_at).toLocaleString())}` : ""}</p>`;
  bindLinks();
}

async function showDetail(id) {
  try {
    const b = await (await fetch(`/api/assessments/${encodeURIComponent(id)}`)).json();
    if (b && b.assessment) return detail(b);
  } catch { /* fall through */ }
  $("#main").innerHTML = `<div class="well-panel"><p>That assessment has not reached this base.</p>
    <p><a class="link-btn" href="/" data-link>All assessments</a></p></div>`;
  bindLinks();
}

function bindLinks() {
  document.querySelectorAll("a[data-link]").forEach(a => {
    a.onclick = e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      history.pushState(null, "", a.getAttribute("href"));
      route();
    };
  });
}

let timer = null;
function route() {
  clearInterval(timer);
  const m = location.pathname.match(/^\/a\/([\w-]+)$/);
  if (m) return showDetail(m[1]);
  S.seen = null;
  load(true);
  // A supervisor leaves this open on a desk: a device coming back into range
  // should appear without anyone pressing anything. Cheap, because base reads
  // files and runs no model.
  timer = setInterval(() => load(false), 4000);
}

addEventListener("popstate", route);
document.addEventListener("click", e => {
  const a = e.target.closest("a[data-link]");
  if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  history.pushState(null, "", a.getAttribute("href"));
  route();
});
route();
