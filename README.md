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

- **Gabung!** (for blending two letters, the step before reading words): a train whose engine is a consonant and whose carriage is a vowel. Luna says a sound like "bu"; in easy rounds the engine shows b and she picks the carriage (u). After two clean answers in a row the rounds get harder: she finds the written "bu" among look-alikes (bo, du), which means reading each one. Every answer is blended out loud with the letters lighting up ("b… u… bu"), then a picture word that starts with it (buku 📖) becomes her sticker. A wrong pick is blended too, next to the right one ("That one says b… o… bo. We want b… u… bu."), and after two misses the right one glows. Each game uses three letter families (13 consonants × a i u e o), starting with the ones she found tricky.
- **Suku Kata**: hear the word, see its picture, build it from syllable tiles. Wrong tiles include the spellings children often write (kebon for kebun, beneh for benih).
- **Eja!**: spell it letter by letter into boxes grouped by syllable. Every letter she taps says its Malay sound, and each finished syllable is blended ("k… e… ke"). ng, ny, sy and kh are one tile each, because they are one sound. A wrong tap sounds out the syllable she's on; after two, Luna says the sound she needs and the right tile glows.
- **Cari Gambar**: read the Malay word, tap its picture; Luna says what it means in English.
- **Ujian Ejaan**: Luna reads each word (then syllable by syllable), she writes it on paper, taps Check, and the grown-up marks ✓ or ✗. Missed words come back at the end.

- **Bunyi Huruf** (button under the games): the Malay letter-sound chart. Tap a letter to hear its sound, then a word with it (a… ayam, ny… nyamuk). It's also in Settings.

Bahasa Melayu has its own phonics, so it never uses the English letter sounds: a is always "a" as in *ayam*; e is the soft pepet of *emak* (or the é of *merah*, the taling); i, o and u are pure; c is "ch"; g is always hard; r is rolled; a final h is breathed; p, t and k have no puff of air; ng, ny, sy and kh are single sounds; ai, au and oi glide. When typing a new word with a taling e, write é (e.g. "mérah = red").

The recorded words use a native Malaysian Malay voice (see below); words added later are read by the tablet's own Malay voice (Settings can also switch every Malay word to that voice).

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

The Bahasa Melayu words, syllables, cheers and letter sounds use a native Malaysian voice instead: Mesolitica's [VITS-yasmin](https://huggingface.co/mesolitica/VITS-yasmin), a text-to-speech model trained on Malaysian Malay speech (the voice code in `tools/malay_vits/` is MIT-licensed, from [malaya-speech](https://github.com/mesolitica/malaya-speech)). It reads ordinary Malay spelling, so it says pepet and taling e, rolled r and pure vowels the way a Malaysian does. Its model page doesn't state a licence for the voice itself, so the model isn't included here, only the clips made with it for this family game. Meta's MMS Malay voice was also tried and was understood less well. `tools/malay_voice.py` makes every Malay clip and checks it before it's kept:

- **Every vowel is measured.** Each word is cut into its syllables and the vowel of each is measured (formants, at the loudest part of the syllable) against the dictionary pronunciation, so a pepet is a pepet (*lebah*, not *lébah*) and an a is an a (*enam*, not *anam*). The voice decides pepet or taling from the whole text it's given, so each word is said a few ways (different endings and speeds), and of the takes with every vowel right, the one whose vowels are clearest is kept (*pokok* with two full o's, not the second drifting towards u). *helang* came out as *hélang* every time, so Gabung's h + e has no picture word (its syllable "he" is breathed onto a pepet from another word); *gigi* always started with a hiss ("jigi"), so gi's picture is now *gincu*; *mi* is now *misai*; and the cheer *Hebat!* (said too close to *hibat*) is now *Bijak!* When a word is still off on its own, it's lifted out of a short phrase (*seekor kucing*, *ada duit*), where the voice says it more carefully.
- **Consonants are checked too:** b, d, g and j must be voiced (*gajah*, not *kajah*), p, t and k must not have an English puff of air, and a weak h is made clear (the voice says *hotel* almost as *otel* and *benih* as *beni*), with breath in the colour of its vowel, which is what h is.
- **Syllables** (for Suku Kata, Eja! and Gabung!) are cut from real words where the voice says them right: on its own, "be" is read as the English letter name "bee". The syllable's vowel is checked before and after it's held a little longer.
- **Letter sounds** follow the Malay phonics module of Mohamad Rozi Kasim, *Pembangunan Model Kesedaran Bunyi Fonem Bahasa Melayu* (Jurnal Pendidikan Bahasa Melayu 15(2), 2025): the six vowels a, e (pepet), é (taling), i, o, u; consonants with a short "eh" ([beh], [ceh], [deh] … [ngeh], [nyeh], [syeh], [kheh]); s, f, m, n, l and ng held ("sss", "mmm"); and the diphthongs ai, au, oi.

One word still measures a little off and was kept: the u of *kuat* glides towards the a after it (ku-wat), which is how it's said. Settings → **Check every Malay recording** plays every Malay clip so a grown-up can listen before she does: tap ✗ on any that sounds wrong, then **Copy the list** and send it to be re-made.

Reading words, numbers and the letter sounds are in British English, the way phonics is taught in Malaysian schools ("o" as in "on", "a" as in "ant"). Each letter sound is cut out of a real word at the exact frames where that sound is, so consonants are pure (no "buh" or "kah") and every vowel is the right short vowel; the script checks each one (voicing, vowel shape, length) and also re-takes any word that would start with a stray "uh". Settings → **Letter sounds** plays every sound with a word that has it.

To change a line, edit the `<script id="lines">` block in `index.html`, then re-record from the repository root:

```
pip install kokoro-onnx soundfile praat-parselmouth scipy torch
python3 tools/make_voice.py
```

The Malay voice isn't downloaded by the script: get `model.pth` and `config.json` from [huggingface.co/mesolitica/VITS-yasmin](https://huggingface.co/mesolitica/VITS-yasmin) into one folder and pass it with `--bm-model-dir` (default `~/.cache/malay-tts/VITS-yasmin`).

Only clips whose text changed are re-recorded (and every Malay clip when the Malay voice code changes). New words added to the word lists are recorded the same way.

## Files

| File | What it does |
|---|---|
| `index.html` | The whole game |
| `sw.js` | Keeps the game playable offline, including Luna's voice |
| `audio/` | Luna's recorded lines (`p/`), reading words (`w/`), letter sounds (`s/`), numbers (`n/`) and Bahasa Melayu words, syllables, cheers, meanings, letter sounds and their example words (`m/`) |
| `tools/make_voice.py` | Records the voice clips |
| `tools/malay_voice.py` | Makes and checks the Bahasa Melayu clips with the native Malay voice (`tools/malay_vits/`: its MIT-licensed model code) |
| `manifest.webmanifest` | App name, icon and full-screen setting |
| `fonts/` | Andika (reading font) and Grandstander (title font) |
| `icons/` | Home-screen icons |
