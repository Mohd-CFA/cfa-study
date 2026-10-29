/* CFA L1 · Study — service worker (offline support)
 *
 * Put this file NEXT TO index.html (same folder on GitHub Pages).
 *
 * What it does
 *  - The page itself (index.html, which already contains the app, PDF.js and styles) is served
 *    network-first, so a new version you upload is picked up on the next load; if the network
 *    is down or slow (> 3.5 s) the last good copy is used instead.
 *  - The Supabase library (loaded from a CDN) is cached on first use and then served from the
 *    cache, so the app starts offline and does not break when the CDN changes or is unreachable.
 *  - Everything else — above all the Supabase API (auth + sync) — is NOT touched.
 *
 * To force every device to fetch a fresh copy of the Supabase library, bump VERSION.
 */
const VERSION = 'v1';
const CACHE = 'cfa-l1-' + VERSION;
const LIB_MARK = '/@supabase/supabase-js';          // matches jsDelivr and unpkg URLs of the library
const NAV_TIMEOUT = 3500;

const pageKey = url => { const u = new URL(url); u.search = ''; u.hash = ''; return u.toString(); };

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    // warm the cache with the page the registration scope points to (index.html on GitHub Pages)
    try { const r = await fetch(new Request(self.registration.scope, { cache: 'reload' })); if (r.ok) await cache.put(pageKey(self.registration.scope), r); } catch (e) { /* offline install: the first normal visit fills it */ }
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith('cfa-l1-') && k !== CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});

async function pageFirst(request) {
  const cache = await caches.open(CACHE);
  const key = pageKey(request.url);
  const cached = (await cache.match(key, { ignoreSearch: true })) || (await cache.match(pageKey(self.registration.scope)));
  const ctl = new AbortController();
  const timer = cached ? setTimeout(() => ctl.abort(), NAV_TIMEOUT) : null;   // only race against the clock when a fallback exists
  try {
    const res = await fetch(key, { cache: 'no-cache', credentials: 'same-origin', signal: ctl.signal });
    if (res.ok) { await cache.put(key, res.clone()); return res; }
    return cached || res;
  } catch (e) {
    return cached || Response.error();
  } finally { if (timer) clearTimeout(timer); }
}

async function libFirst(request) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(request.url, { ignoreVary: true });
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok) cache.put(request.url, res.clone());
  return res;
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (req.mode === 'navigate' && url.origin === self.location.origin) { event.respondWith(pageFirst(req)); return; }
  if (url.pathname.includes(LIB_MARK)) event.respondWith(libFirst(req));
});

// the page asks us to pre-cache the library right after registration, so the very first offline visit already works
self.addEventListener('message', event => {
  const d = event.data || {};
  if (d.type !== 'precache' || !Array.isArray(d.urls)) return;
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    for (const u of d.urls) {
      try {
        if (!String(u).includes(LIB_MARK) || await cache.match(u, { ignoreVary: true })) continue;
        const r = await fetch(u, { mode: 'cors' });
        if (r.ok) await cache.put(u, r);
      } catch (e) { /* retried on the next visit */ }
    }
  })());
});
