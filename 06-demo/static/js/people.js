// The household: a list, and a form to add, edit or remove a person. People
// are managed here and nowhere else; the model is schema-constrained to triage
// output and never creates or edits a person.

import { api } from "./api.js";
import { esc, fmt, citeChip } from "./answer.js";
import { icon } from "./icons.js";

// Terms the escalation rules recognise, offered as suggestions. The live panel
// shows what a profile turns on, so free text is still fine.
const CONDITIONS = ["type 2 diabetes", "type 1 diabetes", "coronary artery disease", "angina",
  "previous heart attack", "high blood pressure", "atrial fibrillation", "breast cancer",
  "lung cancer", "lymphoma", "asthma", "COPD"];
const MEDICATIONS = ["metformin", "insulin", "atorvastatin", "aspirin", "apixaban", "warfarin",
  "bisoprolol", "amlodipine", "chemotherapy", "salbutamol inhaler"];

export const ruleName = s => s.charAt(0).toUpperCase() + s.slice(1);

export function facts(p) {
  const out = [`${p.age}, ${p.sex}`];
  if (p.conditions.length) out.push(p.conditions.join(", "));
  if (p.medications.length) out.push(p.medications.join(", "));
  if (p.surgery) out.push(`${p.surgery.what}, ${p.surgery.weeks_ago} weeks ago`);
  if (!p.conditions.length && !p.medications.length && !p.surgery) out.push("no conditions, no medications");
  return out.join(" · ");
}

// WHAT THEY TAKE, HOW OFTEN, WHEN. The schedule was writable from the form and
// shown nowhere, which made it a field that swallowed what a clinician typed.
// Viraj's report 2026-09-20.
//
// IT IS NOT THE MEDICATIONS LINE. The list the model reads is unchanged and
// still shown as plain names under the person's facts; this is the record
// beside it, and 06-demo/selftest_profile_text.py asserts that none of it
// reaches the prompt.
export function scheduleHTML(p) {
  const rows = Object.entries(p.medication_schedule || {});
  const seen = p.last_seen_by || p.last_seen_on;
  if (!rows.length && !seen && !p.patient_id) return "";
  return `<div class="rec-block">
    ${p.patient_id ? `<div class="rec-line"><b>Patient ID</b><span class="mono">${esc(p.patient_id)}</span></div>` : ""}
    ${rows.length ? `<div class="rec-line"><b>Medication schedule</b><ul class="sched">${rows.map(([k, v]) =>
      `<li><span class="drug">${esc(k)}</span><span class="when">${esc(v)}</span></li>`).join("")}</ul></div>` : ""}
    ${seen ? `<div class="rec-line"><b>Last seen</b><span>${esc([p.last_seen_by, p.last_seen_on].filter(Boolean).join(" · "))}</span></div>` : ""}
  </div>`;
}

export function peopleListHTML(people, flash) {
  return `<div class="page">
    ${flash ? `<p class="saved" role="status">${esc(flash)}</p>` : ""}
    <div class="head-row"><h1>People</h1><span class="grow"></span>
      <a class="btn primary" href="/people/new" data-link>${icon("plus")}Add person</a></div>
    <p class="lede">Each person's profile changes what the app watches for when it assesses them.
      Profiles are changed here, never in the conversation.</p>
    ${people.some(p => p.sample) ? `<p class="lede">Sample profiles are made up for this demo.</p>` : ""}
    <ul class="people">${people.map(p => `<li><a href="/people/${esc(p.id)}" data-link>
      <span class="nm">${esc(p.label)}${p.child ? '<span class="u16">Under 16</span>' : ""}${p.sample ? '<span class="sample">Sample</span>' : ""}</span>
      <span class="fx">${esc(facts(p))}</span>
      <span class="rec">${scheduleHTML(p)}</span>
      <span class="rl">${p.child ? "Not assessed by this app"
        : p.watching.length ? `Watching for ${p.watching.map(w => `<span class="rtag">${esc(w.rule)}</span>`).join("")}`
        : "No profile rules apply"}</span>
      <span class="ch">${icon("chevron")}</span></a></li>`).join("")}</ul>
  </div>`;
}

// ------------------------------------------------------------------ the form

