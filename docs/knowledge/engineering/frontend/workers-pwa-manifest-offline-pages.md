# Progressive Web App on Cloudflare Pages / Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are deploying a PWA on Cloudflare Pages and need:
1. A dynamic `manifest.webmanifest` served by a Pages Function (theme-colour
   from env, start_url per locale)
2. An offline fallback page cached via the Cache API when the network is down
3. A deferred install prompt so you control when the A2HS banner appears
4. Background sync to replay failed form submissions once connectivity returns

## Context

- **Cloudflare Pages** serves static assets; **Pages Functions** handle
  dynamic routes under `functions/`
- The **Cache API** is available in both Service Workers (browser) and
  Workers (edge); here we use it in the browser SW
- **Background Sync** requires the SW to be registered with
  `'background-sync'` permission and a `sync` event handler
- `manifest.webmanifest` must be served with
  `Content-Type: application/manifest+json`

---

## 1 — Dynamic manifest via Pages Function

```typescript
// functions/manifest.webmanifest.ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  THEME_COLOR: string;  // e.g. "#0066cc"
  APP_NAME: string;
}

export const onRequestGet: PagesFunction<Env> = async ({ env, request }) => {
  const locale = new URL(request.url).searchParams.get('locale') ?? 'en';

  const manifest = {
    name: env.APP_NAME,
    short_name: env.APP_NAME,
    description: 'Cloudflare-powered PWA',
    start_url: `/${locale}/`,
    display: 'standalone',
    background_color: '#ffffff',
    theme_color: env.THEME_COLOR ?? '#0066cc',
    orientation: 'portrait-primary',
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any maskable' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
    ],
    screenshots: [
      { src: '/screenshots/home.png', sizes: '1280x720', type: 'image/png', form_factor: 'wide' },
    ],
    categories: ['productivity'],
    shortcuts: [
      { name: 'Dashboard', url: `/${locale}/dashboard`, icons: [{ src: '/icons/dashboard.png', sizes: '96x96' }] },
    ],
  };

  return new Response(JSON.stringify(manifest), {
    headers: {
      'content-type': 'application/manifest+json',
      'cache-control': 'public, max-age=3600',
    },
  });
};
```

Link from HTML:
```html
<link rel="manifest" >
<meta name="theme-color" content="#0066cc">
```

## 2 — Service Worker: pre-cache shell + offline fallback

```typescript
// public/sw.ts  (compiled to public/sw.js)
declare const self: ServiceWorkerGlobalScope;

const CACHE = 'app-v1';
const OFFLINE_URL = '/offline.html';
const PRECACHE = [
  '/',
  '/offline.html',
  '/styles.css',
  '/app.js',
  '/icons/icon-192.png',
];

// Install: pre-cache shell assets
self.addEventListener('install', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(PRECACHE))
  );
  // Activate immediately, don't wait for old SW to finish
  self.skipWaiting();
});

// Activate: evict stale caches
self.addEventListener('activate', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch: network-first for HTML, cache-first for assets, offline fallback
self.addEventListener('fetch', (event: FetchEvent) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (request.headers.get('accept')?.includes('text/html')) {
    // Network-first for HTML
    event.respondWith(
      fetch(request)
        .then(resp => {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(request, clone));
          return resp;
        })
        .catch(async () => {
          const cached = await caches.match(request);
          return cached ?? (await caches.match(OFFLINE_URL))!;
        })
    );
  } else {
    // Cache-first for assets
    event.respondWith(
      caches.match(request).then(cached =>
        cached ?? fetch(request).then(resp => {
          caches.open(CACHE).then(c => c.put(request, resp.clone()));
          return resp;
        })
      )
    );
  }
});

// Background Sync: replay queued POST requests
self.addEventListener('sync', (event: SyncEvent) => {
  if (event.tag === 'form-sync') {
    event.waitUntil(replayQueuedRequests());
  }
});

async function replayQueuedRequests(): Promise<void> {
  const db = await openQueue();
  const tx = db.transaction('queue', 'readwrite');
  const store = tx.objectStore('queue');
  const all: Array<{ id: number; url: string; body: string; headers: Record<string, string> }> =
    await promisify(store.getAll());

  for (const item of all) {
    try {
      const resp = await fetch(item.url, {
        method: 'POST',
        headers: item.headers,
        body: item.body,
      });
      if (resp.ok) await promisify(store.delete(item.id));
    } catch {
      // Leave in queue; sync will retry
    }
  }
}

// Minimal IDB helpers (no library)
function openQueue(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('form-queue', 1);
    req.onupgradeneeded = () => req.result.createObjectStore('queue', { keyPath: 'id', autoIncrement: true });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
function promisify<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error); });
}
```

