// One side's answer to one turn: while it works, and once the guards have run.
// The same functions render a live turn and a saved one, so history reads
// exactly as the answer did when it arrived.

import { icon } from "./icons.js";

export const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const fmt = n => Number(n || 0).toLocaleString("en-US");
export const secs = ms => `${(ms / 1000).toFixed(ms < 9950 ? 1 : 0)} s`;

// Viraj's copy, unchanged.
export const DISPOSITION = {
  red: "Call emergency services now",
  yellow: "Be seen today",
  green: "Self-care, and the signs that change the answer",
};

const cut = (s, n = 90) => (s = String(s), s.length > n ? s.slice(0, n - 1) + "…" : s);

// "Source: NHLBI, National Institutes of Health" -> "NHLBI". The registry's own
// short name, not a publisher string cut at a comma.
const shortSource = c => c && c.attribution ? c.attribution.replace(/^Source:\s*/, "").split(",")[0] : "";

export function citeChip(key, n, chunk) {
  const src = shortSource(chunk);
  return `<button class="cite" data-k="${esc(key)}" type="button">` +
    (n ? `<span class="n">${n}</span>` : "") + `<span class="k">${esc(key)}</span>` +
    (src ? `<span class="p">${esc(src)}</span>` : "") + `</button>`;
}

function bar(kind, word, disp, animate) {
  return `<div class="bar ${kind}${animate ? " develop" : ""}" role="heading" aria-level="2">` +
    `<span class="w">${esc(word)}</span><span class="d">${esc(disp)}</span></div>`;
}

function section(title, body) {
  return `<div class="sec"><h3>${esc(title)}</h3>${body}</div>`;
}

const gone = (text, why) =>
  `<li class="gone"><s>${esc(cut(text))}</s><span class="tag">removed: ${esc(why)}</span></li>`;

// Citations the guard removed are often long pasted fragments, and they all have
// the same reason, so they share one line and each is clipped to one line.
function goneCitations(list) {
  if (list.length === 1) return `<ul class="plain">${gone(list[0], "not in the source registry")}</ul>`;
  return `<p class="gone-head"><span class="tag">removed</span>${list.length} citations that are not in the source registry</p>` +
    `<ul class="plain clip">${list.map(x => `<li class="gone"><s>${esc(x)}</s></li>`).join("")}</ul>`;
}

// ------------------------------------------------------------- while it works

// p: { first, src, reading, readAt, tokenAt, tokens, tail, checking, now }
export function pendingHTML(p) {
  const st = (name, cls, sub) =>
    `<div class="st ${cls}"><b>${name}</b><span>${sub || "&nbsp;"}</span></div>`;
  const now = p.now || performance.now();
  const ret = p.src
    ? st("Retrieve", "done", p.first ? `${p.src.keys.length} sources` : `reused ${p.src.keys.length}`)
    : st("Retrieve", "on", "finding sources");
  let read;
  if (!p.reading) read = st("Read", "", "");
  else if (!p.tokenAt) {
    const est = p.reading.estimate_ms;
    read = st("Read", "on", secs(now - p.readAt) + (est >= 1500 ? `, about ${secs(est)}` : ""));
  } else read = st("Read", "done", secs(p.tokenAt - p.readAt));
  const write = !p.tokenAt ? st("Write", "", "")
    : st("Write", p.checking ? "done" : "on", `${fmt(p.tokens)} tokens`);
  const check = p.checking ? st("Check", "on", "guards") : st("Check", "", "");
  let h = `<div class="steps4" role="status" aria-label="Working">${ret}${read}${write}${check}</div>`;
  // The raw stream is there for whoever wants it, one tap away; the steps
  // above already show that the model is writing.
  if (p.tokenAt) {
    h += `<div class="raw-live"><button class="link-btn" type="button" data-raw-toggle aria-expanded="${!!p.showRaw}">` +
      `${p.showRaw ? "Hide" : "Show"} what the model is writing</button>` +
      (p.showRaw ? `<pre>${esc(p.raw)}</pre>` : "") + `</div>`;
  }
  if (p.slow) {
    h += `<div class="notice">${icon("info")}<span><b>Re-reading this whole assessment.</b> ` +
      `The model's memory of it was cleared, so it is reading everything again, ` +
      `about ${secs(p.reading.full_read_ms)} in all.</span></div>`;
  }
  return h;
}

