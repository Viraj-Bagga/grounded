#!/usr/bin/env bash
# Usage: ./run-spike.sh [req.json|req-schema.json]
set -euo pipefail

HOST="${HOST:-127.0.0.1:8080}"
REQ="${1:-$(dirname "$0")/req.json}"
OUT="$(mktemp)"

echo "POST http://$HOST/v1/chat/completions  <-  $(basename "$REQ")"
START=$(python3 -c 'import time;print(time.time())')

curl -s "http://$HOST/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d @"$REQ" > "$OUT"

END=$(python3 -c 'import time;print(time.time())')

python3 - "$OUT" "$START" "$END" <<'PY'
import json, sys

path, start, end = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
with open(path) as f:
    raw = f.read()

try:
    d = json.loads(raw)
except json.JSONDecodeError:
    print("non-JSON response:")
    print(raw[:2000])
    sys.exit(1)

if "error" in d:
    print("server error:", json.dumps(d["error"], indent=2))
    sys.exit(1)

t = d.get("timings") or {}
pn, pm = t.get("prompt_n"), t.get("prompt_ms")
en, em = t.get("predicted_n"), t.get("predicted_ms")

print()
print("--- timings ---")
if pm is None:
    print("no timings field returned; read the server stderr instead")
else:
    print(f"prompt tokens      {pn}")
    print(f"prompt eval        {pm:.0f} ms   ({t.get('prompt_per_second', 0):.1f} tok/s)")
    print(f"generated tokens   {en}")
    print(f"generation         {em:.0f} ms   ({t.get('predicted_per_second', 0):.1f} tok/s)")
    print(f"model wall clock   {pm + em:.0f} ms")
print(f"curl wall clock    {(end - start) * 1000:.0f} ms")

msg = d["choices"][0]["message"]
reasoning = msg.get("reasoning_content") or ""
content = msg.get("content") or ""

print()
print("--- reasoning trace ---")
if reasoning:
    print(f"PRESENT, {len(reasoning)} chars")
    print(reasoning[:400] + ("..." if len(reasoning) > 400 else ""))
else:
    print("none returned in reasoning_content")

print()
print("--- content ---")
print(content)

print()
print("--- parse check ---")
stripped = content.strip()
if stripped.startswith("```"):
    stripped = stripped.split("```")[1]
    if stripped.startswith("json"):
        stripped = stripped[4:]
try:
    parsed = json.loads(stripped)
except json.JSONDecodeError as e:
    print("FAIL: not parseable JSON:", e)
    sys.exit(0)

required = ["urgency", "rationale", "red_flags", "next_steps", "citations", "follow_up_questions"]
missing = [k for k in required if k not in parsed]
extra = [k for k in parsed if k not in required]
print("parseable: yes")
print("urgency   :", parsed.get("urgency"))
print("missing   :", missing or "none")
print("extra     :", extra or "none")
print("fenced    :", "yes (bad)" if content.strip().startswith("```") else "no")
PY

rm -f "$OUT"
