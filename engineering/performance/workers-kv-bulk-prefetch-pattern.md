# KV Bulk Prefetch Pattern to Eliminate Sequential Round-Trips

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Worker handler reads several KV keys sequentially — user session, feature flags,
personalization config, A/B variant — each `await env.KV.get()` adding 5–15 ms. On a
route that needs 6 keys, that is 30–90 ms of pure I/O latency before any business logic
runs. The fix is to issue all reads in parallel at the top of the request and store
results in a request-scoped cache.

---

## Context

KV reads within the same Cloudflare region are fast (5–15 ms) but not free. Sequential
await chains serialize I/O that can run in parallel. `Promise.all` issues all reads
concurrently and resolves when the last one completes — total latency is the slowest
read, not the sum of all reads.

A request-scoped prefetch cache (a plain `Map` keyed by KV key name) ensures each key
is read once per request, even if multiple functions in the same handler would otherwise
call `KV.get()` independently. This is especially important in modular Worker code where
middleware, auth layers, and business logic each reach for KV.

**Cold isolate warm-up**: On a fresh isolate (new deployment, scaled-out instance) the
in-isolate module-scope cache is empty. Prefetching at request start fills it for
subsequent requests on the same isolate.

---

## Solution

### 1. Basic parallel prefetch with Promise.all

```typescript
interface Env {
  APP_KV: KVNamespace;
}

interface RequestContext {
  userId: string;
  kvCache: Map<string, string | null>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const userId = extractUserId(request);

    // Determine all keys needed for this request
    const keysToFetch = [
      `session:${userId}`,
      `flags:global`,
      `flags:user:${userId}`,
      `ab:variant:${userId}`,
      `config:theme`,
      `ratelimit:${userId}`,
    ];

    // Issue all reads in parallel — total latency = slowest single read
    const values = await Promise.all(
      keysToFetch.map((key) => env.APP_KV.get(key))
    );

    // Build request-scoped cache
    const kvCache = new Map<string, string | null>(
      keysToFetch.map((key, i) => [key, values[i]])
    );

    const ctx: RequestContext = { userId, kvCache };
    return handleRequest(request, env, ctx);
  },
};
```

### 2. Request-scoped KV accessor

```typescript
class KVCache {
  private cache: Map<string, string | null>;
  private kv: KVNamespace;
  private hits = 0;
  private misses = 0;

  constructor(kv: KVNamespace, prefetched: Map<string, string | null>) {
    this.kv = kv;
    this.cache = new Map(prefetched);
  }

  async get(key: string): Promise<string | null> {
    if (this.cache.has(key)) {
      this.hits++;
      return this.cache.get(key) ?? null;
    }
    // Cache miss — fetch from KV and store
    this.misses++;
    const value = await this.kv.get(key);
    this.cache.set(key, value);
    return value;
  }

  async getJSON<T>(key: string): Promise<T | null> {
    const raw = await this.get(key);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  }

  stats() {
    return {
      hits: this.hits,
      misses: this.misses,
      hitRate: this.hits / (this.hits + this.misses || 1),
      size: this.cache.size,
    };
  }
}
```

### 3. Determining prefetch keys from URL and JWT

```typescript
async function resolvePrefetchKeys(
  request: Request,
  env: Env,
): Promise<string[]> {
  const url = new URL(request.url);
  const keys: string[] = ['flags:global', 'config:theme', 'config:maintenance'];

  // Route-specific keys
  if (url.pathname.startsWith('/products')) {
    keys.push('catalog:featured', 'promos:active');
  } else if (url.pathname.startsWith('/checkout')) {
    keys.push('payments:config', 'shipping:rates');
  }

  // User-specific keys from JWT (decoded without verification for key resolution;
  // full verification happens later)
  const token = request.headers.get('Authorization')?.replace('Bearer ', '');
  if (token) {
    const payload = decodeJWTPayload(token);
    if (payload?.sub) {
      const uid = payload.sub;
      keys.push(
        `session:${uid}`,
        `flags:user:${uid}`,
        `ab:variant:${uid}`,
        `ratelimit:${uid}`,
      );
    }
  }

  return keys;
}

function decodeJWTPayload(token: string): Record<string, string> | null {
  try {
    const [, payloadB64] = token.split('.');
    const json = atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json);
  } catch {
    return null;
  }
}
```

### 4. Prefetch hit rate measurement

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const keys = await resolvePrefetchKeys(request, env);
    const values = await Promise.all(keys.map((k) => env.APP_KV.get(k)));
    const prefetched = new Map(keys.map((k, i) => [k, values[i]]));
    const cache = new KVCache(env.APP_KV, prefetched);

    const response = await handleRequest(request, env, cache);

    // Emit metrics asynchronously — do not block response
    ctx.waitUntil(
      recordKVMetrics(cache.stats(), new URL(request.url).pathname, env)
    );

    return response;
  },
};

