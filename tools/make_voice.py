#!/usr/bin/env python3
"""Record Luna's voice clips for Word Snap Showdown.

Uses the open Kokoro text-to-speech model to speak every line in the
<script id="lines"> block of index.html and every word in the game's word
lists, then gives the voice a cute, child-like lift at normal speed and saves small MP3s:

    audio/p/<line key>.mp3   Luna's cheers and instructions
    audio/w/<word>.mp3       each reading word, spoken slowly and clearly
    audio/s/<letter>.mp3     each letter's sound for Robot Talk ("c... a... t")
    audio/n/<number>.mp3     every number from 0 to 100 for the maths games
    audio/list.json          every clip, used by sw.js to work offline

Only clips whose text or voice settings changed are re-recorded.

Setup (once):
    pip install kokoro-onnx soundfile
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")

VOICE = "af_heart"   # Kokoro's best-rated voice; the highest and most lively of its American voices
LANG = "en-us"
# A "lift" raises the pitch and the voice's tone together (a cute, child-like sound),
# then stretches the clip back to its original length so Luna talks at normal speed.
LINE_LIFT = 1.22     # cheers: about +3.4 semitones
LINE_SPEED = 1.0     # normal speed
WORD_LIFT = 1.18     # reading words: a touch less (+2.9 semitones) so every sound stays crisp
WORD_SPEED = 0.95    # normal speed, a hair slower so single words aren't clipped
SETTINGS_TAG = f"{VOICE}|{LANG}|v3"
# Names the voice would mispronounce, respelled the way they should sound.
SAY_AS = {"Elyse": "Eleese"}   # "eh-LEES" (the voice reads "Elyse" as "EH-lize")


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
    return lines, words


def ensure_model(model_dir):
    os.makedirs(model_dir, exist_ok=True)
    for name in MODEL_FILES:
        path = os.path.join(model_dir, name)
        if not os.path.exists(path):
            print(f"Downloading {name} ...", flush=True)
            urllib.request.urlretrieve(MODEL_URL + name, path)
    return [os.path.join(model_dir, n) for n in MODEL_FILES]


def record(kokoro, text, speed, lift, out_path):
    import numpy as np
    import soundfile as sf

    samples, sr = kokoro.create(text, voice=VOICE, speed=speed, lang=LANG)
    samples = samples / max(1e-6, float(np.abs(samples).max())) * 0.89
    trim = "silenceremove=start_periods=1:start_threshold=-45dB"
    chain = (f"asetrate={int(sr * lift)},aresample={sr},atempo={1 / lift:.5f},"
             f"{trim},areverse,{trim},areverse,adelay=20,apad=pad_dur=0.05")
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, samples, sr)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name, "-af", chain,
             "-ac", "1", "-ar", "24000", "-c:a", "libmp3lame", "-b:a", "48k", out_path],
            check=True,
        )


# ---------- letter sounds for Robot Talk ----------
# A letter's sound is cut out of a short syllable rather than spoken alone, because the
# model can't say a lone consonant cleanly. Each recipe is (carrier phonemes, how to cut,
# milliseconds of vowel to keep, length to stretch hums and hisses to).
#   "before": the consonant before the vowel starts      "tail": the sound after the vowel ends
#   "whole":  the whole carrier (vowels)
SOUND_REV = "s2"
SOUNDS = {
    # hisses and puffs, cut before the vowel
    "s": ("sɑː", "before", 0, 380), "f": ("fɑː", "before", 0, 380), "h": ("hɑː", "before", 25, None),
    # pops: a short burst with a trace of vowel so they can be heard
    "k": ("kɑː", "before", 15, None), "t": ("tɑː", "before", 15, None), "p": ("pɑː", "before", 15, None),
    "b": ("bɑː", "before", 55, None), "d": ("dɑː", "before", 55, None), "g": ("ɡɑː", "before", 55, None),
    "j": ("ʤɑː", "before", 55, None),
    # glides need a little vowel
    "w": ("wɑː", "rise", 60, None), "y": ("jɑː", "rise", 60, None),
    # hums and buzzes are longest at the end of a syllable
    "m": ("ɑːm", "tail-nasal", 0, 380), "n": ("ɑːn", "tail-nasal", 0, 380),
    "l": ("ɑːl", "tail-drop70", 0, 340), "v": ("ɑːv", "tail-drop45", 0, 340),
    "z": ("ɑːz", "tail-hiss", 0, 380), "x": ("ɑks", "tail-unvoiced", 0, None),
    "r": ("ɹː", "whole", 0, 340),
    # short vowels
    "a": ("æː", "whole", 0, None), "e": ("ɛː", "whole", 0, None), "i": ("ɪː", "whole", 0, None),
    "o": ("ɑː", "whole", 0, None), "u": ("ʌː", "whole", 0, None),
}


def _frames(x, sr):
    import numpy as np
    hop, n = int(.01 * sr), int(.02 * sr)
    out = []
    for i in range(0, len(x) - n, hop):
        f = x[i:i + n]
        w = f * np.hanning(n)
        ac = np.correlate(w, w, "full")[n - 1:]
        lo, hi = int(sr / 450), int(sr / 90)
        sp = np.abs(np.fft.rfft(w))
        fq = np.fft.rfftfreq(n, 1 / sr)
        out.append((np.sqrt((f ** 2).mean()), ac[lo:hi].max() / max(1e-9, ac[0]), (sp * fq).sum() / max(1e-9, sp.sum())))
    return np.array(out), hop


def cut_sound(kokoro, letter):
    import numpy as np
    ph, how, keep_ms, _ = SOUNDS[letter]
    x, sr = kokoro.create(ph, voice=VOICE, speed=1.0, lang=LANG, is_phonemes=True)
    x = x / max(1e-6, float(np.abs(x).max()))
    F, hop = _frames(x, sr)
    rms, voiced, bright = F[:, 0], F[:, 1], F[:, 2]
    peak = rms.max()
    active = np.where(rms > 0.04 * peak)[0]
    first, last = int(active[0]), int(active[-1])
    keep = int(keep_ms / 1000 * sr)
    if how == "whole":
        return x[max(0, (first - 1) * hop):(last + 3) * hop], sr
    if how == "before":
        on = next((i for i in range(first, len(F) - 3)
                   if all(voiced[i:i + 3] > .6) and all(rms[i:i + 3] > .2 * peak)), first)
        return x[max(0, (first - 1) * hop):on * hop + keep], sr
    if how == "rise":
        sm = np.convolve(rms, np.ones(3) / 3, "same")
        d = np.r_[sm[3:] - sm[:-3], [0, 0, 0]]
        lo, hi = first + 4, first + int(.6 * (len(F) - first))
        on = lo + int(np.argmax(d[lo:hi]))
        return x[max(0, (first - 1) * hop):on * hop + keep], sr
    # tail cuts: after the vowel's loudest point, keep the longest stretch that sounds like the consonant
    top = int(np.argmax(rms))
    test = {
        "tail-nasal": lambda i: voiced[i] > .6 and bright[i] < 1000,
        "tail-hiss": lambda i: bright[i] > 4000,
        "tail-unvoiced": lambda i: voiced[i] < .6 or rms[i] < .2 * peak,
        "tail-drop70": lambda i: rms[i] < .7 * peak,
        "tail-drop45": lambda i: rms[i] < .45 * peak,
    }[how]
    best, run_start = (top + 1, top + 1), None
    for i in range(top + 1, last + 2):
        if i <= last and test(i):
            run_start = i if run_start is None else run_start
        elif run_start is not None:
            if i - run_start > best[1] - best[0]:
                best = (run_start, i)
            run_start = None
    return x[best[0] * hop:(best[1] + 1) * hop], sr


def record_sound(kokoro, letter, out_path):
    import numpy as np
    import soundfile as sf

    seg, sr = cut_sound(kokoro, letter)
    seg = seg / max(1e-6, float(np.abs(seg).max())) * 0.85
    stretch_ms = SOUNDS[letter][3]
    chain = []
    if stretch_ms and len(seg) / sr < stretch_ms / 1000:
        chain.append(f"rubberband=tempo={len(seg) / sr / (stretch_ms / 1000):.4f}")
    chain += [f"asetrate={int(sr * WORD_LIFT)}", f"aresample={sr}", f"atempo={1 / WORD_LIFT:.5f}",
              "afade=t=in:d=0.008", "areverse", "afade=t=in:d=0.02", "areverse", "adelay=20", "apad=pad_dur=0.04"]
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, seg, sr)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name, "-af", ",".join(chain),
             "-ac", "1", "-ar", "24000", "-c:a", "libmp3lame", "-b:a", "48k", out_path],
            check=True,
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-dir", default=os.path.expanduser("~/.cache/kokoro"))
    ap.add_argument("--force", action="store_true", help="re-record every clip")
    args = ap.parse_args()

    lines, words = read_game()
    jobs = [("p/" + k, spoken(t), LINE_SPEED, LINE_LIFT) for k, t in lines.items()]
    jobs += [("w/" + w, w + ".", WORD_SPEED, WORD_LIFT) for w in words]
    jobs += [("n/" + str(n), number_word(n) + ".", WORD_SPEED, WORD_LIFT) for n in range(101)]

    list_path = os.path.join(ROOT, "audio", "list.json")
    old = {}
    if os.path.exists(list_path):
        old = json.load(open(list_path)).get("clips", {})

    from kokoro_onnx import Kokoro
    kokoro = Kokoro(*ensure_model(args.model_dir))

    clips, made = {}, 0
    for key, text, speed, lift in jobs:
        sig = hashlib.sha1(f"{SETTINGS_TAG}|{speed}|{lift}|{text}".encode()).hexdigest()[:12]
        out = os.path.join(ROOT, "audio", key + ".mp3")
        if args.force or old.get(key) != sig or not os.path.exists(out):
            record(kokoro, text, speed, lift, out)
            made += 1
        clips[key] = sig

    for letter, recipe in SOUNDS.items():
        key = "s/" + letter
        sig = hashlib.sha1(f"{SETTINGS_TAG}|{SOUND_REV}|{WORD_LIFT}|{recipe}".encode()).hexdigest()[:12]
        out = os.path.join(ROOT, "audio", key + ".mp3")
        if args.force or old.get(key) != sig or not os.path.exists(out):
            record_sound(kokoro, letter, out)
            made += 1
        clips[key] = sig

    wanted = {os.path.join(ROOT, "audio", k + ".mp3") for k in clips}
    for sub in ("p", "w", "s", "n"):
        folder = os.path.join(ROOT, "audio", sub)
        for name in os.listdir(folder) if os.path.isdir(folder) else []:
            path = os.path.join(folder, name)
            if path not in wanted:
                os.remove(path)

    version = hashlib.sha1(json.dumps(clips, sort_keys=True).encode()).hexdigest()[:8]
    json.dump({"voice": SETTINGS_TAG, "version": version, "clips": clips}, open(list_path, "w"), indent=1, sort_keys=True)
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
