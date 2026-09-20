// Voice input for the composer. whisper.cpp, on this machine, offline.
//
// THE TRANSCRIPT GOES IN THE COMPOSER AND NOWHERE ELSE. It is never sent
// straight to triage. The person reads what the system heard and fixes it
// before assessing, because a misheard symptom is a wrong verdict. Nothing in
// this file calls the model or starts an assessment.
//
// WHY THE AUDIO IS CONVERTED HERE AND NOT ON THE SERVER. MediaRecorder gives
// webm/opus at 48 kHz; whisper.cpp wants 16 kHz mono PCM. Doing it in the page
// means the demo server needs no ffmpeg, and it is what a React Native
// recorder would hand over directly. Verified 2026-09-19: transcripts through
// this path are byte-identical to transcribing the original WAV.
//
// SECURE CONTEXT. getUserMedia exists only on a secure origin. 127.0.0.1
// counts; a plain http address on the wifi does not, and there
// navigator.mediaDevices is not merely refused, it is undefined. Measured, see
// 01-data/eval/runs/2026-09-19-whisper-model-choice.txt section 5. So over
// --lan the button is absent with a reason rather than present and broken.

const RATE = 16000;
const MAX_SECONDS = 55;          // the server refuses over 60; this leaves room

// The server writes its refusals lowercase and unpunctuated so they read
// inside a sentence. On their own line under the composer they need both.
const sentence = s => {
  s = String(s || "").trim();
  return s ? s[0].toUpperCase() + s.slice(1) + (/[.!?]$/.test(s) ? "" : ".") : "";
};

// Same rule the server uses to decide "edited", so the line under the composer
// and the SOAP note can never disagree: collapse whitespace, ignore case.
const norm = s => (s || "").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
export const wasEdited = (sent, heard) => norm(sent) !== norm(heard);

// Why the microphone is not offered here. One reason, in the page's own voice.
export function micBlocked(health) {
  // ONE SHORT LINE. Viraj's call 2026-09-19: two lines about browser secure
  // contexts is the user reading our implementation notes. Where it works is
  // the part they can act on; why is in voice.py and the build log.
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia)
    return "Voice only works on the laptop, not over the wifi.";
  if (health && health.remote)
    return "Voice runs on the laptop, so the microphone is only offered there.";
  if (health && health.voice && !health.voice.ok)
    return `Voice is off: ${health.voice.detail}`;
  return null;
}

// --------------------------------------------------------- audio conversion

function toWav(channel) {
  const n = channel.length;
  const buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const tag = (o, t) => { for (let i = 0; i < t.length; i++) v.setUint8(o + i, t.charCodeAt(i)); };
  tag(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); tag(8, "WAVEfmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, RATE, true); v.setUint32(28, RATE * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  tag(36, "data"); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) {
    const x = Math.max(-1, Math.min(1, channel[i]));
    v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true);
  }
  return new Uint8Array(buf);
}

async function blobToWavBase64(blob) {
  const ac = new AudioContext();
  let decoded;
  try { decoded = await ac.decodeAudioData(await blob.arrayBuffer()); }
  finally { ac.close(); }
  const off = new OfflineAudioContext(1, Math.ceil(decoded.duration * RATE), RATE);
  const src = off.createBufferSource();
  src.buffer = decoded; src.connect(off.destination); src.start();
  const out = await off.startRendering();
  const bytes = toWav(out.getChannelData(0));
  let s = "";
  for (let i = 0; i < bytes.length; i += 8192) s += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(s);
}

// ------------------------------------------------------------------ recorder

export class Recorder {
  constructor(onTick, onStop) { this.onTick = onTick; this.onStop = onStop; this.rec = null; }

  get recording() { return !!this.rec; }
  get elapsed() { return this.rec ? (performance.now() - this.startedAt) / 1000 : 0; }

  async start() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const chunks = [];
    const rec = new MediaRecorder(stream);
    rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = () => {
      // Release the device, which is what turns the browser's recording
      // indicator off. On a medical tool that light going out is the only
      // proof the person gets that it stopped listening.
      stream.getTracks().forEach(t => t.stop());
      clearInterval(this.timer);
      this.rec = null;
      this.onStop(chunks.length ? new Blob(chunks, { type: rec.mimeType }) : null);
    };
    this.rec = rec;
    this.startedAt = performance.now();
    rec.start();
    this.timer = setInterval(() => {
      if (this.elapsed >= MAX_SECONDS) this.stop();
      else this.onTick(this.elapsed);
    }, 200);
  }

  stop() { if (this.rec && this.rec.state !== "inactive") this.rec.stop(); }
}

// The label on the button while it is recording: seconds up, then seconds left
// once the cap is close enough to matter.
export function recordingLabel(elapsed) {
  const left = Math.ceil(MAX_SECONDS - elapsed);
  return left <= 10 ? `${left}s left` : `${Math.floor(elapsed)}s`;
}

// --------------------------------------------------------------- the request

export async function transcribe(blob) {
  const audio = await blobToWavBase64(blob);
  const r = await fetch("/api/transcribe", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audio }),
  });
  let body = null;
  try { body = await r.json(); } catch { /* not JSON */ }
  if (!r.ok) throw new Error(sentence((body && body.error) || "transcription failed"));
  return body;                       // { id, text, ms, seconds, model }
}

// What getUserMedia refusals mean, said in a way a person can act on.
export function micError(e) {
  const n = e && e.name;
  if (n === "NotAllowedError" || n === "SecurityError")
    return "The browser blocked the microphone. Allow it for this page, then tap again.";
  if (n === "NotFoundError" || n === "DevicesNotFoundError")
    return "No microphone found on this machine.";
  if (n === "NotReadableError")
    return "Something else is using the microphone.";
  return (e && e.message) || "The microphone could not be started.";
}
