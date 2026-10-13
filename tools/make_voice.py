#!/usr/bin/env python3
"""Record Luna's voice clips for Word Snap Showdown.

Uses the open Kokoro text-to-speech model to speak every line in the
<script id="lines"> block of index.html and every word in the game's word
lists, then gives the voice a cute, child-like lift at normal speed and saves small MP3s:

    audio/p/<line key>.mp3   Luna's cheers and instructions
    audio/w/<word>.mp3       each reading word, spoken slowly and clearly
    audio/s/<letter>.mp3     each letter's phonics sound for Robot Talk ("c... a... t")
    audio/n/<number>.mp3     every number from 0 to 100 for the maths games
    audio/m/...              Bahasa Melayu spelling words (w_), their syllables (s_), cheers (c_)
                             and English meanings (e_)
    audio/list.json          every clip, used by sw.js to work offline

Reading words, numbers and letter sounds use British English, the way phonics is
taught in Malaysian schools ("o" as in "on", "a" as in "ant"). Luna's cheers keep
her original voice.

Only clips whose text or voice settings changed are re-recorded.

Setup (once):
    pip install kokoro-onnx soundfile praat-parselmouth scipy
    # the script downloads the model files (about 350 MB) into --model-dir

Run from the repository root:
    python3 tools/make_voice.py [--model-dir DIR] [--force]
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")

VOICE = "af_heart"   # Kokoro's best-rated voice; the highest and most lively of its voices
LANG = "en-us"       # Luna's cheers and instructions
TEACH_LANG = "en-gb" # reading words, numbers and letter sounds: British English, as taught in school
# A "lift" raises the pitch and the voice's tone together (a cute, child-like sound),
# then stretches the clip back to its original length so Luna talks at normal speed.
LINE_LIFT = 1.22     # cheers: about +3.4 semitones
LINE_SPEED = 1.0     # normal speed
WORD_LIFT = 1.18     # reading words: a touch less (+2.9 semitones) so every sound stays crisp
WORD_SPEED = 0.95    # normal speed, a hair slower so single words aren't clipped
SETTINGS_TAG = f"{VOICE}|{LANG}|v3"
TEACH_TAG = f"{VOICE}|{TEACH_LANG}|clean-onset-6"
# At some speeds the model hums a little "uh" before a word ("uh-fox"). Each word is tried at
# these speeds until it starts cleanly, then slowed to WORD_SPEED without changing its pitch.
TRY_SPEEDS = (1.1, 1.0, 1.2, 0.9, 1.3, 0.8, 1.05, 0.95, 1.15, 0.85)
# Names the voice would mispronounce, respelled the way they should sound.
SAY_AS = {"Elyse": "Eleese"}   # "eh-LEES" (the voice reads "Elyse" as "EH-lize")
# Bahasa Melayu words, syllables and cheers: Luna's voice speaking hand-written Malay phonemes
# (pepet "e" as ə, tapped r, final h breathed), a little slower so every syllable is clear.
BM_SPEED = 0.85
BM_TAG = f"{VOICE}|bm-phonemes-1"


ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_word(n):
    if n < 20:
        return ONES[n]
    if n == 100:
        return "one hundred"
    t, o = divmod(n, 10)
    return TENS[t - 2] + ("-" + ONES[o] if o else "")


def spoken(text):
    for name, sound in SAY_AS.items():
        text = re.sub(rf"\b{name}\b", sound, text)
    return text


def read_game():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    lines = json.loads(re.search(r'<script type="application/json" id="lines">(.*?)</script>', html, re.S).group(1))
    cvc = re.search(r'const CVC="([^"]+)"\.split', html).group(1).split()
    sight = re.search(r'const SIGHT="([^"]+)"\.split', html).group(1).split()
    families = json.loads(re.search(r"const FAMILIES=(\[\[.*?\]\]);", html).group(1))
    words = sorted(set(cvc) | set(sight) | {w for fam in families for w in fam})
    bm = json.loads(re.search(r'<script type="application/json" id="bm">(.*?)</script>', html, re.S).group(1))
    return lines, words, bm


def ensure_model(model_dir):
    os.makedirs(model_dir, exist_ok=True)
    for name in MODEL_FILES:
        path = os.path.join(model_dir, name)
        if not os.path.exists(path):
            print(f"Downloading {name} ...", flush=True)
            urllib.request.urlretrieve(MODEL_URL + name, path)
    return [os.path.join(model_dir, n) for n in MODEL_FILES]


def save_mp3(samples, sr, out_path, filters):
    import soundfile as sf
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, samples, sr)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name, "-af", ",".join(filters),
             "-ac", "1", "-ar", "24000", "-c:a", "libmp3lame", "-b:a", "48k", out_path],
            check=True,
        )


def lift_filters(sr, lift, tempo=1.0):
    """Raise pitch and tone by `lift`, keep the length (times `tempo`), trim silence at both ends."""
    trim = "silenceremove=start_periods=1:start_threshold=-45dB"
    return [f"asetrate={int(sr * lift)}", f"aresample={sr}", f"atempo={tempo / lift:.5f}",
            trim, "areverse", trim, "areverse", "adelay=20", "apad=pad_dur=0.05"]


def record(kokoro, text, speed, lift, out_path):
    import numpy as np
    samples, sr = kokoro.create(text, voice=VOICE, speed=speed, lang=LANG)
    samples = samples / max(1e-6, float(np.abs(samples).max())) * 0.89
    save_mp3(samples, sr, out_path, lift_filters(sr, lift))


# ---------- sound analysis (5 ms frames) ----------
HOP = 0.005


def frames(x, sr):
    """Per 5 ms: loudness (dB below the loudest frame), voicing, brightness and the share of energy
    below 450 Hz (high for hums: m, n, l, r and the voice bar of v, z), plus a one-letter class:
    _ silence, s bright hiss, h soft breath, N voiced hum, v voiced vowel-like."""
    import numpy as np
    import parselmouth
    x = np.asarray(x, np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pitch = parselmouth.Sound(x, sr).to_pitch_ac(time_step=HOP, pitch_floor=110, pitch_ceiling=520,
                                                     voicing_threshold=.45)
    n, hop = int(.02 * sr), int(HOP * sr)
    win, fq = np.hanning(n), np.fft.rfftfreq(n, 1 / sr)
    out = []
    for i in range(0, len(x) - n, hop):
        sp = np.abs(np.fft.rfft(x[i:i + n] * win)) ** 2
        tot = sp.sum() + 1e-12
        f0 = pitch.get_value_at_time((i + n / 2) / sr)
        out.append(dict(s=i + n // 2, db=10 * np.log10(tot / n + 1e-12), voiced=f0 == f0,
                        cen=(sp * fq).sum() / tot, hf=sp[fq > 3000].sum() / tot,
                        low=sp[fq < 450].sum() / max(sp[fq < 4000].sum(), 1e-12)))
    top = max(f["db"] for f in out)
    for f in out:
        f["db"] -= top
        f["c"] = "_" if f["db"] < -35 else (("N" if f["low"] > .75 else "v") if f["voiced"]
                                           else ("s" if f["cen"] > 4000 else "h"))
    return out


def vowel_onset(F, start):
    """First frame where the voice opens into a vowel (energy leaves the low hum band for 4 frames)."""
    return next((i for i in range(start, len(F) - 4)
                 if all(F[j]["voiced"] and F[j]["low"] < .6 for j in range(i, i + 4))), None)


def first_sound(F):
    return next(i for i, f in enumerate(F) if f["c"] != "_")


VOICELESS = ("tʃ", "p", "t", "k", "f", "s", "θ", "ʃ", "h")
VOICED_STOPS = ("dʒ", "b", "d", "ɡ")
VOWELS = "aeiouɑɒɔəɛɪʊʌæɐɜ"
CLOSE_VOWELS = ("iː", "uː", "ʊ", "u", "i")   # these stay in the low hum band, so the hum test can't see them


def buzz(f):
    """Voiced and clearly noisy at once (over 5% of the energy above 3 kHz): the sound of v and z."""
    return f["voiced"] and f["hf"] > .05


def onset_problem(F, phonemes, speed=1.0):
    """How badly a word's start is spoiled (0 = clean): a hum before its first consonant ("uh-fox"),
    a voiced stop started with a hum ("mbus"), a murmur between the consonant and the vowel ("h-mm-op"),
    a first hiss too faint or short to hear ("fox" as "ox"), or a z or v said without voice ("zip" as "sip")."""
    ph = phonemes.replace("ˈ", "").replace("ˌ", "").strip()
    first, bad = first_sound(F), 0
    scale = speed / WORD_SPEED   # frames here are this much shorter than in the finished clip
    if ph[:1] in "zv":
        run = best = 0
        for f in F[first:first + 40]:
            run = run + 1 if buzz(f) else 0
            best = max(best, run)
        lead = next((i for i in range(first, min(len(F), first + 40)) if buzz(F[i])), first + 40) - first
        return max(0, 8 - int(best * scale)) + max(0, int(lead * scale) - 4)   # a hum before the buzz sounds like "n-zip"
    c1 = next((c for c in VOICELESS + VOICED_STOPS if ph.startswith(c)), None)
    if not c1:
        return 0
    rest = ph[len(c1):]
    noise = next((i for i in range(first, min(len(F), first + 16)) if F[i]["c"] in "sh"), None)
    start = first
    if c1 in VOICELESS:
        if noise is None:
            return 99
        bad += sum(F[i]["voiced"] for i in range(first, noise))
        start = noise
        if c1 in ("f", "s", "θ", "ʃ", "h"):
            hiss = noise
            while hiss < len(F) and F[hiss]["c"] in "sh":
                hiss += 1
            need = {"h": 7, "f": 12, "θ": 12}.get(c1, 10)
            bad += max(0, need - int((hiss - noise) * scale))
            loud = max(F[i]["db"] for i in range(noise, hiss))
            bad += max(0, int((-28 if c1 == "h" else -24) - loud))   # too faint to hear

    elif noise is not None:
        bad += max(0, sum(F[i]["voiced"] for i in range(first, noise)) - 3)
        start = noise
    if rest[:1] in VOWELS and not rest.startswith(CLOSE_VOWELS):
        on = vowel_onset(F, start)
        if on is None:
            return bad + 50
        bad += max(0, sum(F[i]["c"] == "N" for i in range(start, on)) - 6)
    return bad


def clean_take(kokoro, text):
    """Speak `text` in British English, retrying other speeds until the word starts cleanly."""
    phonemes = kokoro.tokenizer.phonemize(text, TEACH_LANG)
    best = None
    for speed in TRY_SPEEDS:
        x, sr = kokoro.create(text, voice=VOICE, speed=speed, lang=TEACH_LANG)
        bad = onset_problem(frames(x, sr), phonemes, speed)
        if best is None or bad < best[0]:
            best = (bad, x, sr, speed)
        if bad == 0:
            break
    if best[0]:
        print(f"  note: '{text}' still starts with a slight hum (score {best[0]})")
    return best[1], best[2], best[3]


def strengthen_first_hiss(kokoro, text, x, sr):
    """Some words come out with a faint or partly hummed first hiss ("fox" sounds like "ox").
    When that happens, the f, s, th or sh at the start is re-made as clean noise of the same colour
    at a clearly audible level and blended into the vowel; the rest of the word is untouched."""
    import numpy as np
    from scipy.signal import butter, sosfiltfilt
    ph = kokoro.tokenizer.phonemize(text, TEACH_LANG).replace("ˈ", "").replace("ˌ", "")
    if ph[:1] not in ("f", "s", "θ", "ʃ"):
        return x
    F = frames(x, sr)
    first = first_sound(F)
    # the hiss lasts until the vowel starts for good (3 voiced frames in a row that aren't mostly noise)
    end = next((i for i in range(first, len(F) - 3)
                if all(F[j]["voiced"] and F[j]["hf"] < .2 for j in range(i, i + 3))), None)
    if end is None or end - first < 6:
        return x
    region = range(first, end)
    level = max(F[j]["db"] + 10 * np.log10(max(F[j]["hf"], 1e-6)) for j in region)
    hummed = sum(F[j]["voiced"] for j in region)
    if level >= -22 and not hummed:
        return x
    a, b = F[first]["s"] - int(.008 * sr), F[end]["s"] - int(.01 * sr)
    sos = butter(4, 1000, "high", fs=sr, output="sos")
    noise = sosfiltfilt(sos, stretch_noise(sosfiltfilt(sos, x[a:b]), sr, (b - a) / sr))[:b - a]
    # level: as loud as a well-made first hiss ("fan"): about 16 dB below the word's loudest moment
    peak = max(np.sqrt(np.mean(x[i:i + 480] ** 2)) for i in range(0, len(x) - 480, 120))
    noise *= peak * 10 ** (-16 / 20) / max(1e-12, np.sqrt(np.mean(noise ** 2)))
    fade = int(.015 * sr)
    noise[:fade] *= np.linspace(0, 1, fade)
    out = x.copy()
    out[a:b - fade] = noise[:b - a - fade]
    w = np.linspace(1, 0, fade)
    out[b - fade:b] = noise[b - a - fade:] * w + x[b - fade:b] * (1 - w)
    return out


def record_teaching_word(kokoro, text, out_path):
    import numpy as np
    x, sr, speed = clean_take(kokoro, text)
    x = strengthen_first_hiss(kokoro, text, np.asarray(x, np.float64), sr)
    x = x / max(1e-6, float(np.abs(x).max())) * 0.89
    save_mp3(x, sr, out_path, lift_filters(sr, WORD_LIFT, tempo=WORD_SPEED / speed))


# ---------- Bahasa Melayu ----------
def bm_problem(F, phonemes, speed):
    """Like onset_problem, plus Malay word endings: a final h must be a soft breath (not an "s"
    that would turn "tanah" into "tanas"), and a final s must be clearly hissed."""
    ph = phonemes.replace("ˈ", "").replace("ˌ", "").strip(" .")
    bad = onset_problem(F, ph, speed)
    last = max((i for i, f in enumerate(F) if f["voiced"]), default=len(F) - 1)
    tail = [f["c"] for f in F[last + 1:] if f["c"] != "_"]
    scale = speed / BM_SPEED
    if ph.endswith("h"):
        bad += max(0, 6 - int(tail.count("h") * scale)) + 2 * tail.count("s")
    elif ph.endswith("s"):
        bad += max(0, 10 - int(tail.count("s") * scale))
    return bad


def record_bm(kokoro, phonemes, out_path):
    import numpy as np
    best = None
    for speed in TRY_SPEEDS:
        x, sr = kokoro.create(phonemes + ".", voice=VOICE, speed=speed, lang=TEACH_LANG, is_phonemes=True)
        bad = bm_problem(frames(x, sr), phonemes, speed)
        if best is None or bad < best[0]:
            best = (bad, x, sr, speed)
        if bad == 0:
            break
    bad, x, sr, speed = best
    if bad:
        print(f"  note: Malay '{phonemes}' best take still has problem score {bad}")
    x = np.asarray(x, np.float64)
    x = x / max(1e-6, float(np.abs(x).max())) * 0.89
    save_mp3(x, sr, out_path, lift_filters(sr, WORD_LIFT, tempo=BM_SPEED / speed))


# ---------- letter sounds for Robot Talk ----------
# A pure phonics sound can't be asked for on its own (the model mangles lone sounds), so each one is
# cut out of a British-English word at the exact frames where that sound is, then made the right length.
#   vowel  the steady open middle of the vowel (cat, egg, big, hot, tub) -> said for 0.3 s
#   hiss   s, f, h: the noise before the vowel                          -> held ("sss")
#   puff   p, t, k: the burst and breath before the vowel, no "uh", left at its natural length
#   pop    b, d, g, j: the burst with only a trace (45 ms) of vowel so it can be heard
#   hum    m, n, l, r: the voiced part before the vowel opens           -> held ("mmm")
#   buzz   v, z: only the part that is voiced and noisy at once (else it's f, s or a hum)
#   glide  w, y: the glide plus the start of its slide into the vowel
#   coda   x: the "ks" after the vowel in "fox"
SOUND_REV = "s11"
SOUNDS = {
    "a": ("kˈat", "vowel", (0.7,), .30), "e": ("ˈɛɡ", "vowel", (0.85,), .30), "i": ("bˈɪɡ", "vowel", (1.0,), .30),
    "o": ("hˈɒt", "vowel", (0.7,), .30), "u": ("tˈʌb", "vowel", (0.85,), .30),
    "s": ("sˈat", "hiss", (0.9, 1.0, 1.1, 1.2), .40), "f": ("fˈat", "hiss", (0.9, 1.0, 1.1, 1.2), .40),
    "h": ("hˈat", "hiss", (0.9, 1.0, 1.1, 1.2), .16),
    "p": ("pˈat", "puff", (0.9, 1.0, 1.1, 1.2), None), "t": ("tˈap", "puff", (0.9, 1.0, 1.1, 1.2), None),
    "k": ("kˈat", "puff", (0.9, 1.0, 1.1, 1.2), None),
    "b": ("bˈʌt", "pop", (1.15, 1.25, 1.05), None), "d": ("dˈʌk", "pop", (1.15, 1.25, 1.05), None),
    "g": ("ɡˈʌt", "pop", (1.15, 1.25, 1.05), None), "j": ("dʒˈʌɡ", "pop", (1.15, 1.25, 1.05), None),
    "m": ("mˈat", "hum", (0.85, 0.95, 1.05), .38), "n": ("nˈat", "hum", (0.85, 0.95, 1.05), .38),
    "l": ("lˈɛt", "hum", (0.8, 0.9, 1.0), .35), "r": ("ɹˈɛd", "hum", (0.8, 0.9, 1.0), .35),
    "v": ("vˈan", "buzz", (0.85, 1.0, 0.95, 1.05), .34), "z": ("zˈɪp", "buzz", (1.0, 0.85, 0.95, 1.05), .36),
    "w": ("wˈɛt", "glide", (1.05, 0.95, 1.15), .13), "y": ("jˈɛs", "glide", (1.05, 0.95, 1.15), .13),
    "x": ("fˈɒks", "coda", (1.0, 1.15, 0.9), None),
}


def cut_sound(F, rule, sr):
    """Where the sound is in the carrier word: (start sample, end sample, problem or '')."""
    import numpy as np
    first = first_sound(F)
    pad = int(.006 * sr)
    voiced_runs, i = [], 0
    while i < len(F):
        if F[i]["c"] in "Nv":
            j = i
            while j < len(F) and F[j]["c"] in "Nv":
                j += 1
            voiced_runs.append((i, j))
            i = j
        else:
            i += 1
    a, b = max(voiced_runs, key=lambda r: r[1] - r[0])   # the carrier word's vowel
    if rule == "vowel":
        # the open part of the vowel: voiced, loud, energy out of the low hum band; keep its steady middle
        best = (0, 0)
        i = 0
        while i < len(F):
            j = i
            while j < len(F) and F[j]["voiced"] and F[j]["low"] < .6 and F[j]["db"] > -12:
                j += 1
            best = max(best, (j - i, i))
            i = j + 1
        n, a = best
        return F[a + int(.2 * n)]["s"], F[a + int(.85 * n)]["s"], "" if n >= 16 else "vowel too short"
    if rule in ("hiss", "puff"):
        if F[first]["c"] not in "sh" or any(F[i]["voiced"] for i in range(first, first + 4)):
            return 0, 0, "hum before the consonant"
        v = next(i for i in range(first, len(F)) if F[i]["voiced"])
        return F[first]["s"] - pad, F[v - 1]["s"], ""
    if rule == "pop":
        if sum(F[i]["c"] in "Nv" for i in range(first, a)) > 4:
            return 0, 0, "voicing before the burst"
        return F[first]["s"] - pad, F[a]["s"] + int(.045 * sr), ""
    if rule in ("hum", "buzz", "glide"):
        v0 = next(i for i in range(first, len(F)) if F[i]["voiced"])
        on = vowel_onset(F, v0 + 2)
        if on is None:
            return 0, 0, "no vowel found"
        end = on + 6 if rule == "glide" else on - 2
        if end - v0 < 8:
            return 0, 0, "consonant too short"
        if rule == "buzz":   # keep only the stretch that is voiced and noisy at once (a hum alone is m-like)
            best = (0, 0)
            i = v0
            while i < on:
                j = i
                while j < on and buzz(F[j]):
                    j += 1
                best = max(best, (j - i, i))
                i = j + 1
            if best[0] < 12:
                return 0, 0, "too little voiced buzz (would sound like f, s or a hum)"
            return F[best[1]]["s"], F[best[1] + best[0]]["s"], ""
        return F[v0]["s"], F[end]["s"], ""
    if rule == "coda":
        gap = next(i for i in range(b, len(F)) if F[i]["c"] == "_")
        noise = next(i for i in range(gap, len(F)) if F[i]["c"] in "sh")
        end = max(i for i, f in enumerate(F) if f["c"] != "_")
        return F[noise]["s"] - pad, F[end]["s"] + int(.02 * sr), ""
    raise ValueError(rule)


def stretch_noise(x, sr, seconds):
    """A longer hiss with exactly the colour of the real one: fresh noise shaped by the real hiss's
    spectrum (linear prediction). Repeating slices of a short hiss would buzz instead."""
    import numpy as np
    from scipy.linalg import solve_toeplitz
    from scipy.signal import lfilter
    x = np.asarray(x, np.float64)
    order = 24
    w = x * np.hanning(len(x))
    r = np.correlate(w, w, "full")[len(w) - 1:len(w) + order]
    r[0] *= 1.0001
    a = solve_toeplitz(r[:order], -r[1:order + 1])
    shaped = lfilter([1.0], np.r_[1.0, a], np.random.default_rng(7).standard_normal(int(seconds * sr) + 2000))[2000:]
    return shaped * np.sqrt(np.mean(x ** 2)) / max(1e-12, np.sqrt(np.mean(shaped ** 2)))


def stretch_voice(x, sr, seconds):
    """Hold a voiced sound longer without changing its pitch (Praat's overlap-add, at most 3x per pass)."""
    import numpy as np
    import parselmouth
    from parselmouth.praat import call
    x = np.asarray(x, np.float64)
    while len(x) / sr < seconds * .98:
        factor = min(3.0, seconds / (len(x) / sr))
        x = call(parselmouth.Sound(x, sr), "Lengthen (overlap-add)", 90, 600, factor).values[0]
    return x


def stretch_buzz(x, sr, seconds):
    """Hold v or z longer: the voiced low part is lengthened like a hum, and the hiss above 2.5 kHz
    (which overlap-add would smear away, leaving a plain hum) is re-made like s and f."""
    import numpy as np
    from scipy.signal import butter, sosfiltfilt
    x = np.asarray(x, np.float64)
    lo = sosfiltfilt(butter(6, 2500, "low", fs=sr, output="sos"), x)
    hi = x - lo
    voice = stretch_voice(lo, sr, seconds)
    # kept below 9.5 kHz: the pitch lift moves anything higher off the top of the recording
    hiss = sosfiltfilt(butter(6, [2500, 9500], "band", fs=sr, output="sos"), stretch_noise(hi, sr, len(voice) / sr))
    hiss = hiss[:len(voice)]
    # the hiss rises and falls with the voice, so the sound doesn't start or end as a plain "f" or "s"
    win = int(.02 * sr)
    env = np.sqrt(np.convolve(voice ** 2, np.ones(win) / win, "same"))
    hiss *= env / max(1e-12, env.mean())
    hiss *= np.sqrt(np.mean(hi ** 2)) / max(1e-12, np.sqrt(np.mean(hiss ** 2)))
    # let the voice lead: the hiss waits 15 ms, swells in over 50 ms and fades over the last 40 ms, so the sound
    # starts as "vvv"/"zzz" rather than "f"/"s"
    lead, a, b = int(.015 * sr), int(.05 * sr), int(.04 * sr)
    hiss[:lead] = 0
    hiss[lead:lead + a] *= (1 - np.cos(np.linspace(0, np.pi, a))) / 2
    hiss[-b:] *= (1 + np.cos(np.linspace(0, np.pi, b))) / 2
    return voice + hiss


def make_sound(kokoro, letter):
    import numpy as np
    carrier, rule, speeds, length = SOUNDS[letter]
    tried = []
    for speed in speeds:
        x, sr = kokoro.create(carrier + ".", voice=VOICE, speed=speed, lang=TEACH_LANG, is_phonemes=True)
        start, end, problem = cut_sound(frames(x, sr), rule, sr)
        if not problem:
            break
        tried.append(f"speed {speed}: {problem}")
    else:
        raise SystemExit(f"No clean '{letter}' sound in '{carrier}' ({'; '.join(tried)})")
    seg = np.asarray(x[start:end], np.float64)
    if length and len(seg) / sr < length:
        if rule == "puff":   # keep the burst as it is, lengthen the breath after it
            burst = int(.012 * sr)
            seg = np.concatenate([seg[:burst], stretch_noise(seg[burst:], sr, length - burst / sr)])
        elif rule == "hiss":
            seg = stretch_noise(seg, sr, length)
        elif rule == "buzz":
            seg = stretch_buzz(seg, sr, length)
            # lengthening can blow the first few unvoiced milliseconds up into a short "s"; start where the voice does
            F = frames(np.r_[np.zeros(1200), seg, np.zeros(1200)], sr)
            on = next(i for i, f in enumerate(F) if f["voiced"])
            off = max(i for i, f in enumerate(F) if f["voiced"])
            seg = seg[max(0, F[on]["s"] - 1200 - int(.005 * sr)):F[off]["s"] - 1200 + int(.01 * sr)]
        else:
            seg = stretch_voice(seg, sr, length)
    return seg, sr


def record_sound(kokoro, letter, out_path):
    import numpy as np
    seg, sr = make_sound(kokoro, letter)
    seg = seg / max(1e-6, float(np.abs(seg).max())) * 0.85
    rule = SOUNDS[letter][1]
    fade_out = .012 if rule in ("puff", "pop") else .04
    fade_in = .04 if letter == "h" else .006   # h is a soft breath, not a pop
    save_mp3(seg, sr, out_path, [f"asetrate={int(sr * WORD_LIFT)}", f"aresample={sr}", f"atempo={1 / WORD_LIFT:.5f}",
                                 f"afade=t=in:d={fade_in}", "areverse", f"afade=t=in:d={fade_out}", "areverse",
                                 "adelay=20", "apad=pad_dur=0.04"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-dir", default=os.path.expanduser("~/.cache/kokoro"))
    ap.add_argument("--force", action="store_true", help="re-record every clip")
    args = ap.parse_args()

    lines, words, bm = read_game()
    # (key, text, signature extras, how to record)
    jobs = [("p/" + k, spoken(t), f"{SETTINGS_TAG}|{LINE_SPEED}|{LINE_LIFT}", "line") for k, t in lines.items()]
    jobs += [("w/" + w, w + ".", f"{TEACH_TAG}|{WORD_SPEED}|{WORD_LIFT}", "teach") for w in words]
    jobs += [("n/" + str(n), number_word(n) + ".", f"{TEACH_TAG}|{WORD_SPEED}|{WORD_LIFT}", "teach") for n in range(101)]
    # Bahasa Melayu: m/w_<word>, m/s_<syllable>, m/c_<cheer> in Malay; m/e_<word> is its English meaning
    bm_tag = f"{BM_TAG}|{BM_SPEED}|{WORD_LIFT}"
    jobs += [("m/w_" + d["w"], d["ph"], bm_tag, "bm") for d in bm["words"]]
    jobs += [("m/s_" + syl, ph, bm_tag, "bm") for syl, ph in bm["syllables"].items()]
    jobs += [("m/c_" + c, ph, bm_tag, "bm") for c, (ph, _) in bm["cheers"].items()]
    jobs += [("m/e_" + d["w"], d["en"] + ".", f"{TEACH_TAG}|{WORD_SPEED}|{WORD_LIFT}", "teach") for d in bm["words"] if d.get("en")]

    list_path = os.path.join(ROOT, "audio", "list.json")
    old = {}
    if os.path.exists(list_path):
        old = json.load(open(list_path)).get("clips", {})

    from kokoro_onnx import Kokoro
    kokoro = Kokoro(*ensure_model(args.model_dir))

    clips, made = {}, 0
    for key, text, tag, how in jobs:
        sig = hashlib.sha1(f"{tag}|{text}".encode()).hexdigest()[:12]
        out = os.path.join(ROOT, "audio", key + ".mp3")
        if args.force or old.get(key) != sig or not os.path.exists(out):
            if how == "line":
                record(kokoro, text, LINE_SPEED, LINE_LIFT, out)
            elif how == "bm":
                record_bm(kokoro, text, out)
            else:
                record_teaching_word(kokoro, text, out)
            made += 1
        clips[key] = sig

    for letter, recipe in SOUNDS.items():
        key = "s/" + letter
        sig = hashlib.sha1(f"{TEACH_TAG}|{SOUND_REV}|{WORD_LIFT}|{recipe}".encode()).hexdigest()[:12]
        out = os.path.join(ROOT, "audio", key + ".mp3")
        if args.force or old.get(key) != sig or not os.path.exists(out):
            record_sound(kokoro, letter, out)
            made += 1
        clips[key] = sig

    wanted = {os.path.join(ROOT, "audio", k + ".mp3") for k in clips}
    for sub in ("p", "w", "s", "n", "m"):
        folder = os.path.join(ROOT, "audio", sub)
        for name in os.listdir(folder) if os.path.isdir(folder) else []:
            path = os.path.join(folder, name)
            if path not in wanted:
                os.remove(path)

    version = hashlib.sha1(json.dumps(clips, sort_keys=True).encode()).hexdigest()[:8]
    json.dump({"voice": SETTINGS_TAG, "teach": TEACH_TAG, "version": version, "clips": clips},
              open(list_path, "w"), indent=1, sort_keys=True)
    stamp_version(version)
    print(f"{len(clips)} clips ({len(lines)} lines, {len(words)} words); recorded {made}; voice version {version}.")


def stamp_version(version):
    """Point the game and the offline cache at this set of clips, so tablets drop old recordings."""
    for name, pattern, repl in (
        ("index.html", r'const VOICE_VERSION="[^"]*";', f'const VOICE_VERSION="{version}";'),
        ("sw.js", r'const VOICE = "word-snap-[^"]*";', f'const VOICE = "word-snap-{version}";'),
    ):
        path = os.path.join(ROOT, name)
        text = open(path, encoding="utf-8").read()
        new, n = re.subn(pattern, repl, text)
        if n != 1:
            raise SystemExit(f"Could not find the version line in {name}")
        open(path, "w", encoding="utf-8").write(new)


if __name__ == "__main__":
    sys.exit(main())