// ----------------------------------------------------------------- the answer

// ctx: { animate, canAnswer, children, sources, anchor, raw }
export function answerHTML(ev, ctx = {}) {
  switch (ev.event) {
    case "result": return ev.ungrounded ? ungroundedHTML(ev, ctx) : resultHTML(ev, ctx);
    case "refused": return refusedHTML(ev, ctx);
    case "confirm_subject": return confirmHTML(ev, ctx);
    case "full": return fullHTML(ev);
    case "busy": return `<div class="notice">${icon("info")}<span>${esc(ev.message)}</span></div>`;
    default: return errorHTML(ev);
  }
}

function rulesHTML(ev) {
  const e = ev.escalation;
  if (!e || !e.fired || !e.fired.length) return "";
  const whose = ev.profile === "You" ? "your profile" : `${esc(ev.profile)}'s profile`;
  const U = s => esc(String(s).toUpperCase());
  return `<div class="rules">` + e.fired.map(f => {
    const head = f.status === "raised" ? `Raised ${U(e.original)} to ${U(e.final)}`
      : f.status === "supports" ? `Supports this ${U(e.final)}`
      : f.status === "at_least" ? `Supports at least ${U(f.cap)}`
      : f.status === "noted" ? "Noted" : "Flagged, no change";
    const ic = f.status === "raised" ? "raised" : f.status === "flag" ? "flag" : "supports";
    return `<div class="rule${f.status === "raised" ? " raised" : ""}"><span class="ic">${icon(ic)}</span>` +
      `<div><div><span class="h">${head}</span>: ${esc(f.fact)} on ${whose}, with ${esc(f.symptom)}</div>` +
      `<div class="q">“${esc(f.quote)}”</div>` +
      `<div class="src">${f.keys.map(k => citeChip(k)).join("")}<span class="rid">rule ${esc(f.rule)}</span></div>` +
      `</div></div>`;
  }).join("") + `</div>`;
}

function resultHTML(ev, ctx) {
  const r = ev.result, u = r.urgency, drop = ev.dropped || {};
  const flagged = new Set(((ev.flagged || {}).next_steps) || []);
  let h = bar(u, u.toUpperCase(), DISPOSITION[u] || "", ctx.animate) + rulesHTML(ev);

  const steps = r.next_steps || [], goneSteps = drop.next_steps || [];
  h += section("What to do",
    (steps.length ? `<ol class="keys">${steps.map((s, i) => `<li><span class="key">${i + 1}</span>` +
      `<span>${esc(s)}${flagged.has(s) ? '<span class="tag">flagged, kept</span>' : ""}</span></li>`).join("")}</ol>`
      : `<p class="muted">No steps given.</p>`) +
    (goneSteps.length ? `<ul class="plain">${goneSteps.map(x => gone(x, "medication instruction")).join("")}</ul>` : ""));

  h += section("Why", `<p>${esc(r.rationale || "")}</p>`);

  const flags = r.red_flags || [], goneFlags = drop.red_flags || [];
  h += section("Red flags", flags.length || goneFlags.length
    ? `<ul class="plain">${flags.map(f => `<li>${esc(f)}</li>`).join("")}` +
      `${goneFlags.map(x => gone(x.entry, x.why)).join("")}</ul>`
    : `<p class="muted">None.</p>`);

  const qs = r.follow_up_questions || [], goneQs = drop.follow_up_questions || [];
  if (qs.length || goneQs.length) {
    h += section("Questions for you", `<div class="qs">` + qs.map(q =>
      `<div class="q-row"><span>${esc(q)}</span>` +
      (ctx.canAnswer ? `<button class="btn-line" type="button" data-answer="${esc(q)}">Answer</button>` : "") +
      `</div>`).join("") + `</div>` +
      (goneQs.length ? `<ul class="plain">${goneQs.map(x => gone(x, "no questions on a red")).join("")}</ul>` : ""));
  }

  const cites = ev.citations || [], goneCites = drop.citations || [];
  h += section("Sources",
    (cites.length ? `<div class="cites">${cites.map((c, i) => citeChip(c.key, i + 1, c)).join("")}</div>`
      : `<p class="muted">None cited.</p>`) +
    (goneCites.length ? goneCitations(goneCites) : ""));

  return h + checkedHTML(ev, ctx);
}

