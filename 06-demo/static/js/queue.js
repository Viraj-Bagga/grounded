// The caseload: who is waiting, and who has been seen today.
//
// A health worker arrives at a village with a list, not with one patient. This
// is the screen they work down: tap a name to assess them, mark them seen, next.
//
// NOTHING HERE REACHES A PROMPT. The reason note is the worker's own shorthand
// for why someone is on the list. An assessment is still built from the
// composer text and the profile, exactly as it was. See caseload.py.

import { esc } from "./answer.js";
import { icon } from "./icons.js";

const clock = iso => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

// A person's line under their name. Deliberately the same shape as the People
// page's, so the two screens read as one app.
function who(e) {
  const bits = [];
  if (e.age != null && e.sex) bits.push(`${e.age}, ${esc(e.sex)}`);
  if (e.reason) bits.push(esc(e.reason));
  return bits.join(" · ");
}

function waitingRow(e) {
  return `<li class="q-item${e.missing ? " gone-person" : ""}" data-entry="${esc(e.id)}">
    <div class="q-main">
      <span class="nm">${esc(e.label)}${e.missing ? '<span class="sample">No profile</span>' : ""}</span>
      <span class="fx">${who(e) || "waiting"}</span>
      <span class="m">Added ${esc(clock(e.added))}</span>
    </div>
    <div class="q-acts">
      ${e.missing ? "" : `<button class="btn primary" type="button" data-assess="${esc(e.person_id)}">Assess</button>`}
      <button class="btn plain" type="button" data-seen="${esc(e.id)}">Mark seen</button>
      <button class="icon-btn danger" type="button" data-drop="${esc(e.id)}"
        aria-label="Take ${esc(e.label)} off the list">${icon("close")}</button>
    </div>
  </li>`;
}

function doneRow(e) {
  return `<li class="q-item done">
    <div class="q-main">
      <span class="nm">${esc(e.label)}</span>
      <span class="fx">${who(e) || ""}</span>
      <span class="m">Seen ${esc(clock(e.done_at))}</span>
    </div>
    <div class="q-acts">${e.conversation_id
      ? `<a class="btn plain" href="/c/${esc(e.conversation_id)}" data-link>Open assessment</a>`
      : `<span class="m">no assessment recorded</span>`}</div>
  </li>`;
}

// The add control is a picker of people NOT already waiting, so the same person
// cannot be queued twice from the screen that shows they are already on it.
function addHTML(people, waiting) {
  const already = new Set(waiting.map(e => e.person_id));
  const free = people.filter(p => !already.has(p.id) && p.id !== "none");
  if (!free.length) return `<p class="lede">Everyone on the People page is already waiting.</p>`;
  return `<form class="q-add" id="q-add">
    <label class="sr-only" for="q-who">Who is waiting</label>
    <select id="q-who" name="person_id">${free.map(p =>
      `<option value="${esc(p.id)}">${esc(p.label)}</option>`).join("")}</select>
    <label class="sr-only" for="q-why">Why, in a few words</label>
    <input id="q-why" name="reason" type="text" maxlength="80" autocomplete="off"
      placeholder="Why they are waiting, optional">
    <button class="btn primary" type="submit">${icon("plus")}Add to caseload</button>
  </form>`;
}

export function queueHTML(q, people, flash) {
  const n = q.counts.waiting;
  return `<div class="page">
    ${flash ? `<p class="saved" role="status">${esc(flash)}</p>` : ""}
    <div class="head-row"><h1>Caseload</h1><span class="grow"></span>
      <span class="q-count">${n} waiting · ${q.counts.done_today} seen today</span></div>
    <p class="lede">Who is waiting to be assessed on this device. The list is kept here,
      offline, and nothing on it is sent to the model.</p>
    ${addHTML(people, q.waiting)}
    ${q.waiting.length
      ? `<ul class="q-list">${q.waiting.map(waitingRow).join("")}</ul>`
      : `<p class="hist-empty">Nobody is waiting. Add someone above to start a caseload.</p>`}
    ${q.done.length ? `<h2 class="q-h2">Seen</h2>
      <ul class="q-list">${q.done.slice(0, 20).map(doneRow).join("")}</ul>` : ""}
  </div>`;
}

// `on` carries the three things the page can do, so this module never reaches
// into app.js state: { add(personId, reason), seen(entryId), drop(entryId),
// assess(personId) }.
export function bindQueue(root, on) {
  const form = root.querySelector("#q-add");
  if (form) {
    form.onsubmit = e => {
      e.preventDefault();
      const fd = new FormData(form);
      on.add(String(fd.get("person_id") || ""), String(fd.get("reason") || ""));
    };
  }
  root.querySelectorAll("[data-assess]").forEach(b => {
    b.onclick = () => on.assess(b.dataset.assess);
  });
  root.querySelectorAll("[data-seen]").forEach(b => {
    b.onclick = () => on.seen(b.dataset.seen);
  });
  root.querySelectorAll("[data-drop]").forEach(b => {
    b.onclick = () => on.drop(b.dataset.drop);
  });
}
