// One side's answer to one turn: while it works, and once the guards have run.
// The same functions render a live turn and a saved one, so history reads
// exactly as the answer did when it arrived.
//
// THE RESULT READS IN ONE GLANCE, 2026-09-27 (ui-audit/overhaul.html, option
// B): the verdict and what to do are open; why, the sources and the Checked
// measurements are one tap away, and anything a guard removed is announced by
// a single line that opens to the removals, struck out with their reasons.

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
// Paired straight quotes curled for display. The words are the rule's own.
const curl = s => String(s ?? "").replace(/"([^"]*)"/g, "“$1”");
const uid = () => "f" + Math.random().toString(36).slice(2, 9);

// ------------------------------------------------------------ source names

// A source is shown by its publisher's short name and the opening words of the
// chunk it cites, never by its registry key. The key rides on the button as
// data-k, which is what opens it and what every guard checks.
// "Source: NHLBI, National Institutes of Health" -> "NHLBI".
const shortSource = c => c && c.attribution ? c.attribution.replace(/^Source:\s*/, "").split(",")[0] : "";
const opening = c => {
  const t = String((c && c.text) || "").replace(/\s+/g, " ").trim();
  const first = (t.match(/^.*?[.!?](\s|$)/) || [t])[0].trim();
  return first;
};
// Every chunk the page has seen, by key. Rule lines and a refusal's nearest
// sources arrive as bare keys, so their names are fetched once and filled in.
const SEEN = new Map();
const pending = new Set();
function learn(chunks) { for (const c of chunks || []) if (c && c.key && c.attribution) SEEN.set(c.key, c); }
function fill(key) {
  if (SEEN.has(key) || pending.has(key)) return;
  pending.add(key);
  fetch(`/api/chunk/${encodeURIComponent(key)}`).then(r => r.ok ? r.json() : null).then(c => {
    pending.delete(key);
    if (!c) return;
    SEEN.set(key, c);
    for (const b of document.querySelectorAll(`.cite[data-k="${CSS.escape(key)}"]`)) {
      const p = b.querySelector(".p"), x = b.querySelector(".x");
      if (p) p.textContent = shortSource(c);
      if (x) x.textContent = opening(c);
    }
    for (const s of document.querySelectorAll(`[data-pubs~="${CSS.escape(key)}"]`)) s.textContent = pubsOf(s.dataset.pubs.split(" "));
  }).catch(() => pending.delete(key));
}
const pubsOf = keys => [...new Set(keys.map(k => shortSource(SEEN.get(k))).filter(Boolean))].join(", ") || "Sources";

// A source as a row: publisher, then what it says. `n` numbers the answer's
// own citations; rule and refusal sources are unnumbered.
export function citeChip(key, n, chunk) {
  if (chunk) learn([chunk]);
  const c = SEEN.get(key);
  if (!c) fill(key);
  return `<button class="cite" data-k="${esc(key)}" type="button">` +
    `<span class="p">${esc(shortSource(c) || "Source")}</span>` +
    `<span class="x">${esc(opening(c))}</span>${icon("chevron")}</button>`;
}
// Publisher names for a fold's closed line, filled in as they arrive.
const pubsSpan = keys => `<span data-pubs="${esc(keys.join(" "))}">${esc(pubsOf(keys))}</span>`;

// ------------------------------------------------------------------ pieces

// The verdict: the word, in its triage colour, over what to do, on its tint.
// The .bar is the heading; the rule line sits under it on the same tint.
function bar(kind, word, disp, animate, extra = "") {
  return `<div class="verdict ${kind}${animate ? " develop" : ""}">` +
    `<div class="bar ${kind}" role="heading" aria-level="2">` +
    `<span class="w">${esc(word)}</span><span class="d">${esc(disp)}</span></div>${extra}</div>`;
}

function section(title, body, cls = "") {
  return `<div class="sec${cls ? " " + cls : ""}"><h3>${esc(title)}</h3>${body}</div>`;
}

// A section closed to one line: its name, a preview, and a plus. The body is
// in the page, hidden, so find-in-page and the SOAP note never depend on it.
function fold(title, preview, body, { clamp = false, cls = "" } = {}) {
  const id = uid();
  return `<div class="sec fold${cls ? " " + cls : ""}"><h3>` +
    `<button class="fold-btn" type="button" data-fold aria-expanded="false" aria-controls="${id}">` +
    `<span class="h">${esc(title)}</span><span class="pv${clamp ? " clamp" : ""}">${preview}</span>` +
    `<span class="pm" aria-hidden="true">${icon("plus")}</span></button></h3>` +
    `<div class="fold-body" id="${id}" hidden>${body}</div></div>`;
}

const reason = why => `<span class="tag">removed: ${esc(why)}</span>`;
const gone = (text, why) => `<li class="gone"><s>${esc(cut(text))}</s>${reason(why)}</li>`;

