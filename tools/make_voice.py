#!/usr/bin/env python3
"""Record Luna's voice clips for Word Snap Showdown.

Uses the open Kokoro text-to-speech model to speak every line in the
<script id="lines"> block of index.html and every word in the game's word
lists, then gives the voice a younger, brighter lift and saves small MP3s:

    audio/p/<line key>.mp3   Luna's cheers and instructions
    audio/w/<word>.mp3       each reading word, spoken slowly and clearly
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
# A "lift" plays the clip back faster, which raises the pitch and brightens the voice.
LINE_LIFT = 1.14     # cheers: about +2.3 semitones and 14% faster, for a younger, high-energy Luna
LINE_SPEED = 1.0
WORD_LIFT = 1.08     # reading words: a gentler lift (+1.3 semitones) so every sound stays clear
WORD_SPEED = 0.82    # spoken slowly: about 0.89x after the lift
SETTINGS_TAG = f"{VOICE}|{LANG}|v2"


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
    chain = f"asetrate={int(sr * lift)},aresample={sr},{trim},areverse,{trim},areverse,adelay=20,apad=pad_dur=0.05"
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, samples, sr)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name, "-af", chain,
             "-ac", "1", "-ar", "24000", "-c:a", "libmp3lame", "-b:a", "48k", out_path],
            check=True,
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-dir", default=os.path.expanduser("~/.cache/kokoro"))
    ap.add_argument("--force", action="store_true", help="re-record every clip")
    args = ap.parse_args()

    lines, words = read_game()
    jobs = [("p/" + k, t, LINE_SPEED, LINE_LIFT) for k, t in lines.items()]
    jobs += [("w/" + w, w + ".", WORD_SPEED, WORD_LIFT) for w in words]

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

    wanted = {os.path.join(ROOT, "audio", k + ".mp3") for k in clips}
    for sub in ("p", "w"):
        folder = os.path.join(ROOT, "audio", sub)
        for name in os.listdir(folder) if os.path.isdir(folder) else []:
            path = os.path.join(folder, name)
            if path not in wanted:
                os.remove(path)

    json.dump({"voice": SETTINGS_TAG, "clips": clips}, open(list_path, "w"), indent=1, sort_keys=True)
    print(f"{len(clips)} clips ({len(lines)} lines, {len(words)} words); recorded {made}.")


if __name__ == "__main__":
    sys.exit(main())
