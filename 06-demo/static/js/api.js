// Every call the page makes to 06-demo/server.py.

async function j(url, opts = {}) {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  let body = null;
  try { body = await r.json(); } catch { /* not JSON */ }
  if (!r.ok) {
    const e = new Error((body && body.error) || r.statusText || "request failed");
    e.status = r.status;
    e.body = body;
    throw e;
  }
  return body;
}

const put = (m, b) => ({ method: m, body: JSON.stringify(b) });
const q = encodeURIComponent;

export const api = {
  health: () => j("/api/health"),
  people: () => j("/api/people"),
  person: id => j(`/api/people/${q(id)}`),
  createPerson: p => j("/api/people", put("POST", p)),
  updatePerson: (id, p) => j(`/api/people/${q(id)}`, put("PUT", p)),
  deletePerson: id => j(`/api/people/${q(id)}`, { method: "DELETE" }),
  preview: p => j("/api/people/preview", put("POST", p)),
  conversations: () => j("/api/conversations"),
  conversation: id => j(`/api/conversations/${q(id)}`),
  createConversation: ids => j("/api/conversations", put("POST", { person_ids: ids })),
  chunk: key => j(`/api/chunk/${q(key)}`),
};

// One turn for one side, streamed as server-sent events. onEvent gets every
// event, tokens included. A 409 means that side already has a turn running.
export async function streamTurn(cid, body, onEvent) {
  let r;
  try {
    r = await fetch(`/api/conversations/${q(cid)}/turn`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  } catch (e) {
    onEvent({ event: "error", message: "The app server could not be reached." });
    return;
  }
  if (!r.ok) {
    let b = {};
    try { b = await r.json(); } catch { /* not JSON */ }
    onEvent({ event: r.status === 409 ? "busy" : "error", message: b.error || r.statusText });
    return;
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop();
    for (const p of parts) if (p.startsWith("data: ")) onEvent(JSON.parse(p.slice(6)));
  }
}