// Viraj's wording, final 2026-09-27: "N items removed by safety checks". "Show" is final too.
function noticeHTML(items) {
  if (!items.length) return "";
  const id = uid(), n = items.length;
  return `<div class="guard-note"><button class="note-btn" type="button" data-fold aria-expanded="false" aria-controls="${id}">` +
    `<span class="glyph" aria-hidden="true">!</span><span class="t">${n} ${n === 1 ? "item" : "items"} removed by safety checks</span>` +
    `<span class="more" aria-hidden="true">Show</span></button>` +
    `<ul class="removed" id="${id}" hidden>${items.join("")}</ul></div>`;
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
    h += `<div class="notice">${icon("info")}<span>The model lost this conversation and is re-reading it.</span></div>`;
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
    default: return errorHTML(ev, ctx);
  }
}

const whoseOf = ev => ev.profile === "You" ? "your profile" : `${esc(ev.profile)}'s profile`;

// A rule line under the verdict says what raised or backs it, in words. Its
// quoted source line, sources and rule number are under Why.
function rulesHTML(ev) {
  const e = ev.escalation;
  if (!e || !e.fired || !e.fired.length) return "";
  const lc = s => esc(String(s).toLowerCase());
  return `<div class="rules">` + e.fired.map(f => {
    // Viraj's words: "Raised to red: the steps call for emergency care."
    if (f.kind === "steps") return `<p class="rule raised"><span class="ic">${icon("raised")}</span>` +
      `<span><span class="h">Raised to ${lc(e.final)}</span>: ${esc(f.name)}.</span></p>`;
    const head = f.status === "raised" ? `Raised to ${lc(e.final)}`
      : f.status === "supports" ? `Backs up this ${lc(e.final)}`
      : f.status === "at_least" ? `At least ${lc(f.to || f.cap)}`
      : f.status === "noted" ? "Noted" : "Flagged";
    const ic = f.status === "raised" ? "raised" : f.status === "flag" ? "flag" : "supports";
    return `<p class="rule${f.status === "raised" ? " raised" : ""}"><span class="ic">${icon(ic)}</span>` +
      `<span><span class="h">${head}</span>: ${esc(curl(f.fact))} on ${whoseOf(ev)}, with ${esc(curl(f.symptom))}</span></p>`;
  }).join("") + `</div>`;
}

// Inside Why: each rule's quoted line, the sources it quotes, and its number.
// Final wording: "From <whose> profile".
function ruleQuotes(ev) {
  const fired = (((ev.escalation || {}).fired) || []).filter(f => f.kind !== "steps");
  return fired.map(f => `<div class="rq"><div class="sub">From ${whoseOf(ev)}</div>` +
    `<p class="q">“${esc(f.quote)}”</p>` +
    `<div class="srcs">${f.keys.map(k => citeChip(k)).join("")}</div>` +
    `<p class="rid">rule ${esc(f.rule)}</p></div>`).join("");
}

