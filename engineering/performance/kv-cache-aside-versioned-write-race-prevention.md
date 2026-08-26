# KV Cache-Aside Versioned Write Race Prevention

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Multiple Worker invocations update the same KV key concurrently. A slower writer finishes last and overwrites a newer value written by a faster concurrent request, rolling back the cache to stale data. The bug is intermittent and proportional to traffic: it's invisible in development but emerges under production load when parallel requests race to refresh the same cache entry.

## Context

KV is an eventually-consistent store with **last-write-wins** semantics. There is no built-in compare-and-swap (CAS) primitive. When the cache-aside pattern reads from origin, transforms the result, and writes back to KV, the read-compute-write window is tens to hundreds of milliseconds—long enough for a second request to complete the same cycle and overwrite with an older origin snapshot.

The solution is **optimistic versioning**: embed a monotone version token (timestamp or content hash) in KV metadata. Before writing, compare the in-flight version against the stored version; skip the write if a newer version already exists.

---

## Reading with Version Metadata

```typescript
interface CacheEntry<T> {
  data: T;
}

interface CacheMeta {
  version: number; // Unix epoch ms of the origin fetch
  ttl: number;
}

async function getWithVersion<T>(
  kv: KVNamespace,
  key: string
): Promise<{ value: T | null; version: number }> {
  const result = await kv.getWithMetadata<CacheEntry<T>, CacheMeta>(key, "json");

  if (!result.value) {
    return { value: null, version: 0 };
  }

  return {
    value: result.value.data,
    version: result.metadata?.version ?? 0,
  };
}
```

---

## Versioned Conditional Write

```typescript
/**
 * Write to KV only if `newVersion` is greater than the currently stored version.
 * Returns true if the write was performed, false if skipped due to a newer version.
 */
async function conditionalWrite<T>(
  kv: KVNamespace,
  key: string,
  value: T,
  newVersion: number,
  ttlSeconds: number
): Promise<boolean> {
  // Re-read the current version immediately before writing
  const { value: existing, version: currentVersion } = await getWithVersion<T>(kv, key);

  if (currentVersion >= newVersion) {
    // A concurrent request already wrote a newer or equal version; abort
    console.log(`[kv-cas] Skipping stale write for ${key}: stored=${currentVersion} ours=${newVersion}`);
    return false;
  }

  const entry: CacheEntry<T> = { data: value };
  const meta: CacheMeta = { version: newVersion, ttl: ttlSeconds };

  await kv.put(key, JSON.stringify(entry), {
    expirationTtl: ttlSeconds,
    metadata: meta,
  });

  return true;
}
```

---

## Full Cache-Aside Pattern with Race Prevention

```typescript
interface Env {
  CACHE_KV: KVNamespace;
}

interface Product {
  id: string;
  name: string;
  price: number;
}

async function getProduct(env: Env, productId: string): Promise<Product> {
  const cacheKey = `product:${productId}`;
  const CACHE_TTL = 300; // 5 minutes

  // 1. Try cache first
  const { value: cached, version: cachedVersion } = await getWithVersion<Product>(
    env.CACHE_KV,
    cacheKey
  );

  if (cached) {
    return cached;
  }

  // 2. Record the timestamp of the origin fetch BEFORE the fetch starts
  //    so that concurrent fetches can compare who started earlier
  const fetchStartedAt = Date.now();

  const originResponse = await fetch(
    `https://api.example.com/products/${productId}`
  );

  if (!originResponse.ok) {
    throw new Error(`Origin error: ${originResponse.status}`);
  }

  const product: Product = await originResponse.json();

  // 3. Write back only if our version is newer than whatever is in KV now
  //    Uses fetchStartedAt (not fetchEndedAt) so the fastest request wins
  await conditionalWrite(env.CACHE_KV, cacheKey, product, fetchStartedAt, CACHE_TTL);

  return product;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const productId = url.searchParams.get("id");

    if (!productId) {
      return new Response("Missing id", { status: 400 });
    }

    const product = await getProduct(env, productId);
    return Response.json(product);
  },
} satisfies ExportedHandler<Env>;
```

---

## Cache Invalidation with Version Bump via Queue

When a mutation occurs (e.g., a product price update), broadcast an invalidation message so Workers in all regions write a fresh value:

```typescript
interface Env {
  CACHE_KV: KVNamespace;
  INVALIDATION_QUEUE: Queue<{ key: string; newVersion: number }>;
}

