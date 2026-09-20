#!/usr/bin/env python3
"""Local speech to text for the composer. whisper.cpp, on this machine, offline.

WHAT THIS IS FOR, AND WHAT IT IS NOT FOR. The transcript goes into the composer
as editable text. It is never sent to triage on its own. A misheard symptom is
a wrong verdict, so the person reads what the system heard and fixes it before
assessing. That is the whole safety argument for voice on a medical tool, and
it is why this module returns text and never calls the model.

THE MODEL. ggml-base.en-q5_1, 57 MB, chosen by measurement over five others on
13 clips and 6 voices: 01-data/eval/runs/2026-09-19-whisper-model-choice.txt.
tiny is excluded because it turned "angina" into "anginone" and dropped
"stent". small.en costs 3.2x the size and 2x the RAM for no measured gain on
that set. Set WHISPER_MODEL to re-test in one env var.

CPU, NOT METAL. -ng. Metal is 2.3x faster but CPU is already under a second,
and CPU is the condition every other number in this project is quoted in.

ONE PROCESS PER TRANSCRIPTION, NOT A RESIDENT MODEL. Measured: loading the
model costs 46 ms, against 260 MB resident. There is no case for holding that
next to a 3 GB LLM to save 46 ms, so the memory is gone the moment this
returns. The constraint asked for measurement before choosing, and this is it.
"""

import array
import os
import re
import struct
import sys
import subprocess
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

BIN = Path(os.environ.get("WHISPER_BIN") or ROOT / "03-model" / "whisper" / "bin" / "whisper-cli")
MODEL = Path(os.environ.get("WHISPER_MODEL")
             or ROOT / "03-model" / "whisper" / "ggml-base.en-q5_1.bin")
THREADS = int(os.environ.get("WHISPER_THREADS") or 4)

# whisper.cpp wants exactly this and the page produces exactly this, by
# resampling in the browser. Anything else is rejected rather than coerced:
# a server that guesses at an audio format is a server that transcribes noise.
RATE, CHANNELS, BITS = 16000, 1, 16
BYTES_PER_SECOND = RATE * CHANNELS * BITS // 8
MAX_SECONDS = 60          # the composer stops recording well before this
MIN_SECONDS = 0.2         # an accidental tap, not an utterance

# WHISPER INVENTS SENTENCES OUT OF NON-SPEECH. Measured 2026-09-19 with this
# model: digital silence came back as "you", and Chrome's test beep came back
# as "Oh, my God. Oh, it can't get us back in the fight." Room noise comes back
# as "(crickets chirping)" and the like, which clean() already drops, but a
# bare hallucinated sentence has nothing about it to catch.
#
# A peak floor catches the case that actually happens: a muted microphone, or
# one that captured nothing. 0.01 is about 78x below the quietest clip in the
# model-choice set (p3, peak 0.779) and well above digital silence and the
# gaussian noise floors tested, so it cannot refuse a quiet voice. It does NOT catch a hallucination from real
# room noise, and nothing here claims to. What catches that is the person
# reading the box before they send it, which is the design.
SILENCE_PEAK = 0.01

# One at a time. Two mic taps must not put two whisper processes and 520 MB
# against llama-server while a compare assessment is decoding on both slots.
_lock = threading.Lock()


class Bad(ValueError):
    """The audio is not what this can transcribe. The message reaches the page."""


def available():
    """(ok, detail). Checked at startup so the page can hide the button with a
    reason instead of offering one that fails on the first tap."""
    if not BIN.exists():
        return False, f"whisper-cli not built: run bash 03-model/whisper/build.sh"
    if not MODEL.exists():
        return False, f"{MODEL.name} not downloaded: run bash 03-model/whisper/build.sh"
    return True, f"{MODEL.name}, on this machine"


