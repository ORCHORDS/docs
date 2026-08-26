# PWA Manifest and Service Worker Serving from Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want full Progressive Web App (PWA) capabilities — installability, offline support, push notifications — for a site served through Cloudflare Workers. Static hosting via Pages handles asset delivery, but there are correctness requirements for Content-Type headers on the manifest, cache semantics on the service worker script, and runtime integration between the SW and Worker API endpoints (push subscription, offline fallback from R2).

## Context

Browsers enforce strict rules for PWA components: the web app manifest must be served with `Content-Type: application/manifest+json`, the service worker script must be served with `Content-Type: text/javascript` from the **same origin** as the page, and its `Cache-Control` must not cache it for more than 24 hours (in practice, `no-cache` or `max-age=0` is safest to ensure the browser always checks for an updated SW). The Worker handles these serving requirements and also exposes a `/push-subscribe` endpoint so the SW can forward `PushSubscription` objects to be stored in KV.

## Solution

```typescript
// worker.ts — PWA manifest + SW serving + push subscription endpoint

export interface Env {
  ASSETS: Fetcher;            // bound to Workers Assets (static files)
  OFFLINE_BUCKET: R2Bucket;  // R2 bucket containing offline-fallback.html
  PUSH_SUBS: KVNamespace;    // KV for storing push subscriptions
  VAPID_PUBLIC_KEY: string;  // env var: base64url VAPID public key
}

const MANIFEST: Record<string, unknown> = {
  name: 'Orchords',
  short_name: 'Orchords',
  description: 'Sheet music marketplace',
  start_url: '/?source=pwa',
  display: 'standalone',
  orientation: 'portrait-primary',
  background_color: '#ffffff',
  theme_color: '#1a1a2e',
  icons: [
    { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any maskable' },
    { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
  ],
  screenshots: [
    { src: '/screenshots/desktop.webp', sizes: '1280x800', type: 'image/webp', form_factor: 'wide' },
    { src: '/screenshots/mobile.webp',  sizes: '390x844',  type: 'image/webp', form_factor: 'narrow' },
  ],
  categories: ['music', 'education'],
  shortcuts: [
    {
      name: 'Browse scores',
      url: '/browse',
      icons: [{ src: '/icons/shortcut-browse.png', sizes: '96x96' }],
    },
  ],
};

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    switch (url.pathname) {
      case '/manifest.webmanifest':
      case '/manifest.json':
        return serveManifest();

      case '/sw.js':
        return serveServiceWorkerScript(env);

      case '/push-subscribe':
        return handlePushSubscribe(request, env);

      case '/push-unsubscribe':
        return handlePushUnsubscribe(request, env);

      case '/vapid-public-key':
        return new Response(env.VAPID_PUBLIC_KEY, {
          headers: { 'Content-Type': 'text/plain' },
        });

      default:
        return handleAssetWithOfflineFallback(request, env, ctx);
    }
  },
};

// ---- Manifest ----

function serveManifest(): Response {
  return new Response(JSON.stringify(MANIFEST, null, 2), {
    headers: {
      // The correct MIME type — some browsers reject application/json
      'Content-Type': 'application/manifest+json',
      // Allow browsers to cache for 1 hour; still validates on next page load
      'Cache-Control': 'public, max-age=3600',
    },
  });
}

// ---- Service Worker script ----
// The actual SW source lives in the Workers Assets bundle (sw.js).
// We intercept the request to enforce the required Cache-Control header.

async function serveServiceWorkerScript(env: Env): Promise<Response> {
  const assetResponse = await env.ASSETS.fetch(
    new Request('https://fake-origin/sw.js')
  );

  if (!assetResponse.ok) {
    return new Response('Service worker not found', { status: 404 });
  }

  // Clone and rewrite headers — the default asset Cache-Control would
  // prevent the browser from checking for updates promptly.
  const body = await assetResponse.arrayBuffer();
  return new Response(body, {
    status: 200,
    headers: {
      'Content-Type': 'text/javascript; charset=utf-8',
      // no-cache means "always revalidate", NOT "never cache"
      'Cache-Control': 'no-cache',
      'Service-Worker-Allowed': '/',  // allow SW scope to be root
    },
  });
}

// ---- Push subscription storage ----

async function handlePushSubscribe(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 });
  }

  const sub = await request.json<{
    endpoint: string;
    keys: { p256dh: string; auth: string };
    userId?: string;
  }>();

  if (!sub.endpoint || !sub.keys?.p256dh || !sub.keys?.auth) {
    return new Response('Invalid subscription object', { status: 400 });
  }

  // Key by endpoint URL so re-subscription is idempotent
  const key = `push:${btoa(sub.endpoint).replace(/=/g, '')}`;
  await env.PUSH_SUBS.put(key, JSON.stringify(sub), {
    metadata: { userId: sub.userId ?? 'anonymous', createdAt: Date.now() },
  });

  return new Response(JSON.stringify({ ok: true, key }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function handlePushUnsubscribe(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'DELETE') {
    return new Response('Method not allowed', { status: 405 });
  }
  const { endpoint } = await request.json<{ endpoint: string }>();
  const key = `push:${btoa(endpoint).replace(/=/g, '')}`;
  await env.PUSH_SUBS.delete(key);
  return new Response(null, { status: 204 });
}

// ---- Asset serving with offline fallback ----

async function handleAssetWithOfflineFallback(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const assetResponse = await env.ASSETS.fetch(request);
  if (assetResponse.ok) return assetResponse;

  // Navigator is offline or asset missing — serve offline page from R2
  if (assetResponse.status === 404 || assetResponse.status === 503) {
    const offline = await env.OFFLINE_BUCKET.get('offline-fallback.html');
    if (offline) {
      return new Response(offline.body, {
        status: 200,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      });
    }
  }

  return assetResponse;
}
```

