# Periodic Background Sync — Offline-Ready PWA on Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project users open the app expecting a fresh feed even after days offline. The regular
Background Sync API fires only once after a failed request; it does not keep the feed
current while the app is closed. Periodic Background Sync (PBS) lets the installed PWA
periodically fetch new content in the background so the next foreground open is instant,
even without a network pull-to-refresh.

## Context

The Periodic Background Sync API allows an installed PWA to register a tag that the browser
fires at roughly the requested interval. The actual interval is throttled by browser heuristics
(site engagement score, battery, network) and subject to a minimum of ~1 hour in Chrome.
Handlers run inside the Service Worker. Payloads are cached via Cache API or IndexedDB and
served from there when the user opens the app. Cloudflare Pages serves the SW and the static
shell; the cached data comes from the Workers API.

**Browser support**: Chrome/Edge on Android and desktop (flag removed). Safari/Firefox do not
support PBS; feature-detect and degrade to a pull-to-refresh pattern.

## Requesting Permission and Registering the Sync

```typescript
// src/lib/periodicSync.ts
export const PBS_TAG = "wam-feed-refresh";
export const PBS_MIN_INTERVAL_MS = 60 * 60 * 1000; // 1 hour minimum

export async function registerPeriodicSync(): Promise<void> {
  if (!("serviceWorker" in navigator) || !("periodicSync" in ServiceWorkerRegistration.prototype)) {
    console.info("Periodic Background Sync not supported");
    return;
  }

  const registration = await navigator.serviceWorker.ready;

  // Requires "periodic-background-sync" permission
  const status = await navigator.permissions.query({
    name: "periodic-background-sync" as PermissionName,
  });

  if (status.state !== "granted") {
    console.info("Periodic sync permission not granted:", status.state);
    return;
  }

  try {
    await (registration as any).periodicSync.register(PBS_TAG, {
      minInterval: PBS_MIN_INTERVAL_MS,
    });
    console.info("Periodic sync registered:", PBS_TAG);
  } catch (err) {
    console.warn("Periodic sync registration failed:", err);
  }
}

export async function unregisterPeriodicSync(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  const registration = await navigator.serviceWorker.ready;
  await (registration as any).periodicSync?.unregister(PBS_TAG);
}
```

## Service Worker: Handling the Periodic Sync Event

```typescript
// public/sw.ts  (compiled to public/sw.js by Vite/esbuild)
import { PBS_TAG } from "../src/lib/periodicSync";

const FEED_CACHE = "wam-feed-v1";
const FEED_API   = "https://api.example.com/feed?limit=50";

self.addEventListener("periodicsync", (event: Event) => {
  const e = event as any; // PeriodicSyncEvent
  if (e.tag === PBS_TAG) {
    e.waitUntil(refreshFeedCache());
  }
});

async function refreshFeedCache(): Promise<void> {
  try {
    const response = await fetch(FEED_API, { credentials: "include" });
    if (!response.ok) throw new Error(`Feed fetch failed: ${response.status}`);

    const cache = await caches.open(FEED_CACHE);
    // Store with the timestamp so the UI can show "last updated X ago"
    const timestamped = new Response(response.body, {
      status: response.status,
      headers: {
        ...Object.fromEntries(response.headers),
        "X-Cached-At": new Date().toISOString(),
      },
    });
    await cache.put(FEED_API, timestamped);

    // Notify open clients so they can update without a reload
    const clients = await self.clients.matchAll({ type: "window" });
    for (const client of clients) {
      client.postMessage({ type: "FEED_UPDATED", at: Date.now() });
    }
  } catch (err) {
    console.error("Periodic sync feed refresh failed:", err);
    throw err; // Rethrow so the browser knows the sync failed (affects retry heuristics)
  }
}
```

## Service Worker: Intercepting Feed Requests

```typescript
// public/sw.ts (continued)
self.addEventListener("fetch", (event: FetchEvent) => {
  const url = new URL(event.request.url);
  if (url.href === FEED_API) {
    event.respondWith(cacheFirstWithRefresh(event.request));
  }
});

async function cacheFirstWithRefresh(request: Request): Promise<Response> {
  const cached = await caches.match(request);
  if (cached) {
    // Return cached immediately; also revalidate in background
    refreshFeedCache().catch(() => {});
    return cached;
  }
  // No cache — fetch and store
  const response = await fetch(request);
  const cache = await caches.open(FEED_CACHE);
  await cache.put(request, response.clone());
  return response;
}
```

