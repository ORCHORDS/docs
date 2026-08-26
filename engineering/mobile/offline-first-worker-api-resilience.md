# Offline-First Resilience for Cloudflare Worker APIs

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

User submits a post on a subway — airplane mode or a silent
CGNAT drop. The app renders it optimistically. On reconnect
the post is absent: the failed POST was never retried. On
high-packet-loss mobile links 20–40 % of writes can vanish
with no error surfacing to the user.

## Context

example project is an anonymous social platform backed by 133+
Cloudflare Worker routes. The client is a mobile-first PWA
with no native shell. Posts are anonymous so duplicate
submissions create no PII risk but do create duplicate D1
rows. The resilience layer must queue, deduplicate, and
reconcile without storing any user identity on-device.

## 1. IndexedDB Outbox Queue and Idempotency Key

Write every mutating request to IndexedDB *before* touching
the network. A client-generated UUID doubles as the
idempotency key. The Worker echoes it; the client deletes
the entry only after a confirmed 2xx.

```ts
// client/outbox.ts
export async function enqueue(payload: MutationPayload) {
  const db = await openDB('example project-outbox', 1, {
    upgrade(d) {
      d.createObjectStore('mutations', { keyPath: 'id' });
    },
  });
  await db.put('mutations', {
    id: crypto.randomUUID(), // idempotency key
    queuedAt: Date.now(),
    retries: 0,
    payload,
  });
}
export const dequeue = async (id: string) =>
  (await openDB('example project-outbox', 1)).delete('mutations', id);
```

On the Worker, store seen keys in KV with a 24-hour TTL:

```ts
// worker/posts.ts
if (await env.IDEMPOTENCY.get(idKey))
  return Response.json({ duplicate: true });
await env.IDEMPOTENCY.put(idKey, '1', { expirationTtl: 86_400 });
```

## 2. Background Sync with Safari / Firefox Fallback

The `sync` event fires when connectivity returns. Supported
in Chrome 49+, Edge 79+, Samsung Internet 5+. **Safari
(iOS/macOS) and Firefox do not support it** — roughly 24 %
of global mobile traffic as of 2026-08-17.

```js
// sw.js
self.addEventListener('sync', (event) => {
  if (event.tag === 'flush-outbox')
    event.waitUntil(flushOutbox()); // must be synchronous
});

async function flushOutbox() {
  const db = await openDB('example project-outbox', 1);
  for (const item of await db.getAll('mutations')) {
    const res = await fetch('/api/posts', {
      method: 'POST',
      headers: { 'Idempotency-Key': item.id,
                 'Content-Type': 'application/json' },
      body: JSON.stringify(item.payload),
    });
    if (res.ok) await db.delete('mutations', item.id);
    // throwing here causes the browser to schedule a retry
  }
}
```

Safari/Firefox fallback — drain from the main thread on the
`online` event:

```ts
window.addEventListener('online', async () => {
  const reg = await navigator.serviceWorker.ready;
  ('sync' in reg)
    ? await reg.sync.register('flush-outbox')
    : await drainOutboxInPage(); // mirrors flushOutbox above
});
```

## 3. SWR Fetch Strategy for GET Endpoints

The Worker emits a short `max-age` with a wider revalidation
window. The service worker serves the cached response
instantly and refreshes it in the background.

```ts
// Worker: GET /api/feed
res.headers.set('Cache-Control',
  'public, max-age=30, stale-while-revalidate=300');
```

```js
// sw.js — stale-while-revalidate for /api/feed
self.addEventListener('fetch', (event) => {
  if (!event.request.url.includes('/api/feed')) return;
  event.respondWith(caches.open('feed-v1').then(async (c) => {
    const hit  = await c.match(event.request);
    const live = fetch(event.request).then((r) => {
      if (r.ok) c.put(event.request, r.clone());
      return r;
    });
    return hit ?? live;
  }));
});
```

## 4. Classifying Failures: Offline / Server / CGNAT

| Mode          | JS signal              | Action              |
|---------------|------------------------|---------------------|
| Airplane mode | `TypeError` (no fetch) | Queue immediately   |
| Server error  | `res.status >= 500`    | Backoff then retry  |
| CGNAT timeout | `AbortError`           | Backoff then retry  |

Carrier-Grade NAT silently kills idle TCP after 30–90 s; the
fetch hangs forever without an abort signal. Always wrap:

```ts
const fetchT = (url: string, opts: RequestInit = {}, ms = 15_000) => {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), ms);
  return fetch(url, { ...opts, signal: c.signal })
           .finally(() => clearTimeout(t));
};
```

`navigator.onLine` returns `true` on a dead CGNAT link.
Treat any `TypeError` or `AbortError` as "offline" and
route the payload straight to the IndexedDB outbox.

