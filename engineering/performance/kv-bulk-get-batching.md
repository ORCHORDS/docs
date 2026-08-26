# KV Bulk Get Batching Optimization

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Worker fetches multiple KV keys per request using sequential `KVNamespace.get()` calls. Each
call is an independent sub-request: with 10 keys and ~5 ms per read, a request accumulates
50 ms of serial KV latency before any computation begins. CPU time and TTFB both suffer.

## Context

Workers KV provides a simple key/value API but does not expose a native multi-get operation.
The optimisation strategy is two-pronged: parallelise reads with `Promise.all` to overlap
network waits, and collapse repeated reads of the same key within a request using a
request-scoped in-memory cache (a "data-loader" pattern). For extremely hot keys a module-scope
short-lived cache eliminates KV sub-requests entirely across multiple requests on the same
warm isolate.

---

## 1. Parallel Fetch with `Promise.all`

Replace sequential `await kv.get()` chains with a single `Promise.all`. All KV reads are
inflight concurrently; total wall time is the slowest individual read, not the sum.

```typescript
interface Env {
  KV: KVNamespace;
}

async function bulkGet(
  keys: string[],
  env: Env,
): Promise<Map<string, string | null>> {
  if (keys.length === 0) return new Map();

  const values = await Promise.all(
    keys.map((k) => env.KV.get(k, { type: 'text', cacheTtl: 60 })),
  );

  return new Map(keys.map((k, i) => [k, values[i]]));
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const keys = ['config:theme', 'config:locale', 'config:flags', 'config:limits'];
    const data = await bulkGet(keys, env);
    return Response.json(Object.fromEntries(data));
  },
};
```

## 2. Request-scoped Deduplication Cache

When the same key is requested multiple times within a single request (e.g., by different
middleware layers), resolve the key only once using a per-request `Map<string, Promise<...>>`.

```typescript
class KVLoader {
  private readonly kv: KVNamespace;
  private readonly pending = new Map<string, Promise<string | null>>();

  constructor(kv: KVNamespace) {
    this.kv = kv;
  }

  get(key: string): Promise<string | null> {
    let p = this.pending.get(key);
    if (!p) {
      p = this.kv.get(key, { type: 'text', cacheTtl: 60 });
      this.pending.set(key, p);
    }
    return p;
  }

  async getMany(keys: string[]): Promise<Map<string, string | null>> {
    const values = await Promise.all(keys.map((k) => this.get(k)));
    return new Map(keys.map((k, i) => [k, values[i]]));
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const loader = new KVLoader(env.KV); // one per request – no cross-request leakage

    // Two independent middleware-style functions both need 'config:flags'
    const [flags, theme] = await Promise.all([
      loader.get('config:flags'),
      loader.get('config:theme'),
    ]);
    // 'config:flags' is fetched once despite being requested by two call sites

    return Response.json({ flags, theme });
  },
};
```

## 3. Module-scope Hot-key Cache

For keys that change rarely (feature flags, routing config), a module-scope cache with TTL
eliminates KV sub-requests entirely for warm isolates.

```typescript
interface CacheEntry {
  value: string | null;
  expiresAt: number;
}

const hotCache = new Map<string, CacheEntry>();
const HOT_TTL_MS = 10_000; // 10 seconds

async function getHot(key: string, env: Env): Promise<string | null> {
  const hit = hotCache.get(key);
  if (hit && hit.expiresAt > Date.now()) return hit.value;

  const value = await env.KV.get(key, 'text');
  hotCache.set(key, { value, expiresAt: Date.now() + HOT_TTL_MS });
  return value;
}

async function bulkGetHot(keys: string[], env: Env): Promise<Map<string, string | null>> {
  const misses: string[] = [];
  const result = new Map<string, string | null>();

  for (const k of keys) {
    const hit = hotCache.get(k);
    if (hit && hit.expiresAt > Date.now()) {
      result.set(k, hit.value);
    } else {
      misses.push(k);
    }
  }

  if (misses.length > 0) {
    const fetched = await Promise.all(misses.map((k) => env.KV.get(k, 'text')));
    for (let i = 0; i < misses.length; i++) {
      const v = fetched[i];
      hotCache.set(misses[i], { value: v, expiresAt: Date.now() + HOT_TTL_MS });
      result.set(misses[i], v);
    }
  }

  return result;
}
```

## 4. Chunked Parallel Fetch for Large Key Sets

Workers have a sub-request concurrency limit. When fetching more than 50 keys, chunk the set
to stay within bounds while still overlapping IO.

```typescript
async function chunkedBulkGet(
  keys: string[],
  env: Env,
  chunkSize = 50,
): Promise<Map<string, string | null>> {
  const result = new Map<string, string | null>();
  for (let i = 0; i < keys.length; i += chunkSize) {
    const chunk = keys.slice(i, i + chunkSize);
    const values = await Promise.all(
      chunk.map((k) => env.KV.get(k, { type: 'text', cacheTtl: 30 })),
    );
    chunk.forEach((k, j) => result.set(k, values[j]));
  }
  return result;
}
```

---

## Anti-patterns

- **Sequential `for...of` with `await kv.get()`** – each iteration blocks on the previous;
  use `Promise.all` instead.
- **No `cacheTtl` on reads** – omitting `cacheTtl` bypasses the built-in edge cache layer;
  set it for any key that does not need sub-second freshness.
- **Storing per-user values in module-scope cache** – the hot cache is isolate-scoped and
  outlives a single request. Only cache keys whose values are safe to share across all users.
- **Unbounded module-scope cache** – without a TTL or size cap the cache grows until the
  isolate is evicted, holding stale data longer than intended.

## Gotchas

- Workers KV is eventually consistent with up to 60 s propagation delay after a `put()`.
  Do not use it for values that require immediate read-your-writes semantics.
- `cacheTtl` minimum is 60 seconds per the KV API; lower values are rounded up.
- Workers sub-request limits: Free tier allows 50 sub-requests per invocation; Paid tier
  allows 1 000. Exceeding the limit throws a `TypeError` at runtime.
- The module-scope cache is per-isolate. Two concurrent Worker instances handling the same
  zone each maintain their own cache; there is no shared in-process state between them.

## Verification

```typescript
// Track cache layer contribution with Server-Timing
function annotate(res: Response, hot: number, kv: number): Response {
  const r = new Response(res.body, res);
  r.headers.set('Server-Timing', `hot-cache;dur=${hot},kv-fetch;dur=${kv}`);
  return r;
}
```

Compare total KV fetch duration before and after batching. Expect wall-time reduction
proportional to key count: 10 sequential reads at 5 ms each → ~50 ms; parallel → ~8 ms.

## Related

- `kv-read-performance.md`
- `kv-eventual-consistency-stale-data.md`
- `workers-subrequest-fanout-parallelism.md`

## Sources

- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- https://developers.cloudflare.com/workers/platform/limits/#subrequests
- https://developers.cloudflare.com/kv/reference/cache-ttl/
