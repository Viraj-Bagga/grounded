// The app shell: routes, person chips, history, the conversation and the
// composer. No framework and no build step; it has to run with the laptop
// offline, from 06-demo/server.py.

import { api, streamTurn, streamInstall, streamFlush } from "./api.js";
import { answerHTML, pendingHTML, esc, fmt, secs } from "./answer.js";
import { peopleListHTML, personFormHTML, bindPersonForm, facts, ruleName } from "./people.js";
import { icon } from "./icons.js";
import { queueHTML, bindQueue } from "./queue.js";
import { syncHTML, bindSync, logLine } from "./sync.js";
import { Recorder, transcribe, micBlocked, micError, recordingLabel, wasEdited } from "./voice.js";

const $ = (s, el = document) => el.querySelector(s);

// Demo presets. Numbered, because keys 1 to 3 pick them on a keyboard.
// THREE PRESETS, THREE BEATS. Viraj's call 2026-09-19. "Burning after a meal"
// was cut because it demos the green path, which is usually refused: the model
// cites nothing when it is reassured. "Tight chest on the stairs" was cut
// because it came back red like the first preset, so it duplicated it. Both
// texts and what they taught are in the build-log if either is ever wanted
// back; the stairs rewording of 2026-09-19 is recorded in claude.md.
// The fourth field is who the preset is for. A single id is a DEFAULT: it
// applies when nobody is picked, which is the state the app now opens in, and
// it never overrides a person the user chose. An array is a pairing and always
// applies, because it is a whole demo beat. Viraj's call 2026-09-19: the beats
// keep running on a profile now that a typed question carries none.
const PRESETS = [
  ["Crushing chest pressure",
   "Heavy pressure in the middle of my chest that has not let up for almost half an hour. I feel sick and I am sweating.",
   "T+0:00 began while sitting watching television. T+0:04 spread to the jaw. T+0:11 sweating and nausea. T+0:26 unchanged after resting.",
   "self"],
  // BEAT 3. Retrieval reliably supplies CP-PERI-002 here, and its
  // "Fast heartbeat / Fever" lines are the ones the model copies onto patients
  // who have neither, so the grounding guard has something real to catch. The
  // case is SILENT on fever and heart rate, deliberately: a demo should not
  // depend on the subtlest branch in the code, which is denial handling.
  ["Sharp pain when breathing in",
   "Sharp pain in my left chest, worse when I breathe in. It eases if I sit up and lean forward. Walking around does not change it.",
   "T+0:00 began at rest. T+0:10 worse on deep breath. T+1:30 unchanged, no relation to exertion.",
   "self"],
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

// NO PROFILE is the default and is not a person: it is not in the store, not on
// the People page, and cannot be edited. A question asked against it carries no
// age, sex, conditions or medications, so no escalation rule can fire.
const NOBODY = { id: "none", label: "No profile", virtual: true, watching: [], child: false,
                 conditions: [], medications: [] };

const S = {
  health: null, people: [], convs: [], regions: [], region: null,
  // The caseload, refreshed with the other lists so the sidebar count is live.
  queue: { waiting: [], done: [], counts: { waiting: 0, done: 0, done_today: 0 } },
  // Where base is, what is waiting to go, and the live log of a flush.
  sync: { base_url: "", device: { id: "", label: "" }, pending: [], sent: 0 },
  flush: { running: false, lines: [] },
  picked: [NOBODY.id], compare: false,
  conv: null, live: {}, liveSaid: null,
  draft: { text: "", timeline: "", showTl: false, heard: null },
  // The microphone's own state. `heard` lives on the draft instead, because it
  // belongs to the words in the box and has to travel with them.
  voice: { rec: null, elapsed: 0, busy: false, error: null },
  // One entry per pack being pulled from the distribution node, keyed by
  // region id: { running, done, total, nfiles, files:[{path,sha256}], error }.
  installing: {},
  flash: null, autoSend: false,
};
const touch = matchMedia("(pointer: coarse)").matches;
const byId = id => (id === NOBODY.id ? NOBODY : S.people.find(p => p.id === id));

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
  if (/^\/regions\/?$/.test(path)) return showRegions();
  if (/^\/queue\/?$/.test(path)) return showQueue();
  if (/^\/sync\/?$/.test(path)) return showSync();
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

// ---------------------------------------------------- who this is for

// One line above the composer, not a chip row across the top. It is touched
// once an assessment, not once a screen, so it sits where the thumb already is
// and the top of the phone goes back to being paper. Viraj's call 2026-09-19.
function forWhoHTML(ids = S.picked, pair = S.compare, live = false) {
  const people = ids.map(byId).filter(Boolean);
  const label = !people.length ? NOBODY.label
    : people.length === 2
      ? people.map((p, i) => `${esc(p.label)}<span class="ab">${"AB"[i]}</span>`).join(" ")
      : esc(people[0].label);
  if (live) {
    return `<div class="forwho" aria-label="Who this is for"><span>For</span>` +
      `<span class="nm" data-for-name>${label}</span></div>`;
  }
  return `<button class="forwho" type="button" id="forwho" aria-haspopup="dialog">` +
    `<span>For</span><span class="nm" data-for-name>${label}</span>${icon("chevron")}</button>`;
}

function bindForWho() {
  const b = $("#main #forwho");
  if (b) b.onclick = openPicker;
}

function pickerHTML() {
  const rows = [NOBODY, ...S.people].map(p => {
    const slot = S.picked.indexOf(p.id);
    const on = slot >= 0;
    const sub = p.virtual ? "A general question, with no profile behind it" : facts(p);
    return `<li><button type="button" data-person="${esc(p.id)}" aria-pressed="${on}">` +
      `<span class="nm">${esc(p.label)}${p.child ? '<span class="u16">Under 16</span>' : ""}</span>` +
      `<span class="fx">${esc(sub)}</span>` +
      (on ? (S.compare ? `<span class="slot">${"AB"[slot]}</span>` : `<span class="tick">${icon("check")}</span>`) : "") +
      `</button></li>`;
  }).join("");
  const hint = S.compare
    ? `<p class="pk-hint">Pick two people. The same question is asked about both, side by side.</p>` : "";
  return `<button class="pk-tool" type="button" data-compare aria-pressed="${S.compare}">${icon("compare")}` +
    `Compare two people<span class="state">${S.compare ? "On" : "Off"}</span></button>${hint}` +
    `<ul class="pk">${rows}</ul>` +
    `<ul class="pk"><li><a href="/people/new" data-link>${icon("plus")}<span class="nm">Add a person</span></a></li>` +
    `<li><a href="/people" data-link><span class="nm">Everyone and their profiles</span></a></li></ul>`;
}

function renderPicker() {
  $("#picker-body").innerHTML = pickerHTML();
  $("#picker-body [data-compare]").onclick = () => { toggleCompare(true); renderPicker(); };
  $("#picker-body").querySelectorAll("[data-person]").forEach(b => b.onclick = () => {
    pickPerson(b.dataset.person);
    if (!S.compare || S.picked.length === 2) closePicker(); else renderPicker();
  });
  $("#picker-body").querySelectorAll("a[data-link]").forEach(a => a.onclick = () => closePicker());
}

function openPicker() {
  renderPicker();
  const d = $("#picker");
  d.showModal();
  d.onclick = e => { if (e.target === d) closePicker(); };   // the backdrop
}

const closePicker = () => $("#picker").close();

function pickPerson(id) {
  if (S.compare) {
    // No profile is not a side of a comparison: picking it turns Compare off.
    if (id === NOBODY.id) { S.compare = false; S.picked = [id]; }
    else {
      let next = S.picked.includes(id) ? S.picked.filter(x => x !== id)
        : [...S.picked.filter(x => x !== NOBODY.id), id].slice(-2);
      if (!next.length) next = [id];
      S.picked = next;
    }
  } else {
    S.picked = [id];
  }
  const onNew = !location.pathname.startsWith("/c/") && !location.pathname.startsWith("/people");
  if (onNew) showNew(); else go("/");
}

function toggleCompare(stay = false) {
  S.compare = !S.compare;
  // The current person stays as A, but "no profile" cannot be a side.
  S.picked = S.picked.slice(0, 1).filter(id => !(S.compare && id === NOBODY.id));
  if (stay) { if (location.pathname === "/") showNew(); else go("/"); return; }
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
  // aria-current is "page" on the one you are on and ABSENT everywhere else.
  // It used to be set to "false" on the others, which is legal but noisy, and
  // the region link never got it at all.
  const path = location.pathname;
  const current = (id, on) => {
    const el = $(id);
    if (on) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  };
  current("#people-link", path.startsWith("/people"));
  current("#queue-link", path.startsWith("/queue"));
  current("#sync-link", path.startsWith("/sync"));
  current("#region-link", path.startsWith("/regions"));
  $("#people-n").textContent = S.people.length;
  const nq = S.queue.counts.waiting;
  $("#queue-n").textContent = nq ? `${nq} waiting` : "Empty";
  $("#queue-link").classList.toggle("has-waiting", nq > 0);
  const ns = S.sync.pending.length;
  $("#sync-n").textContent = ns ? `${ns} to send` : "All sent";
  $("#sync-link").classList.toggle("has-waiting", ns > 0);
}

function renderStatus() {
  const h = S.health;
  const el = $("#status");
  el.classList.toggle("down", !(h && h.ok));
  el.innerHTML = `<span class="lamp"></span>` + (h && h.ok
    ? (h.remote ? `Model on the laptop, ready` : `Model loaded, ready`)
    : `Model not running. Start llama-server.`);
}

async function refreshLists() {
  const [c, p, q, y] = await Promise.all([
    api.conversations(), api.people(), api.queue(),
    // Never blocks the rest: sync is the one list that can be stale without
    // anything on screen being wrong.
    api.sync().catch(() => S.sync)]);
  S.convs = c.conversations;
  S.people = p.people;
  S.queue = q;
  S.sync = y;
  renderHistory();
}

// WHAT A SCREEN READER IS TOLD WHEN AN ANSWER LANDS.
//
// Streaming is silent by design: announcing tokens would read a JSON document
// aloud one fragment at a time. So nothing is announced until the answer is
// complete, and then the OUTCOME is, once. The disposition is included because
// the colour is not available to a listener and the word alone ("red") is not
// an instruction.
const DISPOSITION_SPOKEN = {
  red: "Call emergency services now",
  yellow: "Be seen today",
  green: "Self-care, and the signs that change the answer",
};

function announce(final, who) {
  const el = $("#announce");
  if (!el || !final) return;
  const name = who ? `${who}: ` : "";
  let msg = "";
  if (final.event === "result") {
    const u = (final.result || {}).urgency;
    msg = `${name}${u}. ${DISPOSITION_SPOKEN[u] || ""}.`
      + (final.ungrounded ? " Not grounded in sources." : "")
      + ((final.escalation || {}).changed ? " Raised by a profile rule." : "");
  } else if (final.event === "refused") {
    msg = `${name}no verdict. ${final.message || "This is outside what the app covers."}`;
  } else if (final.event === "error") {
    msg = `${name}the answer did not finish. ${final.message || ""}`;
  } else if (final.event === "confirm_subject") {
    msg = final.message || "Who is this for?";
  } else {
    return;
  }
  // Re-setting the same string does not re-announce, so clear it first.
  el.textContent = "";
  setTimeout(() => { el.textContent = msg.replace(/\s+/g, " ").trim(); }, 60);
}

// --------------------------------------------------------------- new assessment

// True when this page was opened from another machine. The model runs on the
// laptop either way; a phone on the wifi is a screen, and the page says so
// rather than leave "this device" to be read as the phone.
const remoteViewer = () => !!(S.health && S.health.remote);

function showNew() {
  const q = new URLSearchParams(location.search).get("p");
  if (q && byId(q)) { S.picked = [q]; S.compare = false; history.replaceState(null, "", "/"); }
  S.picked = S.picked.filter(byId);
  if (!S.picked.length) S.picked = [NOBODY.id];
  S.conv = null; S.live = {}; S.liveSaid = null;
  document.title = "New assessment · Triage";
  renderHistory();
  const compareHint = S.compare && S.picked.filter(byId).length < 2
    ? `<div class="notice">${icon("compare")}<span>Pick a second person to compare them.</span></div>` : "";
  // The profile card went, but this did not go with it. A child's profile gets
  // the scope notice BEFORE anything is typed, not only after a verdict is
  // asked for (constraint 13). It is the one thing the empty screen still says
  // unprompted, and only for a person it applies to.
  const kid = S.picked.map(byId).filter(x => x && x.child);
  const kidNote = kid.length
    ? `<div class="kid-note">${esc(kid.map(k => k.label).join(" and "))} ${kid.length > 1 ? "are" : "is"}` +
      ` under 16. This app can't assess children.</div>` : "";
  const src = S.health ? `${fmt(S.health.sources)} government sources` : "government sources";
  // NEARLY BLANK: no profile card, no rule line, no heading. Three presets and
  // two lines of scope, CENTRED in the space above the composer rather than
  // pinned to its bottom edge. Viraj's call 2026-09-19 from the phone: bottom
  // alignment left the top two thirds of a 390x844 screen empty, which reads
  // as a void with content fallen to the floor rather than as an empty state.
  //
  // THE SCOPE BLOCK IS TWO LINES, NOT ONE. What this is, then how it runs.
  // They are different kinds of statement and ran together as one sentence.
  // The second is quieter because it is the honesty note, and it has to stay
  // on the first screen and above the composer: over the wifi it carries "the
  // model runs on the laptop, not on this phone" and ui_check asserts both
  // that wording and its position.
  // THE MAIN SCREEN HAD NO h1. Every other route has one; this one is a
  // composer, so its heading is for the document outline and screen readers
  // rather than for the eye. Visually hidden, not absent.
  $("#main").innerHTML = `<div class="page blank"><h1 class="sr">New assessment</h1>${compareHint}${kidNote}
    <ul class="picks">${PRESETS.map((p, i) =>
      `<li><button type="button" data-preset="${i}">` +
      `<span class="lbl">${esc(p[0])}</span>` +
      `<span class="n">${i + 1}</span>${icon("chevron")}</button></li>`).join("")}</ul>
    <div class="scope">
      <p class="what">Chest pain only · ${src}</p>
      <p class="how">${remoteViewer()
        ? "The model runs on the laptop, not on this phone"
        : "Runs on this device"} · no internet</p>
    </div>
  </div>` + composerHTML({ first: true });
  $("#main").querySelectorAll("[data-preset]").forEach(b => b.onclick = () => usePreset(+b.dataset.preset));
  bindComposer();
  if (S.autoSend) { S.autoSend = false; send(); }
}

function usePreset(i) {
  const [, text, tl, who] = PRESETS[i];
  S.draft = { text, timeline: tl, showTl: !!tl, heard: null };
  const pair = Array.isArray(who) ? who.filter(byId) : [];
  if (pair.length === 2) {
    // A pair is a whole demo beat: Compare on, both people, sent at once.
    S.compare = true;
    S.picked = pair;
    showNew();
    send();
    return;
  }
  // A single id is the preset's DEFAULT person. It applies only when nobody is
  // picked, which is how the app opens, so the demo beats still run on a
  // profile. It never overrides a person the user chose for themselves.
  const one = Array.isArray(who) ? pair[0] : who;
  const nobody = !S.picked.length || (S.picked.length === 1 && S.picked[0] === NOBODY.id);
  if (one && byId(one) && nobody) S.picked = [one];
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

function composerHTML({ first, left, max = 4, names, busy, who }) {
  const forWho = forWhoHTML(who ? who.ids : S.picked, who ? who.pair : S.compare, who ? who.live : false);
  if (busy) {
    return `<div class="composer"><form class="in" id="compose" autocomplete="off">${forWho}
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
    ${forWho}${line}
    <div class="field-row">
      <label class="sr" for="ta">${first ? "What is happening" : "Follow-up"}</label>
      <textarea class="ta" id="ta" rows="1" placeholder="${ph}">${esc(S.draft.text)}</textarea>
      <span id="mic-slot">${micHTML()}</span>
      <button class="send" id="send" type="submit" aria-label="Send">${icon("send")}</button>
    </div>
    <div id="heard-slot">${heardHTML(first)}</div>
    ${first ? `<div id="tl-wrap" ${S.draft.showTl ? "" : "hidden"}><label class="sr" for="tl">Timeline</label>
      <textarea class="ta tl-in" id="tl" rows="1" placeholder="Timeline, optional: T+0:00 began while sitting…">${esc(S.draft.timeline)}</textarea></div>
      <button class="link-btn" type="button" id="tl-toggle">${S.draft.showTl ? "Remove when it started" : "Add when it started"}</button>` : ""}
  </form></div>`;
}

// THE MICROPHONE. Tap to record, tap to stop. What comes back goes in the box
// as editable text and is never sent on its own: a misheard symptom is a wrong
// verdict, so the person reads it first. See static/js/voice.js and voice.py.
function micHTML() {
  if (micBlocked(S.health)) return "";
  const v = S.voice;
  if (v.busy)
    return `<button class="mic working" id="mic" type="button" disabled
      aria-label="Writing down what you said">${icon("mic")}</button>`;
  if (v.rec)
    return `<button class="mic on" id="mic" type="button" aria-label="Stop recording"
      >${icon("stop")}<span class="t">${recordingLabel(v.elapsed)}</span></button>`;
  return `<button class="mic" id="mic" type="button" aria-label="Say it instead of typing"
    >${icon("mic")}</button>`;
}

// One line, under the composer. It carries the transcription time next to the
// instruction to check the words, because those two belong together.
function heardHTML(first) {
  const v = S.voice, h = S.draft.heard;
  if (v.error) return `<div class="heard">${esc(v.error)}</div>`;
  if (v.busy) return `<div class="heard">Writing down what you said\u2026</div>`;
  if (v.rec) return `<div class="heard">Listening. Tap again to stop.</div>`;
  const blocked = micBlocked(S.health);
  if (blocked) return first ? `<div class="heard quiet">${esc(blocked)}</div>` : "";
  if (!h) return "";
  const edited = wasEdited(S.draft.text, h.text);
  return `<div class="heard">Heard in ${secs(h.ms)}${edited ? ", then edited" : ""}.
    <b>Read it before you send.</b>
    <span class="src">${esc(h.model)}, on this machine</span></div>`;
}

// The same sense of "first" the composer itself uses: no side has been
// answered yet, whether or not the assessment exists on disk.
const firstComposer = () => !S.conv || S.conv.sides.every(s => !s.anchor);

// Only the mic button and the line under it. The textarea is left alone, so
// redrawing never steals focus or moves the cursor while somebody is typing.
function refreshVoice() {
  const m = $("#mic-slot"); if (m) m.innerHTML = micHTML();
  const h = $("#heard-slot"); if (h) h.innerHTML = heardHTML(firstComposer());
  const b = $("#send"); if (b) b.disabled = sendDisabled();
  bindMic();
}

// Send is closed while the microphone is open or the words are still being
// written down. Sending mid-recording would assess a half-typed box and then
// drop the transcript into an empty one.
function sendDisabled() {
  const ta = $("#ta");
  return !!(S.voice.rec || S.voice.busy) || !!(ta && ta.disabled)
    || Object.keys(S.live).some(k => !S.live[k].final);
}

function bindMic() {
  const b = $("#mic");
  if (!b) return;
  b.onclick = async () => {
    const v = S.voice;
    if (v.busy) return;
    if (v.rec) return v.rec.stop();
    v.error = null;
    const rec = new Recorder(
      elapsed => {
        v.elapsed = elapsed;
        const t = $("#mic .t");            // just the seconds, 5 times a second
        if (t) t.textContent = recordingLabel(elapsed);
      },
      blob => onRecorded(blob));
    try { await rec.start(); v.rec = rec; v.elapsed = 0; }
    catch (e) { v.error = micError(e); }
    refreshVoice();
  };
}

async function onRecorded(blob) {
  const v = S.voice;
  v.rec = null;
  if (!blob) return refreshVoice();
  v.busy = true;
  refreshVoice();
  try {
    const heard = await transcribe(blob);
    if (!heard.text) {
      v.error = "Nothing was heard. Try again, closer to the microphone.";
    } else {
      S.draft.heard = heard;
      const ta = $("#ta");
      // Added to what is already in the box, not dropped over it. Somebody who
      // typed half a sentence and then reached for the microphone keeps both.
      const pre = (ta ? ta.value : S.draft.text).trim();
      S.draft.text = pre ? `${pre} ${heard.text}` : heard.text;
      if (ta) {
        ta.value = S.draft.text;
        grow(ta);
        ta.focus();
        ta.setSelectionRange(ta.value.length, ta.value.length);
      }
    }
  } catch (e) {
    v.error = e.message || "The transcription failed.";
  } finally {
    v.busy = false;
    refreshVoice();
  }
}

function grow(ta) { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 160) + "px"; }

function bindComposer() {
  const form = $("#compose");
  const newBtn = $("#main .composer [data-new]");
  if (newBtn) newBtn.onclick = () => startOver();
  if (!form) return;
  const ta = $("#ta"), tl = $("#tl");
  grow(ta); if (tl) grow(tl);
  ta.addEventListener("input", () => {
    const h = S.draft.heard;
    const was = h && wasEdited(S.draft.text, h.text);
    S.draft.text = ta.value;
    grow(ta);
    // Redraw the line only when "then edited" actually flips, not per keystroke.
    if (h && wasEdited(ta.value, h.text) !== was) refreshVoice();
  });
  if (tl) tl.addEventListener("input", () => { S.draft.timeline = tl.value; grow(tl); });
  ta.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && !touch) { e.preventDefault(); form.requestSubmit(); }
  });
  const tog = $("#tl-toggle");
  if (tog) tog.onclick = () => {
    S.draft.showTl = !S.draft.showTl;
    if (!S.draft.showTl) S.draft.timeline = "";
    $("#tl-wrap").hidden = !S.draft.showTl;
    tog.textContent = S.draft.showTl ? "Remove when it started" : "Add when it started";
    if (S.draft.showTl) { tl.value = ""; tl.focus(); }
  };
  bindForWho();
  bindMic();
  form.onsubmit = e => { e.preventDefault(); send(); };
  const busy = sendDisabled();
  $("#send").disabled = busy;
  if (!touch && !busy) ta.focus();
}