def wav_info(data):
    """Validate a canonical PCM WAV. Returns (seconds, peak) where peak is the
    loudest sample as a fraction of full scale.

    Walks the chunk list rather than assuming fmt at 12 and data at 36, because
    a browser or a recorder is free to put a LIST chunk in between.
    """
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise Bad("that is not a WAV file")
    fmt = None
    data_len = None
    data_at = None
    i = 12
    while i + 8 <= len(data):
        cid, size = struct.unpack_from("<4sI", data, i)
        body = i + 8
        if cid == b"fmt " and size >= 16:
            fmt = struct.unpack_from("<HHIIHH", data, body)
        elif cid == b"data":
            # A truncated final chunk is the normal shape of a stopped
            # recording, so trust the bytes present over the declared size.
            data_len = min(size, len(data) - body)
            data_at = body
        i = body + size + (size & 1)
    if fmt is None or data_len is None:
        raise Bad("that WAV has no fmt or data chunk")
    audio_format, channels, rate, _, _, bits = fmt
    if audio_format != 1 or bits != BITS:
        raise Bad("the audio must be 16-bit PCM")
    if channels != CHANNELS or rate != RATE:
        raise Bad(f"the audio must be {RATE} Hz mono, not {rate} Hz with {channels} channels")
    seconds = data_len / BYTES_PER_SECOND
    if seconds > MAX_SECONDS:
        raise Bad(f"that is {seconds:.0f} seconds; keep it under {MAX_SECONDS}")
    if seconds < MIN_SECONDS:
        raise Bad("that was too short to hear anything")
    # max() over an array is a C loop, so this is a few ms even at 60 seconds.
    pcm = array.array("h")
    pcm.frombytes(data[data_at:data_at + data_len - (data_len % 2)])
    if sys.byteorder == "big":
        pcm.byteswap()
    peak = (max(max(pcm), -min(pcm)) / 32768) if pcm else 0.0
    return round(seconds, 2), peak


# whisper marks non-speech in square brackets: [BLANK_AUDIO], [MUSIC]. None of
# it is a symptom, and a composer filled with [BLANK_AUDIO] reads as a bug.
_BRACKETED = re.compile(r"\[[^\]]*\]")
_ONLY_PARENS = re.compile(r"^(?:\s*\([^)]*\)\s*)+$")


def clean(raw):
    text = " ".join(_BRACKETED.sub(" ", raw).split())
    return "" if _ONLY_PARENS.match(text) else text


def transcribe(wav_bytes):
    """{text, ms, seconds, model}. Raises Bad on audio this cannot take."""
    seconds, peak = wav_info(wav_bytes)
    ok, detail = available()
    if not ok:
        raise Bad(detail)
    # Do not hand silence to a model that will make something up out of it.
    if peak < SILENCE_PEAK:
        raise Bad("nothing reached the microphone. Check it is not muted, then tap again")
    with _lock:
        t0 = time.time()
        # A real file, not a pipe: whisper-cli seeks its input.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            f.write(wav_bytes)
            f.flush()
            try:
                p = subprocess.run(
                    [str(BIN), "-m", str(MODEL), "-f", f.name,
                     "-l", "en", "-nt", "-np", "-t", str(THREADS), "-ng"],
                    capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                raise Bad("transcription timed out")
        if p.returncode != 0:
            raise Bad(f"whisper-cli failed: {(p.stderr or '').strip()[:200]}")
        return {"text": clean(p.stdout), "ms": int((time.time() - t0) * 1000),
                "seconds": seconds, "model": MODEL.stem.replace("ggml-", "")}


# ---------------------------------------------------------------- provenance
#
# WHY THE SERVER REMEMBERS, RATHER THAN TRUSTING WHAT THE PAGE SENDS BACK.
# The SOAP note says whether the symptoms were spoken and whether the person
# corrected what was heard. A clinician reading that is entitled to a fact, not
# a claim the page made about itself. So the transcript is kept here for as
# long as it takes to send the turn, and "edited" is decided by comparing the
# text that actually arrived against the text this machine produced.
#
# Bounded and in memory only: provenance for a turn in flight, not a record of
# what anyone said. It does not survive a restart, and an id that has fallen
# off the end simply means the turn carries no provenance, which is honest.
_RECENT = OrderedDict()
_RECENT_MAX = 32
_recent_lock = threading.Lock()


def remember(result):
    tid = uuid.uuid4().hex[:12]
    with _recent_lock:
        _RECENT[tid] = result
        while len(_RECENT) > _RECENT_MAX:
            _RECENT.popitem(last=False)
    return tid


def provenance(tid, text):
    """What to store on a turn, or None if this turn was typed.

    `edited` is computed here, not reported: it is whether the text that
    arrived differs from the text this machine heard, ignoring only whitespace.
    """
    if not tid:
        return None
    with _recent_lock:
        r = _RECENT.get(tid)
    if not r:
        return None
    said = " ".join((r["text"] or "").split())
    sent = " ".join((text or "").split())
    return {"ms": r["ms"], "seconds": r["seconds"], "model": r["model"],
            "edited": sent.casefold() != said.casefold(), "heard": said}
