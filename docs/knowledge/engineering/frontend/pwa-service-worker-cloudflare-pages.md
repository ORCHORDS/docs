# PWA Service Worker on Cloudflare Pages — Cache Strategy & iOS Add-to-Home Quirks

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

The PWA manifest is ignored on iOS (no splash screen, wrong icon), the service worker
fails to register when the app is deployed under a subdirectory, and API responses are
served stale from the service worker cache when Cloudflare Pages has already purged the
CDN copy. On Android, "Add to Home Screen" never prompts automatically.

## Context

example project (example.com) is a Next.js 14 `output: 'export'` PWA deployed on Cloudflare Pages.
The goal is offline capability for the feed and player, with fresh data for the API.
Service workers on Pages must co-exist with Cloudflare's own edge cache — both layers
intercept requests and the interaction must be explicit.

---

## PWA Manifest — Minimal Correct Config

```json
// public/manifest.json
{
  "name": "example project — example project App",
  "short_name": "example project",
  "description": "Discover and share music",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#0a0a0a",
  "theme_color": "#7c3aed",
  "orientation": "portrait-primary",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-192-maskable.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ],
  "screenshots": [
    { "src": "/screenshots/feed-mobile.png", "sizes": "390x844", "type": "image/png", "form_factor": "narrow" }
  ]
}
```

### Link in layout.tsx

```tsx
<head>
  <link rel="manifest"  />
  {/* iOS does not read the manifest — requires these meta tags */}
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="apple-mobile-web-app-title" content="example project" />
  {/* iOS ignores manifest icons — requires <link rel="apple-touch-icon"> */}
  <link rel="apple-touch-icon"  />
  {/* Splash screens — generate per device resolution or use PWACompat */}
  <link rel="apple-touch-startup-image"
    media="(device-width: 390px) and (device-height: 844px) and (-webkit-device-pixel-ratio: 3)" />
</head>
```

---

## Service Worker Registration

```ts
// lib/registerSW.ts
export async function registerServiceWorker() {
  if (typeof window === 'undefined') return;
  if (!('serviceWorker' in navigator)) return;

  try {
    const reg = await navigator.serviceWorker.register('/sw.js', {
      // scope must match the Pages deploy path; '/' works for root deploys
      scope: '/',
      // updateViaCache: 'none' means SW file is always fetched from network
      updateViaCache: 'none',
    });

    reg.addEventListener('updatefound', () => {
      const newWorker = reg.installing;
      newWorker?.addEventListener('statechange', () => {
        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
          // New version available — notify the user
          dispatchEvent(new CustomEvent('sw:update-available'));
        }
      });
    });
  } catch (err) {
    console.error('[SW] Registration failed:', err);
  }
}
```

Register after `DOMContentLoaded` to not compete with critical resources:

```tsx
// app/layout.tsx  (client component boundary)
'use client';
import { useEffect } from 'react';
import { registerServiceWorker } from '@/lib/registerSW';

export function ServiceWorkerProvider() {
  useEffect(() => { registerServiceWorker(); }, []);
  return null;
}
```

---

## Cache Strategy

| Request Type | Strategy | Rationale |
|---|---|---|
| HTML shells (`/`, `/feed`) | Network-first, SW fallback | Always try latest; serve cache offline |
| `/_next/static/**` | Cache-first | Immutable hashed assets |
| `/fonts/**` | Cache-first (1 year) | Immutable font files |
| `/icons/**`, `/images/**` | Stale-while-revalidate | Tolerate slight staleness |
| `/api/**`, Cloudflare Worker endpoints | Network-first, no cache | API must be fresh |
| `/manifest.json` | Network-first | PWA metadata should update promptly |

### public/sw.js

```js
const STATIC_CACHE  = 'example project-static-v1';
const DYNAMIC_CACHE = 'example project-dynamic-v1';

const STATIC_ASSETS = [
  '/',
  '/feed',
  '/offline.html',
  '/manifest.json',
];

// Install: pre-cache app shells and static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((c) => c.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: evict old caches
self.addEventListener('activate', (event) => {
  const keep = [STATIC_CACHE, DYNAMIC_CACHE];
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !keep.includes(k)).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Never intercept: API calls, Cloudflare Workers, non-GET
  if (request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/cdn-cgi/')) return;

  // Cache-first: hashed Next.js static chunks
  if (url.pathname.startsWith('/_next/static/')) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Cache-first: fonts and icons (long-lived)
  if (url.pathname.startsWith('/fonts/') || url.pathname.startsWith('/icons/')) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Network-first with offline fallback: HTML navigation
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstWithFallback(request));
    return;
  }

  // Stale-while-revalidate: images and everything else
  event.respondWith(staleWhileRevalidate(request, DYNAMIC_CACHE));
});

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  const cache = await caches.open(cacheName);
  cache.put(request, response.clone());
  return response;
}

async function networkFirstWithFallback(request) {
  try {
    const response = await fetch(request);
    const cache = await caches.open(DYNAMIC_CACHE);
    cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached ?? caches.match('/offline.html');
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache  = await caches.open(cacheName);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request).then((r) => { cache.put(request, r.clone()); return r; });
  return cached ?? fetchPromise;
}
```