function resultHTML(ev, ctx) {
  const r = ev.result, u = r.urgency, drop = ev.dropped || {};
  learn(ev.citations);
  const flagged = new Set(((ev.flagged || {}).next_steps) || []);
  const wrote = String(((ev.escalation || {}).original) || "").toLowerCase();
  const lower = wrote ? `written for a ${wrote}` : "does not match the verdict";
  let h = bar(u, u.toUpperCase(), DISPOSITION[u] || "", ctx.animate, rulesHTML(ev));

  // The banner already says the disposition, so a step that only repeats it
  // is not shown again as step 1.
  const same = s => String(s).toLowerCase().replace(/[.\s]+$/, "") === String(DISPOSITION[u] || "").toLowerCase();
  const steps = (r.next_steps || []).filter(s => !same(s));
  h += section("What to do", steps.length
    ? `<ol class="keys">${steps.map((s, i) => `<li><span class="key">${i + 1}</span>` +
      `<span>${esc(s)}${flagged.has(s) ? '<span class="tag">flagged, kept</span>' : ""}</span></li>`).join("")}</ol>`
    : (r.next_steps || []).length ? `<p class="muted">${esc(DISPOSITION[u])}.</p>` : `<p class="muted">No steps given.</p>`, "todo");

  const qs = r.follow_up_questions || [];
  if (qs.length) {
    // Final wording: "A question for you" when there is one.
    h += section(qs.length === 1 ? "A question for you" : "Questions for you", `<div class="qs">` + qs.map(q =>
      `<div class="q-row"><span>${esc(q)}</span>` +
      (ctx.canAnswer ? `<button class="btn-line" type="button" data-answer="${esc(q)}">Answer</button>` : "") +
      `</div>`).join("") + `</div>`);
  }

  // Everything a guard removed, behind one line. Constraint 16's struck
  // rationale is listed here and also stays whole under Why, where it was.
  const goneCites = drop.citations || [];
  const items = [
    ...(drop.next_steps || []).map(x => gone(x, "medication instruction")),
    ...(drop.next_steps_urgency || []).map(x => gone(x, lower)),
    ...(drop.rationale_urgency ? [gone(drop.rationale_urgency, lower)] : []),
    ...(drop.red_flags || []).map(x => gone(x.entry, x.why)),
    ...(drop.follow_up_questions || []).map(x => gone(x, "no questions on a red")),
    ...goneCites.map(x => `<li class="gone clip"><s>${esc(x)}</s>${reason("not in the source registry")}</li>`),
  ];
  h += noticeHTML(items);

  // Why, closed to its first two lines. On a raise the model's reason was
  // written for the lower verdict, so it is struck out whole and the rule's
  // quoted line is the reason shown.
  const goneWhy = drop.rationale_urgency || "";
  const fired = (((ev.escalation || {}).fired) || []).filter(f => f.kind !== "steps");
  const flags = r.red_flags || [];
  // Viraj's wording, final: "The model's original reason".
  const whyBody =
    (r.rationale ? `<p class="lead">${esc(r.rationale)}</p>` : "") +
    ruleQuotes(ev) +
    (goneWhy ? `<div class="rq"><div class="sub">The model's original reason</div><p class="gone"><s>${esc(goneWhy)}</s>${reason(lower)}</p></div>` : "") +
    (!r.rationale && !goneWhy && !fired.length ? `<p class="muted">No reason given.</p>` : "") +
    `<div class="rq"><div class="sub">Red flags</div>${flags.length
      ? `<ul class="plain">${flags.map(f => `<li>${esc(f)}</li>`).join("")}</ul>` : `<p class="muted">None.</p>`}</div>`;
  const whyPv = r.rationale ? esc(r.rationale)
    : fired.length ? `“${esc(fired[0].quote)}”`
    : goneWhy ? "The model's original reason was removed." : "No reason given.";

  const cites = ev.citations || [];
  const keys = cites.map(c => c.key);
  h += `<div class="folds">` + fold("Why", whyPv, whyBody, { clamp: true, cls: "why" }) +
    fold("Sources", cites.length ? pubsSpan(keys) : "None cited",
      cites.length ? `<div class="srcs">${cites.map((c, i) => citeChip(c.key, i + 1, c)).join("")}</div>`
        : `<p class="muted">None cited.</p>`, { cls: "sources" }) +
    checkedHTML(ev, ctx) + `</div>`;
  return h;
}

// A red that cites nothing. The urgency and its disposition are shown, because
// a possible emergency is never withheld. Nothing else the model wrote is shown,
// and there is no sources panel, because none of it is grounded. Profile rules
// still show: they quote their own chunks. See post_flight in 02-pairs/guards.py.
function ungroundedHTML(ev, ctx) {
  const u = ev.result.urgency, goneCites = (ev.dropped || {}).citations || [];
  return bar(u, u.toUpperCase(), DISPOSITION[u] || "", ctx.animate, rulesHTML(ev)) +
    `<div class="ungrounded"><div class="h">Not grounded in sources</div><p>${esc(ev.ungrounded.note)}</p></div>` +
    noticeHTML(goneCites.map(x => `<li class="gone clip"><s>${esc(x)}</s>${reason("not in the source registry")}</li>`)) +
    `<div class="folds">` +
    fold("Why", esc(ev.ungrounded.reason), `<p class="lead">${esc(ev.ungrounded.reason)}</p>` + ruleQuotes(ev),
      { clamp: true, cls: "why" }) +
    checkedHTML(ev, ctx) + `</div>`;
}

// No verdict: out of scope, a categorical exclusion, or a child's profile.
function refusedHTML(ev, ctx) {
  const child = !!ev.child;
  let h = bar("hold", child ? "NOT ASSESSED" : "OUT OF SCOPE",
    child ? "Child profile, no verdict given" : "No verdict given", ctx.animate);
  h += `<div class="sec"><p class="msg">${esc(ev.message)}</p></div>`;
  const rows = [["Why", esc(ev.reason)]];
  if (ev.urgency_withheld) rows.push(["Withheld", `A ${esc(ev.urgency_withheld)} verdict was produced and withheld.`]);
  // The nearest sources are registry keys, so they open like any other.
  if (ev.nearest) rows.push(["Nearest", `<div class="srcs">${ev.nearest.map(k => citeChip(k)).join("")}</div>`]);
  if (!child && ctx.sources) rows.push(["Scope", `Chest pain only, ${fmt(ctx.sources)} sources.`]);
  // The closed Why row. Viraj's wording, final: "No verdict: Grounded only
  // covers chest pain." It is said only of a plain out-of-scope refusal: a
  // child's profile or a categorical exclusion (pregnancy) is refused for a
  // different reason, so those rows carry no preview and the reason is inside.
  const pv = child || ev.categorical ? "" : "No verdict: Grounded only covers chest pain.";
  h += `<div class="folds">` + fold("Why", pv,
    `<dl class="kv">${rows.map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join("")}</dl>`, { cls: "why-not" }) +
    (ev.timings ? checkedHTML(ev, ctx) : "") + `</div>`;
  return h;
}

