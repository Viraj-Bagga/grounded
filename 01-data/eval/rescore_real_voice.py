#!/usr/bin/env python3
"""Re-score whisper models on Viraj's real voice, against the synthetic set.

    .venv/bin/python 01-data/eval/rescore_real_voice.py

Reads 01-data/eval/audio/lines.tsv and the wavs beside it, written by
01-data/eval/audio/record.sh. Writes the run to 01-data/eval/runs/ and prints
it. Touches llama-server not at all: whisper is its own process.

WHY THIS EXISTS. The model choice of 2026-09-19 was made on macOS `say`
output, which has no room noise, no hesitation and no phone mic. That set
ranks models fairly against the same input and overstates all of them, and it
could not see the part of the base-to-small gap that only shows up on real
audio. This is the measurement that actually decides base.en-q5_1 against
small.en. See 01-data/eval/runs/2026-09-19-whisper-model-choice.txt.

EVERY TRANSCRIPT IS PRINTED IN FULL, not just a WER. Five clips is small
enough that the words are the evidence, and a number you can recompute is not
worth a re-run.
"""

import array
import math
import re
import struct
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIO = ROOT / "01-data" / "eval" / "audio"
RUNS = ROOT / "01-data" / "eval" / "runs"
WHISPER = ROOT / "03-model" / "whisper"
CLI = WHISPER / "bin" / "whisper-cli"

# Every model in the running. base.en-q5_1 is the one that ships.
MODELS = ["base.en-q5_1", "base.en", "small.en-q5_1", "small.en"]

# The words that decide something. A miss here is not a WER point, it is a
# wrong verdict or a guard that does not fire. Constraints 11, 12 and 13.
SAFETY = {
    "preset1": ["not", "half", "hour", "chest", "pressure", "sick", "sweating"],
    "preset2": ["left", "chest", "worse", "breathe", "lean", "forward", "not"],
    "preset3": ["indigestion", "lunch"],
    "extra1":  ["nitroglycerin", "angina", "stent", "two", "ramipril", "blood", "pressure"],
    "extra2":  ["not", "pregnant", "no", "fever", "no", "cough", "left", "right", "three"],
}

# "twenty minutes" and "20 minutes" are the same answer, and whisper prefers
# digits. Normalising both sides keeps the WER about words that matter.
NUMBERS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
           "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
           "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
           "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
           "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
           "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90"}


def words(s):
    s = s.lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9' ]", " ", s)
    return [NUMBERS.get(w, w) for w in s.split()]


def wer(ref, hyp):
    r, h = words(ref), words(hyp)
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (r[i - 1] != h[j - 1]))
    return d[-1][-1], len(r)


def level(wav):
    """(seconds, peak, rms) of a 16 kHz mono WAV, walking the chunk list."""
    d = wav.read_bytes()
    i, at, n = 12, None, 0
    while i + 8 <= len(d):
        cid, size = struct.unpack_from("<4sI", d, i)
        if cid == b"data":
            at, n = i + 8, min(size, len(d) - i - 8)
        i += 8 + size + (size & 1)
    a = array.array("h")
    a.frombytes(d[at:at + n - (n % 2)])
    peak = max(max(a), -min(a)) / 32768
    rms = math.sqrt(sum(x * x for x in a) / len(a)) / 32768
    return n / 32000, peak, rms


