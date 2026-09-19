#!/usr/bin/env bash
# Live demonstration of the distribution node, on loopback.
#
#   07-distribute/demo.sh DEST [PORT]
#
# Starts the node on 127.0.0.1:PORT (default 8790), lists what it offers, pulls
# every pack into DEST, verifies each one from disk, and stops the node. Pulls
# the 2.84 GB model too, so DEST needs that much free space; delete DEST after.
#
# LOOPBACK. Client and node share this machine, so the MB/s it prints measures
# the software path, not Wi-Fi. A network number needs a second device.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
DEST="${1:?usage: demo.sh DEST [PORT]}"
PORT="${2:-8790}"
NODE="http://127.0.0.1:$PORT"

echo "== distribution node demo, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "   loopback only: node and client on this machine, $NODE"
echo "   python $("$PY" -c 'import sys; print(sys.version.split()[0])'), stdlib only"
echo

"$PY" "$HERE/server.py" --port "$PORT" &
NODE_PID=$!
trap 'kill "$NODE_PID" 2>/dev/null; wait "$NODE_PID" 2>/dev/null || true' EXIT

echo "== what the node offers"
"$PY" "$HERE/client.py" list --node "$NODE" --wait 120
echo

IDS=$(curl -s "$NODE/packs" | "$PY" -c 'import json,sys; print(" ".join(sorted({p["id"] for p in json.load(sys.stdin)["packs"]})))')
for id in $IDS; do
  echo "== pull $id"
  "$PY" "$HERE/client.py" pull "$id" --node "$NODE" --dest "$DEST"
  echo
done

for dir in "$DEST"/*/*/; do
  echo "== verify ${dir#$DEST/}"
  "$PY" "$HERE/client.py" verify "$dir"
  echo
done
