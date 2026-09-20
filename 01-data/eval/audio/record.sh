#!/usr/bin/env bash
# Record the real-voice set for the whisper re-score. Nothing to install:
# ffmpeg is already here and reads the built-in microphone through
# avfoundation. Recording touches llama-server not at all.
#
#   bash 01-data/eval/audio/record.sh
#
# It prints a line, you press Enter, you read it, you press Enter again. Five
# lines. Re-run it any time; it asks before overwriting a file you already did,
# so a single bad take costs one line and not the set.
#
# WHY 48 kHz MONO AND NOT 16 kHz. MediaRecorder in the browser captures at
# 48 kHz and the page resamples to the 16 kHz whisper wants. Recording at 48
# and resampling in the scorer walks the same path the demo walks, and keeps
# the original in case it is ever wanted at full rate.
#
# WHAT THE FIVE LINES ARE FOR. 1 to 3 are the demo presets, word for word:
# they say whether voice works on a real voice for the thing judges will see.
# 4 and 5 decide base.en against small.en, which the presets cannot: every
# difference measured between those models on 2026-09-19 was clinical
# vocabulary (ramipril, angina, stent), and no preset contains any. 5 is the
# negation and laterality set, which is the failure that would matter most,
# because a flipped negation flips a guard.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEVICE="${MIC:-:0}"

command -v ffmpeg >/dev/null || { echo "ffmpeg not found"; exit 1; }

# id, filename, the words to read. The reference is written from THIS table, so
# what gets scored is always what you were asked to say.
IDS=(preset1 preset2 preset3 extra1 extra2)
FILES=(preset1-crushing.wav preset2-pleuritic.wav preset3-indigestion.wav
       extra1-medications.wav extra2-negations.wav)
LINES=(
"Heavy pressure in the middle of my chest that has not let up for almost half an hour. I feel sick and I am sweating."
"Sharp pain in my left chest, worse when I breathe in. It eases if I sit up and lean forward. Walking around does not change it."
"A bit of indigestion after lunch, nothing much."
"I take nitroglycerin for my angina and I had a stent fitted two years ago. I am also on ramipril for my blood pressure."
"I am not pregnant. No fever, no cough. It is not the left side, it is the right side, and it started three days ago."
)

cat <<'EOF'

  RECORDING THE REAL-VOICE SET
  ----------------------------
  Read each line the way you would actually say it. Do not enunciate for the
  microphone and do not repair a stumble: a hesitation is data, because the
  synthetic set had none and that is the whole reason for doing this.

  Record where you will be demoing. The room noise is the point.

  macOS will ask for microphone permission the first time. Allow it.

EOF
printf "  Press Enter to begin. "
read -r _

done_n=0
for i in "${!IDS[@]}"; do
  out="$HERE/${FILES[$i]}"
  if [ -f "$out" ]; then
    printf "\n  %d/5  %s already exists. Redo it? [y/N] " "$((i+1))" "${FILES[$i]}"
    read -r ans
    case "$ans" in y|Y) ;; *) echo "      kept"; done_n=$((done_n+1)); continue;; esac
  fi
  printf "\n  %d/5  READ THIS:\n\n      %s\n\n" "$((i+1))" "${LINES[$i]}"
  printf "      Press Enter to start recording. "
  read -r _
  ffmpeg -hide_banner -loglevel error -f avfoundation -i "$DEVICE" \
    -ac 1 -ar 48000 -c:a pcm_s16le -y "$out" >/dev/null 2>"$HERE/.ff.log" &
  pid=$!
  sleep 0.4
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "      RECORDING FAILED:"; sed 's/^/        /' "$HERE/.ff.log"
    echo "        If it mentions permission, allow the microphone for this app and re-run."
    exit 1
  fi
  printf "      RECORDING. Read the line, then press Enter. "
  read -r _
  kill -INT "$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out" 2>/dev/null)
  if [ -z "$d" ]; then
    echo "      that file did not come out. Re-run the script to redo it."
  else
    printf "      saved %s, %.2f s\n" "${FILES[$i]}" "$d"
    done_n=$((done_n+1))
  fi
done
rm -f "$HERE/.ff.log"

# The reference transcript, written from the table above so it cannot drift
# from what you were actually asked to read.
ref="$HERE/lines.tsv"
: > "$ref"
for i in "${!IDS[@]}"; do
  printf "%s\t%s\t%s\n" "${IDS[$i]}" "${FILES[$i]}" "${LINES[$i]}" >> "$ref"
done

echo
echo "  $done_n of 5 recorded, in $HERE"
ls -1 "$HERE"/*.wav 2>/dev/null | while read -r f; do
  printf "    %-28s %6.2f s  %s\n" "$(basename "$f")" \
    "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")" \
    "$(ffprobe -v error -show_entries stream=sample_rate,channels -of csv=p=0 "$f")"
done
echo
echo "  Reference written to $(basename "$ref"). Tell Claude and it will re-score"
echo "  base.en-q5_1 against small.en-q5_1 and small.en on these."