// A red that cites nothing. The urgency and its disposition are shown, because
// a possible emergency is never withheld. Nothing else the model wrote is shown,
// and there is no sources panel, because none of it is grounded. Profile rules
// still show: they quote their own chunks. See post_flight in 02-pairs/guards.py.
function ungroundedHTML(ev, ctx) {
  const u = ev.result.urgency, goneCites = (ev.dropped || {}).citations || [];
  return bar(u, u.toUpperCase(), DISPOSITION[u] || "", ctx.animate) + rulesHTML(ev) +
    `<div class="ungrounded"><div class="h">Not grounded in sources</div><p>${esc(ev.ungrounded.note)}</p></div>` +
    (goneCites.length ? section("Removed", goneCitations(goneCites)) : "") +
    `<div class="sec"><p class="muted"><b>Why:</b> ${esc(ev.ungrounded.reason)}</p></div>` +
    checkedHTML(ev, ctx);
}

// No verdict: out of scope, a categorical exclusion, or a child's profile.
function refusedHTML(ev, ctx) {
  const child = !!ev.child;
  let h = bar("hold", child ? "NOT ASSESSED" : "OUT OF SCOPE",
    child ? "Child profile, no verdict given" : "No verdict given", ctx.animate);
  h += `<div class="sec"><p>${esc(ev.message)}</p></div>`;
  const rows = [["Why", esc(ev.reason)]];
  if (ev.urgency_withheld) rows.push(["Withheld", `A ${esc(ev.urgency_withheld)} verdict was produced and withheld.`]);
  if (ev.nearest) rows.push(["Nearest", ev.nearest.map(k => `<span class="mono">${esc(k)}</span>`).join(", ")]);
  if (!child && ctx.sources) rows.push(["Scope", `Chest pain only, ${fmt(ctx.sources)} sources.`]);
  h += `<div class="sec details"><dl>${rows.map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join("")}</dl></div>`;
  return h + (ev.timings ? checkedHTML(ev, ctx) : "");
}

// A child word on an adult profile. Asks who this is about; refuses nothing.
function confirmHTML(ev, ctx) {
  return bar("hold", "WHO IS THIS FOR?", "No verdict yet", ctx.animate) +
    `<div class="sec"><p>${esc(ev.message)}</p><div class="actions">` +
    `<button class="btn primary" type="button" data-continue>Continue as ${esc(ev.who)}</button>` +
    (ctx.children || []).map(c =>
      `<button class="btn plain" type="button" data-switch="${esc(c.id)}">Switch to ${esc(c.label)}</button>`).join("") +
    `</div></div>`;
}

function fullHTML(ev) {
  return `<div class="full"><p style="margin:0">${esc(ev.message)}</p>` +
    `<button class="btn plain" type="button" data-new>Start a new assessment</button></div>`;
}

function errorHTML(ev) {
  return `<div class="err-panel"><div class="err">${icon("alert")}<span>Something went wrong</span></div>` +
    `<div>${esc(ev.message)}</div></div>`;
}

// ------------------------------------------------ the one line, and its details

function countRemoved(d = {}) {
  return ["red_flags", "next_steps", "citations", "follow_up_questions"]
    .reduce((n, k) => n + ((d[k] || []).length), 0);
}