export function personFormHTML(p, isNew, conversationsFor) {
  const s = p.surgery || null;
  return `<div class="page wide">
    <div class="head-row"><a class="btn quiet" href="/people" data-link>${icon("back")}People</a></div>
    <div class="head-row"><h1>${isNew ? "Add person" : `Edit ${esc(p.label)}`}</h1></div>
    <div class="form-grid">
      <form class="form" novalidate autocomplete="off">
        <section>
          <h2>Who</h2>
          <div class="f" data-f="label"><label for="f-label">Name</label>
            <input class="inp" id="f-label" name="label" value="${esc(p.label || "")}" maxlength="40" required>
            <div class="err" hidden>${icon("alert")}<span></span></div></div>
          <div class="f" data-f="age"><label for="f-age">Age</label>
            <input class="inp short" id="f-age" name="age" inputmode="numeric" value="${p.age ?? ""}" required>
            <div class="hint">In whole years. Under 16, the app will not assess them.</div>
            <div class="err" hidden>${icon("alert")}<span></span></div></div>
          <div class="f" data-f="sex"><span class="lab" id="f-sex">Sex</span>
            <div class="seg" role="group" aria-labelledby="f-sex">
              ${["female", "male"].map(v => `<button type="button" data-sex="${v}" aria-pressed="${p.sex === v}">${v[0].toUpperCase() + v.slice(1)}</button>`).join("")}
            </div>
            <div class="err" hidden>${icon("alert")}<span></span></div></div>
        </section>
        <section>
          <h2>Health</h2>
          ${tokenField("conditions", "Conditions", p.conditions || [], CONDITIONS, "Type a condition, then press Enter")}
          ${tokenField("medications", "Medications", p.medications || [], MEDICATIONS, "Type a medication, then press Enter")}
        </section>
        <section>
          <h2>Recent surgery</h2>
          <label class="check"><input type="checkbox" id="f-surg" ${s ? "checked" : ""}> Had surgery in the last year</label>
          <div class="pair-f" id="f-surg-fields" ${s ? "" : "hidden"} style="margin-top:1rem">
            <div class="f" data-f="surgery"><label for="f-what">What was it</label>
              <input class="inp" id="f-what" value="${esc(s ? s.what : "")}" maxlength="60">
              <div class="err" hidden>${icon("alert")}<span></span></div></div>
            <div class="f" data-f="surgery_weeks"><label for="f-weeks">Weeks ago</label>
              <input class="inp" id="f-weeks" inputmode="numeric" value="${s ? s.weeks_ago : ""}">
              <div class="err" hidden>${icon("alert")}<span></span></div></div>
          </div>
        </section>
        <section>
          <h2>Record</h2>
          <p class="hint" style="margin:-.25rem 0 .875rem">Record-keeping for a clinician.
            <b>None of this is shown to the model</b>: the profile it reads is the panel on the right,
            and nothing below changes it.</p>
          <div class="pair-f">
            <div class="f" data-f="patient_id"><label for="f-pid">Patient ID</label>
              <input class="inp" id="f-pid" maxlength="40" value="${esc(p.patient_id || "")}">
              <div class="err" hidden>${icon("alert")}<span></span></div></div>
            <div class="f" data-f="last_seen_on"><label for="f-seen-on">Last seen by a clinician</label>
              <input class="inp" id="f-seen-on" type="date" value="${esc(p.last_seen_on || "")}">
              <div class="err" hidden>${icon("alert")}<span></span></div></div>
          </div>
          <div class="f" data-f="last_seen_by"><label for="f-seen-by">Who saw them</label>
            <input class="inp" id="f-seen-by" maxlength="80" value="${esc(p.last_seen_by || "")}">
            <div class="err" hidden>${icon("alert")}<span></span></div></div>
          <div class="f" data-f="medication_schedule"><label for="f-sched">Medication schedule</label>
            <div class="hint">One a line, as <code>metformin: 500mg twice daily</code>.
              The medicines themselves stay in the list above, which is what the model reads.</div>
            <textarea class="inp" id="f-sched" rows="3">${esc(Object.entries(p.medication_schedule || {})
              .map(([k, v]) => `${k}: ${v}`).join("\n"))}</textarea>
            <div class="err" hidden>${icon("alert")}<span></span></div></div>
          <div class="f" data-f="history_notes"><label for="f-notes">History notes</label>
            <textarea class="inp" id="f-notes" rows="4" maxlength="600">${esc(p.history_notes || "")}</textarea>
            <div class="err" hidden>${icon("alert")}<span></span></div></div>
        </section>
        <div class="actions">
          <button class="btn primary" type="submit">${isNew ? "Add person" : "Save changes"}</button>
          <a class="btn quiet" href="/people" data-link>Cancel</a>
          <span class="grow"></span>
          ${isNew ? "" : `<button class="btn plain" type="button" data-del>${icon("trash")}Delete ${esc(p.label)}</button>`}
        </div>
        <div class="confirm-del" hidden>
          <p style="margin:0"><b>Delete ${esc(p.label || "")}?</b> ${conversationsFor
            ? `Their ${fmt(conversationsFor)} past assessment${conversationsFor === 1 ? " stays" : "s stay"} in the history, under this name.`
            : "They have no past assessments."}</p>
          <div class="actions" style="margin-top:0">
            <button class="btn primary" type="button" data-del-yes>Delete</button>
            <button class="btn quiet" type="button" data-del-no>Keep</button></div>
        </div>
      </form>
      <aside class="preview" aria-live="polite"><div class="loading">Checking what this profile turns on…</div></aside>
    </div>
  </div>`;
}

