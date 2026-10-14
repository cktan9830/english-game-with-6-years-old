"""The Bahasa Melayu voice for Word Snap Showdown.

Malay must be read with Malay sounds, so the Malay clips use a voice trained on native Malaysian speech:
Mesolitica's "VITS-yasmin" (https://huggingface.co/mesolitica/VITS-yasmin). It reads ordinary Malay
spelling, so words are pronounced the way a Malaysian reads them (pepet and taling e, rolled r, final h).

Download model.pth and config.json from that page into one folder and pass it as --bm-model-dir
(default ~/.cache/malay-tts/VITS-yasmin). Needs: pip install torch scipy soundfile praat-parselmouth

What is made, and how:
  words        read as written (this week's ejaan words, picture words, cheers)
  syllables    an open syllable said on its own is often read as an English letter name ("be" as "bee"),
               so each one is checked: ba, ku, ... are kept when the voice says the right vowel; otherwise
               (and always for the pepet e of be, ke, ce) the syllable is taken from the start of a real
               word (be from "betul", ke from "kecil") and its vowel held a little longer
  letter sounds (bunyi huruf), following the Malay phonics module of Mohamad Rozi Kasim, "Pembangunan
               Model Kesedaran Bunyi Fonem Bahasa Melayu", Jurnal Pendidikan Bahasa Melayu 15(2), 2025:
               - the six vowels a (ayam), e pepet (emak), é taling (elok), i (ikan), o (otak), u (ular):
                 the vowel of a real word, held
               - consonants with a short "eh": b [beh], c [ceh], d [deh] ... ng [ngeh], ny [nyeh],
                 sy [syeh], kh [kheh], as in the module's tables
               - s, m, n, l, f and z held: "sss", "mmm"
               - the diphthongs ai (pantai), au (pisau), oi (sepoi), from the end of a real word
Every vowel is measured (formants) against the voice's own vowels before a clip is kept.
"""
import json
import os
import re
import sys
import warnings

