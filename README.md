# Word Snap Showdown

A two-player reading race for a young reader and a grown-up. Luna the snow fox says a word, both players race to tap it, and the grown-up's cards appear after an adjustable head start.

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
| `audio/` | Luna's recorded lines (`p/`) and reading words (`w/`) |
| `tools/make_voice.py` | Records the voice clips |
| `manifest.webmanifest` | App name, icon and full-screen setting |
| `fonts/` | Andika (reading font) and Grandstander (title font) |
| `icons/` | Home-screen icons |
