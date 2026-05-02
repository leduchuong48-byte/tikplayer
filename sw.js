const SW_VERSION = 'tikplayer-shell-v1';
const SHELL_CACHE = `${SW_VERSION}-shell`;
const RUNTIME_CACHE = `${SW_VERSION}-runtime`;
const PRECACHE_URLS = [
  '/',
  '/manifest.json',
  '/offline.html',
  '/static/hls.min.js',
  '/static/artplayer.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-512-maskable.png',
  '/static/icons/apple-touch-icon.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.addAll(PRECACHE_URLS)));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => !k.startsWith(SW_VERSION)).map(k => caches.delete(k))))
  );
});

function isRangeRequest(req) {
  return req.headers.has('range');
}

function isNetworkOnlyUrl(url) {
  const p = url.pathname;
  if (p.startsWith('/v1/transcode') || p.startsWith('/v1/download') || p.startsWith('/v1/stream')) return true;
  if (p.endsWith('.m3u8') || p.endsWith('.ts') || p.endsWith('.mp4') || p.endsWith('.mkv') || p.endsWith('.mov') || p.endsWith('.webm')) return true;
  return false;
}

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);

  if (req.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;
  if (isRangeRequest(req) || isNetworkOnlyUrl(url)) return;

  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const net = await fetch(req);
        return net;
      } catch {
        const cache = await caches.open(SHELL_CACHE);
        return (await cache.match('/')) || (await cache.match('/offline.html')) || Response.error();
      }
    })());
    return;
  }

  const path = url.pathname;
  const isApi = path.startsWith('/v1/');
  if (isApi) {
    event.respondWith((async () => {
      try {
        return await fetch(req);
      } catch {
        const cache = await caches.open(RUNTIME_CACHE);
        return (await cache.match(req)) || Response.error();
      }
    })());
    return;
  }

  const isStatic = path.startsWith('/static/') || path === '/manifest.json';
  if (isStatic) {
    event.respondWith((async () => {
      const cache = await caches.open(RUNTIME_CACHE);
      const cached = await cache.match(req);
      const netPromise = fetch(req).then(res => {
        if (res && res.ok) cache.put(req, res.clone());
        return res;
      }).catch(() => null);
      return cached || (await netPromise) || Response.error();
    })());
  }
});
