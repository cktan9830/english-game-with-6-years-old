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
# Bahasa Melayu has its own sounds, so it gets its own voice and its own letter sounds (see the
# Bahasa Melayu section below). Kokoro has no Malay voice; its Hindi voice is the closest match:
# p, t, k without the puff of air English adds, pure vowels and a true pepet "e". It speaks
# hand-written Malay phonemes, a little slower so every syllable is clear.
BM_VOICE = "hf_alpha"
BM_SPEED = 0.85
BM_TAG = f"{BM_VOICE}|bm-phonemes-4"


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
        below4k = max(sp[fq < 4000].sum(), 1e-12)
        out.append(dict(s=i + n // 2, db=10 * np.log10(tot / n + 1e-12), voiced=f0 == f0,
                        cen=(sp * fq).sum() / tot, hf=sp[fq > 3000].sum() / tot,
                        low=sp[fq < 450].sum() / below4k,
                        # share in the vowel-formant band: near zero during a hum (m, n, a voice bar)
                        mid=sp[(fq > 500) & (fq < 2500)].sum() / below4k))
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


# ---------- Bahasa Melayu ----------
# Malay is not read with English sounds: a is always "a" as in "ada", e is the pepet of "emak" (or the
# taling of "merah"), i, o and u are pure, c is "ch", g is always hard, r is rolled, a final h is a soft
# breath, p, t and k have no puff of air, and ng, ny, sy and kh are single sounds.
#
# The Hindi voice has two habits that would spoil a word: it often hums before the first consonant
# ("mm-benih", "uh-tanah"), and it sometimes lets out a tiny echo vowel after a final consonant
# ("lembut-uh"). Every take is checked for both; the hum and the echo are cut off, and of all the
# speeds tried, the take with the fewest remaining problems is kept.
BM_VOWELS = "aeiouəɨɛɔ"
BM_VOICELESS = ("tʃ", "p", "t", "k", "c", "s", "ʃ", "f", "x", "h", "ʔ")
BM_EITHER = ("dʒ", "ɟ", "b", "d", "ɡ", "z")   # voiced in Malay, but the voice sometimes lets them go voiceless


def bm_plain(phonemes):
    return phonemes.replace("ˈ", "").replace("ˌ", "").replace("ː", "").strip(" .")


def bm_units(phonemes):
    p, out, i = bm_plain(phonemes), [], 0
    while i < len(p):
        u = p[i:i + 2] if p[i:i + 2] in ("tʃ", "dʒ") else p[i]
        out.append(u)
        i += len(u)
    return out


def bm_first(phonemes):
    """The first sound of a Malay phoneme string and what kind of sound it is."""
    c = bm_units(phonemes)[0]
    kind = ("stop" if c in ("p", "t", "k") else "aff" if c in ("tʃ", "c") else
            "vstop" if c in ("b", "d", "ɡ", "ɟ", "dʒ") else "fric" if c in ("s", "ʃ", "f", "x") else
            "h" if c == "h" else "z" if c in ("z", "v") else "vowel" if c in BM_VOWELS else "son")
    return c, kind


def bm_islands(phonemes):
    """How many separate voiced stretches the word should have: (fewest, most). Voiceless sounds split
    the voicing; b, d, g, j and z may or may not."""
    lo = hi = 0
    in_lo = in_hi = False
    for u in bm_units(phonemes):
        if u in BM_VOICELESS:
            in_lo = in_hi = False
            continue
        if u in BM_EITHER:
            in_hi = False
            continue
        if not in_lo:
            lo, in_lo = lo + 1, True
        if not in_hi:
            hi, in_hi = hi + 1, True
    return lo, hi


def vowelish(f):
    return f["voiced"] and f["mid"] >= .06 and f["db"] > -20


def noisy(f):
    return not f["voiced"] and f["c"] in "sh"


def voiced_runs(F, start=0, floor=-25, merge=1, least=3):
    """Stretches of voicing louder than `floor` dB, joining gaps of up to `merge` frames."""
    runs = []
    for i in range(start, len(F)):
        if F[i]["voiced"] and F[i]["db"] > floor:
            if runs and i - runs[-1][1] <= merge:
                runs[-1][1] = i + 1
            else:
                runs.append([i, i + 1])
    return [r for r in runs if r[1] - r[0] >= least]


