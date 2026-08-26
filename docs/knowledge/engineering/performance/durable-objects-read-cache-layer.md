# Durable Objects Read Latency Cache Layer

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Durable Object (DO) that stores configuration, session data, or counters receives many
concurrent reads. Each read invokes an RPC call to the DO's single-location instance, adding
10–80 ms of cross-region round-trip latency and consuming CPU budget on the DO itself for reads
that never mutate state.

## Context

Durable Objects execute in a single location regardless of where the requesting Worker runs.
Every RPC – even a simple getter – crosses the network to that location. For read-heavy workloads
the DO becomes a hot spot. The solution is a layered cache: an in-memory map inside the DO
eliminates storage reads; a short-lived cache in the calling Worker collapses duplicate RPCs
within the same isolate; and Workers KV provides a cross-region read layer for data that is
tolerant of seconds of staleness.

---

## 1. In-memory Cache Inside the Durable Object

Store frequently read state in a `Map` after the first `storage.get`. Subsequent reads within
the same DO instance serve from memory, skipping the storage layer entirely.

```typescript
export class SessionStore implements DurableObject {
  private readonly state: DurableObjectState;
  private cache = new Map<string, unknown>();

  constructor(state: DurableObjectState) {
    this.state = state;
    // Eagerly load hot keys after hibernation wake-up
    this.state.blockConcurrencyWhile(async () => {
      const stored = await this.state.storage.get<Record<string, unknown>>('data');
      if (stored) {
        for (const [k, v] of Object.entries(stored)) this.cache.set(k, v);
      }
    });
  }

  async fetch(request: Request): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === '/get') {
      const key = new URL(request.url).searchParams.get('key') ?? '';
      return Response.json(this.cache.get(key) ?? null);
    }

    if (pathname === '/set' && request.method === 'PUT') {
      const { key, value } = await request.json<{ key: string; value: unknown }>();
      this.cache.set(key, value);
      await this.state.storage.put('data', Object.fromEntries(this.cache));
      return new Response('ok');
    }

    return new Response('Not found', { status: 404 });
  }
}
```

## 2. Calling-Worker In-isolate Cache

Cache the DO response in the calling Worker isolate for the lifetime of the isolate (typically
seconds to minutes). Collapses concurrent identical reads within one isolate.

```typescript
interface Env {
  SESSION_DO: DurableObjectNamespace;
}

const localCache = new Map<string, { value: unknown; expiresAt: number }>();
const LOCAL_TTL_MS = 5_000;

async function getCachedDOValue(
  key: string,
  sessionId: string,
  env: Env,
): Promise<unknown> {
  const cacheKey = `${sessionId}:${key}`;
  const hit = localCache.get(cacheKey);
  if (hit && hit.expiresAt > Date.now()) return hit.value;

  const id = env.SESSION_DO.idFromName(sessionId);
  const stub = env.SESSION_DO.get(id);
  const res = await stub.fetch(`https://do/get?key=<redacted-secret>
  const value = await res.json();

  localCache.set(cacheKey, { value, expiresAt: Date.now() + LOCAL_TTL_MS });
  return value;
}
```

## 3. KV Read Cache for Cross-region Staleness Tolerance

Write-through to Workers KV so geographically distant Workers can satisfy reads locally
without routing to the DO's home region.

```typescript
interface Env {
  SESSION_DO: DurableObjectNamespace;
  KV: KVNamespace;
}

const KV_TTL = 10; // seconds

async function getWithKVCache(
  key: string,
  sessionId: string,
  env: Env,
): Promise<unknown> {
  const kvKey = `session:${sessionId}:${key}`;

  // Attempt KV read first – served from nearest PoP
  const cached = await env.KV.get(kvKey, 'json');
  if (cached !== null) return cached;

  // Miss: fetch from DO and populate KV
  const id = env.SESSION_DO.idFromName(sessionId);
  const stub = env.SESSION_DO.get(id);
  const res = await stub.fetch(`https://do/get?key=<redacted-secret>
  const value = await res.json();

  await env.KV.put(kvKey, JSON.stringify(value), { expirationTtl: KV_TTL });
  return value;
}

// Invalidate KV on write
async function setAndInvalidate(
  key: string,
  value: unknown,
  sessionId: string,
  env: Env,
): Promise<void> {
  const id = env.SESSION_DO.idFromName(sessionId);
  const stub = env.SESSION_DO.get(id);
  await stub.fetch(`https://do/set?`, {
    method: 'PUT',
    body: JSON.stringify({ key, value }),
  });
  await env.KV.delete(`session:${sessionId}:${key}`);
}
```

## 4. Batch Read via Single RPC to Reduce Round-trips

Instead of one RPC per key, fetch all needed keys in one call.

```typescript
// DO method
async function handleBatchGet(request: Request, cache: Map<string, unknown>) {
  const keys: string[] = await request.json();
  const result: Record<string, unknown> = {};
  for (const k of keys) result[k] = cache.get(k) ?? null;
  return Response.json(result);
}

// Caller
async function batchGetFromDO(
  keys: string[],
  sessionId: string,
  env: Env,
): Promise<Record<string, unknown>> {
  const id = env.SESSION_DO.idFromName(sessionId);
  const stub = env.SESSION_DO.get(id);
  const res = await stub.fetch('https://do/batch-get', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(keys),
  });
  return res.json();
}
```

---

## Anti-patterns

- **Reading from `this.state.storage` on every request** – storage is durable but not free;
  in-memory maps eliminate repeated disk reads for hot keys.
- **No TTL on calling-Worker cache** – an unbounded in-isolate cache can serve data minutes
  old if the isolate stays alive. Always stamp an `expiresAt`.
- **KV as write-primary store** – KV is eventually consistent and lacks transactions; it is
  appropriate only as a read cache in front of the DO, never as the source of truth.
- **Caching mutable state without an invalidation path** – every write path must invalidate
  or update all cache layers; partial invalidation causes stale reads.

## Gotchas

- DO hibernation clears the in-memory `Map`; `blockConcurrencyWhile` in the constructor
  rebuilds it on wake before any requests are processed.
- `DurableObjectState.storage.get` inside `blockConcurrencyWhile` is serialised against other
  requests; keep the warm-up payload small to avoid blocking the first request.
- Workers KV `delete` is eventually consistent; a stale KV read is possible for up to 60 s
  after deletion in the worst case across all PoPs.
- Local isolate caches are per-isolate and not shared across concurrent Worker instances
  serving the same zone.

## Verification

```typescript
// Add Server-Timing headers to observe cache hit/miss
function withTiming(res: Response, label: string, ms: number): Response {
  const r = new Response(res.body, res);
  r.headers.append('Server-Timing', `${label};dur=${ms}`);
  return r;
}
```

Compare `Server-Timing` for `kv-hit`, `local-hit`, and `do-rpc` paths in production traces.
Target: KV hit < 5 ms, local cache hit < 0.5 ms, DO RPC < 80 ms.

## Related

- `durable-objects-hibernation-wake-latency.md`
- `durable-objects-memory-optimization.md`
- `kv-read-performance.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/state/
- https://developers.cloudflare.com/durable-objects/best-practices/
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
