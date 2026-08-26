# Offline-First with Service Workers, Workers API, and Cloudflare Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want your web app to work offline, serve stale content instantly while refreshing in the background, and sync user actions (form submissions, mutations) that occur while offline once connectivity is restored. The Cloudflare Workers API acts as the origin, Cloudflare Queues handles background sync durability, and a browser Service Worker manages local caching and deferred requests.

## Context

- Browser Service Worker (no Workers runtime — this runs in the browser)
- Cloudflare Workers as the API origin (`api.example.com`)
- Cloudflare Queues for durable offline-action replay
- Cache API (browser) for asset and API response caching
- IndexedDB (`idb-keyval` pattern) for offline action queue
- TypeScript 5.x for both Worker and Service Worker code
- Wrangler v3

---

## Section 1 — Service Worker registration and lifecycle

```typescript
// src/sw-register.ts — loaded in the main app bundle
export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) {
    console.warn('Service Workers not supported in this browser');
    return null;
  }

  try {
    const registration = await navigator.serviceWorker.register('/sw.js', {
      scope: '/',
      updateViaCache: 'none', // always check for SW updates
    });

    registration.addEventListener('updatefound', () => {
      const newWorker = registration.installing;
      newWorker?.addEventListener('statechange', () => {
        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
          // New SW installed — notify user to refresh
          dispatchEvent(new CustomEvent('sw-update-available'));
        }
      });
    });

    // Trigger background sync after registration
    if ('sync' in registration) {
      await (registration as SyncRegistration).sync.register('offline-actions');
    }

    return registration;
  } catch (err) {
    console.error('SW registration failed', err);
    return null;
  }
}

// Prompt user when update is available
window.addEventListener('sw-update-available', () => {
  if (confirm('New version available. Reload to update?')) {
    window.location.reload();
  }
});

interface SyncRegistration extends ServiceWorkerRegistration {
  sync: { register(tag: string): Promise<void> };
}
```

---

## Section 2 — Service Worker: stale-while-revalidate caching

```typescript
// public/sw.ts — compiled to public/sw.js (no bundler needed if using swc or tsc directly)
declare const self: ServiceWorkerGlobalScope;

const CACHE_VERSION = 'v3'; // bump on deploy to invalidate old caches
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const API_CACHE = `api-${CACHE_VERSION}`;

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/app.js',
  '/app.css',
  '/manifest.json',
  '/icons/icon-192.png',
];

// ── Install: pre-cache static assets ──────────────────────────────────────────
self.addEventListener('install', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  // Take control immediately without waiting for old SW to retire
  self.skipWaiting();
});

// ── Activate: delete stale caches ─────────────────────────────────────────────
self.addEventListener('activate', (event: ExtendableEvent) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k !== STATIC_CACHE && k !== API_CACHE)
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

// ── Fetch: route-aware strategy ────────────────────────────────────────────────
self.addEventListener('fetch', (event: FetchEvent) => {
  const url = new URL(event.request.url);

  // 1. Non-GET requests: network-only, queue offline
  if (event.request.method !== 'GET') {
    event.respondWith(networkWithOfflineQueue(event.request));
    return;
  }

  // 2. API requests: stale-while-revalidate
  if (url.hostname === 'api.example.com') {
    event.respondWith(staleWhileRevalidate(event.request, API_CACHE));
    return;
  }

  // 3. Static assets: cache-first
  if (STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(cacheFirst(event.request, STATIC_CACHE));
    return;
  }

  // 4. Navigation requests: network-first, fall back to cached shell
  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirstWithShellFallback(event.request));
    return;
  }

  // 5. Everything else: network-only
  event.respondWith(fetch(event.request));
});

// ── Cache strategies ───────────────────────────────────────────────────────────
async function staleWhileRevalidate(request: Request, cacheName: string): Promise<Response> {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  // Revalidate in the background
  const revalidate = fetch(request)
    .then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => null);

  // Return stale immediately if available, otherwise wait for network
  return cached ?? (await revalidate) ?? new Response('Offline', { status: 503 });
}

async function cacheFirst(request: Request, cacheName: string): Promise<Response> {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}

async function networkFirstWithShellFallback(request: Request): Promise<Response> {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cache = await caches.open(STATIC_CACHE);
    return (await cache.match('/index.html')) ?? new Response('Offline', { status: 503 });
  }
}
```