function tokenField(name, label, values, suggestions, placeholder) {
  return `<div class="f" data-f="${name}"><label for="f-${name}">${label}</label>
    <div class="tokens" data-tokens="${name}">
      ${values.map(v => tokHTML(v)).join("")}
      <input id="f-${name}" list="dl-${name}" placeholder="${placeholder}" maxlength="60">
    </div>
    <datalist id="dl-${name}">${suggestions.map(s => `<option value="${esc(s)}">`).join("")}</datalist>
    <div class="err" hidden>${icon("alert")}<span></span></div></div>`;
}

const tokHTML = v => `<span class="tok" data-v="${esc(v)}">${esc(v)}` +
  `<button type="button" aria-label="Remove ${esc(v)}">${icon("close")}</button></span>`;

function previewHTML(pv, label) {
  const name = label || "This person";
  let h = `<h2>What the app will watch for</h2>`;
  if (pv.child) {
    h += `<div class="kid-note" style="margin-top:0">${esc(name)} is under 16. This app can't assess children.</div>`;
  } else if (!pv.watching.length) {
    h += `<p class="muted" style="margin:0">No profile rules apply. The model still assesses every answer, and the guards still run.</p>`;
  } else {
    h += pv.watching.map(w => `<div class="w-rule">
      <div class="h"><span class="rtag">${esc(w.rule)}</span> ${esc(ruleName(w.name))}</div>
      <div class="muted" style="font-size:var(--t-14)">Because of ${esc(w.fact)}. ${w.action === "flag"
        ? "It flags the answer and does not change the urgency."
        : `It raises the urgency one level${w.cap === "yellow" ? ", up to yellow" : ", up to red"}.`}</div>
      <div class="q">“${esc(w.quote)}”</div>
      <div class="cites">${w.keys.map(k => citeChip(k)).join("")}</div></div>`).join("");
  }
  h += `<div><h2 style="margin-bottom:.5rem">What the model reads</h2><pre>${esc(pv.prompt)}</pre></div>`;
  return h;
}

