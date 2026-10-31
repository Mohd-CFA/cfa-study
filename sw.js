/* CFA L1 · Study — service worker (offline support) — v2
 *
 * Put this file NEXT TO index.html (same folder on GitHub Pages).
 *
 *  - The page (index.html, which contains the app, PDF.js and styles) opens INSTANTLY from the saved copy.
 *    In the background the worker asks the server whether the page changed (a tiny conditional request).
 *    Only when it really changed is the new copy stored, and the open page shows "A new version is ready · Reload".
 *    First visit, or nothing saved yet: network first.
 *  - The Supabase library (CDN) is cached on first use and then served from the cache.
 *  - Everything else — above all the Supabase API (auth + sync + uploads) — is NOT touched.
 *
 * To force every device to drop its saved copies, bump VERSION.
 */
const VERSION = 'v2';
const CACHE = 'cfa-l1-' + VERSION;
const LIB_MARK = '/@supabase/supabase-js';          // matches jsDelivr and unpkg URLs of the library
const META = new URL('__sw-meta', self.registration.scope).href;
const pageKey = url => { const u = new URL(url); u.search = ''; u.hash = ''; return u.toString(); };

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    // warm the cache with the page the registration scope points to (index.html on GitHub Pages)
    try {
      const r = await fetch(new Request(self.registration.scope, { cache: 'reload' }));
      if (r.ok) { await cache.put(pageKey(self.registration.scope), r.clone()); await saveMeta(cache, await versionOf(r)); }
    } catch (e) { /* offline install: the first normal visit fills it */ }
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith('cfa-l1-') && k !== CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});

// a short fingerprint of a response: ETag / Last-Modified when the server sends them, otherwise a hash of the body
async function versionOf(res) {
  const h = res.headers.get('etag') || res.headers.get('last-modified');
  if (h) return h;
  const buf = await res.clone().arrayBuffer();
  const d = new Uint8Array(await crypto.subtle.digest('SHA-1', buf));
  return 'sha1:' + Array.from(d, b => b.toString(16).padStart(2, '0')).join('');
}
const saveMeta = (cache, v) => cache.put(META, new Response(JSON.stringify({ v })));
const readMeta = async cache => { try { const r = await cache.match(META); return r ? await r.json() : null; } catch (e) { return null; } };

// background check: does the server have a newer page? (usually a 304 — no download, nothing written)
async function revalidate(key) {
  try {
    const cache = await caches.open(CACHE);
    const res = await fetch(key, { cache: 'no-cache', credentials: 'same-origin' });
    if (!res.ok) return;
    const v = await versionOf(res), old = await readMeta(cache), have = await cache.match(key);
    if (old && old.v === v && have) return;                    // unchanged → keep everything as it is
    await cache.put(key, res.clone());
    await saveMeta(cache, v);
    if (old && old.v !== v) {                                   // a different version replaced the saved one → tell open pages
      for (const c of await self.clients.matchAll({ type: 'window' })) c.postMessage({ type: 'update-ready' });
    }
  } catch (e) { /* offline or server down: keep using the saved copy */ }
}

async function pageFirst(event) {
  const request = event.request, key = pageKey(request.url);
  const cache = await caches.open(CACHE);
  const cached = (await cache.match(key, { ignoreSearch: true })) || (await cache.match(pageKey(self.registration.scope)));
  if (cached) { event.waitUntil(revalidate(key)); return cached; }
  try {                                                         // nothing saved yet → network
    const res = await fetch(key, { cache: 'no-cache', credentials: 'same-origin' });
    if (res.ok) { await cache.put(key, res.clone()); await saveMeta(cache, await versionOf(res)); }
    return res;
  } catch (e) { return Response.error(); }
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
  if (req.mode === 'navigate' && url.origin === self.location.origin) { event.respondWith(pageFirst(event)); return; }
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