---

## Section 3 — Offline action queue with Background Sync

```typescript
// public/sw.ts (continued)

interface OfflineAction {
  id: string;
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string;
  timestamp: number;
}

// Store offline actions in Cache API (or IndexedDB for structured data)
async function queueOfflineAction(request: Request): Promise<void> {
  const body = await request.clone().text();
  const action: OfflineAction = {
    id: crypto.randomUUID(),
    url: request.url,
    method: request.method,
    headers: Object.fromEntries(request.headers.entries()),
    body,
    timestamp: Date.now(),
  };

  const cache = await caches.open('offline-actions');
  await cache.put(
    new Request(`/offline-action/${action.id}`),
    new Response(JSON.stringify(action))
  );
}

async function replayOfflineActions(): Promise<void> {
  const cache = await caches.open('offline-actions');
  const keys = await cache.keys();

  for (const key of keys) {
    const resp = await cache.match(key);
    if (!resp) continue;

    const action: OfflineAction = await resp.json();

    try {
      const replay = await fetch(action.url, {
        method: action.method,
        headers: action.headers,
        body: action.body || undefined,
      });

      if (replay.ok || replay.status === 409) {
        // 409 Conflict = server already has it (idempotent), still delete
        await cache.delete(key);
      }
    } catch {
      // Network still unavailable — leave in queue for next sync
    }
  }
}

async function networkWithOfflineQueue(request: Request): Promise<Response> {
  try {
    return await fetch(request);
  } catch {
    await queueOfflineAction(request);
    return Response.json(
      { queued: true, message: 'Action saved. Will sync when online.' },
      { status: 202 }
    );
  }
}

// Background Sync event — fires when connectivity is restored
self.addEventListener('sync', (event: SyncEvent) => {
  if (event.tag === 'offline-actions') {
    event.waitUntil(replayOfflineActions());
  }
});

declare class SyncEvent extends ExtendableEvent {
  readonly tag: string;
}
```

---

## Section 4 — Cloudflare Workers API with Queues for durability

When replayed actions reach the Worker origin, enqueue them to Queues for guaranteed processing even if the Worker itself is briefly overloaded.

```typescript
// workers/api/src/index.ts
export interface Env {
  ACTION_QUEUE: Queue<OfflineActionPayload>;
  DB: D1Database;
}

interface OfflineActionPayload {
  type: 'create-order' | 'update-profile' | 'submit-form';
  userId: string;
  data: Record<string, unknown>;
  clientTimestamp: number;
  idempotencyKey: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'POST' && new URL(request.url).pathname === '/api/actions') {
      return handleAction(request, env);
    }
    return new Response('Not found', { status: 404 });
  },

  // Queue consumer — processes replayed offline actions
  async queue(batch: MessageBatch<OfflineActionPayload>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processAction(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error('Failed to process action', msg.body.idempotencyKey, err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function handleAction(request: Request, env: Env): Promise<Response> {
  const payload = await request.json<OfflineActionPayload>();

  // Check idempotency — skip if already processed
  const existing = await env.DB
    .prepare('SELECT id FROM processed_actions WHERE idempotency_key = ?')
    .bind(payload.idempotencyKey)
    .first();

  if (existing) {
    return Response.json({ status: 'already-processed' }, { status: 409 });
  }

  // Enqueue for durable processing
  await env.ACTION_QUEUE.send(payload);

  return Response.json({ status: 'queued' }, { status: 202 });
}

async function processAction(payload: OfflineActionPayload, env: Env): Promise<void> {
  // Idempotent upsert
  await env.DB.prepare(
    'INSERT OR IGNORE INTO processed_actions (idempotency_key, type, user_id, processed_at) VALUES (?, ?, ?, ?)'
  ).bind(payload.idempotencyKey, payload.type, payload.userId, new Date().toISOString()).run();

  switch (payload.type) {
    case 'create-order':
      await env.DB.prepare(
        'INSERT OR IGNORE INTO orders (id, user_id, data, created_at) VALUES (?, ?, ?, ?)'
      ).bind(
        payload.idempotencyKey,
        payload.userId,
        JSON.stringify(payload.data),
        new Date(payload.clientTimestamp).toISOString()
      ).run();
      break;
    default:
      console.warn('Unknown action type', payload.type);
  }
}
```