// Wire the form. Returns nothing; navigation happens through `go`.
export function bindPersonForm(root, p, isNew, { go, onSaved, openChunk }) {
  const form = root.querySelector("form");
  const state = {
    sex: p.sex || "",
    conditions: [...(p.conditions || [])],
    medications: [...(p.medications || [])],
  };

  const read = () => {
    const surg = root.querySelector("#f-surg").checked;
    return {
      label: root.querySelector("#f-label").value,
      age: root.querySelector("#f-age").value,
      sex: state.sex,
      conditions: state.conditions,
      medications: state.medications,
      surgery: surg ? { what: root.querySelector("#f-what").value, weeks_ago: root.querySelector("#f-weeks").value } : null,
      // RECORD FIELDS. They ride along on the same save and the server keeps
      // them beside the profile, never inside it. The preview panel is built
      // from profile_text, so adding any of this must leave the panel alone;
      // 06-demo/selftest_profile_text.py is what proves it.
      patient_id: root.querySelector("#f-pid").value,
      last_seen_by: root.querySelector("#f-seen-by").value,
      last_seen_on: root.querySelector("#f-seen-on").value,
      history_notes: root.querySelector("#f-notes").value,
      medication_schedule: Object.fromEntries(
        root.querySelector("#f-sched").value.split("\n")
          .map(l => l.split(/:(.*)/s))
          .filter(x => x.length > 1 && x[0].trim() && x[1].trim())
          .map(x => [x[0].trim(), x[1].trim()])),
    };
  };

  let timer = null, seq = 0;
  const refresh = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const pv = await api.preview(read());
        if (mine !== seq) return;
        const aside = root.querySelector(".preview");
        aside.innerHTML = previewHTML(pv, root.querySelector("#f-label").value.trim());
        aside.querySelectorAll(".cite").forEach(b => b.onclick = () => openChunk(b.dataset.k));
      } catch { /* the preview is advisory; saving still validates */ }
    }, 180);
  };

  const showErrors = errors => {
    root.querySelectorAll(".f[data-f]").forEach(f => {
      const msg = errors[f.dataset.f];
      f.classList.toggle("bad", !!msg);
      const e = f.querySelector(".err");
      if (e) { e.hidden = !msg; e.querySelector("span").textContent = msg || ""; }
    });
    const first = root.querySelector(".f.bad input, .f.bad button");
    if (first) first.focus();
  };

  root.querySelectorAll("[data-sex]").forEach(b => b.onclick = () => {
    state.sex = b.dataset.sex;
    root.querySelectorAll("[data-sex]").forEach(x => x.setAttribute("aria-pressed", x === b));
    refresh();
  });

  root.querySelectorAll("[data-tokens]").forEach(box => {
    const name = box.dataset.tokens, input = box.querySelector("input");
    const add = () => {
      const v = input.value.replace(/,/g, " ").trim().replace(/\s+/g, " ");
      if (v && !state[name].some(x => x.toLowerCase() === v.toLowerCase())) {
        state[name].push(v);
        input.insertAdjacentHTML("beforebegin", tokHTML(v));
        refresh();
      }
      input.value = "";
    };
    input.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
      else if (e.key === "Backspace" && !input.value && state[name].length) {
        state[name].pop();
        box.querySelectorAll(".tok")[state[name].length]?.remove();
        refresh();
      }
    });
    input.addEventListener("change", add);         // picking a suggestion
    input.addEventListener("blur", add);
    box.addEventListener("click", e => {
      const btn = e.target.closest(".tok button");
      if (!btn) { if (e.target === box) input.focus(); return; }
      const tok = btn.closest(".tok");
      state[name] = state[name].filter(x => x !== tok.dataset.v);
      tok.remove();
      refresh();
    });
  });

  const surg = root.querySelector("#f-surg");
  surg.onchange = () => { root.querySelector("#f-surg-fields").hidden = !surg.checked; refresh(); };
  form.addEventListener("input", refresh);

  form.onsubmit = async e => {
    e.preventDefault();
    root.querySelectorAll("[data-tokens] input").forEach(i => i.dispatchEvent(new Event("change")));
    const btn = form.querySelector("[type=submit]");
    btn.disabled = true;
    try {
      const saved = isNew ? await api.createPerson(read()) : await api.updatePerson(p.id, read());
      onSaved(saved, isNew ? `Added ${saved.label}.` : `Saved ${saved.label}.`);
    } catch (err) {
      showErrors((err.body && err.body.errors) || { label: err.message });
    } finally {
      btn.disabled = false;
    }
  };

  const del = root.querySelector("[data-del]");
  if (del) {
    const box = root.querySelector(".confirm-del");
    del.onclick = () => { box.hidden = false; box.querySelector("[data-del-no]").focus(); };
    box.querySelector("[data-del-no]").onclick = () => { box.hidden = true; del.focus(); };
    box.querySelector("[data-del-yes]").onclick = async () => {
      await api.deletePerson(p.id);
      onSaved(null, `Deleted ${p.label}. Their past assessments are still in the history.`);
    };
  }
  refresh();
  if (isNew) root.querySelector("#f-label").focus();
}