## 3 — Deferred install prompt (client)

```typescript
// public/pwa.ts
let deferredPrompt: BeforeInstallPromptEvent | null = null;

window.addEventListener('beforeinstallprompt', (e: Event) => {
  // Prevent the default mini-infobar
  e.preventDefault();
  deferredPrompt = e as BeforeInstallPromptEvent;
  document.getElementById('install-btn')?.removeAttribute('hidden');
});

document.getElementById('install-btn')?.addEventListener('click', async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  console.log(`Install outcome: ${outcome}`);
  deferredPrompt = null;
  document.getElementById('install-btn')?.setAttribute('hidden', '');
});

// Register SW
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js', { scope: '/' })
    .then(reg => console.log('SW registered', reg.scope))
    .catch(err => console.error('SW registration failed', err));
}

// Queue a form submission for background sync
async function queueFormSubmit(url: string, body: string, headers: Record<string, string>): Promise<void> {
  const db = await openQueueClient();
  const tx = db.transaction('queue', 'readwrite');
  tx.objectStore('queue').add({ url, body, headers });
  await new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = rej; });
  const reg = await navigator.serviceWorker.ready;
  await reg.sync.register('form-sync');
}

function openQueueClient(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('form-queue', 1);
    req.onupgradeneeded = () => req.result.createObjectStore('queue', { keyPath: 'id', autoIncrement: true });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
```

## Anti-patterns

- **Cache-first strategy for HTML** — users get stale pages indefinitely; use
  network-first (stale-while-revalidate for SPAs is acceptable).
- **Including API responses in the pre-cache** — they become stale immediately;
  only cache static shell assets at install time.
- **Serving the manifest with `text/plain`** — Chrome silently ignores it;
  always use `application/manifest+json`.

## Gotchas

1. `skipWaiting()` + `clients.claim()` can cause the new SW to take control of
   pages that loaded with the old SW's assets — test for asset version mismatches.
2. Background Sync is not yet supported in Safari (as of 2026-08); queue items
   persist in IDB but won't replay automatically — also fire on
   `navigator.onLine` change as a fallback.
3. Pages Functions filenames map to URL paths: `functions/manifest.webmanifest.ts`
   → `/manifest.webmanifest`. Dots are allowed in filenames.
4. Chrome requires HTTPS (or localhost) for `beforeinstallprompt` to fire.

## Verification

```bash
# Deploy to Pages preview
npx wrangler pages deploy public --project-name=my-pwa

# Validate manifest
curl -I https://my-pwa.pages.dev/manifest.webmanifest \
  | grep content-type
# Expected: content-type: application/manifest+json

# Lighthouse PWA audit
npx lighthouse https://my-pwa.pages.dev --only-categories=pwa --output=json \
  | jq '.categories.pwa.score'
# Expected: 1 (100 %)

# Test offline: DevTools → Network → Offline → reload page
# Should show /offline.html
```

## Related

- `documentation/docs/policies/frontend/workers-web-push-notifications-vapid.md`
- `documentation/workers/workers-cache-api-patterns.md`

## Sources

- https://web.dev/learn/pwa/
- https://developers.cloudflare.com/pages/functions/
- https://developer.mozilla.org/en-US/docs/Web/API/Background_Synchronization_API
- https://w3c.github.io/manifest/