function startOver() {
  const ids = S.conv ? S.conv.sides.map(s => s.person_id).filter(byId) : S.picked;
  S.picked = ids.length ? ids : ["self"];
  S.compare = S.picked.length === 2;
  S.draft = { text: "", timeline: "", showTl: false, heard: null };
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
  const heard = S.draft.heard;
  S.draft = { text: "", timeline: "", showTl: false, heard: null };
  S.voice.error = null;
  S.liveSaid = { text, timeline, at: new Date().toISOString() };
  // Both sides of a comparison carry the same transcript, because it is the
  // same sentence spoken once and assessed for two people.
  await Promise.all(conv.sides.map((_, i) => runTurn(conv.id, i, text, timeline, false, heard)));
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
  renderHistory();
  document.title = `${conv.title || "Assessment"} · Triage`;

  const n = Math.max(...conv.sides.map(s => s.turns.length));
  const whoSaid = `For ${conv.sides.map(s => s.profile.label === "You" ? "you" : s.profile.label).join(" and ")}`;
  // Same reason as the new-assessment screen: the page is a conversation and
  // shows no title, but the document still needs one heading.
  let h = `<h1 class="sr">Assessment ${esc(whoSaid.toLowerCase())}</h1>`;
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
  if (n && !Object.keys(S.live).length) {
    h += `<div class="export"><a class="link-a" href="/api/conversations/${encodeURIComponent(conv.id)}/soap.txt"` +
      ` download>Download the SOAP note</a><span class="muted">Plain text, for a clinician. ` +
      `It shows what the guards removed and why.</span></div>`;
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
      names: conv.sides.map(s => s.profile.label).join(" and "),
      // An assessment's people are frozen when it starts, so here the line
      // says who it is for and does not open the picker.
      who: { ids: conv.sides.map(s => s.person_id), pair, live: true } });
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
      return runTurn(S.conv.id, k, p.text, p.timeline, true, p.heard);
    }
    const sw = t.closest("[data-switch]");
    if (sw && liveEl) {
      const p = S.live[+liveEl.dataset.live];
      S.picked = [sw.dataset.switch]; S.compare = false;
      S.draft = { text: p.text, timeline: p.timeline, showTl: !!p.timeline, heard: p.heard };
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
async function runTurn(cid, k, text, timeline, confirmed, heard = null) {
  const side = S.conv.sides[k];
  const p = S.live[k] = { first: !side.anchor, src: null, reading: null, readAt: 0, tokenAt: 0,
    tokens: 0, raw: "", tail: "", checking: false, final: null, text, timeline, heard };
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

  // heard_id, not the transcript. The server kept what it produced and works
  // out for itself whether the person changed it, because the SOAP note states
  // that to a clinician and it has to be a fact rather than the page's word.
  await streamTurn(cid, { side: k, text, timeline, confirmed_subject: confirmed,
                          heard_id: heard && heard.id }, ev => {
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
  announce(p.final, S.conv && S.conv.sides.length === 2
    ? (S.conv.sides[k] || {}).profile?.label : null);

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

// ------------------------------------------------------------------ regions

// EXPERIMENTAL add-on packs, and the page says what they are: extra sources,
// built and distributable, NOT wired into retrieval. Selecting one changes
// what this page tells you about emergency numbers and nothing else. Viraj's
// call 2026-09-19, because rewiring retrieval the night before judging would
// put the scope floor and the refusal wording at risk.
// Bytes the way the node and the client say them, so the page and the
// terminal transcript never disagree about how big a pack is.
function bytes(n) {
  n = Number(n || 0);
  if (n < 1000) return `${n} B`;
  if (n < 1e6) return `${(n / 1e3).toFixed(2)} kB`;
  if (n < 1e9) return `${(n / 1e6).toFixed(2)} MB`;
  return `${(n / 1e9).toFixed(2)} GB`;
}

// THE BUTTON SAYS WHERE THE PACK IS. Not installed and the node has it:
// Download, with what it costs. Installed: Use this region. Chosen: Active.
// The base corpus never appears here; it ships with the app and is not a
// download, which is why its card is written out separately below.
function packButton(r, active) {
  const p = r.pack || {};
  const job = S.installing[r.id];
  if (job && job.running)
    return `<button class="btn primary" type="button" disabled>Downloading\u2026</button>`;
  if (!p.installed) {
    if (!p.offered)
      return `<button class="btn" type="button" disabled>Not on the node</button>
        <p class="muted sm">${S.nodeOk === false
          ? `The distribution node at ${esc(S.node || "")} is not running.`
          : "This pack is not being served."}</p>`;
    return `<button class="btn primary" type="button" data-install="${esc(r.id)}"
      >Download \u00b7 ${bytes(p.size)}</button>`;
  }
  return `<button class="btn ${active ? "plain" : "primary"}" type="button"
    data-region="${esc(r.id)}" ${active ? "disabled" : ""}
    >${active ? "Active" : "Use this region"}</button>`;
}

// What arrived, while it is arriving. The packs are small and on loopback, so
// this is over in well under a second: the bar is honest rather than useful.
// THE PANEL BELOW IT IS THE POINT and it stays, because the evidence that
// every file was hashed from disk is worth more than the animation.
function packProgress(r) {
  const job = S.installing[r.id];
  const p = r.pack || {};
  if (job && job.error) {
    return `<div class="dl bad">
      <p><b>${job.integrity ? "The bytes did not match the manifest."
        : "The download did not finish."}</b> Nothing was installed.</p>
      <p class="mono sm">${esc(job.error)}</p></div>`;
  }
  if (job && job.running) {
    const pct = job.total ? Math.round((100 * job.done) / job.total) : 0;
    return `<div class="dl">
      <div class="bar" role="progressbar" aria-valuenow="${pct}"><span style="width:${pct}%"></span></div>
      <p class="sm">${bytes(job.done)} of ${bytes(job.total)} \u00b7
        ${fmt(job.files.length)} of ${fmt(job.nfiles)} files hashed from disk</p>
      ${job.files.length ? `<ul class="dl-f">${job.files.slice(-6).map(f =>
        `<li><span class="p">${esc(f.path)}</span>` +
        `<span class="mono">${esc((f.sha256 || "").slice(0, 12))}</span></li>`).join("")}</ul>` : ""}
    </div>`;
  }
  if (!p.installed) return "";
  return `<div class="dl ok">
    <p><b>Installed on this device.</b> ${fmt(p.installed_files)} files,
      ${bytes(p.installed_size)}, every one hashed from disk against the manifest.</p>
    <p class="mono sm">pack_sha256 ${esc((p.installed_sha256 || "").slice(0, 24))}\u2026</p>
  </div>`;
}

function regionCard(r, active) {
  const topics = [...new Set((r.chunks || []).map(c => c.topic))].join(", ").replace(/_/g, " ");
  const pubs = [...new Set((r.chunks || []).map(c => c.publisher))];
  const p = r.pack || {};
  return `<div class="pack${active ? " on" : ""}" id="pack-${esc(r.id)}">
    <div class="pack-h"><b>${esc(r.title)}</b>${active ? '<span class="tag">active</span>' : ""}</div>
    <p class="muted">${esc(r.description || "")}</p>
    <dl class="pack-d">
      <dt>Adds</dt><dd>${fmt((r.chunks || []).length)} chunks: ${esc(topics)}
        <div class="keys-row">${(r.chunks || []).map(c =>
          `<span class="mono">${esc(c.key)}</span>`).join("")}</div></dd>
      <dt>Sources</dt><dd>${pubs.map(esc).join("; ")}</dd>
      <dt>Emergency</dt><dd>${r.emergency_number
        ? `<b>${esc(r.emergency_number)}</b>` : "no single number: local emergency services"}</dd>
      <dt>Licence</dt><dd>${esc((r.license || {}).name || "?")}.
        ${(r.license || {}).commercial === false
          ? "<b>Not for commercial use.</b>" : ""} ${esc((r.license || {}).plain || "")}</dd>
      <dt>Retrieval</dt><dd>Unchanged. The model still reads the base corpus only.</dd>
      <dt>Pack</dt><dd>${p.installed
        ? `installed here, version ${esc(p.installed_version || "?")}`
        : p.offered
          ? `${bytes(p.size)} in ${fmt(p.files)} files, on the node, not on this device yet`
          : "not available from the node"}</dd>
    </dl>
    <div class="pack-act">${packProgress(r)}${packButton(r, active)}</div>
  </div>`;
}

// S.regions plus where the distribution node is and whether it answered.
// One loader, because the regions page and the first paint both need it.
async function loadRegions() {
  try {
    const d = await api.regions();
    S.regions = d.regions || [];
    S.node = d.node;
    S.nodeOk = d.node_ok;
  } catch {
    S.regions = [];
    S.nodeOk = false;
  }
}

async function showRegions() {
  S.conv = null;
  document.title = "Regions \u00b7 Triage";
  await loadRegions();
  renderHistory();
  const active = S.regions.find(r => r.id === S.region);
  const nodeLine = S.nodeOk
    ? `Packs come from the distribution node at <span class="mono">${esc(S.node || "")}</span>,
       over the network, with no internet. Every file is hashed from disk against the pack's
       manifest before anything counts as installed.`
    : `<b>The distribution node is not running.</b> Installed packs still work.
       To offer downloads, start it with
       <span class="mono">python 07-distribute/server.py</span>.`;
  $("#main").innerHTML = `<div class="page">
    <h1 class="pg-h">Regions</h1>
    <div class="notice">${icon("info")}<span><b>These packs are experimental and do not
      change the answers.</b> The model reads the base corpus, ${fmt(S.health ? S.health.sources : 0)}
      chest pain sources, whichever region is chosen. A region pack is extra material, built and
      ready to distribute, and it changes what this page tells you about emergency numbers.</span></div>
    <div class="notice"><span class="node-dot${S.nodeOk ? " on" : ""}"></span><span>${nodeLine}</span></div>
    ${S.regions.length ? "" : `<p class="muted">No region packs are on this machine yet.</p>`}
    <div class="packs">
      <div class="pack${S.region ? "" : " on"}">
        <div class="pack-h"><b>Base corpus only</b>${S.region ? "" : '<span class="tag">active</span>'}</div>
        <p class="muted">Chest pain, US government sources, public domain. What the model reads.</p>
        <dl class="pack-d"><dt>Pack</dt><dd>ships with the app, always installed</dd></dl>
        <div class="pack-act"><button class="btn ${S.region ? "primary" : "plain"}" type="button" data-region=""
          ${S.region ? "" : "disabled"}>${S.region ? "Use the base corpus alone" : "Active"}</button></div>
      </div>
      ${S.regions.map(r => regionCard(r, active && active.id === r.id)).join("")}
    </div>
  </div>`;
  bindPacks($("#main"));
}

function bindPacks(root) {
  root.querySelectorAll("[data-region]").forEach(b => b.onclick = () => {
    S.region = b.dataset.region || null;
    try { localStorage.setItem("region", S.region || ""); } catch { /* private window */ }
    showRegions();
    renderRegionRow();
  });
  root.querySelectorAll("[data-install]").forEach(b => b.onclick = () => install(b.dataset.install));
}

// Only this card's buttons and progress, so a download does not redraw the
// page under the person's finger five times a second.
function paintPack(rid) {
  const card = document.getElementById(`pack-${rid}`);
  const r = S.regions.find(x => x.id === rid);
  if (!card || !r) return;
  const act = card.querySelector(".pack-act");
  if (!act) return;
  act.innerHTML = packProgress(r) + packButton(r, S.region === rid);
  bindPacks(card);
}

// PULL A PACK FROM THE NODE. The verification is the reference client's, run
// on the server; this only shows what it reports. A pack is installed when its
// manifest.json exists, which the client writes last, after every file has
// hashed. Retrieval does not change and the card keeps saying so.
async function install(rid) {
  if (S.installing[rid] && S.installing[rid].running) return;
  const job = S.installing[rid] = { running: true, done: 0, total: 0, nfiles: 0, files: [] };
  paintPack(rid);
  await streamInstall(rid, ev => {
    switch (ev.event) {
      case "start": job.total = ev.size || 0; job.nfiles = ev.files || 0; break;
      case "verified":
        job.files.push({ path: ev.path, sha256: ev.sha256 });
        job.done = ev.done || job.done;
        break;
      case "error":
        job.error = ev.message || "the install failed";
        job.integrity = !!ev.integrity;
        job.running = false;
        break;
      case "dropped":
        job.error = "the connection dropped before the install finished";
        job.running = false;
        break;
      case "done": job.running = false; break;
      default: return;                      // line, file: the bar moves on verified
    }
    paintPack(rid);
  });
  job.running = false;
  // Re-read from the server rather than believing the stream: installed means
  // manifest.json is on disk, and only the server can say that.
  await loadRegions();
  if (!job.error) delete S.installing[rid];
  if (location.pathname === "/regions") showRegions();
}

function renderRegionRow() {
  const el = $("#region-link");
  if (!el) return;
  const r = S.regions.find(x => x.id === S.region);
  el.querySelector(".n").textContent = r ? (r.name || r.title) : "Base only";
}

// -------------------------------------------------------------------- caseload

// The screen a health worker actually works down. Assess takes them to a new
// assessment with that person already picked; the server has already attached
// the assessment to their caseload entry, so Mark seen is the only thing left.
async function showQueue() {
  S.conv = null;
  document.title = "Caseload · Triage";
  await refreshLists();
  $("#main").innerHTML = queueHTML(S.queue, S.people, S.flash);
  S.flash = null;
  bindQueue($("#main"), {
    add: async (id, reason) => {
      try { S.queue = await api.enqueue(id, reason); }
      catch (e) { S.flash = e.body?.errors?.reason || "That could not be added."; }
      await showQueue();
    },
    seen: async entry => {
      S.queue = await api.markSeen(entry, null);
      await showQueue();
    },
    drop: async entry => {
      S.queue = await api.unqueue(entry);
      await showQueue();
    },
    assess: id => { S.picked = [id]; S.compare = false; go("/"); },
  });
}

// ------------------------------------------------------------------ send to base

// The only screen in the app that needs a network, and it says so. Nothing is
// sent until the button is pressed: see sync.js.
async function showSync() {
  S.conv = null;
  document.title = "Send to base · Triage";
  await refreshLists();
  paintSync();
}

function paintSync() {
  $("#main").innerHTML = syncHTML(S.sync, S.flush);
  bindSync($("#main"), {
    setBase: async url => {
      try { S.sync = await api.setBase(url); S.flash = null; }
      catch (e) { S.flush.lines = [esc(e.body?.error || "That address was not accepted.")]; }
      paintSync();
    },
    send: async () => {
      S.flush = { running: true, lines: [] };
      paintSync();
      await streamFlush(e => {
        const line = logLine(e);
        if (line) S.flush.lines.push(line);
        paintSync();
      });
      S.flush.running = false;
      await refreshLists();
      paintSync();
    },
  });
}

// ------------------------------------------------------------------- people

async function showPeople() {
  S.conv = null;
  document.title = "People · Triage";
  const p = await api.people();
  S.people = p.people;
  renderHistory();
  $("#main").innerHTML = peopleListHTML(S.people, S.flash);
  S.flash = null;
}

async function showPersonForm(id) {
  S.conv = null;
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
  const region = S.regions.find(r => r.id === S.region);
  const otherNumber = /\b9-?1-?1\b/.test(c.text || "");
  $("#sheet-foot").innerHTML =
    (region && otherNumber ? `<div class="sheet-note">${icon("info")}<span>` +
      (region.emergency_number
        ? `This source is a US page and says 9-1-1. The emergency number for ${esc(region.name || region.title)} is <b>${esc(region.emergency_number)}</b>.`
        : `This source is a US page and says 9-1-1. ${esc(region.name || region.title)} has no single emergency number: use local emergency services.`) +
      ` The source is shown unchanged.</span></div>` : "") +
    `<b>${esc(c.publisher)}</b>` +
    `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.url)}</a>` +
    `<span>Retrieved ${esc(c.retrieval_date)} · ${esc(c.attribution)}</span>`;
  dlg.showModal();
}
$("#sheet-x").onclick = () => $("#sheet").close();
$("#picker-x").onclick = closePicker;
$("#sheet").addEventListener("click", e => { if (e.target === $("#sheet")) $("#sheet").close(); });

// --------------------------------------------------------------------- boot

async function health() {
  try { S.region = localStorage.getItem("region") || null; } catch { S.region = null; }
  await loadRegions();
  // BASE IS THE DEFAULT AND A STALE ID DOES NOT OVERRIDE IT. The region is
  // remembered per origin, so a pack chosen once on one address stays chosen
  // there. If the id no longer names a pack on this machine, it is not a
  // region: drop it rather than sit in a state where the sidebar says "Base
  // only" while S.region is still set.
  if (S.region && !S.regions.some(r => r.id === S.region && (r.pack || {}).installed)) {
    S.region = null;
    try { localStorage.removeItem("region"); } catch { /* private window */ }
  }
  renderRegionRow();
  try { S.health = await api.health(); } catch { S.health = null; }
  renderStatus();
}

async function boot() {
  await Promise.all([health(), refreshLists().catch(() => {})]);
  route();
  setInterval(health, 15000);
}
boot();
