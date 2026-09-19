// The app shell: routes, person chips, history, the conversation and the
// composer. No framework and no build step; it has to run with the laptop
// offline, from 06-demo/server.py.

import { api, streamTurn } from "./api.js";
import { answerHTML, pendingHTML, esc, fmt } from "./answer.js";
import { peopleListHTML, personFormHTML, bindPersonForm, facts, ruleName } from "./people.js";
import { icon } from "./icons.js";

const $ = (s, el = document) => el.querySelector(s);

// Demo presets. Numbered, because keys 1 to 5 pick them on a keyboard.
const PRESETS = [
  ["Crushing chest pressure",
   "Heavy pressure in the middle of my chest that has not let up for almost half an hour. I feel sick and I am sweating.",
   "T+0:00 began while sitting watching television. T+0:04 spread to the jaw. T+0:11 sweating and nausea. T+0:26 unchanged after resting."],
  ["Burning after a meal",
   "Burning in my chest after dinner, worse when I lie flat, with a sour taste coming up.",
   "T+0:00 began about 40 minutes after a large late meal. T+0:15 worse lying down. T+0:35 eased sitting upright."],
  // Stable angina. Reworded 2026-09-19 for the 35-chunk corpus: the old text,
  // "going up the stairs ... sat down", matched a pneumonia chunk on "going"
  // and "down" and the model cited it. This one retrieves CP-ANG-005,
  // CP-ANG-009 and CP-ACS-005, all angina, and held 3 of 3 live, citing only
  // those. 01-data/eval/runs/2026-09-19-stairs-and-pairing-screen.txt
  ["Tight chest on the stairs",
   "Tightness in my chest when I climb stairs or walk uphill. It goes away within a few minutes when I rest, same as the last few months.",
   "T+0:00 began climbing two flights. T+0:03 stopped to rest. T+0:06 resolved completely."],
  // BEAT 3. Retrieval reliably supplies CP-PERI-002 here, and its
  // "Fast heartbeat / Fever" lines are the ones the model copies onto patients
  // who have neither, so the grounding guard has something real to catch. The
  // case is SILENT on fever and heart rate, deliberately: a demo should not
  // depend on the subtlest branch in the code, which is denial handling.
  ["Sharp pain when breathing in",
   "Sharp pain in my left chest, worse when I breathe in. It eases if I sit up and lean forward. Walking around does not change it.",
   "T+0:00 began at rest. T+0:10 worse on deep breath. T+1:30 unchanged, no relation to exertion."],
  // BEAT 3, REFRAMED 2026-09-19: same symptom, two people. One click turns
  // Compare on, sets You against Mum and sends (Viraj's call, so the whole beat
  // is one click at the desk). Mum gets a red that R1 escalated (her diabetes,
  // CP-ACS-002) with the rule line; You gets refused, because the model cited
  // nothing. Held on every run on the 35-chunk corpus: You refused 6 of 6, Mum
  // escalated to red 3 of 3, one grounded and two through the refusal rescue.
  // It replaced "Feeling a bit sick and sweaty after dinner", which refused You
  // only 2 of 3. 01-data/eval/runs/2026-09-19-beat3-reframe-indigestion-pairs.txt
  ["Indigestion (You and Mum)",
   "A bit of indigestion after lunch, nothing much.", "", ["self", "mum"]],
];

const S = {
  health: null, people: [], convs: [],
  picked: ["self"], compare: false,
  conv: null, live: {}, liveSaid: null,
  draft: { text: "", timeline: "", showTl: false },
  flash: null, autoSend: false,
};
const touch = matchMedia("(pointer: coarse)").matches;
const byId = id => S.people.find(p => p.id === id);

// ------------------------------------------------------------------- routing

function go(path, replace = false) {
  history[replace ? "replaceState" : "pushState"](null, "", path);
  drawer(false);
  route();
}

