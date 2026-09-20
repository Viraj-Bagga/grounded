// BASE, the supervisor's screen. Reads /api/dashboard and renders it.
//
// It recomputes nothing. Every verdict, citation, rule and removal on this
// page came out of the assessment a field device saved and sent, so what a
// supervisor reads is what the health worker read. See base_server.py.

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const WORD = { red: "red", yellow: "yellow", green: "green", refused: "out of scope",
               child: "not assessed", error: "error" };
const when = iso => {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const t = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return d >= today ? t : `${d.toLocaleDateString([], { day: "numeric", month: "short" })}, ${t}`;
};

const verdict = s => `<span class="v ${esc(s.state || "none")}">${esc(WORD[s.state] || "no answer")}</span>`;

function sideHTML(s) {
  const tags = [
    s.raised ? `<span class="tag raised">raised by a profile rule</span>` : "",
    s.ungrounded ? `<span class="tag ungrounded">not grounded</span>` : "",
  ].filter(Boolean).join(" ");
  return `<div class="side">
    <h3>${esc(s.label)} ${verdict(s)} ${tags}</h3>
    <dl>
      <dt>Sources</dt><dd>${s.citations.length
        ? `<span class="keys">${s.citations.map(k => `<span class="key">${esc(k)}</span>`).join("")}</span>`
        : `<span class="muted">none cited</span>`}</dd>
      <dt>Guards</dt><dd>${s.removed
        ? `${s.removed} item${s.removed === 1 ? "" : "s"} removed before it was shown`
        : `<span class="muted">nothing removed</span>`}</dd>
      ${s.rules.length ? `<dt>Rules</dt><dd>${s.rules.map(r => `<span class="tag">${esc(r)}</span>`).join(" ")}</dd>` : ""}
    </dl>
  </div>`;
}

function caseHTML(c) {
  const worst = ["red", "yellow", "green"].find(v => c.sides.some(s => s.state === v));
  const said = (c.sides[0] && c.sides[0].said) || c.title || "Untitled";
  return `<details class="case">
    <summary>
      ${c.sides.map(verdict).join(" ")}
      <span class="said">${esc(said.length > 90 ? said.slice(0, 90) + "…" : said)}</span>
      <span class="when">${esc(c.sides.map(s => s.label).join(" · "))} · ${esc(when(c.updated))}</span>
    </summary>
    <div class="body">
      ${c.sides.map(sideHTML).join("")}
      <p class="sha">from ${esc(c.device_label || c.device)} · assessment ${esc(c.id)}<br>verified sha256 ${esc(c.sha256)}</p>
    </div>
  </details>`;
}

function render(d) {
  const c = d.counts;
  const tiles = [
    ["Assessed today", c.today, false],
    ["Red today", c.red_today, c.red_today > 0],
    ["Still waiting in the field", c.outstanding, false],
    ["Devices reporting", c.devices, false],
    ["Assessments held", c.assessments, false],
  ];
  $("#main").innerHTML = `
    <div class="tiles">${tiles.map(([k, n, alarm]) =>
      `<div class="tile${alarm ? " alarm" : ""}"><div class="n">${n}</div><div class="k">${esc(k)}</div></div>`).join("")}</div>

    <h2>Devices</h2>
    ${d.devices.length ? `<ul class="devices">${d.devices.map(x => `<li>
        <strong>${esc(x.label || x.id)}</strong><span class="id">${esc(x.id)}</span>
        <span class="grow"></span>
        <span class="muted">${(x.caseload && x.caseload.waiting) || 0} waiting ·
          ${(x.caseload && x.caseload.done_today) || 0} seen today · last heard ${esc(when(x.last_seen))}</span>
      </li>`).join("")}</ul>`
      : `<p class="empty">No device has reported yet. A field device sends its caseload when it
         comes back into range.</p>`}

    <h2>Assessments</h2>
    ${d.assessments.length
      ? `<ul class="cases">${d.assessments.map(x => `<li>${caseHTML(x)}</li>`).join("")}</ul>`
      : `<p class="empty">Nothing has arrived yet.</p>`}`;
}

async function load() {
  try {
    render(await (await fetch("/api/dashboard")).json());
  } catch (e) {
    $("#main").innerHTML = `<p class="empty">Base could not read its own store: ${esc(e.message)}</p>`;
  }
}

load();
// A supervisor leaves this open on a desk. Polling is the whole interaction:
// a device coming back into range should appear without anyone pressing
// anything. Cheap, because base reads files and runs no model.
setInterval(load, 4000);
