# Service Worker Caching vs Cloudflare CDN on Pages

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

After deploying an updated build to Cloudflare Pages, users
on mobile devices continue to see the previous version for
hours or until they force-quit and relaunch the app. The
Cloudflare CDN correctly serves the new files (confirmed
via `curl` with `Cache-Control: no-cache`), but the Service
Worker (SW) installed in the browser is intercepting
requests and serving stale responses from the Cache Storage
API. On desktop the new version loads within minutes; on
Android Chrome and iOS Safari it can persist for 24+ hours.
A hard refresh (Ctrl+Shift+R / Cmd+Shift+R) resolves it on
desktop but mobile browsers have no equivalent gesture.

## Context

A Next.js PWA deployed to Cloudflare Pages involves two
independent caching layers that can fight each other:

```
Request flow (simplified)
─────────────────────────────────────────────────────────
Browser
  │
  ├─► Service Worker Cache Storage  ◄─── Layer 1
  │     (lives in the browser)
  │
  └─► Cloudflare CDN Edge Cache     ◄─── Layer 2
        (Cloudflare Pages network)
          │
          └─► Origin build output
─────────────────────────────────────────────────────────
```

When a SW uses Cache-First for static assets, it never
reaches the CDN. The SW itself is re-fetched by the browser
on a navigation (subject to the SW's own HTTP cache TTL),
but if the SW file is also cached at the CDN with a long
`max-age`, the browser may not even see the new SW script —
so the installed SW continues serving the old JS bundle.

Cloudflare Pages applies its own `Cache-Control` headers to
files in the build output. The `_next/static/` chunk files
get `public, max-age=31536000, immutable` (correct —
content-addressed). The `sw.js` and other root-level files
get shorter TTLs by default, but the exact behaviour
depends on your `_headers` configuration.

## Cache-Control header precedence

```
Header source              Priority  Applies to
──────────────────────────────────────────────────────────
Browser fetch (sw.js)      Browser   SW script fetch uses
                           policy    HTTP cache — typically
                                     max-age=0 or 86400

Cloudflare Pages default   CDN       Applied when no custom
  for HTML/JS/CSS:                   _headers rule matches
  max-age=0 for HTML,
  immutable for _next/static

Your _headers file          CDN       Overrides the default
  (public/_headers)                   for matched paths

Service Worker Cache        SW        Intercepts fetch()
  Storage (Cache API)                 before the network
                                      is reached at all
──────────────────────────────────────────────────────────
SW Cache wins over CDN because it intercepts before the
network request is made. HTTP cache applies to the SW
script file fetch itself, not to the SW's cache.open().
```

## Configuring SW script headers in _headers

The SW script (`/sw.js` or `/service-worker.js`) must
always be served with `no-cache` so the browser checks for
an update on every navigation rather than serving a stale
SW from the HTTP cache. Add this to `public/_headers`:

```
# public/_headers

/sw.js
  Cache-Control: no-cache, no-store, must-revalidate
  Service-Worker-Allowed: /

/service-worker.js
  Cache-Control: no-cache, no-store, must-revalidate
  Service-Worker-Allowed: /

# Ensure Next.js static chunks are immutable (default
# on CF Pages; explicit here for documentation)
/_next/static/*
  Cache-Control: public, max-age=31536000, immutable
```

The `Service-Worker-Allowed` header expands the SW scope
beyond its script path — useful if your SW sits at `/sw.js`
but must intercept `/feed/*` requests.

## SW caching strategies and which to use

```
Strategy         How it works          Use for
─────────────────────────────────────────────────────────────
Cache First      SW cache → network    Static assets with
                 (network only if      content-addressed hashes
                 cache miss)           e.g. /_next/static/**

Network First    Network → SW cache    API responses, user
                 (cache only if net    data, any mutable content
                 fails)

Stale While      Return cache, then    Navigation HTML —
Revalidate       fetch update in BG    feels instant, updates
(SWR)            for next visit        in the background

Network Only     No caching            POST requests, analytics,
                                       real-time data

Cache Only       Only SW cache,        Offline fallback assets
                 error if missing      explicitly pre-cached
─────────────────────────────────────────────────────────────
For example project on Cloudflare Pages:
  _next/static/**   → Cache First (immutable, hash in name)
  /                  → Stale-While-Revalidate (fast, fresh)
  /api/**            → Network First
  /feed/**           → Stale-While-Revalidate
  push-notification routes → Network First (must be fresh)
```

## Workbox configuration for Next.js PWA

Using `next-pwa` (Serwist fork or `@ducanh2912/next-pwa`):

```js
// next.config.js
const withPWA = require('@ducanh2912/next-pwa').default({
  dest: 'public',        // sw.js emitted to public/sw.js
  cacheOnFrontEndNav: true,
  aggressiveFrontEndNavCaching: false,
  reloadOnOnline: true,

  workboxOptions: {
    // Avoid caching API routes — they must always hit the
    // network on Cloudflare Workers/Pages Functions.
    exclude: [
      /^\/api\//,
      /_next\/server\//,
    ],

    runtimeCaching: [
      // Navigation: stale-while-revalidate
      {
        urlPattern: /^https:\/\/[^/]+\/(?!_next\/static).*/,
        handler: 'StaleWhileRevalidate',
        options: {
          cacheName: 'pages-cache',
          expiration: { maxEntries: 64, maxAgeSeconds: 86400 },
        },
      },
      // Static chunks: cache first (immutable)
      {
        urlPattern: /\/_next\/static\//,
        handler: 'CacheFirst',
        options: {
          cacheName: 'static-assets',
          expiration: {
            maxEntries: 256,
            maxAgeSeconds: 31536000,
          },
        },
      },
    ],
  },
});
```

## Mobile SW lifecycle issues

Mobile browsers have unique SW lifecycle behaviour that
amplifies stale-cache problems:

```
Issue                     iOS Safari            Android Chrome
──────────────────────────────────────────────────────────────
SW update check on        Navigation +          Navigation +
nav                       24h minimum between   every navigation
                          update checks if      (no hold-off)
                          app was added to
                          home screen (A2HS)

Waiting SW                Waits indefinitely    Waits indefinitely
                          until all tabs close  until all tabs close

Background fetch of       Suspended when app    Allowed; Android
updated SW                is backgrounded on    can update in BG
                          A2HS installs

Tab / app lifecycle       iOS kills SW on       More lenient — SW
                          memory pressure;      survives longer
                          reinstalls on next    but still finite
                          launch
──────────────────────────────────────────────────────────────
```

The "waiting SW" problem is the most common source of users
being stuck on the old version: the new SW is installed but
cannot activate because the old one still controls an open
tab. On mobile the user rarely closes all tabs manually.

## Update detection and skipWaiting pattern

```ts
// sw.ts (Workbox custom SW or raw SW)
import { skipWaiting, clientsClaim } from 'workbox-core';

// During development only — not recommended for production
// because it can cause race conditions:
// skipWaiting();
// clientsClaim();

// Production-safe: listen for a message from the app
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
```

```ts
// In your React app — show an "Update available" banner
// and let the user trigger the skip explicitly.
import { useRegisterSW } from 'virtual:pwa-register/react';

export function UpdateBanner() {
  const { needRefresh, updateServiceWorker } = useRegisterSW({
    onRegisteredSW(swUrl, r) {
      // Poll every 60 s for a new SW on mobile where
      // background checks are suppressed.
      if (r) {
        setInterval(() => {
          r.update();
        }, 60 * 1000);
      }
    },
  });

  if (!needRefresh[0]) return null;

  return (
    <div role="alert" className="update-banner">
      <span>A new version is available.</span>
      <button onClick={() => updateServiceWorker(true)}>
        Reload
      </button>
    </div>
  );
}
```

The `updateServiceWorker(true)` call posts `SKIP_WAITING`
to the waiting SW, then reloads the page. This is the
recommended UX pattern — never call `skipWaiting()`
unconditionally in the SW because it can break in-flight
navigation if the SW activates mid-page.

## Anti-patterns

- **`skipWaiting()` unconditionally in the SW install
  handler** — the new SW activates immediately, potentially
  changing the cache state while an existing page is still
  loading resources. This causes broken page loads,
  especially on slow mobile connections.
- **Cache-First for navigation HTML** — serving `/index.html`
  from cache with no revalidation means a newly deployed
  HTML shell is never seen until the cache expires. Use
  Stale-While-Revalidate for navigation requests.
- **Long `max-age` on `sw.js`** — if the SW script is cached
  by the HTTP cache for hours, the browser will not even
  check for an update. Always serve `sw.js` with
  `Cache-Control: no-cache`.
- **Caching POST requests** — the Fetch event fires for all
  requests including POST. Never put POST/PUT/DELETE
  responses into Cache Storage.
- **Not purging old caches on SW activate** — after a SW
  version bump, old `CACHE_NAME-v1` entries accumulate in
  Cache Storage, consuming quota. Always delete stale caches
  in the activate handler.

## Gotchas

- **iOS A2HS enforces a 24-hour SW update check hold-off**
  — when example project is installed as a home screen PWA on iOS,
  Safari will not check for an updated SW more than once per
  24 hours. The periodic polling in `onRegisteredSW` works
  around this but the initial 24-hour window cannot be
  shortened.
- **Cloudflare Pages edge cache is separate from the CDN
  cache exposed to Workbox** — CF Pages edge caches at the
  PoP level. Your SW's `fetch()` calls hit the nearest PoP,
  not the origin. `Cache-Control: no-cache` on a request
  still hits the PoP but adds `If-None-Match`; the PoP may
  return a 304 without contacting the origin.
- **`output: 'export'` has no runtime** — there is no
  Next.js server to serve SW scope headers at runtime.
  All SW-related headers must be set via `_headers`.
- **Cache Storage quota** — on iOS, Cache Storage is capped
  at 50 MB per origin (as of 2026). Caching large font
  files or video posters can exhaust this limit and cause
  silent failures. Monitor via `navigator.storage.estimate()`.

## Verification

- `curl -I https://example project.example.com/sw.js` returns
  `Cache-Control: no-cache, no-store, must-revalidate`.
- After deploying a new build, the "Update available" banner
  appears within 60 seconds on a running mobile app.
- Chrome DevTools → Application → Service Workers shows
  "activated and running" for the new SW after clicking
  "Reload" on the banner.
- Old cache namespaces (`app-v1`, etc.) are deleted after
  SW activation — verify in DevTools → Application → Cache
  Storage.

## Related

- `documentation/categories/frontend/nextjs-static-export-cloudflare-pages-routing.md`
- `documentation/categories/frontend/cloudflare-pages-headers-csp-mobile.md`
- `documentation/categories/frontend/offline-fallback-pages.md`
- `documentation/categories/frontend/browser-service-worker-cache.md`
- `documentation/categories/frontend/pwa-manifest-config.md`

## Source URLs (verified 2026-08-22)

- Cloudflare Pages — Headers —
  https://developers.cloudflare.com/pages/configuration/headers/
- Workbox — Caching strategies —
  https://developer.chrome.com/docs/workbox/caching-strategies-overview/
- web.dev — Service worker lifecycle —
  https://web.dev/articles/service-worker-lifecycle
- MDN — Cache Storage quota —
  https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria
- Serwist / next-pwa docs —
  https://serwist.pages.dev/docs/next/getting-started