def bm_burst(F, s0):
    """For a word starting with b, d, g or j: (release frame, vowel frame). The voice often hums
    loudly before them, so the release is found from the vowel backwards: the quietest moment
    between the hum and the vowel's peak is the closed mouth, and the steepest rise after it is the
    release (for j, where its friction starts)."""
    top = max(f["db"] for f in F)
    peak = max(i for i, f in enumerate(F) if f["db"] >= top - 1.5)
    lo = min(s0 + 5, peak)
    m = min(range(lo, peak + 1), key=lambda i: F[i]["db"])
    v = next((i for i in range(m, peak + 1) if F[i]["voiced"] and F[i]["db"] > -8), peak)
    rel = max(range(m + 1, v + 2), key=lambda i: F[i]["db"] - F[i - 2]["db"]) - 1
    return rel, v


def bm_onset(F, phonemes):
    """Where the word really starts (frame) and how much was wrong with its start. A hum before p, t,
    k, c, s, sy, kh, f or h is cut off; before b, d, g, j or z only the last 30 ms of it are kept (a short
    voice lead is how Malay says them; a long one sounds like "mm-benih")."""
    c, kind = bm_first(phonemes)
    s0 = first_sound(F)
    if kind in ("son", "vowel"):
        return s0, 0
    if kind == "vstop":
        rel, v = bm_burst(F, s0)
        if c in ("dʒ", "ɟ"):     # j: the release is where its friction starts
            rel = next((i for i in range(s0 + 3, v) if noisy(F[i]) or buzz(F[i])), rel)
        return (s0, 0) if rel - s0 <= 6 else (rel - 6, (rel - s0 - 6) // 4)
    if kind == "z":
        z0 = next((i for i in range(s0, min(len(F), s0 + 80)) if buzz(F[i])), None)
        if z0 is None:
            return s0, 50
        return (s0, 0) if z0 - s0 <= 4 else (z0 - 2, (z0 - s0 - 4) // 4)
    # a hum before the consonant, maybe starting with a breath: voicing within 4 frames that lasts
    hum_at = next((i for i in range(s0, min(len(F), s0 + 4)) if F[i]["voiced"]), None)
    after = s0
    if hum_at is not None and sum(F[i]["voiced"] for i in range(hum_at, min(len(F), hum_at + 6))) >= 5:
        after = hum_at
        while after < len(F) and F[after]["voiced"] and not (kind == "h" and buzz(F[after])):
            after += 1
    n0 = next((i for i in range(after, min(len(F), after + 80)) if noisy(F[i]) or (kind == "h" and buzz(F[i]))), None)
    if n0 is None:
        return s0, 50        # the consonant is missing ("anah" for "tanah")
    hum = sum(F[i]["voiced"] for i in range(s0, n0))
    if hum <= 2:
        return s0, 0
    bad = 2 + hum // 4
    if kind in ("stop", "aff"):
        # the hum fades into breath, the mouth closes, then the consonant bursts: start in the closure
        v = next((i for i in range(n0, len(F)) if F[i]["voiced"] and F[i]["db"] > -20), len(F) - 1)
        lo = min(F[i]["db"] for i in range(n0, v))
        return max(i for i in range(n0, v) if F[i]["db"] <= lo + 3), bad
    if kind == "fric" and c in ("s", "ʃ"):
        return next((i for i in range(n0, min(len(F), n0 + 30)) if F[i]["c"] == "s"), n0), bad
    return n0, bad


def bm_tail(F, phonemes, start):
    """The frame just after the word's last sound, and whether an echo vowel had to be cut off. After
    a final p, t or k the mouth closes (a moment of silence) and the stop is released; anything voiced
    after that release is an echo ("lembut-uh"), and it and everything after it is dropped."""
    end = max(i for i, f in enumerate(F) if f["c"] != "_") + 1
    if bm_units(phonemes)[-1] not in ("p", "t", "k", "ʔ"):
        return end, 0
    runs = [r for r in voiced_runs(F, start) if r[1] - r[0] >= 12]
    if not runs:
        return end, 0
    i, gap = runs[-1][1], 0
    while i < len(F):
        quiet = not F[i]["voiced"] and F[i]["db"] < -30
        gap = gap + 1 if quiet else 0
        if gap >= 3 and not quiet:
            break
        if gap >= 3 and i + 1 < len(F) and not (not F[i + 1]["voiced"] and F[i + 1]["db"] < -30):
            i += 1
            break
        i += 1
    if gap < 3:
        return end, 0
    echo = next((j for j in range(i, len(F) - 1) if F[j]["voiced"] and F[j + 1]["voiced"]), None)
    if echo is not None:
        return echo, 1
    noise = next((j for j in range(i, len(F)) if noisy(F[j])), i)
    stop = noise
    while stop < len(F) and noisy(F[stop]):
        stop += 1
    return min(end, stop + 2), 0


def bm_problems(F, phonemes, speed):
    """What is still wrong with a trimmed take (0 = nothing)."""
    c, kind = bm_first(phonemes)
    units = bm_units(phonemes)
    scale = speed / BM_SPEED          # frames here are this much shorter than in the finished clip
    s0 = first_sound(F)
    bad = 0
    if kind in ("stop", "aff") and len(units) > 1 and units[1] in BM_VOWELS:
        # Malay p, t and k let the voice in at once (English ones puff first); a long gap here also
        # means the vowel was swallowed ("k-bun" for "kebun")
        n0 = next((i for i in range(s0, len(F)) if noisy(F[i])), s0)
        v = next((i for i in range(n0, len(F)) if F[i]["voiced"] and F[i]["db"] > -20), len(F))
        bad += max(0, int((v - n0) * scale) - (8 if kind == "stop" else 26))
        if units[1] in "aeəɛoɔ":
            # a hum between the consonant and an open vowel ("k-mm-ebun"); i and u are too close to tell apart
            w = next((i for i in range(v, len(F)) if vowelish(F[i])), v)
            bad += max(0, sum(F[i]["voiced"] and F[i]["mid"] < .04 for i in range(v, w)) - 4)
    lo, hi = bm_islands(phonemes)
    runs = voiced_runs(F, s0)
    bad += 3 * max(0, lo - len(runs), len(runs) - hi) + max(0, min(len(runs), hi) - lo)   # prefer b, d, g, j voiced
    for a, b in runs[:-1]:
        # p, t, k and c inside a word close silently; a hummed closure turns "cepat" into "cebat"
        hummed = sum(F[i]["voiced"] and F[i]["mid"] < .04 and F[i]["db"] < -12 for i in range(max(a, b - 15), b))
        bad += max(0, hummed - 4)
    last = max(i for i, f in enumerate(F) if f["voiced"])
    tail = [f["c"] for f in F[last + 1:] if f["c"] != "_"]
    if units[-1] == "h":       # re-made as a clear breath (bm_breathe); it must stay an "h", never an "s"
        bad += 2 * tail.count("s")
    elif units[-1] == "s":
        bad += max(0, 10 - int(tail.count("s") * scale))
    return bad


def bm_breathe(x, sr, seconds=.14, level=-13):
    """A final h that can be heard: the voice often drops it ("beni" for "benih"). The word's last
    vowel is breathed out without voice, in its own colour (noise shaped by that vowel's formants),
    as a Malay speaker does, fading away over `seconds`."""
    import numpy as np
    from scipy.signal import butter, lfilter, sosfiltfilt
    import parselmouth
    F = frames(x, sr)
    last = max(i for i, f in enumerate(F) if f["voiced"] and f["db"] > -25)
    stop = min(len(x), F[last]["s"] + int(.006 * sr))
    # the voice lets a final vowel drift towards "i" as it fades ("tana-i"): end the vowel where it
    # leaves its steady sound
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fm = parselmouth.Sound(x, sr).to_formant_burg(time_step=.005, max_number_of_formants=5, maximum_formant=5500)
    f2 = lambda t: fm.get_value_at_time(2, t)
    t_end = stop / sr
    steady = np.nanmedian([f2(t) for t in np.arange(t_end - .2, t_end - .08, .005)])
    run = 0
    for t in np.arange(t_end - .08, t_end, .005):
        run = run + 1 if abs(f2(t) - steady) > 400 else 0
        if run == 2:
            stop = int((t - .005) * sr)
            break
    vowel = x[max(0, stop - int(.05 * sr)):stop]
    # lightly pre-emphasised, so the breath keeps the vowel's formants without the voice's heavy low end,
    # and kept below 5 kHz so it stays a soft "h", never an "s" ("tanas")
    breath = stretch_noise(lfilter([1, -.6], [1], vowel), sr, seconds)
    breath = sosfiltfilt(butter(4, [300, 5000], "band", fs=sr, output="sos"), breath)
    breath *= np.sqrt(np.mean(vowel ** 2)) * 10 ** (level / 20) / max(1e-12, np.sqrt(np.mean(breath ** 2)))
    n, rise = len(breath), int(.012 * sr)
    env = np.ones(n)
    env[:rise] = np.linspace(0, 1, rise)
    env[rise:] = np.linspace(1, 0, n - rise) ** 1.5
    fall = int(.012 * sr)
    out = np.r_[x[:stop], np.zeros(n - fall)]
    out[stop - fall:stop] *= np.linspace(1, 0, fall)       # the voice stops ...
    out[stop - fall:] += breath * env                         # ... as the breath takes over
    return out


def bm_take(kokoro, phonemes, speeds=TRY_SPEEDS):
    """The cleanest take of a Malay word or syllable, trimmed: (problems, samples, sr, speed)."""
    import numpy as np
    kind = bm_first(phonemes)[1]
    final_h = bm_units(phonemes)[-1] == "h"
    # The voice says "ah" the Hindi way, as "eh" ("tanah" comes out "tanai"), and often drops a final h:
    # it is asked for the word without its h, and the h is breathed on afterwards (bm_breathe).
    say = phonemes.strip(" .")
    say = say[:-1] if final_h else say
    best = None
    for speed in speeds:
        x, sr = kokoro.create(say + ".", voice=BM_VOICE, speed=speed, lang="en-us", is_phonemes=True)
        x = np.asarray(x, np.float64)
        F = frames(x, sr)
        if not any(f["voiced"] for f in F):
            continue
        start, bad = bm_onset(F, say)
        end, echo = bm_tail(F, say, start)
        a = max(0, F[start]["s"] - int(.012 * sr))
        cut = bm_units(say)[-1] in ("p", "t", "k", "ʔ") and end < len(F)
        b = min(len(x), F[end]["s"] + int((-.012 if echo else .006) * sr)) if cut else len(x)
        y = x[a:b].copy()
        fade = int((.02 if kind in ("vstop", "z") and start != first_sound(F) else .004) * sr)
        y[:fade] *= np.linspace(0, 1, fade)
        if cut:
            out = int(.015 * sr)
            y[-out:] *= np.linspace(1, 0, out)
        if not any(f["voiced"] and f["db"] > -25 for f in frames(y, sr)):
            continue
        if final_h:
            y = bm_breathe(y, sr)
        pad = np.zeros(int(.03 * sr))
        bad += echo + bm_problems(frames(np.r_[pad, y, pad], sr), phonemes, speed)
        if best is None or bad < best[0]:
            best = (bad, y, sr, speed)
        if bad == 0:
            break
    return best


def record_bm(kokoro, phonemes, out_path):
    import numpy as np
    bad, x, sr, speed = bm_take(kokoro, phonemes)
    if bad:
        print(f"  note: Malay '{phonemes}' best take still has problem score {bad}")
    x = x / max(1e-6, float(np.abs(x).max())) * 0.89
    save_mp3(x, sr, out_path, lift_filters(sr, WORD_LIFT, tempo=BM_SPEED / speed))


# ---------- Bahasa Melayu letter sounds (bunyi huruf) for Eja! and the sound chart ----------
# Cut from the Malay voice the same way as the English sounds, with Malay rules:
#   vowel  a, e (pepet), é (taling), i, o, u: the steady middle of the vowel, held 0.32 s. Each is
#          cut from several words and the take whose formants are closest to the Malay vowel is kept.
#   diph   ai, au, oi: the whole glide
#   stop   p, t, k, c, b, d, g, j: the release with a trace (40 ms) of pepet, as a teacher says "pə";
#          p, t and k must let the voice in within 40 ms (no English puff of air)
#   hiss   s, sy, f, kh, h: the noise, held
#   hum    m, n, ng, l: the voiced part before the vowel, held
#   nyglide  ny: the hum and its slide into the vowel (an "n" alone would be heard as n)
#   glide  w, y: the glide and its slide into the vowel
#   buzz   z: the part that is voiced and noisy at once
#   trill  r: Malay r is rolled; no voice rolls it, so a held pepet is broken by quick tongue taps (26 a second)
BM_SOUND_REV = "b1"
BM_SOUND_SPEEDS = (1.0, 0.9, 1.1, 0.85, 1.2)
BM_SOUNDS = {
    "a": (("pˈap", "kˈak", "tˈat"), "vowel", .32),
    "e": (("pˈɨp", "kˈɨk", "tˈɨt"), "vowel", .32),
    "ee": (("kˈek", "tˈet", "pˈep"), "vowel", .32),
    "i": (("pˈip", "kˈik", "tˈit"), "vowel", .32),
    "o": (("bˈoːb", "pˈoːp", "kˈoːk", "ˈoː"), "vowel", .32),
    "u": (("bˈuː", "pˈuːp", "kˈuːk", "ɡˈuː"), "vowel", .32),
    "ai": (("pˈai", "pˈaj", "kˈai"), "diph", .42),
    "au": (("pˈau", "pˈaw", "kˈau"), "diph", .42),
    "oi": (("pˈoi", "pˈoj", "kˈoi"), "diph", .42),
    "p": (("pˈɨ", "pˈa"), "stop", None), "t": (("tˈɨ", "tˈa"), "stop", None),
    "k": (("kˈɨ", "kˈa"), "stop", None), "c": (("tʃˈɨ", "cˈɨ", "tʃˈa"), "stop", None),
    "b": (("bˈɨ", "bˈa"), "stop", None), "d": (("dˈɨ", "dˈa"), "stop", None),
    "g": (("ɡˈɨ", "ɡˈa"), "stop", None), "j": (("dʒˈɨ", "ɟˈɨ", "dʒˈa"), "stop", None),
    "s": (("sˈa", "ˈasa"), "hiss", .40), "sy": (("ʃˈa", "ˈaʃa"), "hiss", .40),
    "f": (("fˈa", "ˈafa"), "hiss", .40), "kh": (("ˈaxa", "xˈa", "ˈaxɨ"), "hiss", .32),
    "h": (("ˈahɨ", "ˈaha", "hˈa"), "hiss", .16),
    "m": (("mˈa",), "hum", .38), "n": (("nˈa",), "hum", .38), "ng": (("ŋˈa", "ŋˈɨ"), "hum", .38),
    "l": (("lˈa",), "hum", .35), "ny": (("ɲˈa", "ɲˈɨ"), "nyglide", .32),
    "w": (("wˈa",), "glide", .14), "y": (("jˈa",), "glide", .14),
    "z": (("zˈa", "ˈaza"), "buzz", .36),
    "r": (("pˈɨp", "kˈɨk", "tˈɨt"), "trill", .36),
}
# Where each Malay vowel sits (F1, F2 in Hz for this voice before the lift); diphthongs: start -> end
BM_VOWEL_AT = {"a": (900, 1650), "e": (550, 1650), "ee": (530, 2350), "i": (400, 2900), "o": (540, 1050),
               "u": (400, 1000), "r": (550, 1650)}
BM_GLIDE_AT = {"ai": ((900, 1650), (420, 2600)), "au": ((900, 1650), (420, 950)), "oi": ((470, 1000), (420, 2600))}


def bark(f):
    import math
    return 13 * math.atan(.00076 * f) + 3.5 * math.atan((f / 7500) ** 2)


def formants_at(x, sr, a, b):
    """Median F1 and F2 between samples a and b."""
    import numpy as np
    import parselmouth
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fm = parselmouth.Sound(np.asarray(x, np.float64), sr).to_formant_burg(
            time_step=.005, max_number_of_formants=5, maximum_formant=5500)
    ts = np.arange(a, b, int(.005 * sr)) / sr
    return tuple(float(np.nanmedian([fm.get_value_at_time(k, t) for t in ts])) for k in (1, 2))


def vowel_dist(fs, target):
    return ((bark(fs[0]) - bark(target[0])) ** 2 + (bark(fs[1]) - bark(target[1])) ** 2) ** .5


def bm_cut(x, sr, F, carrier, sid, rule):
    """Where the sound is in the carrier: (start sample, end sample, how far off it is, problem or '')."""
    s0 = first_sound(F)
    if rule in ("vowel", "trill"):
        best, i = (0, 0), 0
        while i < len(F):
            j = i
            while j < len(F) and F[j]["voiced"] and F[j]["db"] > -12:
                j += 1
            best = max(best, (j - i, i))
            i = j + 1
        n, a = best
        if n < 14:
            return 0, 0, 0, "vowel too short"
        a, b = F[a + int(.2 * n)]["s"], F[a + int(.85 * n)]["s"]
        return a, b, vowel_dist(formants_at(x, sr, a, b), BM_VOWEL_AT[sid]), ""
    if rule == "diph":
        v = next((i for i in range(s0, len(F)) if F[i]["voiced"] and F[i]["db"] > -15), None)
        if v is None:
            return 0, 0, 0, "no vowel"
        e = v
        while e + 1 < len(F) and F[e + 1]["voiced"] and F[e + 1]["db"] > -18:
            e += 1
        if e - v < 20:
            return 0, 0, 0, "glide too short"
        a, b = F[v]["s"], F[e]["s"]
        q = (b - a) // 5
        start, end = BM_GLIDE_AT[sid]
        off = vowel_dist(formants_at(x, sr, a, a + q), start) + vowel_dist(formants_at(x, sr, b - q, b), end)
        return a, b, off, ""
    if rule == "stop":
        start, bad = bm_onset(F, carrier)
        if bad >= 50:
            return 0, 0, 0, "no consonant"
        c, kind = bm_first(carrier)
        if kind == "vstop":
            v = bm_burst(F, first_sound(F))[1]
            return F[start]["s"], F[min(len(F) - 1, v + 12)]["s"], bad, ""
        n0 = next((i for i in range(start, len(F)) if noisy(F[i])), None)
        v = next((i for i in range(n0 or start, len(F)) if F[i]["voiced"] and F[i]["db"] > -20), None)
        if n0 is None or v is None:
            return 0, 0, 0, "no burst"
        if v - n0 > (8 if kind == "stop" else 26):
            return 0, 0, 0, f"breath before the vowel ({(v - n0) * 5} ms)"
        w = next((i for i in range(v, len(F)) if vowelish(F[i])), v)
        if sum(F[i]["voiced"] and F[i]["mid"] < .04 and F[i]["db"] < -10 for i in range(v, w)) > 4:
            return 0, 0, 0, "hum between the consonant and the vowel"
        return F[start]["s"], F[min(len(F) - 1, v + (10 if kind == "stop" else 6))]["s"], bad, ""
    if rule == "hiss":
        after = s0
        if bm_first(carrier)[1] == "vowel":   # "ˈasa": the hiss between the two vowels
            after = next((i for i in range(s0, len(F)) if F[i]["voiced"]), s0)
        best, i = (0, 0), after
        while i < len(F):
            j = i
            while j < len(F) and noisy(F[j]) and F[j]["db"] > -32:
                j += 1
            best = max(best, (j - i, i))
            i = j + 1
        n, a = best
        if n < (5 if sid in ("h", "kh") else 8):
            return 0, 0, 0, "hiss too short"
        bright = sum(F[k]["c"] == "s" for k in range(a, a + n)) / n
        if sid in ("s", "sy") and bright < .5:
            return 0, 0, 0, "not bright enough for s"
        return F[a]["s"] - int(.004 * sr), F[a + n - 1]["s"], 0, ""
    if rule in ("hum", "nyglide", "glide"):
        v0 = next((i for i in range(s0, len(F)) if F[i]["voiced"]), None)
        w = next((i for i in range(v0 or 0, len(F) - 3) if all(vowelish(F[k]) for k in range(i, i + 3))), None)
        if v0 is None or w is None:
            return 0, 0, 0, "no vowel found"
        if rule == "glide":
            return F[max(v0, w - 12)]["s"], F[w + 6]["s"], 0, ""
        if w - 2 - (v0 + 2) < 10:
            return 0, 0, 0, "consonant too short"
        return F[v0 + 2]["s"], F[w - 2]["s"] if rule == "hum" else F[w + 5]["s"], 0, ""
    if rule == "buzz":
        best, i = (0, 0), s0
        while i < len(F):
            j = i
            while j < len(F) and buzz(F[j]):
                j += 1
            best = max(best, (j - i, i))
            i = j + 1
        if best[0] < 10:
            return 0, 0, 0, "too little voiced buzz"
        return F[best[1]]["s"], F[best[1] + best[0]]["s"], 0, ""
    raise ValueError(rule)


def roll(x, sr, rate=26.0, depth=.06, tap=.013):
    """Turn a held voiced sound into a rolled r: the tongue tip taps `rate` times a second, each tap
    nearly closing the mouth for `tap` seconds (a smooth dip to `depth` of the level)."""
    import numpy as np
    t = np.arange(len(x)) / sr
    phase = t % (1 / rate)
    env = np.ones(len(x))
    m = phase < tap
    env[m] = 1 - (1 - depth) * .5 * (1 - np.cos(2 * np.pi * phase[m] / tap))
    return x * env


def make_bm_sound(kokoro, sid):
    import numpy as np
    carriers, rule, length = BM_SOUNDS[sid]
    best, tried = None, []
    for carrier in carriers:
        for speed in BM_SOUND_SPEEDS:
            x, sr = kokoro.create(carrier + ".", voice=BM_VOICE, speed=speed, lang="en-us", is_phonemes=True)
            x = np.asarray(x, np.float64)
            a, b, off, problem = bm_cut(x, sr, frames(x, sr), carrier, sid, rule)
            if problem:
                tried.append(f"{carrier}@{speed}: {problem}")
                continue
            if best is None or off < best[0]:
                best = (off, x[a:b], sr, carrier, speed)
            if off == 0:
                break
        if best and best[0] == 0:
            break
    if best is None:
        raise SystemExit(f"No clean Malay '{sid}' sound ({'; '.join(tried)})")
    off, seg, sr, carrier, speed = best
    if rule in ("vowel", "trill"):
        seg = stretch_voice(seg, sr, length)
        if rule == "trill":
            seg = roll(seg, sr)
    elif rule == "diph":
        if len(seg) / sr < length:
            seg = stretch_voice(seg, sr, length)
    elif rule == "hiss":
        seg = stretch_noise(seg, sr, length)
    elif rule == "hum" or rule == "glide":
        if len(seg) / sr < length:
            seg = stretch_voice(seg, sr, length)
    elif rule == "nyglide":
        slide = int(.07 * sr)    # the last 70 ms: the end of the hum and the slide into the vowel
        hum = stretch_voice(seg[:-slide], sr, length - .07)
        fade = int(.012 * sr)
        w = np.linspace(1, 0, fade)
        seg = np.r_[hum[:-fade], hum[-fade:] * w + seg[-slide:-slide + fade] * (1 - w), seg[-slide + fade:]]
    elif rule == "buzz":
        seg = stretch_buzz(seg, sr, length)
        F = frames(np.r_[np.zeros(1200), seg, np.zeros(1200)], sr)
        on = next(i for i, f in enumerate(F) if f["voiced"])
        stop = max(i for i, f in enumerate(F) if f["voiced"])
        seg = seg[max(0, F[on]["s"] - 1200 - int(.005 * sr)):F[stop]["s"] - 1200 + int(.01 * sr)]
    return seg, sr, carrier, speed, off


def record_bm_sound(kokoro, sid, out_path):
    import numpy as np
    seg, sr, carrier, speed, off = make_bm_sound(kokoro, sid)
    seg = seg / max(1e-6, float(np.abs(seg).max())) * 0.85
    rule = BM_SOUNDS[sid][1]
    fade_out = .012 if rule == "stop" else .04
    fade_in = .04 if sid == "h" else .02 if rule == "stop" and sid in "bdgj" else .006
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
    # the Malay sound chart: m/b_<sound> is the sound itself (cut below), m/x_<sound> its example word
    jobs += [("m/x_" + d["id"], d["ph"], bm_tag, "bm") for d in bm["sounds"]]
    # Gabung!: a picture word for each consonant + vowel syllable (m/g_<syllable>, "bu" -> buku)
    jobs += [("m/g_" + syl, d["ph"], bm_tag, "bm") for syl, d in bm.get("gabung", {}).items()]
    missing = [d["id"] for d in bm["sounds"] if d["id"] not in BM_SOUNDS]
    if missing:
        raise SystemExit(f"No Malay sound recipe for: {', '.join(missing)}")

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

    for sid, recipe in BM_SOUNDS.items():
        key = "m/b_" + sid
        sig = hashlib.sha1(f"{BM_TAG}|{BM_SOUND_REV}|{WORD_LIFT}|{recipe}|{BM_VOWEL_AT.get(sid)}|{BM_GLIDE_AT.get(sid)}"
                           .encode()).hexdigest()[:12]
        out = os.path.join(ROOT, "audio", key + ".mp3")
        if args.force or old.get(key) != sig or not os.path.exists(out):
            record_bm_sound(kokoro, sid, out)
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