// A child word on an adult profile. Asks who this is about; refuses nothing.
function confirmHTML(ev, ctx) {
  return bar("hold", "WHO IS THIS FOR?", "No verdict yet", ctx.animate) +
    `<div class="sec"><p class="msg">${esc(ev.message)}</p><div class="actions">` +
    `<button class="btn primary" type="button" data-continue>Continue as ${esc(ev.who)}</button>` +
    (ctx.children || []).map(c =>
      `<button class="btn plain" type="button" data-switch="${esc(c.id)}">Switch to ${esc(c.label)}</button>`).join("") +
    `</div></div>`;
}

function fullHTML(ev) {
  return `<div class="full"><p style="margin:0">${esc(ev.message)}</p>` +
    `<button class="btn plain" type="button" data-new>Start a new assessment</button></div>`;
}

// A turn that failed says so first, in the words the announcement already
// uses, then why, then offers the one thing to do: send the same words again.
// It used to stop at "Something went wrong". Only the last turn of a side
// offers it, and not while anything is being written.
function errorHTML(ev, ctx = {}) {
  return `<div class="err-panel"><div class="err">${icon("alert")}<span>The answer did not finish.</span></div>` +
    `<div>${esc(ev.message)}</div>` +
    (ctx.retry ? `<div class="err-acts"><button class="btn plain" type="button" data-retry>Try again</button></div>` : "") +
    `</div>`;
}

// ------------------------------------------------ the one line, and its details

function countRemoved(d = {}) {
  return ["red_flags", "next_steps", "next_steps_urgency", "citations", "follow_up_questions"]
    .reduce((n, k) => n + ((d[k] || []).length), 0) + (d.rationale_urgency ? 1 : 0);
}

// Checked is the last closed row. Every number on it is the server's own
// measurement of this turn.
function checkedHTML(ev, ctx) {
  const t = ev.timings || {}, c = ev.cache || {};
  const removed = countRemoved(ev.dropped);
  let read;
  if (ev.first) read = c.reused ? `read ${fmt(t.prompt_n)}, ${fmt(c.reused)} cached` : `read ${fmt(t.prompt_n)}`;
  else if (c.re_read) read = `re-read ${fmt((t.prompt_n || 0) + (c.reused || 0))}, ${fmt(c.reused)} cached`;
  else read = `${fmt(c.reused)} cached, read ${fmt(t.prompt_n)}`;
  const bits = [secs(ev.total_ms || 0), read, `wrote ${fmt(t.predicted_n)}`];
  // Spoken turns say so on the face of the line, not only inside the details.
  // It is a provenance fact about the words, so it reads before the timings.
  if (ev.heard) bits.unshift(`heard ${secs(ev.heard.ms)}`);
  if (removed) bits.push(`<b>${removed} removed</b>`);
  const why = !ev.first && c.re_read
    ? `<span class="why">The model lost this conversation and re-read it.</span>`
    : "";
  const id = uid();
  return `<div class="sec fold checked-fold"><button class="checked" type="button" aria-expanded="false" aria-controls="${id}">` +
    `<span class="h">Checked</span><span class="pv">${bits.join('<span class="dot"></span>')}${why}</span>` +
    `<span class="pm" aria-hidden="true">${icon("plus")}</span></button>` +
    `<div class="details" id="${id}" hidden>${detailsHTML(ev, ctx)}</div></div>`;
}

function detailsHTML(ev, ctx) {
  const t = ev.timings || {}, c = ev.cache || {}, d = ev.dropped || {};
  const rows = [
    // Only on a turn that was spoken. Transcription happens before any of the
    // rest, on this machine, so it sits above Retrieve and carries whether the
    // person corrected what the microphone heard.
    ...(ev.heard ? [["Heard", `${ev.heard.seconds} s of speech in ${secs(ev.heard.ms)}, `
      + `${ev.heard.model} on this machine; `
      + (ev.heard.edited ? "edited before sending" : "sent unchanged")]] : []),
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
  let h = `<dl class="kv">${rows.map(([a, b]) => `<dt>${a}</dt><dd class="num">${b}</dd>`).join("")}</dl>`;
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
  h += `<div class="fine">Runs on this device. Reasoning off, schema enforced, guards on, no network.</div>`;
  return h;
}