// Called by a write API endpoint after updating the database
async function invalidateCacheEntry(env: Env, productId: string): Promise<void> {
  const key = `product:${productId}`;
  const newVersion = Date.now();

  // Option A: Delete immediately (simple, causes a thundering-herd on next read)
  // await env.CACHE_KV.delete(key);

  // Option B: Queue a fresh fetch and overwrite via consumer Worker
  await env.INVALIDATION_QUEUE.send({ key, newVersion });
}

// Queue consumer Worker (separate Worker bound to the same KV namespace)
export const queueHandler: ExportedHandler<Env> = {
  async queue(batch: MessageBatch<{ key: string; newVersion: number }>, env: Env) {
    for (const msg of batch.messages) {
      const { key, newVersion } = msg.body;
      // Extract resource ID from key pattern "product:{id}"
      const productId = key.split(":")[1];

      const freshProduct = await fetch(
        `https://api.example.com/products/${productId}`
      ).then(r => r.json<Product>());

      const written = await conditionalWrite(env.CACHE_KV, key, freshProduct, newVersion, 300);
      console.log(`Invalidation for ${key}: written=${written}`);
      msg.ack();
    }
  },
};
```

---

## Monitoring Write Skips

Track how often conditional writes are skipped to tune cache TTLs and detect anomalous contention:

```typescript
import { AnalyticsEngineDataset } from "@cloudflare/workers-types";

interface Env {
  CACHE_KV: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset;
}

async function trackedConditionalWrite<T>(
  env: Env,
  key: string,
  value: T,
  version: number,
  ttl: number
): Promise<void> {
  const written = await conditionalWrite(env.CACHE_KV, key, value, version, ttl);

  env.ANALYTICS.writeDataPoint({
    blobs: [key, written ? "write" : "skip"],
    doubles: [version],
    indexes: [key.split(":")[0]], // namespace prefix as index
  });
}
```

---

## Anti-patterns

- **Using `Date.now()` as version at write-time rather than fetch-start-time**: a slow origin call makes a late write look newer. Record the timestamp immediately before the origin fetch, not after.
- **Deleting the KV key on invalidation without a follow-up warm-up**: every delete creates a cold cache miss for all concurrent readers. Prefer overwriting with the fresh value via a queue consumer.
- **Relying on KV `metadata` version without re-reading before write**: the `getWithVersion` read and the `kv.put` are not atomic. Always re-read inside `conditionalWrite` immediately before the put.
- **Using a counter as version instead of a timestamp**: a counter requires its own synchronized state (another KV key or Durable Object), adding a round-trip. A millisecond timestamp is monotone and needs no external coordination for cache freshness use-cases.

## Gotchas

- KV **eventual consistency** means a conditional write may not be immediately visible to readers in a different region. The version-check only prevents *backward* writes; it does not prevent brief periods where different regions see different versions.
- KV metadata is limited to **1024 bytes** of JSON. Keep `CacheMeta` small; do not embed large objects.
- The re-read inside `conditionalWrite` costs an additional KV read unit. At scale (millions of cache misses per day) this doubles KV read costs during miss bursts. Weigh against the correctness benefit.
- There is a **~1 ms consistency window** between the re-read and the put where another writer can slip in with the same version. Use a content hash (e.g., SHA-1 of the serialized value) rather than a timestamp for true content-addressed versioning.

## Verification

```bash
# Simulate concurrent cache misses with hey and check for stale data
hey -n 100 -c 50 "https://myworker.example.workers.dev/?id=42"

# Check KV metadata version via Wrangler
wrangler kv key get --namespace-id=<ID> "product:42" --metadata
# Expected metadata: {"version":<recent timestamp>,"ttl":300}

# Confirm write-skip count in Analytics Engine
# SELECT blob2, count() FROM <dataset> WHERE blob1 = 'product:42'
# GROUP BY blob2  → should see "skip" rows when concurrent requests race
```

## Related

- `kv-eventual-consistency-stale-data.md`
- `kv-bulk-get-batching.md`
- `cache-stampede-prevention.md`
- `workers-request-coalescing-deduplication.md`
- `durable-objects-storage-read-coalescing.md`

## Sources

- KV `getWithMetadata` API: https://developers.cloudflare.com/kv/api/read-key-value-pairs/#get-value-and-metadata
- KV `put` metadata: https://developers.cloudflare.com/kv/api/write-key-value-pairs/#create-expiring-keys
- KV consistency model: https://developers.cloudflare.com/kv/reference/consistency/