function route() {
  const path = location.pathname;
  let m;
  if ((m = path.match(/^\/c\/([\w-]+)\/?$/))) return showConversation(m[1]);
  if (/^\/people\/?$/.test(path)) return showPeople();
  if (path === "/people/new") return showPersonForm(null);
  if ((m = path.match(/^\/people\/([\w-]+)\/?$/))) return showPersonForm(m[1]);
  return showNew();
}

document.addEventListener("click", e => {
  const a = e.target.closest("a[data-link]");
  if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
  e.preventDefault();
  go(a.getAttribute("href"));
});
addEventListener("popstate", route);

// ------------------------------------------------------------------- chrome

function drawer(open) {
  $("#side").classList.toggle("open", open);
  $("#scrim").hidden = !open;
  $("#menu").setAttribute("aria-expanded", open);
}
$("#menu").onclick = () => drawer(!$("#side").classList.contains("open"));
$("#scrim").onclick = () => drawer(false);
addEventListener("keydown", e => { if (e.key === "Escape") drawer(false); });

function renderChips(active, pair = S.compare) {
  const people = S.people;
  $("#chips").innerHTML = people.map(p => {
    const slot = active.indexOf(p.id);
    return `<button class="chip" type="button" data-person="${esc(p.id)}" aria-pressed="${slot >= 0}">` +
      `${esc(p.label)}${p.child ? '<span class="u16">Under 16</span>' : ""}` +
      (pair && slot >= 0 ? `<span class="ab">${"AB"[slot]}</span>` : "") + `</button>`;
  }).join("") +
    `<span class="sep" aria-hidden="true"></span>` +
    `<button class="chip tool only-wide" type="button" data-compare aria-pressed="${S.compare}">${icon("compare")}Compare</button>` +
    `<a class="chip tool add" href="/people/new" data-link aria-label="Add a person">${icon("plus")}</a>`;
  $("#chips").querySelectorAll("[data-person]").forEach(b => b.onclick = () => pickPerson(b.dataset.person));
  $("#chips [data-compare]").onclick = toggleCompare;
  const narrow = $("#compare-narrow");
  narrow.setAttribute("aria-pressed", S.compare);
  narrow.onclick = toggleCompare;
  const on = $("#chips [aria-pressed=true]");
  if (on) {
    const box = $("#chips"), l = on.offsetLeft, r = l + on.offsetWidth;
    if (l < box.scrollLeft || r > box.scrollLeft + box.clientWidth) box.scrollLeft = l - 8;
  }
}

function pickPerson(id) {
  if (S.compare) {
    let next = S.picked.includes(id) ? S.picked.filter(x => x !== id) : [...S.picked, id].slice(-2);
    if (!next.length) next = [id];
    S.picked = next;
  } else {
    S.picked = [id];
  }
  const onNew = !location.pathname.startsWith("/c/") && !location.pathname.startsWith("/people");
  if (onNew) showNew(); else go("/");
}

function toggleCompare() {
  S.compare = !S.compare;
  S.picked = S.picked.slice(0, 1);        // the current person stays as A
  go("/");
}

function renderHistory() {
  const here = location.pathname.startsWith("/c/") ? location.pathname.slice(3).replace(/\/$/, "") : null;
  const groups = { Today: [], Yesterday: [], Earlier: [] };
  const today = new Date(); today.setHours(0, 0, 0, 0);
  for (const c of S.convs) {
    const d = new Date(c.updated);
    const g = d >= today ? "Today" : d >= new Date(today - 864e5) ? "Yesterday" : "Earlier";
    groups[g].push(c);
  }
  const mark = s => {
    const w = s.state === "red" || s.state === "yellow" || s.state === "green" ? s.state : null;
    return w ? `<span class="mk ${w}" title="${w}">${w[0].toUpperCase()}</span>`
      : s.state ? `<span class="mk hold" title="no verdict">${icon("none")}</span>` : `<span class="mk none" title="no answer yet"></span>`;
  };
  const time = iso => `<span class="nw">${new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>`;
  const word = s => s.state === "child" ? "not assessed" : s.state === "refused" ? "out of scope"
    : s.state === "error" ? "error" : s.state || "no answer";
  const rows = Object.entries(groups).filter(([, v]) => v.length).map(([g, list]) =>
    `<h2>${g}</h2>` + list.map(c => `<a class="hist-row" href="/c/${esc(c.id)}" data-link${c.id === here ? ' aria-current="page"' : ""}>` +
      `<span class="marks">${c.sides.map(mark).join("")}</span>` +
      `<span><span class="t">${esc(c.title || "Untitled")}</span>` +
      `<span class="m">${c.sides.map(s => `${esc(s.label)}, ${esc(word(s))}`).join(" · ")} · ${time(c.updated)}</span></span></a>`).join("")).join("");
  $("#history").innerHTML = rows || `<p class="hist-empty">Assessments you make appear here, saved on this device.</p>`;
  const onPeople = location.pathname.startsWith("/people");
  $("#people-link").setAttribute("aria-current", onPeople ? "page" : "false");
  $("#people-n").textContent = S.people.length;
}