```typescript
// public/sw.js — Service Worker (TypeScript source, compiled to sw.js)
/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope;

const CACHE_NAME = 'orchords-v1';
const PRECACHE_URLS = [
  '/',
  '/browse',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
];

// ---- Install ----

self.addEventListener('install', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(PRECACHE_URLS))
  );
  // Take over immediately without waiting for old SW to be released
  self.skipWaiting();
});

// ---- Activate ----

self.addEventListener('activate', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ---- Fetch: network-first for API, cache-first for assets ----

self.addEventListener('fetch', (event: FetchEvent) => {
  const url = new URL(event.request.url);

  // Let non-GET and cross-origin pass through
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) {
    return;
  }

  // API routes: network-first, no caching
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Assets: stale-while-revalidate
  event.respondWith(
    caches.open(CACHE_NAME).then(async cache => {
      const cached = await cache.match(event.request);
      const networkFetch = fetch(event.request).then(response => {
        if (response.ok) cache.put(event.request, response.clone());
        return response;
      }).catch(() => null);

      return cached ?? await networkFetch ?? new Response('Offline', { status: 503 });
    })
  );
});

// ---- Push ----

self.addEventListener('push', (event: PushEvent) => {
  const data = event.data?.json<{ title: string; body: string; url?: string }>() ?? {
    title: 'Orchords',
    body: 'You have a new notification',
  };

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/icons/icon-192.png',
      badge: '/icons/badge-96.png',
      data: { url: data.url ?? '/' },
    })
  );
});

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  event.waitUntil(
    self.clients.openWindow(event.notification.data.url as string)
  );
});
```

## Implementation Details

**`application/manifest+json` is required.** Chrome and Safari will ignore a manifest served as `application/json` or `text/plain` for installability checks. Always use the registered MIME type.

**Service Worker `Cache-Control: no-cache`.** The browser's SW update algorithm checks for a byte-difference in the SW script. If the SW is cached aggressively (e.g., `max-age=86400`), users won't receive updates for up to 24 hours. `no-cache` forces an `If-None-Match` / `If-Modified-Since` revalidation on every page load, keeping update latency to a single navigation.

**`Service-Worker-Allowed: /` header.** By default, a SW's scope is limited to the directory of the SW script. Serving `sw.js` from `/sw.js` gives it a root scope (`/`) automatically, but if it were at `/static/sw.js`, you'd need this header to extend the scope.

**`self.skipWaiting()` + `clients.claim()`.** These two calls together ensure that a newly installed SW takes control immediately, without waiting for all open tabs to close. Useful during development; consider omitting `clients.claim()` in production if mid-session takeover causes page state issues.

**R2 offline fallback.** Storing the offline page in R2 (rather than in Workers Assets) allows updating it without a full deployment. Update the R2 object via the Cloudflare dashboard or API.

## Anti-patterns

- **Registering the SW from inside a `DOMContentLoaded` handler only** — this delays registration and the first install. Register as early as possible with `if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js')`.
- **Caching POST responses** — the Cache API only stores GET responses. Attempting to cache a POST will throw.
- **`Cache-Control: immutable` on the SW script** — browsers may respect this and never check for updates.
- **Serving the manifest without the `icons` array** — Chrome requires at least a 192×192 and a 512×512 icon to show the install prompt.

## Gotchas

- **HTTPS is required.** Service Workers only register on secure origins (`https://` or `localhost`). If your Worker is behind a Cloudflare zone set to "Flexible" SSL, the SW sees an HTTP origin and will refuse to register.
- **Scope vs. path.** A SW at `/app/sw.js` without `Service-Worker-Allowed: /` can only control requests under `/app/`. Pages at `/` will not be controlled.
- **Push subscription expiry.** Push subscriptions can expire or be invalidated by the browser vendor. Handle `410 Gone` responses from the push service by deleting the KV entry.
- **iOS Safari quirks.** iOS 16.4+ supports PWA install and push but requires the user to explicitly add the page to the Home Screen. The `beforeinstallprompt` event does not fire on iOS; show your own install UI prompt instead.

## Verification

```bash
# Deploy
npx wrangler deploy

# Check manifest headers
curl -I https://your-worker.example.com/manifest.webmanifest
# Expect: Content-Type: application/manifest+json

# Check SW headers
curl -I https://your-worker.example.com/sw.js
# Expect: Content-Type: text/javascript, Cache-Control: no-cache

# Lighthouse PWA audit
npx lighthouse https://your-worker.example.com --only-categories=pwa --output=json | \
  jq '.categories.pwa.score'
# Should be 1.0 (100%)
```

## Related

- `documentation/categories/frontend/workers-server-sent-events-stream.md` — push alternative for real-time updates
- `documentation/categories/frontend/workers-image-optimization-pipeline.md` — offline-cached images should use transformed URLs
- Cloudflare R2 docs — storing and retrieving offline fallback assets

## Sources

- https://web.dev/articles/add-manifest
- https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API
- https://developers.cloudflare.com/workers/static-assets/
- https://developers.cloudflare.com/r2/
