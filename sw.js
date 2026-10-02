// Keeps Word Snap Showdown playable offline. The game page is fetched fresh when online
// (so updates show up), with the saved copy used when there is no internet.
// Luna's voice clips (listed in audio/list.json) are saved in the background on first open.
const CACHE = "word-snap-21e49df5";  // set by tools/make_voice.py to the voice version
const FILES = [
  "./", "index.html", "manifest.webmanifest", "audio/list.json",
  "fonts/andika-400.woff2", "fonts/andika-700.woff2",
  "fonts/grandstander-500.woff2", "fonts/grandstander-700.woff2", "fonts/grandstander-900.woff2",
  "icons/icon-192.png", "icons/icon-512.png", "icons/icon-maskable-512.png", "icons/apple-touch-icon.png"
];
async function cacheVoice(cache) {
  try {
    const list = await (await fetch("audio/list.json", { cache: "no-cache" })).json();
    const urls = Object.keys(list.clips).map((k) => `audio/${k}.mp3?v=${list.version}`);
    for (let i = 0; i < urls.length; i += 8) {
      await Promise.allSettled(urls.slice(i, i + 8).map(async (u) => {
        const res = await fetch(u);
        if (res.ok) await cache.put(u.split("?")[0], res);
      }));
    }
  } catch (e) { /* the game still plays clips as it fetches them */ }
}
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
      .then(() => caches.open(CACHE).then(cacheVoice))
  );
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put("index.html", copy));
          return res;
        })
        .catch(() => caches.match("index.html"))
    );
    return;
  }
  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then(
      (hit) => hit || fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
        return res;
      })
    )
  );
});