```toml
# wrangler.toml for the API Worker
name = "api-worker"
main = "workers/api/src/index.ts"
compatibility_date = "2025-08-01"

[[queues.producers]]
binding = "ACTION_QUEUE"
queue = "offline-actions"

[[queues.consumers]]
queue = "offline-actions"
max_batch_size = 10
max_batch_timeout = 30
max_retries = 3
dead_letter_queue = "offline-actions-dlq"

[[d1_databases]]
binding = "DB"
database_name = "api-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

---

## Section 5 — Cache versioning and cache invalidation

```typescript
// src/sw-version.ts — run at build time to inject CACHE_VERSION
// In your build script:
const version = `v${Date.now()}`;
const swContent = await Bun.file('public/sw.ts').text();
const versioned = swContent.replace(/const CACHE_VERSION = '[^']+';/, `const CACHE_VERSION = '${version}';`);
await Bun.write('public/sw.ts', versioned);
```

```bash
# Force clients to pick up new SW and purge old caches
# 1. Bump CACHE_VERSION in sw.ts (or automate via build script above)
# 2. Deploy
wrangler deploy

# Verify active cache version from DevTools console:
# caches.keys().then(console.log)
```

---

## Anti-patterns

- Do not cache `POST`/`PUT`/`DELETE` responses with the Cache API — only cache GET responses.
- Do not use stale-while-revalidate for authenticated user-specific API routes without cache-key scoping (e.g., include a hashed user token in the cache key).
- Do not forget to version your cache — without bumping `CACHE_VERSION` on deploy, users may serve outdated JS/CSS indefinitely.
- Do not implement Background Sync as a polling loop in the SW — register a sync tag and let the browser fire it; polling keeps the SW alive and drains battery.
- Do not store sensitive data (tokens, PII) in the Cache API — it is unencrypted on disk.

## Gotchas

- Background Sync (`SyncEvent`) is a Chrome/Edge feature; Safari supports a subset via periodic background sync only. Always implement a fallback (`online` event listener) for cross-browser support.
- `self.skipWaiting()` in the install event activates the new SW immediately but may cause the new SW to control pages that loaded with the old SW — test for mixed-version states.
- Cloudflare Queues `msg.retry({ delaySeconds })` requires `delaySeconds` to be ≥ 0 and the consumer's `max_retries` to be > 0 in `wrangler.toml`.
- The D1 `INSERT OR IGNORE` idempotency pattern only works if `idempotency_key` has a UNIQUE constraint — add it in your schema migration.
- SW scope is determined by the URL of `sw.js` — a worker at `/dashboard/sw.js` only controls `/dashboard/*`. Register from the root.

## Verification

```bash
# Build and deploy Workers API
wrangler deploy

# Create Queues
wrangler queues create offline-actions
wrangler queues create offline-actions-dlq

# Apply D1 schema
wrangler d1 execute DB --file=./schema.sql

# Open app in browser, open DevTools > Application > Service Workers
# Verify SW is registered and active

# Simulate offline in DevTools (Network tab > Offline)
# Submit a form — should get 202 Queued response
# Go back online — Background Sync fires, DevTools > Application > Background Sync shows replay

# Check Queue stats
wrangler queues list
wrangler queues consumer list offline-actions

# Tail Worker logs to see queue processing
wrangler tail api-worker --format pretty
```

## Related

- `documentation/docs/policies/frontend/workers-alpine-js-minimal-interactivity-workers.md`
- `documentation/backend/queues-consumer-patterns.md`
- `documentation/backend/d1-idempotent-writes.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API
- https://developer.mozilla.org/en-US/docs/Web/API/Background_Synchronization_API
- https://developers.cloudflare.com/d1/
