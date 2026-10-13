# Word Snap Showdown

Reading, maths and Bahasa Melayu games for a young reader and a grown-up, hosted by Luna the bunny. The home screen has **English**, **Maths** and **Bahasa** tabs.

### English

- **Word Snap**: Luna says a word and both players race to tap it on their own side. The grown-up's cards appear after an adjustable head start.
- **Robot Talk** (take turns): Luna says a word sound by sound ("c… a… t") and the player taps the matching picture.
- **Read & Match** (take turns): read the word silently, then tap its picture.

In the turn games the play area turns to face whoever's turn it is, so only one person touches the screen at a time. The young reader gets a second try; the grown-up has a countdown that auto-balances.

### Maths (take turns)

- **Count & Catch**: count the pictures, tap the number. The grown-up gets a bigger pile and only a quick look.
- **Make Ten**: carrots in a ten-frame basket; how many more make 10 (or 20)? The grown-up makes 100.
- **Sum Snap**: add and take away with pictures to count. The grown-up gets two-digit sums.
- **Bunny Hop**: a race board. Roll the dice, count on, and tap the square you'll land on; carrot squares give 2 extra hops. She always hops; the grown-up only hops if he answers in time.

After her first wrong tap, Luna counts along with her and she tries again. Every right answer pays out a star, a prize flying into her bar and a number sticker, and answers in a row win bonus stars. Settings → **Maths numbers** switches between numbers up to 10 and up to 20.

### Bahasa (take turns, plus a practice test)

This week's Bahasa Melayu spelling (ejaan) words, learnt by suku kata the way school teaches them. Edit the list in Settings → **Bahasa Melayu spelling words** (one word per line, optional "= meaning").

- **Suku Kata**: hear the word, see its picture, build it from syllable tiles. Wrong tiles include the spellings children often write (kebon for kebun, beneh for benih).
- **Eja!**: spell it letter by letter into boxes grouped by syllable. Every letter she taps says its Malay sound, and each finished syllable is blended ("k… e… ke"). ng, ny, sy and kh are one tile each, because they are one sound. A wrong tap sounds out the syllable she's on; after two, Luna says the sound she needs and the right tile glows.
- **Cari Gambar**: read the Malay word, tap its picture; Luna says what it means in English.
- **Ujian Ejaan**: Luna reads each word (then syllable by syllable), she writes it on paper, taps Check, and the grown-up marks ✓ or ✗. Missed words come back at the end.

- **Bunyi Huruf** (button under the games): the Malay letter-sound chart. Tap a letter to hear its sound, then a word with it (a… ayam, ny… nyamuk). It's also in Settings.

Bahasa Melayu has its own phonics, so it never uses the English letter sounds: a is always "a" as in *ayam*; e is the soft pepet of *emak* (or the é of *merah*, the taling); i, o and u are pure; c is "ch"; g is always hard; r is rolled; a final h is breathed; p, t and k have no puff of air; ng, ny, sy and kh are single sounds; ai, au and oi glide. When typing a new word with a taling e, write é (e.g. "mérah = red").

The recorded words use a separate Malay voice; words added later are read by the tablet's own Malay voice (Settings can also switch every Malay word to that voice).

### Sticker book

Every word or number she gets right becomes a sticker in her sticker book, which grows prettier as it fills: plain → rainbow → ribbon → sparkly → jewels → royal → magic gold. Words she misses come back more often.

### Saving the sticker book

Stickers are saved on each tablet and, once a family code is set up, online in a free Firebase Realtime Database (Spark plan, Singapore). On the first tablet: Settings → **Create a family code**. On the other tablet: type that code → **Connect**. Each tablet saves its own stickers under the code and the book adds every tablet's stickers together, so tablets never overwrite each other. The database rules only allow reading or writing a book by its exact 12-character code, and only sticker data in the expected shape. Settings also offers **Save a backup file** / **Restore from a file**; restoring never removes stickers.

## Play

**Game link:** https://cktan9830.github.io/english-game-with-6-years-old/

Open the game link in the tablet's browser, then add it to the home screen:

- **iPad:** Safari → Share → **Add to Home Screen**
- **Android:** Chrome → ⋮ menu → **Add to Home screen** / **Install app**

Open it once while online. After that it works offline.

## How it's hosted

GitHub Pages serves this repository's `main` branch. Every push to `main` updates the live game within a minute or two.

## Luna's voice

Luna's cheers, every reading word and every number from 0 to 100 are pre-recorded clips in `audio/`, made with the open Kokoro text-to-speech model (voice `af_heart`, pitched up for a cute, child-like sound at normal speed). If a clip can't play, the game falls back to the device's own voice.

The Bahasa Melayu words, syllables, cheers and letter sounds use a different voice: Kokoro has no Malay voice, and its Hindi voice (`hf_alpha`) is the closest to Malay: p, t and k without English's puff of air, pure vowels and a true pepet. It speaks hand-written Malay phonemes. That voice tends to hum before a word and to let a tiny echo vowel out after a final p, t or k; the script cuts both off, breathes a clear final h onto words like *tanah* and *benih* (the voice drops it, or says "ah" as "eh"), and keeps the cleanest of several takes. The Malay letter sounds are cut from Malay syllables the same way as the English ones; for each vowel the take whose formants sit closest to the Malay vowel is kept. Malay r is rolled, which no voice does, so the r sound is a held pepet broken by quick tongue taps.

Reading words, numbers and the letter sounds are in British English, the way phonics is taught in Malaysian schools ("o" as in "on", "a" as in "ant"). Each letter sound is cut out of a real word at the exact frames where that sound is, so consonants are pure (no "buh" or "kah") and every vowel is the right short vowel; the script checks each one (voicing, vowel shape, length) and also re-takes any word that would start with a stray "uh". Settings → **Letter sounds** plays every sound with a word that has it.

To change a line, edit the `<script id="lines">` block in `index.html`, then re-record from the repository root:

```
pip install kokoro-onnx soundfile praat-parselmouth scipy
python3 tools/make_voice.py
```

Only clips whose text changed are re-recorded. New words added to the word lists are recorded the same way.

## Files

| File | What it does |
|---|---|
| `index.html` | The whole game |
| `sw.js` | Keeps the game playable offline, including Luna's voice |
| `audio/` | Luna's recorded lines (`p/`), reading words (`w/`), letter sounds (`s/`), numbers (`n/`) and Bahasa Melayu words, syllables, cheers, meanings, letter sounds and their example words (`m/`) |
| `tools/make_voice.py` | Records the voice clips |
| `manifest.webmanifest` | App name, icon and full-screen setting |
| `fonts/` | Andika (reading font) and Grandstander (title font) |
| `icons/` | Home-screen icons |