## React Integration: Show Staleness Banner

```tsx
// src/components/FeedStaleBanner.tsx
import { useEffect, useState } from "react";

export function FeedStaleBanner({ onRefresh }: { onRefresh: () => void }) {
  const [staleAt, setStaleAt] = useState<Date | null>(null);

  useEffect(() => {
    if (!navigator.serviceWorker) return;

    const handler = (event: MessageEvent) => {
      if (event.data?.type === "FEED_UPDATED") {
        setStaleAt(null); // Background sync just refreshed — clear banner
      }
    };

    navigator.serviceWorker.addEventListener("message", handler);

    // Check when the cache was last written
    caches.open("wam-feed-v1").then(async (cache) => {
      const response = await cache.match("https://api.example.com/feed?limit=50");
      const cachedAt = response?.headers.get("X-Cached-At");
      if (cachedAt) {
        const age = Date.now() - new Date(cachedAt).getTime();
        if (age > 30 * 60 * 1000) setStaleAt(new Date(cachedAt));
      }
    });

    return () => navigator.serviceWorker.removeEventListener("message", handler);
  }, []);

  if (!staleAt) return null;

  return (
    <div role="status" aria-live="polite" className="feed-stale-banner">
      Feed last updated {formatRelative(staleAt)} —{" "}
      <button onClick={onRefresh}>Refresh now</button>
    </div>
  );
}

function formatRelative(date: Date): string {
  const diff = Math.round((Date.now() - date.getTime()) / 60000);
  return diff < 60 ? `${diff} min ago` : `${Math.round(diff / 60)} hr ago`;
}
```

## Registering the SW and Periodic Sync in App Bootstrap

```typescript
// src/main.tsx
import { registerPeriodicSync } from "./lib/periodicSync";

if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    const registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    console.info("SW registered:", registration.scope);

    // PBS registration should happen after the SW is active
    await registration.active;
    await registerPeriodicSync();
  });
}
```

## Anti-patterns

- **Registering PBS without checking permission first** — Chrome silently rejects the
  registration if the permission is not `granted`; always query first.
- **Fetching excessive data in the sync handler** — The browser monitors data usage during
  background sync; large fetches reduce the frequency of future firings.
- **Not re-throwing errors in `waitUntil`** — Swallowing errors prevents the browser from
  learning the sync failed, breaking its retry/backoff logic.
- **Assuming the interval is exact** — Treat PBS as best-effort background pre-loading, not a
  real-time notification channel.

## Gotchas

- PBS requires the app to be **installed** as a PWA (added to home screen or desktop). It
  does not fire for browser tabs only.
- Chrome enforces a minimum interval (~1 hour) regardless of what `minInterval` you pass.
- The `"periodic-background-sync"` permission is granted automatically when the site has
  high engagement; it cannot be manually triggered in DevTools — use
  `chrome://flags/#enable-periodic-background-sync` for testing.
- Cache eviction: browsers may purge caches if storage is under pressure; always handle
  a cache miss gracefully by falling back to fetch.

## Verification

```bash
# In Chrome DevTools → Application → Background Services → Periodic Background Sync
# Click "Record" then simulate a sync fire via the DevTools UI

# Inspect the feed cache
# Application → Cache storage → wam-feed-v1

# Check registration list
const reg = await navigator.serviceWorker.ready;
const tags = await reg.periodicSync.getTags();
console.log(tags); // ["wam-feed-refresh"]
```

## Related

- `pwa-service-worker-cloudflare-pages.md`
- `browser-service-worker-cache.md`
- `offline-fallback-pages.md`
- `background-fetch-api-r2-progressive-download.md`
- `shared-worker-cloudflare-pages-background-sync.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/Web_Periodic_Background_Synchronization_API
- https://developer.chrome.com/docs/capabilities/periodic-background-sync
- https://developers.cloudflare.com/pages/configuration/serving-pages/
- https://web.dev/articles/periodic-background-sync