---

## iOS Add-to-Home Quirks

| Behaviour | Android Chrome | iOS Safari |
|---|---|---|
| Automatic install prompt | Yes (`beforeinstallprompt`) | No — manual only |
| Splash screen from manifest | Yes | No — needs `apple-touch-startup-image` |
| Icon from manifest | Yes | No — needs `apple-touch-icon` |
| `display: standalone` | Yes | Yes (since iOS 11.3) |
| Push notifications in PWA | Yes | Yes (since iOS 16.4) |
| SW scope | Unrestricted | Must be on same origin, ≤ manifest scope |
| SW persistence | Persistent | Evicted after 7 days of no use |

On iOS, the SW is evicted when the PWA has not been opened for 7 days. Pre-cache the
minimum offline shell to avoid a blank screen after eviction by implementing a
`/offline.html` fallback (see cache strategy above).

---

## Cloudflare Pages `_headers` for SW

```
# public/_headers

# Service Worker must NOT be cached by Cloudflare CDN
# so browsers always get the latest version check
/sw.js
  Cache-Control: no-cache, no-store, must-revalidate
  Service-Worker-Allowed: /

/manifest.json
  Cache-Control: public, max-age=3600
  Content-Type: application/manifest+json; charset=utf-8
```

`Service-Worker-Allowed: /` extends the default scope (same directory as `sw.js`) to
the root, which is required when `sw.js` is at the root but scope is `/`.

---

## Anti-patterns

- **Caching API responses with cache-first** — returns stale data after DB writes.
- **Not setting `Cache-Control: no-cache` on `sw.js`** — Cloudflare CDN caches it;
  users never receive SW updates.
- **Forgetting `self.skipWaiting()` + `clients.claim()`** — new SW waits indefinitely
  for old tabs to close.
- **Using `workbox` without understanding its Cloudflare Pages interaction** — Workbox's
  precache manifest conflicts with `_next/static` versioning.

---

## Gotchas

- Cloudflare Pages serves every file with `Etag` headers. Even with `Cache-Control: no-cache`,
  the browser sends `If-None-Match` and Cloudflare returns `304` — the browser still
  byte-compares and updates the SW only if content changed. This is correct behaviour.
- iOS Safari requires HTTPS for service workers — always use the production domain or
  `localhost` during development; Wrangler Pages dev serves over HTTP by default, which
  blocks SW registration except on `localhost`.
- `register('/sw.js')` in a Next.js app with `basePath` set requires
  `register('${basePath}/sw.js')` — the path is relative to the page's URL, not the domain root.

---

## Verification

```bash
# 1. Confirm manifest is valid
npx pwa-asset-generator --help  # generate icons and splash screens
curl -I https://example.com/manifest.json | grep content-type
# Expected: application/manifest+json

# 2. Check SW is NOT cached by CDN
curl -sI https://example.com/sw.js | grep -E "cache-control|cf-cache-status"
# Expected: cache-control: no-cache, ...; cf-cache-status: BYPASS or DYNAMIC

# 3. Lighthouse PWA audit
npx lighthouse https://example.com --form-factor mobile \
  --only-categories pwa

# 4. Offline test in Chrome DevTools
# Application > Service Workers > check "Offline" > reload page
# Should serve /offline.html or cached feed

# 5. iOS manual test
# Safari > Share > Add to Home Screen
# Verify: icon, splash, standalone mode, no address bar
```

---

## Related

- `pwa-manifest-config.md`
- `browser-service-worker-cache.md`
- `service-worker-caching-cloudflare-cdn-conflict.md`
- `offline-fallback-pages.md`
- `cloudflare-pages-headers-csp-mobile.md`
- `service-worker-navigation-preload-race-control.md`

## Sources

- Cloudflare Pages _headers — https://developers.cloudflare.com/pages/configuration/headers/
- MDN Service Worker API — https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API
- Apple PWA documentation — https://developer.apple.com/documentation/webkit/delivering-video-content-for-safari
- web.dev PWA checklist — https://web.dev/articles/pwa-checklist
- iOS SW eviction — https://webkit.org/blog/10247/new-webkit-features-in-safari-13-1/