def main():
    ref_file = AUDIO / "lines.tsv"
    if not ref_file.exists():
        sys.exit(f"no {ref_file}. Run: bash 01-data/eval/audio/record.sh")
    if not CLI.exists():
        sys.exit("no whisper-cli. Run: bash 03-model/whisper/build.sh")

    cases = []
    for line in ref_file.read_text(encoding="utf-8").strip().split("\n"):
        cid, fname, text = line.split("\t")
        wav = AUDIO / fname
        if wav.exists():
            cases.append((cid, wav, text))
    if not cases:
        sys.exit("lines.tsv has no recorded files beside it")

    models = [m for m in MODELS if (WHISPER / f"ggml-{m}.bin").exists()]
    missing = [m for m in MODELS if m not in models]

    # The page captures at 48 kHz and resamples to 16 kHz mono. Do the same
    # here, so what is scored is what the demo would actually hand whisper.
    prepared = []
    for cid, wav, text in cases:
        out = wav.with_suffix(".16k.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-ac", "1",
                        "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(out)], check=True)
        prepared.append((cid, wav, out, text))

    results = {}
    for m in models:
        results[m] = {}
        for cid, _, wav16, _ in prepared:
            t0 = time.time()
            p = subprocess.run([str(CLI), "-m", str(WHISPER / f"ggml-{m}.bin"),
                                "-f", str(wav16), "-l", "en", "-nt", "-np",
                                "-t", "4", "-ng"], capture_output=True, text=True)
            results[m][cid] = (" ".join(p.stdout.split()), int((time.time() - t0) * 1000))

    out = []
    w = out.append
    w("=" * 80)
    w("WHISPER ON A REAL VOICE: base.en AGAINST small.en")
    w(f"Date:   {date.today().isoformat()}")
    w("Voice:  Viraj, recorded with 01-data/eval/audio/record.sh")
    w("Build:  whisper.cpp v1.9.4 from source, CPU (-ng), 4 threads")
    w("        48 kHz mono capture, resampled to 16 kHz the way the page does")
    w("Against: 01-data/eval/runs/2026-09-19-whisper-model-choice.txt (synthetic)")
    if missing:
        w(f"NOT RUN: {', '.join(missing)} (model file absent)")
    w("=" * 80)
    w("")
    w("THE CLIPS")
    total = 0.0
    for cid, wav, wav16, _ in prepared:
        secs, peak, rms = level(wav16)
        total += secs
        w(f"  {cid:<9} {wav.name:<28} {secs:6.2f} s   peak {peak:.3f}   rms {rms:.5f}")
    w(f"  {'':<9} {'':<28} {total:6.2f} s total")
    w("")
    w("  For comparison, the synthetic set measured peak 0.779 to 0.928 and")
    w("  rms 0.109 to 0.164. A real room should read lower on both. The")
    w("  silence floor in voice.py refuses under peak 0.01.")
    w("")
    w("-" * 80)
    w("1. WORD ERROR RATE, numbers normalised so 'twenty' and '20' agree")
    w("-" * 80)
    w(f"  {'model':<18}{'WER%':>8}{'errs':>7}{'words':>7}{'safety misses':>16}")
    table = []
    for m in models:
        E = N = 0
        miss = []
        for cid, _, _, text in prepared:
            hyp = results[m][cid][0]
            e, n = wer(text, hyp)
            E += e
            N += n
            hw = words(hyp)
            # Normalise the safety words the same way, or "two" is reported
            # missing every time the model correctly writes "2".
            want = [NUMBERS.get(x, x) for x in SAFETY.get(cid, [])]
            for word in want:
                if hw.count(word) < want.count(word):
                    miss.append(f"{cid}:{word}")
        table.append((m, 100 * E / N, E, N, sorted(set(miss))))
    for m, pct, e, n, miss in sorted(table, key=lambda r: r[1]):
        w(f"  {m:<18}{pct:>8.2f}{e:>7}{n:>7}{len(miss):>16}")
        if miss:
            w(f"  {'':<18}{' '.join(miss)}")
    w("")
    w("-" * 80)
    w("2. EVERY TRANSCRIPT, IN FULL. This is the evidence; the table is a summary.")
    w("-" * 80)
    for cid, _, _, text in prepared:
        w("")
        w(f"  [{cid}]  said: {text}")
        for m in models:
            hyp, ms = results[m][cid]
            mark = "  " if hyp.lower().rstrip(".") == text.lower().rstrip(".") else "! "
            w(f"    {mark}{m:<16} {ms:>5} ms  {hyp}")
    w("")
    w("-" * 80)
    w("3. WHAT THIS DECIDES, AND WHAT IT DOES NOT")
    w("-" * 80)
    w("  DECIDES: whether base.en-q5_1 still holds on a real voice in a real")
    w("  room. On the synthetic set it tied small.en at 3.2x less size, 2x less")
    w("  RAM and 2.2x the speed. If small pulls ahead HERE on extra1, which is")
    w("  the clinical vocabulary line, that is the case for spending the 181 MB.")
    w("")
    w("  DOES NOT DECIDE: anything about a phone microphone, any other voice,")
    w("  or any other room. Five clips from one speaker is a sanity check on a")
    w("  choice already made, not a benchmark.")
    w("")
    w("  A MISS IN extra2 IS THE WORST OUTCOME ON THIS PAGE. A dropped 'not' or")
    w("  a swapped left and right is a wrong verdict or a guard that does not")
    w("  fire, and no downstream check can catch it. The composer being")
    w("  editable is what stands between that and the screen.")

    text_out = "\n".join(out) + "\n"
    RUNS.mkdir(parents=True, exist_ok=True)
    dest = RUNS / f"{date.today().isoformat()}-whisper-real-voice.txt"
    dest.write_text(text_out, encoding="utf-8")
    print(text_out)
    print(f"written to {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
