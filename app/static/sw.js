// Service worker: cache dos arquivos estáticos (app abre rápido e funciona com internet fraca).
// As chamadas /api/* sempre vão para a rede.
const CACHE = "tv-v5";
const ASSETS = ["/", "/static/style.css?v=5", "/static/app.js?v=5", "/static/resultado.css?v=3", "/static/resultado.js?v=3", "/static/icon-192.png", "/static/logo_alfabits.png", "/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  // rede primeiro, cache como reserva
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
