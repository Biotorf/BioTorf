/* BIOTORF Business OS · service worker (PWA)
   Стратегия:
   - навигация → network-first с fallback на кэшированный index.html (офлайн-экран SPA);
   - статика (шрифты/картинки/js/css) → cache-first;
   - API/бэкенд НЕ кэшируем — данные всегда свежие. */
const VERSION = 'biotorf-pwa-v4';
const STATIC_CACHE = `${VERSION}-static`;
const NAV_CACHE = `${VERSION}-nav`;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll([
      '/manifest.webmanifest',
      '/favicon.png',
      '/x192.png',
      '/x512.png',
      '/x180.png',
    ])).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith('biotorf-pwa-') && !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  let url;
  try { url = new URL(req.url); } catch { return; }
  if (url.origin !== self.location.origin || /^\/(api|auth|health|webhooks)(\/|$)/.test(url.pathname)) return;

  // Навигация (открытие приложения): сеть, при офлайне — кэш или index.html
  if (req.mode === 'navigate') {
    const key = url.pathname === '/manual.html' ? '/manual.html' : '/index.html';
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok && res.headers.get('Content-Type')?.includes('text/html')) {
            const copy = res.clone();
            caches.open(NAV_CACHE).then((c) => c.put(key, copy)).catch(() => {});
          }
          return res;
        })
        .catch(async () => {
          const cached = await caches.match(key);
          return cached || new Response(
            '<!doctype html><meta charset="utf-8"><title>BIOTORF</title>' +
            '<body style="font-family:sans-serif;background:#0b1220;color:#fff;display:grid;place-items:center;height:100vh;margin:0">' +
            '<div style="text-align:center"><h2>BIOTORF Business OS</h2><p>Нет соединения. Откройте приложение, когда интернет появится.</p></div></body>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        })
    );
    return;
  }

  // Статика из нашего origin: cache-first с дозаписью в кэш
  if (/\.(js|css|png|svg|ico|woff2?|webmanifest)$/.test(url.pathname)) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(STATIC_CACHE).then((c) => c.put(req, copy));
        return res;
      }))
    );
  }
});
