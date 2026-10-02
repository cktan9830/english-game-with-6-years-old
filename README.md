# Word Snap Showdown

Reading games for a young reader and a grown-up, hosted by Luna the bunny.

- **Word Snap**: Luna says a word and both players race to tap it on their own side. The grown-up's cards appear after an adjustable head start.
- **Robot Talk** (take turns): Luna says a word sound by sound ("c… a… t") and the player taps the matching picture.
- **Read & Match** (take turns): read the word silently, then tap its picture.

In the turn games the play area turns to face whoever's turn it is, so only one person touches the screen at a time. The young reader gets a second try; the grown-up has a countdown that auto-balances.

Every word she gets right becomes a sticker in her sticker book, which grows prettier as it fills: plain → rainbow → ribbon → sparkly → jewels → royal → magic gold. Words she misses come back more often. Stickers are saved on the tablet itself.

## Play

**Game link:** https://cktan9830.github.io/english-game-with-6-years-old/

Open the game link in the tablet's browser, then add it to the home screen:

- **iPad:** Safari → Share → **Add to Home Screen**
- **Android:** Chrome → ⋮ menu → **Add to Home screen** / **Install app**

Open it once while online. After that it works offline.

## How it's hosted

GitHub Pages serves this repository's `main` branch. Every push to `main` updates the live game within a minute or two.

## Luna's voice

Luna's cheers and every reading word are pre-recorded clips in `audio/`, made with the open Kokoro text-to-speech model (voice `af_heart`, pitched up for a cute, child-like sound at normal speed). If a clip can't play, the game falls back to the device's own voice.

To change a line, edit the `<script id="lines">` block in `index.html`, then re-record from the repository root:

```
pip install kokoro-onnx soundfile
python3 tools/make_voice.py
```

Only clips whose text changed are re-recorded. New words added to the word lists are recorded the same way.

## Files

| File | What it does |
|---|---|
| `index.html` | The whole game |
| `sw.js` | Keeps the game playable offline, including Luna's voice |
| `audio/` | Luna's recorded lines (`p/`), reading words (`w/`) and letter sounds (`s/`) |
| `tools/make_voice.py` | Records the voice clips |
| `manifest.webmanifest` | App name, icon and full-screen setting |
| `fonts/` | Andika (reading font) and Grandstander (title font) |
| `icons/` | Home-screen icons |