DEFAULT_DIR = os.path.expanduser("~/.cache/malay-tts/VITS-yasmin")
SPEED = 1.1          # a little slower than conversation (VITS length scale), so a child hears every sound
_SYMBOLS = (["pad", "start", "eos"] + list("-") + list("!'(),.:;? ")
            + list("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
# where this voice's vowels sit (F1, F2 in Hz), measured on clear words (apa, betul, ekor, ikan, otak, itu,
# susu, madu, ibu): u and o differ mostly in height, u's F1 about 360, o's about 470
VOWELS = {"a": (870, 1550), "e": (510, 1750), "ee": (490, 2550), "i": (310, 2700), "o": (470, 980), "u": (365, 950)}


class Voice:
    def __init__(self, model_dir=DEFAULT_DIR):
        import torch
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from malay_vits.model_infer import SynthesizerTrn
        cfg = json.load(open(os.path.join(model_dir, "config.json")))
        d, t, m = cfg["data"], cfg["train"], cfg["model"]
        self.net = SynthesizerTrn(len(_SYMBOLS), d["filter_length"] // 2 + 1, t["segment_size"] // d["hop_length"],
                                  n_speakers=0, **m).eval()
        self.net.load_state_dict(torch.load(os.path.join(model_dir, "model.pth"), map_location="cpu"))
        self.sr = d["sampling_rate"]
        self.last_take = self.last_raw = None

    def say(self, text, speed=SPEED):
        """Malay text -> samples. Deterministic (no sampling noise), so a clip never changes by chance."""
        import numpy as np
        import torch
        s = re.sub(r"[ ]+", " ", text.replace("é", "e").replace("É", "E")).strip()
        if s[-1] not in ".,?!":
            s += " ."
        ids = [_SYMBOLS.index(c) for c in s if c in _SYMBOLS]
        x = [0] * (2 * len(ids) + 1)
        x[1::2] = ids                      # a blank between symbols, as the model was trained
        t = torch.LongTensor(x).unsqueeze(0)
        with torch.no_grad():
            a = self.net.infer(t, torch.LongTensor([t.size(1)]), noise_scale=0.0, noise_scale_w=0.0,
                               length_scale=speed)[0][0, 0].numpy()
        return a.astype(np.float64)


# ---------- measuring ----------
def _mv():
    import make_voice
    return make_voice


def runs(F, pred, start=0, end=None):
    end = len(F) if end is None else end
    out, i = [], start
    while i < end:
        if pred(F[i]):
            j = i
            while j < end and pred(F[j]):
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def vowel_of(x, sr, a=None, b=None, closed=False):
    """(F1, F2, nearest Malay vowel) of the longest loud voiced stretch between samples a and b. For a closed
    syllable (kul, bun) only the start of that stretch is measured: its end is the m, n, l or r after it."""
    mv = _mv()
    F = mv.frames(x, sr)
    lo = 0 if a is None else next(i for i, f in enumerate(F) if f["s"] >= a)
    hi = len(F) if b is None else max(i for i, f in enumerate(F) if f["s"] <= b) + 1
    rs = runs(F, lambda f: f["voiced"] and f["db"] > -15, lo, hi)
    if not rs:
        return None
    i, j = max(rs, key=lambda r: r[1] - r[0])
    n = j - i
    if closed:
        j, n = i + max(4, n * 3 // 5), max(4, n * 3 // 5)
    f1, f2 = mv.formants_at(x, sr, F[i + n // 4]["s"], F[j - 1 - n // 4]["s"])
    return f1, f2, min(VOWELS, key=lambda v: mv.vowel_dist((f1, f2), VOWELS[v]))


def peak_vowels(x, sr, cuts):
    """(F1, F2, nearest Malay vowel) of each cut syllable [(a, b), ...], measured only where that syllable
    is loudest and open (within 4 dB of its peak, not on the hum of m, n, ng, l): the vowel itself, not
    the consonants around it. None for a syllable with no voice."""
    import numpy as np
    import parselmouth
    mv = _mv()
    F = mv.frames(x, sr)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fm = parselmouth.Sound(np.asarray(x, np.float64), sr).to_formant_burg(
            time_step=.005, max_number_of_formants=5, maximum_formant=5500)
    out = []
    for a, b in cuts:
        idx = [i for i, f in enumerate(F) if a <= f["s"] < b and f["voiced"]]
        if not idx:
            out.append(None)
            continue
        top = max(F[i]["db"] for i in idx)
        sel = ([i for i in idx if F[i]["db"] >= top - 4 and F[i]["mid"] >= .06]
               or [i for i in idx if F[i]["db"] >= top - 4])
        f1 = float(np.nanmedian([fm.get_value_at_time(1, F[i]["s"] / sr) for i in sel]))
        f2 = float(np.nanmedian([fm.get_value_at_time(2, F[i]["s"] / sr) for i in sel]))
        out.append((f1, f2, min(VOWELS, key=lambda v: mv.vowel_dist((f1, f2), VOWELS[v]))))
    return out


def vowel_ok(v, want):
    """Is a measured vowel (F1, F2, nearest) one of `want`? After d, t, n, g, k or y the tongue pulls o and u
    forward (F2 rises towards 1400 Hz: donat, gorila), so a rounded vowel still well behind the pepet
    (F2 under 1550 Hz, the pepet sits at 1750) of the right height counts as o or u."""
    if v is None:
        return False
    if v[2] in want:
        return True
    f1, f2 = v[0], v[1]
    if "o" in want and f2 < 1550 and 400 <= f1 <= 580:
        return True
    if "u" in want and f2 < 1550 and f1 < 420:
        return True
    return False


def trim(x, sr, floor=-40):
    """Cut leading and trailing silence (keeping 10 ms), and any stray noise the voice adds after a pause
    at the end ("teh ." can come out as "teh … s"). A word's own last sound (a final h, s, or the release
    of t and k) follows its vowel without a pause, so it stays."""
    import numpy as np
    w = int(.01 * sr)
    e = np.array([np.sqrt(np.mean(x[i:i + w] ** 2)) + 1e-9 for i in range(0, len(x) - w, w)])
    db = 20 * np.log10(e / e.max())
    on = np.where(db > floor)[0]
    x = x[max(0, (on[0] - 1) * w):min(len(x), (on[-1] + 2) * w)]
    mv = _mv()
    F = mv.frames(x, sr)
    voiced = [i for i, f in enumerate(F) if f["voiced"] and f["db"] > -30]
    if voiced:
        quiet = 0
        for i in range(voiced[-1] + 1, len(F)):
            quiet = quiet + 1 if F[i]["c"] == "_" else 0
            if quiet >= 6:                         # 30 ms of silence: the word is over
                return x[:F[i - 5]["s"] + int(.01 * sr)]
    return x


def fade(x, sr, start=.005, end=.03):
    import numpy as np
    x = x.copy()
    a, b = int(start * sr), int(end * sr)
    x[:a] *= np.linspace(0, 1, a)
    x[-b:] *= np.linspace(1, 0, b)
    return x


# ---------- h ----------
# This voice says h very lightly: at the start of a word only 5-50 ms of faint breath (hotel comes out as
# "otel"), and at the end after i or e hardly any (benih as "beni"). A child learning that the letter h makes
# a sound must hear it, so a weak h is replaced by a clear one: breath in the colour of its own vowel (noise
# shaped by that vowel's formants), which is what h is.
def _breath_of(vowel, sr, seconds, level, band=(300, 5000), tilt=.6):
    import numpy as np
    from scipy.signal import butter, lfilter, sosfiltfilt
    mv = _mv()
    b = mv.stretch_noise(lfilter([1, -tilt], [1], vowel), sr, seconds)
    b = sosfiltfilt(butter(4, list(band), "band", fs=sr, output="sos"), b)
    return b * np.sqrt(np.mean(vowel ** 2)) * 10 ** (level / 20) / max(1e-12, np.sqrt(np.mean(b ** 2)))


def h_start(x, sr, seconds=.085, level=-17):
    """x (a word or syllable spelled with h first) with a clear h before its first vowel."""
    import numpy as np
    mv = _mv()
    F = mv.frames(x, sr)
    s0 = mv.first_sound(F)
    v0 = next(i for i in range(s0, len(F)) if F[i]["voiced"] and F[i]["db"] > -25)
    vs = F[v0]["s"]
    loud = next((i for i in range(v0, len(F)) if F[i]["db"] > -8), v0)       # the vowel at full voice
    vowel = x[F[loud]["s"]:F[loud]["s"] + int(.05 * sr)]
    # an h is turbulence at the throat: the vowel's formants, but with more of its upper part than the voice
    breath = _breath_of(vowel, sr, seconds, level, band=(400, 6500), tilt=.9)
    n, rise, k = len(breath), int(.015 * sr), int(.02 * sr)
    env = np.ones(n)
    env[:rise] = np.linspace(0, 1, rise)
    env[-k:] = np.linspace(1, .3, k)
    voice = x[vs:].copy()
    voice[:k] *= np.linspace(.2, 1, k)
    out = np.r_[breath * env, np.zeros(len(voice) - k)]
    out[n - k:] += voice
    return out


def h_end(x, sr):
    """x (spelled with h last) with a final h that can be heard. Kept as it is when the voice breathed one."""
    mv = _mv()
    F = mv.frames(x, sr)
    last = max(i for i, f in enumerate(F) if f["voiced"] and f["db"] > -25)
    breath = [f for f in F[last + 1:last + 30] if not f["voiced"] and f["db"] > -26]
    if len(breath) >= 8:
        return x
    return mv.bm_breathe(x, sr, seconds=.14, level=-11)


def with_h(x, sr, text):
    """Make the h of a word or syllable heard, wherever the spelling has h at the start or end."""
    t = text.lower().strip(" .!?")
    if t.endswith("h") and not t.endswith(("sh", "kh", "gh")):
        x = h_end(x, sr)
    if t.startswith("h"):
        x = h_start(x, sr)
    return x


# ---------- cutting syllables out of real words ----------
VOWEL_LETTERS = "aeiou"


def split_syllables(text):
    """Malay syllables: V.CV, VC.CV, V.V; ng ny sy kh gh count as one letter; final ai au oi is one vowel."""
    u, i = [], 0
    while i < len(text):
        two = text[i:i + 2]
        u.append(two if two in ("ng", "ny", "sy", "kh", "gh") else text[i])
        i += len(u[-1])
    isv = lambda c: c in VOWEL_LETTERS
    nuc = [i for i, c in enumerate(u) if isv(c)]
    n = len(u)
    if n >= 2 and isv(u[-1]) and isv(u[-2]) and u[-2] + u[-1] in ("ai", "au", "oi"):
        nuc.pop()
    out, start = [], 0
    for k, v in enumerate(nuc):
        end = n if k == len(nuc) - 1 else v + 1 + max(0, nuc[k + 1] - v - 2)
        out.append("".join(u[start:end]))
        start = end
    return out


def _onset(syl):
    c = syl[:2] if syl[:2] in ("ng", "ny", "sy", "kh", "gh") else syl[:1]
    return "" if c in VOWEL_LETTERS else c


def cut_syllables(x, sr, syls, dips=(3, 2, 1.5)):
    """Sample bounds [(a, b), ...] of each syllable of a word said by the voice, found from its loudness:
    one loud voiced peak per syllable, split where the next syllable's consonant begins (the closure of
    p t k c, the hiss of s sy h kh f, the lowest point before b d g j, the start of the hum of m n ng ny,
    l r w y). Silence inside a stop is dropped. None when the word doesn't show one peak per syllable."""
    import numpy as np
    mv = _mv()
    F = mv.frames(x, sr)
    db = np.array([f["db"] for f in F])
    sm = np.convolve(db, np.ones(5) / 5, "same")
    voiced = np.array([f["voiced"] for f in F])
    on = mv.first_sound(F)
    off = max(i for i, f in enumerate(F) if f["c"] != "_")
    # syllable peaks: the loudest voiced frame of each stretch between dips of 3 dB or voiceless gaps
    cand = [i for i in range(on + 1, off) if voiced[i] and sm[i] >= sm[i - 1] and sm[i] > sm[i + 1] and sm[i] > -20]
    for need in dips:     # two vowels side by side (ku.at) dip only a little
        peaks = []
        for c in cand:
            if peaks:
                p = peaks[-1]
                gap = not all(voiced[p:c + 1])
                dip = min(sm[p:c + 1])
                if not gap and min(sm[p], sm[c]) - dip < need:
                    if sm[c] > sm[p]:
                        peaks[-1] = c
                    continue
            peaks.append(c)
        if len(peaks) >= len(syls):
            break
    if len(peaks) != len(syls):
        return None
    bounds = [F[on]["s"] - int(.01 * sr)]
    ends = []
    for k in range(1, len(syls)):
        p, q = peaks[k - 1], peaks[k]
        c = _onset(syls[k])
        if c in ("p", "t", "k", "c"):
            quiet = [i for i in range(p, q) if not voiced[i]]
            if not quiet:
                return None
            closure = quiet[0]
            burst = next((i for i in range(closure, q) if F[i]["c"] in "sh" and sm[i] > sm[closure] + 3), closure)
            ends.append(F[closure]["s"])
            bounds.append(F[burst]["s"] - int(.008 * sr))
            continue
        if c in ("s", "sy", "h", "kh", "f"):
            noise = next((i for i in range(p, q) if not voiced[i] or mv.buzz(F[i])), None)
            if noise is None:
                return None
            ends.append(F[noise]["s"])
            bounds.append(F[noise]["s"])
            continue
        dip = min(range(p, q + 1), key=lambda i: sm[i])
        if c in ("b", "d", "g", "j", ""):
            cut = dip
        else:   # m n ng ny l r w y: where the voice first drops towards the dip
            cut = next((i for i in range(p, dip + 1) if sm[i] < sm[dip] + 3), dip)
        ends.append(F[cut]["s"])
        bounds.append(F[cut]["s"])
    ends.append(F[off]["s"] + int(.03 * sr))
    return [(a, b) for a, b in zip(bounds, ends)]


def syllable_clip(x, sr, a, b, hold=None):
    """One cut syllable, with soft edges; an open syllable's vowel can be held to `hold` seconds."""
    seg = x[max(0, a):b]
    if hold and len(seg) / sr < hold:
        return hold_vowel(seg, sr, hold)
    return fade(seg, sr, end=.03)


def hold_vowel(seg, sr, seconds):
    """An open syllable with its vowel held: the steady middle of the vowel (its loudest stretch) is
    lengthened, and the syllable ends there, softly, before the mouth starts to move towards whatever
    came next in the word (holding that would turn ke- of kebun into "keu")."""
    import numpy as np
    mv = _mv()
    F = mv.frames(seg, sr)
    vo = [i for i, f in enumerate(F) if f["voiced"]]
    if not vo:
        return fade(seg, sr, end=.03)
    top = max(F[i]["db"] for i in vo)
    peak = max(vo, key=lambda i: F[i]["db"])
    i0 = peak
    while i0 > 0 and F[i0 - 1]["voiced"] and F[i0 - 1]["db"] >= top - 4:
        i0 -= 1
    i1 = peak
    while i1 + 1 < len(F) and F[i1 + 1]["voiced"] and F[i1 + 1]["db"] >= top - 4:
        i1 += 1
    q = (i1 - i0) // 4
    m0, m1 = F[i0 + q]["s"], F[i1 - q]["s"]
    if m1 - m0 < .04 * sr:              # a short vowel (pepet): hold all of its loud part
        m0, m1 = F[i0]["s"], F[i1]["s"]
    if m1 - m0 < .04 * sr:              # still too little to hold: 40 ms around its loudest point
        c = F[peak]["s"]
        m0, m1 = max(0, c - int(.02 * sr)), min(len(seg), c + int(.02 * sr))
    head = seg[:m0]
    held = mv.stretch_voice(seg[m0:m1], sr, max((m1 - m0) / sr, seconds - m0 / sr))
    k = int(.008 * sr)
    if len(head) < k:                   # the clip starts on the vowel itself
        return fade(held, sr, start=.01, end=.07)
    w = np.linspace(1, 0, k)
    out = np.r_[head[:-k], head[-k:] * w + held[:k] * (1 - w), held[k:]]
    return fade(out, sr, end=.07)


def first_syllable(x, sr, nasal_next=False):
    """(start, end, vowel start) samples of a word's first open syllable (used for vowel sounds)."""
    mv = _mv()
    F = mv.frames(x, sr)
    s0 = mv.first_sound(F)
    loud = runs(F, lambda f: f["voiced"] and f["db"] > -18, s0)
    if not loud:
        return None
    i, j = loud[0]
    if nasal_next:
        v = next((k for k in range(i, j) if F[k]["mid"] >= .06), i)
        j = next((k for k in range(v + 4, j) if F[k]["mid"] < .035), j)
    return F[s0]["s"] - int(.01 * sr), F[j - 1]["s"] + int(.004 * sr), F[i]["s"]


def check_vowel(x, sr, want, closed=False):
    """Is the syllable's vowel the right one? want: a e(pepet) ee(taling) i o u, or a set of them."""
    got = peak_vowels(x, sr, [(0, len(x))])[0]
    return vowel_ok(got, want if isinstance(want, (set, tuple)) else (want,)), got


def vowel_letter(syl, pepet=True):
    v = next(c for c in syl if c in VOWEL_LETTERS)
    return "e" if v == "e" and pepet else ("ee" if v == "e" else v)


# Where each syllable can be taken from, best first: a word ending in it (the last syllable of a word is
# said fully, with a natural fall) or a word starting with it (pepet e never ends a word). Words where the
# vowel is clear in this voice were chosen by measuring it (o, for one, drifts towards e before c, d and l).
LAST_IN = {
    "pa": ["apa"], "pi": ["api"], "pu": ["sapu"], "ta": ["kata"], "ti": ["hati"], "tu": ["itu"],
    "ka": ["suka"], "ki": ["kaki"], "ku": ["aku"], "ca": ["baca"], "ci": ["kunci"], "cu": ["cucu"],
    "sa": ["rasa"], "si": ["nasi"], "su": ["susu"], "hu": ["tahu"], "bu": ["ibu"], "du": ["madu"],
    "gu": ["lagu", "ragu", "tugu"], "lu": ["malu"], "mu": ["kamu"], "nu": ["menu"], "ru": ["guru"], "da": ["ada"],
    "di": ["padi"], "ga": ["juga"], "gi": ["lagi"], "la": ["kala"], "li": ["kali"], "ma": ["lama"],
    "mi": ["kami"], "na": ["bina"], "ni": ["ini"], "ra": ["kira"], "ri": ["lari"], "at": ["buat", "kuat"],
    "kul": ["pukul"], "bun": ["sabun"],
}
FIRST_IN = {
    "be": ["betul"], "ce": ["cepat"], "de": ["dekat"], "ge": ["getah", "gelas", "gemuk", "gelap"], "ke": ["kecil"], "le": ["lepas"],
    "me": ["menang"], "ne": ["nelayan"], "pe": ["pecah"], "re": ["retak"], "se": ["sepuluh"], "te": ["tepat"],
    "bo": ["botol"], "co": ["comel", "colek", "cokelat"], "do": ["dosa", "dodol"], "go": ["gosip", "gotong", "gosok"],
    "ho": ["hotel"], "ko": ["kotak"], "lo": ["lori", "loceng"], "mo": ["motor"], "no": ["nota"], "po": ["pokok"],
    "ro": ["roti"], "so": ["sotong"], "to": ["topi"], "hi": ["hitam"], "ki": ["kita"], "mi": ["misi"],
    "ni": ["nipis"], "pi": ["pisang"], "si": ["sikat"], "li": ["lipas"], "ru": ["rusa"],
    "at": ["atlet", "atlas"],
}


def syllable(voice, syl, own=None):
    """One syllable as this voice says it: (samples, where it came from, problem). Tries, in order: the
    syllable in the word it belongs to (own: the word's chosen take and the syllable's bounds), the syllable
    said on its own, the end of a word that ends in it, the start of a word that starts with it; each in a
    few takes (see TAKES). The vowel is checked on the syllable as cut, before an open vowel is held."""
    sr = voice.sr
    want = vowel_letter(syl)
    closed = syl[-1] not in VOWEL_LETTERS
    hold = None if closed else .30
    sources = []
    if own is not None:
        sources.append(("own word", lambda: [own]))
    if not (len(syl) == 2 and want in ("e", "u", "o")) and syl != "at":
        # (on their own the voice reads those as letter names: be "bee", su "syu", at "ay-tee")
        sources.append(("said", lambda: _said_takes(voice, syl)))
    for w in LAST_IN.get(syl, []):
        sources.append(("end of " + w, lambda w=w: _cut_takes(voice, w, -1)))
    for w in FIRST_IN.get(syl, []):
        sources.append(("start of " + w, lambda w=w: _cut_takes(voice, w, 0)))
    tried = []
    for how, takes in sources:
        last = None
        for x, (a, b) in takes():
            ok, got = check_vowel(x[max(0, a):b], sr, want, closed=closed)
            if ok and onset_problem(x[max(0, a):b], sr, syl):
                ok, got = False, (0, 0, onset_problem(x[max(0, a):b], sr, syl))
            if ok:
                clip = fade(with_h(syllable_clip(x, sr, a, b, hold), sr, syl), sr, end=.03)
                ok, got = check_vowel(clip, sr, want, closed=closed)     # and again as it will be heard
                if ok:
                    return clip, how, ""
            last = got
        tried.append(f"{how}: {last and last[2]}")
    for w in BREATH_ONTO.get(syl, []):
        for x, (a, b) in _cut_takes(voice, w, 0):
            v = _vowel_only(x[max(0, a):b], sr)
            if v is not None and check_vowel(v, sr, want)[0]:
                held = syllable_clip(v, sr, 0, len(v), hold)
                return fade(h_start(held, sr), sr, end=.03), "h + vowel of " + w, ""
        tried.append("h + vowel of " + w)
    return None, "", "; ".join(tried) or "no way to make it"


# This voice says every he- word with taling e (helang as "hélang"), so the pepet "he" is made as h breathed
# onto the pepet vowel of another syllable.
BREATH_ONTO = {"he": ["tepat", "kecil"]}


def _vowel_only(x, sr):
    """A syllable without its first consonant: from where its vowel is voiced and steady."""
    mv = _mv()
    F = mv.frames(x, sr)
    v0 = next((i for i, f in enumerate(F) if f["voiced"] and f["db"] > -20), None)
    return None if v0 is None else x[F[v0]["s"] + int(.015 * sr):]


def _said_takes(voice, syl):
    """The syllable said on its own, in each take: (samples, (start, end))."""
    for end, speed in TAKES:
        x = trim(voice.say(syl + end, speed=speed), voice.sr)
        yield x, (0, len(x))


def _cut_takes(voice, word, which):
    """Syllable number `which` of `word`, in each take that can be cut: (samples, (start, end)). Last, the
    word said after "ada": there a first b, d or g is voiced all through, as it should be."""
    syls = split_syllables(word)
    for end, speed in TAKES:
        x = trim(voice.say(word + end, speed=speed), voice.sr)
        cuts = cut_syllables(x, voice.sr, syls)
        if cuts:
            yield x, cuts[which]
    for end in (" .", "!"):
        x = trim(voice.say("ada " + word + end), voice.sr)
        cuts = cut_syllables(x, voice.sr, ["a", "da"] + syls)
        if cuts:
            yield x, cuts[2:][which]


def word_syllables(voice, word, ph=None):
    """{syllable: (samples, (start, end))} of `word` in the take word() keeps (empty if it can't be cut)."""
    word_take(voice, word, ph)
    x, cuts = voice.last_raw
    if not cuts:
        return {}
    out = {}
    for s, c in zip(split_syllables(word), cuts):
        out.setdefault(s, (x, c))
    return out


# ---------- letter sounds ----------
LETTER_SOUNDS = {
    # vowels: the vowel at the start of a real word (before p, k or t, so it ends cleanly), held
    "a": ("vowel", "apa", "a"), "e": ("vowel", "tepat", "e"), "ee": ("vowel", "ekor", "ee"),
    "i": ("vowel", "ikan", "i"), "o": ("vowel", "otak", "o"), "u": ("vowel", "upah", "u"),
    # diphthongs: the end of a real word
    "ai": ("glide", "pantai", "ai"), "au": ("glide", "pisau", "au"), "oi": ("glide", "sepoi", "oi"),
    # consonants said with a short "eh", as in the phonics module: [beh], [ceh] ...
    # (this voice says z voiceless when it is held, so z is said like the others: [zeh])
    **{c: ("eh", c + "eh", None) for c in ["b", "c", "d", "g", "h", "j", "k", "p", "r", "t", "w", "y", "z",
                                             "ny", "sy", "kh"]},
    # sounds that can be held; ng is held and then opens into its vowel, or it would sound like n
    "s": ("hiss", "sapu", .45), "f": ("hiss", "fail", .45), "m": ("hum", "mata", .45), "n": ("hum", "nasi", .45),
    "l": ("hum", "lama", .42), "ng": ("nasal", "ngeri", .42),
}


def letter_sound(voice, sid):
    """One bunyi huruf: (samples, problem)."""
    import numpy as np
    mv = _mv()
    kind, src, arg = LETTER_SOUNDS[sid]
    sr = voice.sr
    x = voice.say(src)
    F = mv.frames(x, sr)
    if kind == "vowel":
        cut = first_syllable(x, sr)
        if cut is None:
            return None, "no vowel"
        a, b, v = cut
        got = vowel_of(x, sr, v, b)
        if got is None or got[2] != arg:
            return None, f"{src}: first vowel heard as {got and got[2]}"
        seg = x[v + (b - v) // 5:b]
        return fade(mv.stretch_voice(seg, sr, .42), sr, start=.02, end=.08), ""
    if kind == "glide":
        loud = runs(F, lambda f: f["voiced"] and f["db"] > -25)
        i, j = loud[-1]
        if j - i < 15:
            return None, "glide too short"
        seg = x[F[i]["s"]:F[j - 1]["s"]]
        return fade(mv.stretch_voice(seg, sr, .40), sr, start=.01, end=.07), ""
    if kind == "eh":
        tried = []
        for end, speed in TAKES:
            y = trim(voice.say(src + end, speed=speed), sr)
            ok, got = check_vowel(y, sr, ("ee", "e"))
            cons = onset_problem(y, sr, src)
            if ok and not cons:
                return fade(with_h(y, sr, src), sr), ""
            tried.append(f"{end.strip()}@{speed}: {cons or (got and got[2])}")
        return None, f"'{src}': " + "; ".join(tried)
    s0 = mv.first_sound(F)
    if kind == "hiss":
        rs = runs(F, lambda f: not f["voiced"] and f["c"] in "sh" and f["db"] > -35, s0)
        if not rs or rs[0][1] - rs[0][0] < 6:
            return None, "hiss too short"
        i, j = rs[0]
        seg = x[F[i]["s"]:F[j - 1]["s"]]
        return fade(mv.stretch_noise(seg, sr, arg), sr, start=.02, end=.06), ""
    if kind == "hum":
        v0 = next(i for i in range(s0, len(F)) if F[i]["voiced"])
        w = next((i for i in range(v0, len(F) - 3) if all(F[k]["voiced"] and F[k]["mid"] >= .06 for k in range(i, i + 3))), None)
        if w is None or w - v0 < 6:
            return None, "hum too short"
        seg = x[F[v0 + 1]["s"]:F[w - 1]["s"]]
        return fade(mv.stretch_voice(seg, sr, arg), sr, start=.02, end=.06), ""
    if kind == "nasal":
        v0 = next(i for i in range(s0, len(F)) if F[i]["voiced"])
        w = next((i for i in range(v0, len(F) - 3) if all(F[k]["voiced"] and F[k]["mid"] >= .06 for k in range(i, i + 3))), None)
        if w is None or w - v0 < 6:
            return None, "hum too short"
        hum = mv.stretch_voice(x[F[v0 + 1]["s"]:F[w - 2]["s"]], sr, arg - .08)
        slide = x[F[w - 2]["s"]:F[w - 2]["s"] + int(.09 * sr)]
        k = int(.01 * sr)
        r = np.linspace(1, 0, k)
        out = np.r_[hum[:-k], hum[-k:] * r + slide[:k] * (1 - r), slide[k:]]
        return fade(out, sr, start=.02, end=.05), ""
    if kind == "buzz":
        rs = runs(F, mv.buzz, s0)
        if not rs or rs[0][1] - rs[0][0] < 5:
            return None, "too little buzz"
        i, j = max(rs, key=lambda r: r[1] - r[0])
        seg = x[F[i]["s"]:F[j - 1]["s"]]
        return fade(mv.stretch_buzz(seg, sr, arg), sr, start=.02, end=.06), ""
    raise ValueError(kind)


# The voice decides between pepet and taling e (and sometimes how open a vowel is) from the whole text it
# is given, and not always the same way: "lebah ." comes out as "lébah" but "lebah!" as "ləbah". So a word
# is said a few ways, and of the takes whose every vowel is the dictionary's, the clearest is kept.
TAKES = [(" .", SPEED), ("!", SPEED), (",", SPEED), (" !", SPEED), ("?", SPEED), (".", SPEED),
         (" .", 1.0), ("!", 1.0), (" .", 1.25), ("!", 1.25), (",", 1.25)]
_IPA = {"ə": "e", "ɨ": "e", "e": "ee", "ɛ": "ee", "a": "a", "ɑ": "a", "i": "i", "ɪ": "i", "o": "o", "ɔ": "o",
        "u": "u", "ʊ": "u"}


def expected_vowels(word, ph=None):
    """The vowel of each syllable, from the dictionary pronunciation (IPA: ə pepet, e taling) when given;
    from the spelling otherwise, where a plain e may be either (é is taling). A final ai, au, oi counts
    by its first vowel."""
    syls = split_syllables(word.replace("é", "e"))
    if ph:
        p = re.sub(r"[ˈˌː]", "", ph)
        vs = [_IPA[c] for c in p if c in _IPA]
        if len(vs) == len(syls) + 1 and re.search(r"(ai|au|oi|aj|aw|oj)$", p):
            vs = vs[:-1]
        if len(vs) == len(syls):
            return [{v} for v in vs]
    out, k = [], 0
    for syl in syls:
        v = vowel_letter(syl)
        at = word.find(syl[0], k)
        taling = "é" in word[max(0, at):at + len(syl) + 1]
        out.append({"ee"} if taling else {"e", "ee"} if v == "e" else {v})
        k = at + 1
    return out


def take_score(x, sr, word, expect):
    """(wrong vowels, distance from the right ones) for one take of a word; None if it can't be cut."""
    syls = split_syllables(word.replace("é", "e"))
    cuts = cut_syllables(x, sr, syls)
    if not cuts:
        return None
    mv = _mv()
    wrong, dist, got = 0.0, 0.0, []
    for k, (syl, want, v) in enumerate(zip(syls, expect, peak_vowels(x, sr, cuts))):
        if v is None:
            return None
        got.append(v)
        if vowel_ok(v, want):
            dist += min(mv.vowel_dist(v[:2], VOWELS[w]) for w in want)
            continue
        # a final closed i or u said a little lower (kucing as "kuceng", hidung as "hidong") is how
        # Malaysians say it, so it costs less than a wrong vowel
        low = {"i": "ee", "u": "o"}
        lowered = k == len(syls) - 1 and syl[-1] not in VOWEL_LETTERS and any(low.get(w) == v[2] for w in want)
        wrong += .5 if lowered else 1
        dist += min(mv.vowel_dist(v[:2], VOWELS[w]) for w in want)
    return wrong, dist, got


def onset_problem(x, sr, word):
    """How a word's first consonant goes wrong in this voice, if it does: b d g j said without voice
    and with a puff of breath (gajah heard as "kajah"), or p t k with a long English-like puff. ""=fine."""
    c = _onset(split_syllables(word)[0])
    if c not in ("b", "d", "g", "j", "p", "t", "k"):
        return ""
    mv = _mv()
    F = mv.frames(x, sr)
    s0 = mv.first_sound(F)
    # the vowel at full voice (a voice bar can be nearly as loud, so three loud voiced frames in a row)
    v0 = next((i for i in range(s0, len(F) - 2) if all(F[j]["voiced"] and F[j]["db"] > -9 for j in range(i, i + 3))), None)
    if v0 is None:
        return "no vowel"
    pre = F[s0:v0]
    bar = sum(1 for f in pre if f["voiced"])                   # voicing held through the closure
    puff = sum(1 for f in pre if not f["voiced"] and f["c"] in "sh")
    hiss = sum(1 for f in pre if not f["voiced"] and f["c"] == "s")
    high = vowel_letter(split_syllables(word)[0]) in ("i", "u")
    if c in ("b", "d", "g"):
        # gigi said as "jigi": a hiss after the release (a little is natural before i and u)
        if hiss > (6 if high else 4):
            return f"{c} with a hiss ({hiss * 5} ms)"
        return "" if bar >= 3 or puff <= 3 else f"{c} without voice ({puff * 5} ms of breath)"
    if c == "j":
        return "" if bar >= 3 or puff <= 6 else f"j without voice ({puff * 5} ms of breath)"
    # (before i and u the release is naturally longer)
    most = 12 if high else 8
    return "" if puff <= most else f"{c} with a puff of breath ({puff * 5} ms)"


def word_take(voice, text, ph=None):
    """The best take of a word (see TAKES), trimmed, before its h is strengthened. Also sets
    voice.last_take (which take, and anything still not right) and voice.last_raw (samples, syllable cuts)."""
    w = re.sub(r"[^a-zé]", "", text.lower())
    expect = expected_vowels(w, ph)
    syls = split_syllables(w.replace("é", "e"))
    best = None
    for n, (end, speed) in enumerate(TAKES):
        x = trim(voice.say(text.rstrip(".!?, ") + end, speed=speed), voice.sr)
        sc = take_score(x, voice.sr, w, expect)
        if sc is None:
            continue
        cons = onset_problem(x, voice.sr, w)
        # every take is heard out: of those with all vowels right, the one whose vowels sit closest to
        # the voice's own clear vowels (pokok with two full o's, not the second drifting towards u);
        # a slight preference for the plainer readings, which come first
        key = (sc[0] + (1 if cons else 0), sc[1] + .04 * n)
        if best is None or key < best[0]:
            best = (key, x, f"{end.strip()}@{speed}", sc[2], cons)
    if best is not None and best[0][0] > 0 and _onset(syls[0]) in ("p", "t", "k", "c", "s", "b", "d", "g", "j"):
        # Still a vowel off. Said after another word the voice is often more careful (kucing on its own
        # ends like "kuceng", in "ada kucing" it ends in i; gigi on its own starts with a hiss). A word that
        # starts with a stop or s can be lifted cleanly out of that phrase: the stop's closure (or the hiss)
        # marks where it begins.
        for lead in ("ada", "seekor"):
            for end in (" .", "!"):
                x = trim(voice.say(f"{lead} {w}{end}"), voice.sr)
                lead_n = len(split_syllables(lead))
                cuts = cut_syllables(x, voice.sr, split_syllables(lead) + syls)
                if not cuts:
                    continue
                x = x[max(0, cuts[lead_n][0] - int(.01 * voice.sr)):]
                sc = take_score(x, voice.sr, w, expect)
                if sc is None:
                    continue
                cons = onset_problem(x, voice.sr, w)
                key = (sc[0] + (1 if cons else 0), sc[1] + .3)
                if key < best[0]:
                    best = (key, x, f"after '{lead}'{end.strip()}", sc[2], cons)
    if best is None:      # can't be cut into syllables: keep the plain reading
        x = trim(voice.say(text), voice.sr)
        voice.last_take, voice.last_raw = ("plain", None), (x, None)
        return x
    _, x, how, got, cons = best
    bad = [f"{s}:{g[2]}" for s, g, e in zip(syls, got, expect) if not vowel_ok(g, e)]
    voice.last_take = (how, ", ".join(bad + ([cons] if cons else [])) or None)
    voice.last_raw = (x, cut_syllables(x, voice.sr, syls))
    return x


def word(voice, text, ph=None):
    """A whole word or cheer, as written, with every vowel checked and its h made clear."""
    x = word_take(voice, text, ph)
    return fade(with_h(x, voice.sr, re.sub(r"[^a-zé]", "", text.lower())), voice.sr)