function checkedHTML(ev, ctx) {
  const t = ev.timings || {}, c = ev.cache || {};
  const removed = countRemoved(ev.dropped);
  let read;
  if (ev.first) read = c.reused ? `read ${fmt(t.prompt_n)}, ${fmt(c.reused)} cached` : `read ${fmt(t.prompt_n)}`;
  else if (c.re_read) read = `re-read ${fmt((t.prompt_n || 0) + (c.reused || 0))}, ${fmt(c.reused)} cached`;
  else read = `${fmt(c.reused)} cached, read ${fmt(t.prompt_n)}`;
  const bits = ["<b>Checked</b>", secs(ev.total_ms || 0), read, `wrote ${fmt(t.predicted_n)}`];
  if (removed) bits.push(`<b>${removed} removed</b>`);
  const why = !ev.first && c.re_read
    ? `<span class="why">The model's memory of this assessment had been cleared` +
      `${c.slot_taken ? " after another assessment used its slot" : ""}, so it read everything again.</span>`
    : "";
  const id = "d" + Math.random().toString(36).slice(2, 9);
  return `<button class="checked" type="button" aria-expanded="false" aria-controls="${id}">` +
    `${icon("check")}${bits.join('<span class="dot"></span>')}<span class="chev">${icon("chevron")}</span>${why}</button>` +
    `<div class="details" id="${id}" hidden>${detailsHTML(ev, ctx)}</div>`;
}

function detailsHTML(ev, ctx) {
  const t = ev.timings || {}, c = ev.cache || {}, d = ev.dropped || {};
  const rows = [
    ["Retrieve", ev.first ? `${secs(ev.retrieval_ms || 0)}, ${fmt(ev.retrieved_tokens)} tokens of sources`
      : "reused the first turn's sources, no retrieval"],
    ["Read", `${fmt(t.prompt_n)} tokens in ${secs(t.prompt_ms || 0)}` +
      (t.prompt_per_second ? `, ${Math.round(t.prompt_per_second)}/s` : "") + `; ${fmt(c.reused)} from cache`],
    ["Write", `${fmt(t.predicted_n)} tokens in ${secs(t.predicted_ms || 0)}` +
      (t.predicted_per_second ? `, ${t.predicted_per_second.toFixed(1)}/s` : "")],
    ["Check", `${fmt(ev.check_ms || 0)} ms`],
    ["Total", secs(ev.total_ms || 0)],
    ["Slot", c.slot === undefined ? "none" : `${c.slot}` + (c.slot_taken
      ? (c.re_read ? ", used by another assessment in between" : ", used by another assessment in between; its saved copy was restored")
      : "")],
  ];
  let h = `<dl>${rows.map(([a, b]) => `<dt>${a}</dt><dd class="num">${b}</dd>`).join("")}</dl>`;
  if (ctx.anchor) {
    h += `<div><h4>Sources read on the first turn</h4><div class="mono">${ctx.anchor.chunks.map(k =>
      `${esc(k.key)} (${fmt(k.tokens)} tokens, ${esc(k.category)})`).join("<br>")}</div></div>`;
  }
  const removed = [
    ...(d.red_flags || []).map(x => `${x.entry}: ${x.why}`),
    ...(d.next_steps || []).map(x => `${x}: medication instruction`),
    ...(d.citations || []).map(x => `${cut(x)}: not in the source registry`),
    ...(d.follow_up_questions || []).map(x => `${x}: no questions on a red`),
    ...(((ev.flagged || {}).next_steps) || []).map(x => `${x}: flagged, kept`),
  ];
  h += `<div><h4>Removed by app guards</h4>${removed.length
    ? `<ul class="plain">${removed.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<span class="muted">Nothing.</span>`}</div>`;
  if (ctx.raw) h += `<div><h4>What the model wrote</h4><pre>${esc(ctx.raw)}</pre></div>`;
  h += `<div class="fine">Reasoning off, schema-constrained, guards applied, no network.</div>`;
  return h;
}
