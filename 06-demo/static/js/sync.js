// Sending the caseload to base. One direction, and never automatically.
//
// WHY THERE IS A BUTTON AND NOT A BACKGROUND SYNC. The worker is the one who
// knows they have walked back into range, and a silent upload gives them
// nothing to trust. Pressing it and watching each assessment land with its
// hash is the whole reassurance that the day's work arrived.
//
// WHAT THIS PAGE MAY NOT IMPLY. Assessments are triaged offline because the
// model and the corpus are on the device. Sending them is the only part that
// needs a network, and the page says exactly that and nothing more.

import { esc } from "./answer.js";
import { icon } from "./icons.js";

const when = iso => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

function pendingRow(x) {
  return `<li class="sy-row">
    <span class="nm">${esc(x.people.filter(Boolean).join(" and ") || "Assessment")}</span>
    <span class="m">${esc(when(x.updated))}</span>
    <span class="sha">${esc(x.sha256.slice(0, 12))}…</span>
  </li>`;
}

// One line per event from the flush, so the worker watches it happen.
function logLine(e) {
  if (e.event === "start") return `Sending ${e.pending} to ${esc(e.base)}…`;
  if (e.event === "sent") return `${e.already ? "Base already had" : "Landed at base"}: ${esc(e.id)} · ${esc(String(e.sha256).slice(0, 12))}…`;
  if (e.event === "refused") return `REFUSED by base: ${esc(e.id)} · ${esc(e.error || "")}${(e.problems || []).map(p => ` · ${esc(p)}`).join("")}`;
  if (e.event === "offline") return `Base is not reachable. Nothing was lost; it stays on this device.`;
  if (e.event === "error") return `${esc(e.message || "the sync failed")}`;
  if (e.event === "done") {
    if (e.offline) return `Stopped: still ${e.pending_after} to send when base is reachable.`;
    const bits = [`${e.sent.length} sent`];
    if (e.failed.length) bits.push(`${e.failed.length} refused`);
    if (e.pending_after) bits.push(`${e.pending_after} still waiting`);
    return bits.join(", ") + ".";
  }
  return "";
}

export function syncHTML(sy, run) {
  const n = sy.pending.length;
  const busy = run && run.running;
  return `<div class="page">
    <div class="head-row"><h1>Send to base</h1><span class="grow"></span>
      <span class="q-count">${n} waiting to send · ${sy.sent} already at base</span></div>
    <p class="lede">Assessments are made on this device with no network at all. This is the only
      part that needs one: when you are back in range, send the day's caseload to base.</p>

    <div class="sy-base">
      <form class="q-add" id="sy-form">
        <label class="sr-only" for="sy-url">Base address</label>
        <input id="sy-url" name="base_url" type="url" inputmode="url" autocomplete="off"
          value="${esc(sy.base_url)}" placeholder="http://192.168.1.20:8781">
        <button class="btn plain" type="submit">Save address</button>
      </form>
      <p class="m">This device is <strong>${esc(sy.device.label)}</strong>
        <span class="sha">${esc(sy.device.id)}</span>. Base groups its cases by that.</p>
    </div>

    <div class="sy-go">
      <button class="btn primary" id="sy-send" type="button" ${busy || !n ? "disabled" : ""}>
        ${icon("send")}${busy ? "Sending…" : n ? `Send ${n} to base` : "Nothing to send"}</button>
      ${n ? `<span class="m">Nothing leaves this device until you press it.</span>` : ""}
    </div>

    ${run && run.lines.length ? `<ul class="sy-log">${run.lines.map(l =>
      `<li${/REFUSED|not reachable|failed/.test(l) ? ' class="bad"' : ""}>${l}</li>`).join("")}</ul>` : ""}

    ${n ? `<h2 class="q-h2">Waiting to send</h2>
      <ul class="sy-list">${sy.pending.slice(0, 40).map(pendingRow).join("")}</ul>`
      : `<p class="hist-empty">Everything on this device has been accepted at base.</p>`}
  </div>`;
}

export function bindSync(root, on) {
  const form = root.querySelector("#sy-form");
  if (form) form.onsubmit = e => {
    e.preventDefault();
    on.setBase(String(new FormData(form).get("base_url") || ""));
  };
  const btn = root.querySelector("#sy-send");
  if (btn) btn.onclick = () => on.send();
}

export { logLine };