function renderStatus() {
  const h = S.health;
  const el = $("#status");
  el.classList.toggle("down", !(h && h.ok));
  el.innerHTML = `<span class="lamp"></span>` + (h && h.ok
    ? `Model loaded, ready`
    : `Model not running. Start llama-server.`);
}

async function refreshLists() {
  const [c, p] = await Promise.all([api.conversations(), api.people()]);
  S.convs = c.conversations;
  S.people = p.people;
  renderHistory();
}

// --------------------------------------------------------------- new assessment

function whoCard(p, big) {
  const watch = p.child ? "" : p.watching.length
    ? `<ul class="watch">${p.watching.map(w => `<li><span class="rid">${esc(w.rule)}</span>` +
        `<span>${esc(ruleName(w.name))}</span></li>`).join("")}</ul>`
    : `<p class="muted" style="margin:.5rem 0 0">No profile rules apply.</p>`;
  return `<div class="who-card">
    ${big ? `<h1>For ${esc(p.label === "You" ? "you" : p.label)}</h1>` : `<h2 style="margin:0;font-size:var(--t-20)">${esc(p.label)}</h2>`}
    ${p.sample ? `<div><span class="sample">Sample profile</span></div>` : ""}
    <div class="facts">${esc(facts(p))}</div>
    ${p.child ? `<div class="kid-note">${esc(p.label)} is under 16. This app can't assess children.</div>` : ""}
    ${watch}
    <a class="edit" href="/people/${esc(p.id)}" data-link>Edit ${esc(p.label === "You" ? "your profile" : p.label)}</a>
  </div>`;
}

function showNew() {
  const q = new URLSearchParams(location.search).get("p");
  if (q && byId(q)) { S.picked = [q]; S.compare = false; history.replaceState(null, "", "/"); }
  S.picked = S.picked.filter(byId);
  if (!S.picked.length) S.picked = [S.people[0]?.id].filter(Boolean);
  S.conv = null; S.live = {}; S.liveSaid = null;
  document.title = "New assessment · Triage";
  renderChips(S.picked);
  renderHistory();
  const people = S.picked.map(byId);
  const head = people.length === 2
    ? `<div class="who-pair">${people.map((p, i) => `<div><div class="who"><span class="ab">${"AB"[i]}</span>${esc(p.label)}</div>${whoCard(p, false)}</div>`).join("")}</div>`
    : whoCard(people[0], true);
  const compareHint = S.compare && people.length < 2
    ? `<div class="notice">${icon("compare")}<span>Pick a second person in the bar above to compare them.</span></div>` : "";
  const src = S.health ? `${fmt(S.health.sources)} government sources` : "government sources";
  $("#main").innerHTML = `<div class="page">${compareHint}${head}
    <div class="try"><h2>Try one</h2><ol>${PRESETS.map((p, i) =>
      `<li><button type="button" data-preset="${i}"><span class="key">${i + 1}</span>` +
      `<span><span class="lbl">${esc(p[0])}</span><span class="snip">${esc(p[1])}</span></span></button></li>`).join("")}</ol></div>
    <p class="scope">Chest pain only · ${src} · runs on this device, no internet · up to
      ${S.health ? S.health.max_followups : 4} follow-ups in each assessment</p>
  </div>` + composerHTML({ first: true });
  $("#main").querySelectorAll("[data-preset]").forEach(b => b.onclick = () => usePreset(+b.dataset.preset));
  bindComposer();
  if (S.autoSend) { S.autoSend = false; send(); }
}

function usePreset(i) {
  const [, text, tl, who] = PRESETS[i];
  S.draft = { text, timeline: tl, showTl: !!tl };
  const pair = Array.isArray(who) ? who.filter(byId) : [];
  if (pair.length === 2) {
    // A pair is a whole demo beat: Compare on, both people, sent at once.
    S.compare = true;
    S.picked = pair;
    showNew();
    send();
    return;
  }
  const one = Array.isArray(who) ? pair[0] : who;
  if (one && byId(one)) {
    // A preset that needs a profile picks it: alone, or against You to compare.
    S.picked = S.compare && one !== "self" ? ["self", one] : [one];
  }
  showNew();
  $("#ta").focus();
}

addEventListener("keydown", e => {
  if (location.pathname !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.target.closest("input, textarea, select, [contenteditable]")) return;
  const n = +e.key;
  if (n >= 1 && n <= PRESETS.length) { e.preventDefault(); usePreset(n - 1); }
});

// ------------------------------------------------------------------ composer

function allowance(conv) {
  if (!conv) return null;
  const anchored = conv.sides.filter(s => s.anchor);
  if (!anchored.length) return null;
  return Math.min(...anchored.map(s => s.followups_left));
}

function composerHTML({ first, left, max = 4, names, busy }) {
  if (busy) {
    return `<div class="composer"><form class="in" id="compose" autocomplete="off">
      <div class="waiting" role="status">Writing the answer. You can add more once it's done.</div>
      <div class="field-row"><label class="sr" for="ta">Waiting</label>
        <textarea class="ta" id="ta" rows="1" disabled placeholder="Waiting for the answer to finish">${esc(S.draft.text)}</textarea>
        <button class="send" id="send" type="submit" disabled aria-label="Send">${icon("send")}</button></div>
    </form></div>`;
  }
  if (left === 0) {
    return `<div class="composer"><div class="in"><div class="full"><p style="margin:0"><b>This assessment has used its ${max} follow-ups.</b>
      Start a new one to keep going; this one stays in the history.</p>
      <button class="btn plain" type="button" data-new>Start a new assessment${names ? ` for ${esc(names)}` : ""}</button></div></div></div>`;
  }
  let line = "";
  if (!first && left != null) {
    const used = Math.max(0, max - left);
    const pips = `<span class="pips" aria-hidden="true">${Array.from({ length: max }, (_, i) =>
      `<span class="pip${i < used ? " used" : ""}"></span>`).join("")}</span>`;
    line = left === 1
      ? `<div class="allow last">${pips}1 follow-up left</div>`
      : `<div class="allow">${pips}${left} follow-ups left</div>`;
  }
  const ph = first ? "Describe what is happening, in your own words" : "Add something, or answer a question";
  return `<div class="composer"><form class="in" id="compose" autocomplete="off">
    ${line}
    <div class="field-row">
      <label class="sr" for="ta">${first ? "What is happening" : "Follow-up"}</label>
      <textarea class="ta" id="ta" rows="1" placeholder="${ph}">${esc(S.draft.text)}</textarea>
      <button class="send" id="send" type="submit" aria-label="Send">${icon("send")}</button>
    </div>
    ${first ? `<div id="tl-wrap" ${S.draft.showTl ? "" : "hidden"}><label class="sr" for="tl">Timeline</label>
      <textarea class="ta tl-in" id="tl" rows="1" placeholder="Timeline, optional: T+0:00 began while sitting…">${esc(S.draft.timeline)}</textarea></div>
      <button class="link-btn" type="button" id="tl-toggle">${S.draft.showTl ? "Remove the timeline" : "Add a timeline"}</button>` : ""}
  </form></div>`;
}

function grow(ta) { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 160) + "px"; }

function bindComposer() {
  const form = $("#compose");
  const newBtn = $("#main .composer [data-new]");
  if (newBtn) newBtn.onclick = () => startOver();
  if (!form) return;
  const ta = $("#ta"), tl = $("#tl");
  grow(ta); if (tl) grow(tl);
  ta.addEventListener("input", () => { S.draft.text = ta.value; grow(ta); });
  if (tl) tl.addEventListener("input", () => { S.draft.timeline = tl.value; grow(tl); });
  ta.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && !touch) { e.preventDefault(); form.requestSubmit(); }
  });
  const tog = $("#tl-toggle");
  if (tog) tog.onclick = () => {
    S.draft.showTl = !S.draft.showTl;
    if (!S.draft.showTl) S.draft.timeline = "";
    $("#tl-wrap").hidden = !S.draft.showTl;
    tog.textContent = S.draft.showTl ? "Remove the timeline" : "Add a timeline";
    if (S.draft.showTl) { tl.value = ""; tl.focus(); }
  };
  form.onsubmit = e => { e.preventDefault(); send(); };
  const busy = ta.disabled || Object.keys(S.live).some(k => !S.live[k].final);
  $("#send").disabled = busy;
  if (!touch && !busy) ta.focus();
}

function startOver() {
  const ids = S.conv ? S.conv.sides.map(s => s.person_id).filter(byId) : S.picked;
  S.picked = ids.length ? ids : ["self"];
  S.compare = S.picked.length === 2;
  S.draft = { text: "", timeline: "", showTl: false };
  go("/");
}

async function send() {
  const text = S.draft.text.trim();
  if (!text) { $("#ta")?.focus(); return; }
  const timeline = S.draft.showTl ? S.draft.timeline.trim() : "";
  if (S.compare && S.picked.length !== 2 && !S.conv) {
    $("#main .page").insertAdjacentHTML("afterbegin",
      `<div class="notice">${icon("compare")}<span>Pick a second person to compare, or turn Compare off.</span></div>`);
    return;
  }
  let conv = S.conv;
  if (!conv) {
    try { conv = await api.createConversation(S.picked); }
    catch (err) {
      $("#main .page").insertAdjacentHTML("afterbegin",
        `<div class="err-panel"><div class="err">${icon("alert")}<span>Could not start the assessment</span></div><div>${esc(err.message)}</div></div>`);
      return;
    }
    S.conv = conv;
    history.pushState(null, "", `/c/${conv.id}`);
  }
  S.draft = { text: "", timeline: "", showTl: false };
  S.liveSaid = { text, timeline, at: new Date().toISOString() };
  await Promise.all(conv.sides.map((_, i) => runTurn(conv.id, i, text, timeline, false)));
}

// ---------------------------------------------------------- the conversation

async function showConversation(id) {
  if (!S.conv || S.conv.id !== id) {
    S.live = {}; S.liveSaid = null;
    try { S.conv = await api.conversation(id); }
    catch {
      $("#main").innerHTML = `<div class="page"><div class="err-panel"><div class="err">${icon("alert")}` +
        `<span>That assessment was not found</span></div><a href="/" data-link>Start a new assessment</a></div></div>`;
      return;
    }
  }
  renderConversation();
  if (S.conv.busy && S.conv.busy.length && !Object.keys(S.live).length) pollBusy(id);
}

function sideCtx(side, final) {
  return {
    canAnswer: true,
    children: S.people.filter(p => p.child),
    sources: S.health && S.health.sources,
    anchor: side.anchor,
    raw: final && final.raw,
  };
}

function renderConversation() {
  const conv = S.conv;
  const pair = conv.sides.length === 2;
  renderChips(conv.sides.map(s => s.person_id), pair);
  renderHistory();
  document.title = `${conv.title || "Assessment"} · Triage`;

  const n = Math.max(...conv.sides.map(s => s.turns.length));
  const whoSaid = `For ${conv.sides.map(s => s.profile.label === "You" ? "you" : s.profile.label).join(" and ")}`;
  let h = "";
  for (let i = 0; i < n; i++) {
    const t0 = conv.sides.map(s => s.turns[i]).find(Boolean);
    h += saidHTML(t0.text, t0.timeline, whoSaid, t0.at);
    h += turnHTML(conv.sides.map((s, k) => s.turns[i]
      ? answerHTML(s.turns[i].event ? { event: s.turns[i].kind, ...s.turns[i].event } : { event: "error", message: "missing" },
        sideCtx(s, s.turns[i]))
      : ""), pair, conv);
  }
  const lastSaid = n ? conv.sides.map(s => s.turns[n - 1]).find(Boolean).text : null;
  if (S.liveSaid && S.liveSaid.text !== lastSaid) h += saidHTML(S.liveSaid.text, S.liveSaid.timeline, whoSaid, S.liveSaid.at);
  if (Object.keys(S.live).length) {
    h += `<div id="live">${turnHTML(conv.sides.map((s, k) => `<div data-live="${k}">${liveHTML(k)}</div>`), pair, conv)}</div>`;
  }
  const busyOther = (conv.busy || []).filter(k => !S.live[k]);
  if (busyOther.length) {
    h += `<div class="notice" id="busy-note">${icon("info")}<span>` +
      `Still writing${conv.sides.length > 1 ? " this side" : ""}...</span></div>`;
  }
  const first = conv.sides.every(s => !s.anchor);
  const left = allowance(conv);
  $("#main").innerHTML = `<div class="page${pair ? " pair" : ""}" id="thread">${h}</div>` +
    composerHTML({ first, left, busy: Object.values(S.live).some(p => !p.final) || busyOther.length > 0,
      max: S.health ? S.health.max_followups : 4,
      names: conv.sides.map(s => s.profile.label).join(" and ") });
  bindThread();
  bindComposer();
  scrollDown();
}

// What the person said, as a record: who it is about, when, the words, and the
// timeline in the same mono as every other measurement.
const clock = iso => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
const saidHTML = (text, tl, who, at) => `<div class="said">` +
  `<div class="who-at">${esc(who)} <span class="nw">· ${esc(clock(at || new Date().toISOString()))}</span></div>` +
  `<div class="words">${esc(text)}</div>` +
  (tl ? `<div class="tl"><b>Timeline</b><span>${esc(tl)}</span></div>` : "") + `</div>`;

function turnHTML(parts, pair, conv) {
  if (!pair) return `<div class="turn">${parts[0]}</div>`;
  const tabs = `<div class="tabs" role="tablist">${conv.sides.map((s, k) =>
    `<button class="chip" type="button" role="tab" data-tab="${k}" aria-pressed="${k === 0}">` +
    `<span class="ab">${"AB"[k]}</span>${esc(s.profile.label)}</button>`).join("")}</div>`;
  return `<div class="turn pair">${tabs}${parts.map((p, k) =>
    `<div class="side-ans" data-side="${k}" ${k === 0 ? "" : "hidden"}><div class="who"><span class="ab">${"AB"[k]}</span>` +
    `${esc(conv.sides[k].profile.label)}</div>${p}</div>`).join("")}</div>`;
}

function liveHTML(k) {
  const p = S.live[k];
  if (!p) return "";
  if (p.final) return answerHTML(p.final, { ...sideCtx(S.conv.sides[k], { raw: p.raw }), animate: !p.shown });
  return pendingHTML({ ...p, now: performance.now() });
}

function bindThread() {
  const thread = $("#thread");
  thread.onclick = e => {
    const t = e.target;
    const cite = t.closest(".cite");
    if (cite) return openChunk(cite.dataset.k);
    const chk = t.closest(".checked");
    if (chk) {
      const d = document.getElementById(chk.getAttribute("aria-controls"));
      const open = chk.getAttribute("aria-expanded") !== "true";
      chk.setAttribute("aria-expanded", open);
      d.hidden = !open;
      return;
    }
    const ans = t.closest("[data-answer]");
    if (ans) {
      const ta = $("#ta");
      if (!ta) return;
      ta.value = `${ans.dataset.answer}\n`;
      S.draft.text = ta.value;
      grow(ta); ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
      return;
    }
    const tab = t.closest("[data-tab]");
    if (tab) {
      const turn = tab.closest(".turn");
      turn.querySelectorAll("[data-tab]").forEach(b => b.setAttribute("aria-pressed", b === tab));
      turn.querySelectorAll(".side-ans").forEach(s => s.hidden = s.dataset.side !== tab.dataset.tab);
      return;
    }
    const liveEl = t.closest("[data-live]");
    if (t.closest("[data-raw-toggle]") && liveEl) {
      const k = +liveEl.dataset.live, p = S.live[k];
      if (!p) return;
      p.showRaw = !p.showRaw;
      liveEl.innerHTML = liveHTML(k);
      return;
    }
    if (t.closest("[data-continue]") && liveEl) {
      const k = +liveEl.dataset.live, p = S.live[k];
      return runTurn(S.conv.id, k, p.text, p.timeline, true);
    }
    const sw = t.closest("[data-switch]");
    if (sw && liveEl) {
      const p = S.live[+liveEl.dataset.live];
      S.picked = [sw.dataset.switch]; S.compare = false;
      S.draft = { text: p.text, timeline: p.timeline, showTl: !!p.timeline };
      S.autoSend = true;
      return go("/");
    }
    if (t.closest("[data-new]")) return startOver();
  };
}

// Urgency first: land on the latest message with its answer right under it,
// never at the bottom of a long answer with the verdict scrolled away.
function scrollDown() {
  requestAnimationFrame(() => {
    const said = [...document.querySelectorAll("#thread .said")].pop();
    if (said) said.scrollIntoView({ block: "start", behavior: "instant" });
  });
}

// One side's turn, streamed into its live block.
async function runTurn(cid, k, text, timeline, confirmed) {
  const side = S.conv.sides[k];
  const p = S.live[k] = { first: !side.anchor, src: null, reading: null, readAt: 0, tokenAt: 0,
    tokens: 0, raw: "", tail: "", checking: false, final: null, text, timeline };
  if (confirmed) S.liveSaid = S.liveSaid || { text, timeline, at: new Date().toISOString() };
  renderConversation();
  let frame = 0;
  const paint = () => {
    frame = 0;
    const el = document.querySelector(`[data-live="${k}"]`);
    if (el && S.live[k] === p) el.innerHTML = liveHTML(k);
  };
  const soon = () => { if (!frame) frame = requestAnimationFrame(paint); };
  const tick = setInterval(() => {
    if (p.reading && !p.tokenAt && !p.first) {
      const waited = performance.now() - p.readAt;
      p.slow = waited > Math.max(4000, 3 * (p.reading.estimate_ms || 0));
    }
    if (!p.final) soon();
  }, 250);

  await streamTurn(cid, { side: k, text, timeline, confirmed_subject: confirmed }, ev => {
    switch (ev.event) {
      case "retrieved": case "reused": p.src = ev; break;
      case "reading": p.reading = ev; p.readAt = performance.now(); break;
      case "token":
        if (!p.tokenAt) { p.tokenAt = performance.now(); p.slow = false; }
        p.tokens += 1; p.raw += ev.t;
        p.tail = p.raw.slice(-110).replace(/\s+/g, " ");
        break;
      case "checking": p.checking = true; break;
      case "warn": break;
      default: p.final = ev;
    }
    soon();
  });
  clearInterval(tick);
  if (p.final && p.final.event === "dropped") return awaitSaved(cid, k);
  if (!p.final) p.final = { event: "error", message: "The answer stopped before it finished." };
  paint();
  p.shown = true;

  // Recorded outcomes come back from the server with the saved turn; a
  // question, a full assessment or a busy side stay on screen until acted on.
  const others = Object.entries(S.live).filter(([key, q]) => +key !== k && !q.final);
  if (["result", "refused", "error"].includes(p.final.event) && !others.length) {
    const keep = Object.fromEntries(Object.entries(S.live).filter(([, q]) =>
      !["result", "refused", "error"].includes(q.final && q.final.event)));
    try { S.conv = await api.conversation(cid); } catch { /* keep what is on screen */ }
    S.live = keep;
    if (!Object.keys(keep).length) S.liveSaid = null;
    await refreshLists().catch(() => {});
    if (location.pathname === `/c/${cid}`) renderConversation();
  } else if (!others.length) {
    renderConversation();
  }
}

// A stream that dropped mid-answer. The server finishes the turn and saves it,
// so the side shows as still being written until it lands.
async function awaitSaved(cid, k) {
  delete S.live[k];
  try { S.conv = await api.conversation(cid); } catch { /* keep what is on screen */ }
  if (location.pathname !== `/c/${cid}`) return;
  renderConversation();
  pollBusy(cid);
}

// A side still running on the server, from another tab, before a reload, or
// after its stream dropped: wait for it to land.
let polling = null;
function pollBusy(id) {
  if (polling === id) return;
  polling = id;
  const t = setInterval(async () => {
    if (location.pathname !== `/c/${id}`) { polling = null; return clearInterval(t); }
    const conv = await api.conversation(id).catch(() => null);
    if (!conv) return;
    if (!conv.busy || !conv.busy.length) {
      clearInterval(t);
      polling = null;
      S.conv = conv;
      await refreshLists().catch(() => {});
      renderConversation();
    }
  }, 2000);
}

// ------------------------------------------------------------------- people

async function showPeople() {
  S.conv = null;
  document.title = "People · Triage";
  renderChips([]);
  const p = await api.people();
  S.people = p.people;
  renderHistory();
  $("#main").innerHTML = peopleListHTML(S.people, S.flash);
  S.flash = null;
}

async function showPersonForm(id) {
  S.conv = null;
  renderChips([]);
  renderHistory();
  let person = { label: "", age: "", sex: "", conditions: [], medications: [] };
  if (id) {
    try { person = await api.person(id); }
    catch { return go("/people", true); }
  }
  const count = id ? S.convs.filter(c => c.sides.some(s => s.person_id === id)).length : 0;
  document.title = `${id ? `Edit ${person.label}` : "Add person"} · Triage`;
  $("#main").innerHTML = personFormHTML(person, !id, count);
  bindPersonForm($("#main"), person, !id, {
    go, openChunk,
    onSaved: async (saved, msg) => {
      S.flash = msg;
      await refreshLists();
      if (saved && !id) S.picked = [saved.id];
      if (!saved) S.picked = S.picked.filter(x => x !== id);
      go("/people");
    },
  });
}

// ------------------------------------------------------------- source sheet

async function openChunk(key) {
  const dlg = $("#sheet");
  let c;
  try { c = await api.chunk(key); }
  catch {
    $("#sheet-k").textContent = key;
    $("#sheet-n").textContent = "";
    $("#sheet-body").textContent = `${key} is not in the source registry, so there is nothing to open.`;
    $("#sheet-foot").innerHTML = "";
    dlg.showModal();
    return;
  }
  $("#sheet-k").textContent = c.key;
  $("#sheet-n").textContent = `${fmt(c.token_count)} tokens`;
  $("#sheet-body").textContent = c.text;
  $("#sheet-foot").innerHTML = `<b>${esc(c.publisher)}</b>` +
    `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.url)}</a>` +
    `<span>Retrieved ${esc(c.retrieval_date)} · ${esc(c.attribution)}</span>`;
  dlg.showModal();
}
$("#sheet-x").onclick = () => $("#sheet").close();
$("#sheet").addEventListener("click", e => { if (e.target === $("#sheet")) $("#sheet").close(); });

// --------------------------------------------------------------------- boot

async function health() {
  try { S.health = await api.health(); } catch { S.health = null; }
  renderStatus();
}

async function boot() {
  await Promise.all([health(), refreshLists().catch(() => {})]);
  route();
  setInterval(health, 15000);
}
boot();