async function recordKVMetrics(
  stats: ReturnType<KVCache['stats']>,
  path: string,
  env: Env,
): Promise<void> {
  // Write to Analytics Engine or a metrics KV key
  const key = `metrics:kv:${new Date().toISOString().slice(0, 10)}:${path.replace(/\//g, '_')}`;
  const existing = await env.APP_KV.get(key, { type: 'json' }) as Record<string, number> | null;
  const updated = {
    requests: (existing?.requests ?? 0) + 1,
    totalHits: (existing?.totalHits ?? 0) + stats.hits,
    totalMisses: (existing?.totalMisses ?? 0) + stats.misses,
  };
  await env.APP_KV.put(key, JSON.stringify(updated), { expirationTtl: 86400 * 7 });
}
```

### 5. Module-scope isolate warm-up cache

```typescript
// Module-scope: persists across requests on the same isolate
const isolateCache = new Map<string, { value: string | null; expires: number }>();
const ISOLATE_CACHE_TTL_MS = 60_000; // 1 minute

async function getCachedKV(
  kv: KVNamespace,
  key: string,
): Promise<string | null> {
  const now = Date.now();
  const cached = isolateCache.get(key);

  if (cached && cached.expires > now) {
    return cached.value;
  }

  const value = await kv.get(key);
  isolateCache.set(key, { value, expires: now + ISOLATE_CACHE_TTL_MS });
  return value;
}

// Warm up on first request for static keys
let warmed = false;
async function warmIsolateCache(env: Env): Promise<void> {
  if (warmed) return;
  warmed = true;
  const staticKeys = ['flags:global', 'config:theme', 'config:maintenance'];
  await Promise.all(staticKeys.map((k) => getCachedKV(env.APP_KV, k)));
}
```

---

## Implementation Details

- **`Promise.all` vs `Promise.allSettled`**: Use `Promise.allSettled` if individual KV
  read failures should not abort the entire prefetch. Check each result's `status`.
- **KV consistency**: KV is eventually consistent. A key written in the same request will
  not be visible via a subsequent `get` in the same isolate unless you populate the cache
  manually after writing.
- **TTL on prefetched values**: KV metadata includes `metadata.expiration`. If you need
  to respect per-key TTL in the request scope, store `getWithMetadata` results.
- **Prefetch over-fetching**: If route detection is uncertain, err toward prefetching keys
  that may not be used. A KV read for an unused key costs ~5 ms; a sequential miss costs
  the same latency but cannot be parallelized.

---

## Anti-patterns

- **Sequential awaits**: `const a = await kv.get('a'); const b = await kv.get('b');`
  serializes I/O. This is the primary anti-pattern this article addresses.
- **Re-fetching in every middleware layer**: Without a request-scoped cache, the same
  key may be fetched 3–5 times across middleware, auth, and handler code.
- **Module-scope caching without TTL**: Stale values in the isolate cache cause
  correctness bugs. Always set an expiry.
- **Prefetching in `waitUntil`**: Prefetch must complete before the response is built.
  `waitUntil` runs after the response is sent — too late.

---

## Gotchas

- KV is not transactional. Between prefetch and use, another process may have updated
  the key. For critical consistency (e.g., rate limits), always fetch from KV at the
  point of use, not from the cache.
- `Promise.all` with 10+ KV reads may approach the KV rate limit for a single isolate
  (1000 reads/s per namespace per PoP). Monitor with KV analytics.
- In local Wrangler dev (`wrangler dev`), KV reads are local and near-zero latency.
  The parallel prefetch benefit only manifests in production.

---

## Verification

```typescript
// Measure sequential vs parallel
async function benchmark(kv: KVNamespace) {
  const keys = Array.from({ length: 6 }, (_, i) => `test:key:${i}`);

  console.time('sequential');
  for (const key of keys) await kv.get(key);
  console.timeEnd('sequential');

  console.time('parallel');
  await Promise.all(keys.map((k) => kv.get(k)));
  console.timeEnd('parallel');
}
```

Add `Server-Timing` headers to expose prefetch latency to browser DevTools:

```typescript
const t0 = Date.now();
await Promise.all(keys.map((k) => env.APP_KV.get(k)));
const prefetchMs = Date.now() - t0;
// Add to response: Server-Timing: kv-prefetch;dur=12
```

---

## Related

- `speculative-prefetch-kv.md`
- `workers-d1-read-replica-pattern.md`
- `workers-request-coalescing-durable-objects.md`
- `workers-cache-api-fine-grained-control.md`

---

## Sources

- Cloudflare KV documentation — https://developers.cloudflare.com/kv/
- Cloudflare KV limits — https://developers.cloudflare.com/kv/platform/limits/
- MDN Promise.all — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/all
- Cloudflare Workers best practices — https://developers.cloudflare.com/workers/best-practices/
