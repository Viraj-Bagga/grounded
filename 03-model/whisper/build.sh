#!/usr/bin/env bash
# Build whisper.cpp for the voice composer, and fetch the model.
#
#   bash 03-model/whisper/build.sh
#
# Puts a self-contained whisper-cli in 03-model/whisper/bin/ and the model
# beside it, the same way the base GGUF lives in 03-model/base/ and not in a
# scratch dir. Both are gitignored. This script is the reproducible part.
#
# WHY FROM SOURCE AND NOT `brew install whisper.cpp`. Measured 2026-09-19:
# `brew install --dry-run whisper.cpp` reports "Would upgrade 3 dependencies",
# and two of them are llama.cpp and ggml, which are the installed 0.4.0 and
# 0.23.0 that every latency number in the build log was measured on. Upgrading
# llama.cpp puts --jinja, -np 2 and nemotron_h support back in play four days
# from judging to buy nothing. A source build touches no installed formula.
#
# WHY base.en-q5_1. Six models measured on 13 clips and 6 voices,
# 01-data/eval/runs/2026-09-19-whisper-model-choice.txt. It has the lowest WER
# on that set at 57 MB, and against small.en-q5_1 it is 3.2x smaller, 2x less
# RAM and 2.2x faster for no measured accuracy cost. tiny is excluded because
# it turned "angina" into "anginone" and dropped "stent", which are words this
# corpus is made of. Override with WHISPER_MODEL_NAME to re-test.
set -euo pipefail

VERSION="v1.9.4"
MODEL="${WHISPER_MODEL_NAME:-ggml-base.en-q5_1.bin}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/src"
BIN="$HERE/bin"

command -v cmake >/dev/null || { echo "need cmake; try /opt/local/bin or brew install cmake"; exit 1; }

# ---------------------------------------------------------------- 1. source
if [ ! -d "$SRC" ]; then
  echo "==> cloning whisper.cpp $VERSION"
  git clone --depth 1 --branch "$VERSION" https://github.com/ggml-org/whisper.cpp.git "$SRC"
else
  echo "==> reusing $SRC"
fi

# ---------------------------------------------------------------- 2. build
if [ ! -x "$SRC/build/bin/whisper-cli" ]; then
  echo "==> building (a few minutes)"
  cmake -S "$SRC" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release >/dev/null
  cmake --build "$SRC/build" -j"$(sysctl -n hw.ncpu)" --config Release >/dev/null
fi

# ------------------------------------------------------- 3. vendor the binary
# The build bakes an absolute LC_RPATH pointing at the build tree, so a copied
# binary cannot find its dylibs. Repoint it at @executable_path and re-sign:
# arm64 macOS refuses to run a binary whose signature install_name_tool broke.
echo "==> vendoring into bin/"
mkdir -p "$BIN"
cp "$SRC/build/bin/whisper-cli" "$BIN/"
cp "$SRC"/build/bin/libwhisper*.dylib "$SRC"/build/bin/libggml*.dylib "$BIN/"
OLD_RPATH="$(otool -l "$BIN/whisper-cli" | awk '/LC_RPATH/{f=1} f&&/ path /{print $2; exit}')"
[ -n "$OLD_RPATH" ] && install_name_tool -delete_rpath "$OLD_RPATH" "$BIN/whisper-cli" 2>/dev/null || true
install_name_tool -add_rpath "@executable_path" "$BIN/whisper-cli"
codesign --force -s - "$BIN/whisper-cli" 2>/dev/null || true

# ---------------------------------------------------------------- 4. model
if [ ! -f "$HERE/$MODEL" ]; then
  echo "==> downloading $MODEL"
  curl -fL --progress-bar -o "$HERE/$MODEL" \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL"
fi

# ------------------------------------------------------- 5. prove it, once
# Downloaded is not verified. This says a sentence, transcribes it, and checks
# the words came back, with the vendored binary and no build tree on the path.
echo "==> self-test"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
say -v Samantha -o "$TMP/t.wav" --data-format=LEI16@16000 --channels=1 \
  "Heavy pressure in the middle of my chest for twenty minutes."
GOT="$("$BIN/whisper-cli" -m "$HERE/$MODEL" -f "$TMP/t.wav" -l en -nt -np -t 4 -ng 2>/dev/null \
  | tr '[:upper:]' '[:lower:]' | tr -d '\n')"
echo "    heard: $GOT"
case "$GOT" in
  *"pressure in the middle of my chest"*) echo "    PASS" ;;
  *) echo "    FAIL: did not transcribe the test sentence"; exit 1 ;;
esac
echo
echo "whisper-cli : $BIN/whisper-cli"
echo "model       : $HERE/$MODEL  ($(du -h "$HERE/$MODEL" | cut -f1))"