## 5. Exponential Backoff and Retry Budget for 503 / 429

```ts
const RETRYABLE = new Set([429, 500, 502, 503, 504]);
const BUDGET_MS = 60_000; // then hand off to Background Sync

async function resilientPost(url: string, body: unknown,
                             idKey: string) {
  const t0 = Date.now();
  for (let n = 0; ; n++) {
    const res = await fetchT(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json',
                 'Idempotency-Key': idKey },
      body: JSON.stringify(body),
    });
    if (res.ok) return res;
    if (!RETRYABLE.has(res.status)) throw res;
    const ra    = res.headers.get('Retry-After');
    const delay = ra ? +ra * 1_000           // honour header
      : Math.min(1_000 * 2 ** n, 30_000) + Math.random() * 500;
    if (Date.now() - t0 + delay > BUDGET_MS)
      throw new Error('RETRY_BUDGET_EXHAUSTED');
    await new Promise((r) => setTimeout(r, delay));
  }
}
```

On `RETRY_BUDGET_EXHAUSTED` enqueue to IndexedDB and
register the `flush-outbox` Background Sync tag.

## 6. Reconciling Optimistic UI on Reconnect

1. Render with `status: 'optimistic'` immediately.
2. On 2xx, swap the temp local ID for the server ID and
   mark `status: 'confirmed'`.
3. After flush, query by idempotency key to close the loop:

```ts
async function reconcile(localId: string, idKey: string) {
  const res = await fetch(`/api/posts/by-key/${idKey}`);
  if (res.ok)            store.replaceDraft(localId, await res.json());
  else if (res.status === 404) store.markFailed(localId);
  // 200 + { duplicate:true } → existing row; merge by key
}
```

Persist `status` in IndexedDB so a page reload does not
re-queue a post whose confirmation was lost in a crash.

## Anti-patterns

- **Fire-and-forget POST** — skipping the outbox; any
  network hiccup silently loses the write permanently.
- **`navigator.onLine` gating** — CGNAT dead links return
  `true`, bypassing the queue and losing the mutation.
- **Unbounded retries** — no budget; drains battery and
  causes a thundering herd when all clients reconnect.
- **Dual-drain without mutex** — flushing from both the
  `sync` event and the `online` handler fires duplicate
  POSTs before either removes the queue entry.
- **Client-only dedup** — a Worker restart or KV lag still
  produces duplicate D1 rows despite local checks.

## Gotchas

- Background Sync is entirely absent from Safari iOS/macOS
  and Firefox; the `online` fallback is the real delivery
  path for roughly half of mobile users.
- Workbox `BackgroundSyncPlugin` owns its own IndexedDB
  store; mixing it with a custom outbox causes double-drain
  unless you share the store name and key format.
- KV has ~60 s eventual-consistency lag across regions;
  under a failover the dedup check may pass twice. Use a
  Durable Object for strict guarantees on high-RPM routes
  (see `kv-eventually-consistent.md`).
- `event.waitUntil()` must be called synchronously in the
  `sync` callback; the browser drops late promises silently.
- `Retry-After` from Cloudflare rate-limit responses is in
  seconds, not milliseconds.

## Verification

- **Offline POST** — disable network; submit a post; confirm
  one entry in IndexedDB `mutations`; re-enable; confirm
  entry deleted and post visible in feed.
- **Duplicate guard** — replay the same `Idempotency-Key`
  twice; assert D1 row count = 1 and body contains
  `{ "duplicate": true }`.
- **CGNAT** — drop all packets for 90 s; confirm `AbortError`
  routes to outbox, not thrown to the caller.
- **Retry budget** — stub Worker to return 503 for 65 s;
  confirm `RETRY_BUDGET_EXHAUSTED` and outbox entry intact.
- **Reconcile** — confirm `status: 'optimistic'` becomes
  `status: 'confirmed'` after flush + re-fetch cycle.

## Related

- `documentation/categories/mobile/pwa-service-worker-patterns.md`
- `documentation/categories/mobile/mobile-offline-sync-conflict-resolution.md`
- `documentation/categories/mobile/mobile-network-resilience.md`
- `documentation/categories/cloudflare/kv-eventually-consistent.md`
- `documentation/categories/mobile/pwa-offline-caching-strategies.md`

## Source URLs (verified 2026-08-17)

- https://caniuse.com/background-sync
- https://developer.mozilla.org/en-US/docs/Web/API/SyncManager/register
- https://wicg.github.io/background-sync/spec/
- https://developers.cloudflare.com/workers/cache/configuration/
- https://developers.cloudflare.com/kv/api/
- https://web.dev/patterns/web-apps/periodic-background-sync
- https://www.testmuai.com/learning-hub/background-sync-browser-support/
