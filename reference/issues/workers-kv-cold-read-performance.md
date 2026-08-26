# Workers KV Cold Read Performance Investigation

2026-08-24 / example.com / production

---

## Symptom / Use-case

A Cloudflare Worker reading from KV returns responses in under 5 ms for frequently accessed keys but takes 30–120 ms for the same key after a period of low traffic. The difference is not explained by Worker startup time or Durable Object hibernation — the Worker itself is warm (CPU time is in the normal range), yet `env.KV.get()` takes far longer than expected.

Typical reports:
- A configuration key read at the top of every request is fast for the first few hours after a deploy then becomes slow overnight
- Geographically dispersed users all experience the same cold-read latency spike simultaneously, ruling out a single-region issue
- `Cache-Control: no-cache` is set on the origin response, yet KV reads are still slow

---

## Context

Workers KV uses an **eventually consistent, globally distributed cache** layered over a central store. The read path has two tiers:

1. **Edge cache** — a data-center-local cache populated on first read and refreshed on write propagation. Reads from this tier are sub-millisecond from the Worker's perspective.
2. **Central store** — Cloudflare's persistent KV storage, distributed across several backbone nodes but not at every PoP. A cache miss fetches from here with a round-trip that may be 30–100 ms depending on PoP location.

A key becomes "cold" when:
- The edge cache entry expires (TTL-based or capacity eviction)
- No Worker in that PoP has read the key recently
- The key was recently written and propagation to this PoP has not yet occurred (up to 60 s globally)

KV is **optimized for high-read, low-write workloads**. Keys written once and read millions of times are the ideal case; keys written frequently or keys rarely read from a given PoP will see higher cold-read latency.

---

## Diagnosing Cold Read Latency

### Step 1 — Instrument KV reads with per-call timing

```typescript
// src/kv-instrumented.ts
export async function kvGet<T>(
  kv: KVNamespace,
  key: string,
  options?: KVNamespaceGetOptions<'json'>
): Promise<T | null> {
  const t0 = performance.now();
  const value = await kv.get<T>(key, options ?? { type: 'json' });
  const elapsed = performance.now() - t0;

  const isCold = elapsed > 20; // heuristic: >20ms suggests a cache miss
  console.log(JSON.stringify({
    kv_key: key,
    elapsed_ms: elapsed.toFixed(2),
    hit: value !== null,
    cold: isCold,
  }));

  return value;
}
```

### Step 2 — Layer an in-memory Worker cache over KV

```typescript
// src/worker-cache.ts
// Workers isolates are reused across requests; module-level state persists
const workerLocalCache = new Map<string, { value: unknown; expiresAt: number }>();

export async function cachedKvGet<T>(
  kv: KVNamespace,
  key: string,
  ttlSeconds = 30
): Promise<T | null> {
  const now = Date.now();
  const cached = workerLocalCache.get(key);

  if (cached && cached.expiresAt > now) {
    return cached.value as T;
  }

  const value = await kv.get<T>(key, { type: 'json' });
  if (value !== null) {
    workerLocalCache.set(key, {
      value,
      expiresAt: now + ttlSeconds * 1_000,
    });
  }
  return value;
}
```

> **Warning**: module-level cache is isolate-local. Different isolates serving the same Worker may have different cached values. Only cache data that tolerates up to `ttlSeconds` of staleness.

### Step 3 — Use `cacheTtl` to extend KV's edge cache duration

```typescript
// src/worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // cacheTtl tells KV to keep the edge-cache entry alive for 300 s
    // even if the key's own TTL is shorter or not set.
    // Minimum cacheTtl is 60 s.
    const config = await env.CONFIG_KV.get('site-config', {
      type: 'json',
      cacheTtl: 300,
    });

    if (!config) {
      return new Response('config not found', { status: 503 });
    }

    return new Response(JSON.stringify(config), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

### Step 4 — Diagnose write propagation lag

```typescript
// src/write-and-verify.ts
// Use this script during investigation to measure propagation latency
export async function writeAndPoll(
  kv: KVNamespace,
  key: string,
  value: string,
  maxWaitMs = 70_000
): Promise<number> {
  await kv.put(key, value);
  const writeTs = Date.now();

  while (Date.now() - writeTs < maxWaitMs) {
    const read = await kv.get(key);
    if (read === value) {
      return Date.now() - writeTs; // propagation latency in ms
    }
    await new Promise(r => setTimeout(r, 1_000));
  }

  throw new Error(`KV propagation not observed within ${maxWaitMs}ms`);
}
```

### Step 5 — Check metadata reads separately (metadata is not cached the same way)

```typescript
// src/metadata-check.ts
// getWithMetadata incurs a separate lookup; do not use it on hot paths
export async function getValueOnly<T>(kv: KVNamespace, key: string): Promise<T | null> {
  // Prefer .get() over .getWithMetadata() on the critical path
  return kv.get<T>(key, { type: 'json' });
}

export async function getMetadataSeparately<T, M>(
  kv: KVNamespace,
  key: string
): Promise<{ value: T | null; metadata: M | null }> {
  // Only call this in background / non-critical paths
  const result = await kv.getWithMetadata<T, M>(key, { type: 'json' });
  return { value: result.value, metadata: result.metadata };
}
```

### Step 6 — Emit to Analytics Engine for fleet-wide cold-read tracking

```typescript
// src/analytics-kv.ts
export async function trackedKvGet<T>(
  kv: KVNamespace,
  ae: AnalyticsEngineDataset,
  key: string
): Promise<T | null> {
  const t0 = performance.now();
  const value = await kv.get<T>(key, { type: 'json' });
  const elapsed = performance.now() - t0;

  ae.writeDataPoint({
    blobs: [key, value !== null ? 'hit' : 'miss'],
    doubles: [elapsed],
    indexes: ['kv-read-latency'],
  });

  return value;
}
```

---

## Anti-patterns

- **Calling `kv.get()` inside a loop for per-item lookups** — each call is a separate network round-trip; use `kv.list()` with a prefix and batch the reads, or store related data as a single JSON blob.
- **Using `getWithMetadata()` on the hot path** — this prevents the standard KV edge caching path from being used; metadata reads have different (often higher) latency characteristics.
- **Writing to KV on every request to "refresh" a TTL** — KV writes propagate globally and are rate-limited per namespace; high write frequency is an anti-pattern. Use Durable Objects or Cache API for high-write scenarios.
- **Expecting KV to behave like Redis** — KV is not an in-memory store; its performance profile is that of a CDN-adjacent cache, not a low-latency in-memory database.
- **Not setting `cacheTtl`** — omitting this option leaves edge-cache duration up to the platform default, which may be shorter than your read frequency warrants.

---

## Gotchas

- `cacheTtl` is a **minimum** hint to the edge cache, not a guarantee. The edge cache may evict earlier under memory pressure.
- KV `list()` operations are **not** served from the edge cache — they always hit the central store. Avoid listing on the critical path.
- A KV write from one Worker location may take up to **60 seconds** to propagate to a PoP in a different region. Code that writes then immediately reads from a different geographic location may observe stale or missing data.
- The KV namespace's **per-key size limit** is 25 MiB for the value but only **1 KiB for the key name** itself. Large key names can cause `put()` to fail silently in some SDK versions.
- Module-level (`globalThis`) caches in Workers are **not shared between isolates**. Cloudflare may run multiple isolates for the same Worker concurrently; do not rely on the in-memory cache being globally consistent.
- KV reads count against your **KV read unit quota**; aggressive polling from many Workers simultaneously can exhaust daily limits on the free tier.

---

## Verification

1. Add `kvGet` instrumentation (Step 1) and deploy to production. Filter `wrangler tail` for `cold: true` to confirm cold reads are happening.
2. Add `cacheTtl: 300` to hot-path reads (Step 3). Redeploy and observe in tail logs — cold reads should drop significantly after the first request to each PoP.
3. Optionally add the module-level isolate cache (Step 2) for keys that tolerate 30 s staleness. Observe that the KV call disappears from logs for subsequent requests in the same isolate.
4. Run the write-and-poll script (Step 4) from a Worker in a geographically distant region to confirm propagation timing assumptions.
5. Query the Analytics Engine dataset after 24 hours to chart p50/p95/p99 KV read latency; verify the p95 dropped below your target SLA.

---

## Related

- `kv-metadata-size-limit.md`
- `durable-object-hibernation-wake-latency.md`
- `wrangler-dev-vs-prod-bindings.md`
- `cache-api-vary-header.md`

---

## Sources

- Cloudflare Workers KV — How KV works: https://developers.cloudflare.com/kv/concepts/how-kv-works/
- Cloudflare Workers KV — Read from KV: https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- Cloudflare Workers KV — Performance: https://developers.cloudflare.com/kv/reference/kv-performance/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
