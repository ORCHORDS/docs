# Read Repair for Eventual Consistency with Workers KV

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Cloudflare KV is an eventually consistent store: writes propagate globally within ~60 seconds, but a read in a remote PoP may return a stale value during that window. For most content (product listings, configuration, feature flags) this lag is acceptable. For data that changes frequently and where staleness causes user-visible errors—account balances, inventory counts, session tokens—the application needs a strategy to detect and repair stale reads without abandoning KV entirely.

Read repair is a background self-healing technique: when a Worker reads from KV and detects a potentially stale value (by comparing a version token or timestamp), it re-fetches the authoritative value from D1 (the source of truth), serves the fresh value to the caller, and writes the corrected value back to KV asynchronously. Subsequent reads from the same PoP see the corrected value without a round-trip to D1.

## Context

Cloudflare Workers KV stores values with optional metadata. Using metadata to carry a version counter or a source-of-truth checksum enables the Worker to compare the KV value's version against an expected version without reading the full D1 row. The repair write back to KV uses `ctx.waitUntil()` to run after the response is sent, keeping the critical path latency to a single KV read.

D1 is the authoritative store. Every write to D1 increments a `version` integer on the entity row. KV entries store the value plus `{ version, writtenAt }` in their metadata. If `kv.version < expected_version` (or if the metadata is absent), the Worker triggers a repair.

## Versioned KV Write Pattern

All writes to KV must include version metadata so the repair check can compare versions cheaply:

```typescript
// src/cache/kv-versioned.ts
import { Env } from '../types';

export interface VersionedMetadata {
  version: number;
  writtenAt: string;  // ISO-8601
}

export async function putVersioned<T>(
  kv: KVNamespace,
  key: string,
  value: T,
  version: number,
  ttl: number = 300
): Promise<void> {
  const metadata: VersionedMetadata = {
    version,
    writtenAt: new Date().toISOString(),
  };

  await kv.put(key, JSON.stringify(value), {
    expirationTtl: ttl,
    metadata,
  });
}

export async function getVersioned<T>(
  kv: KVNamespace,
  key: string
): Promise<{ value: T; version: number } | null> {
  const result = await kv.getWithMetadata<T, VersionedMetadata>(key, { type: 'json' });
  if (!result.value) return null;

  return {
    value: result.value,
    version: result.metadata?.version ?? 0,
  };
}
```

## Read Repair Implementation

The repair path is triggered when the KV version is behind the D1 version. The fresh value is served immediately; the KV write-back is deferred with `ctx.waitUntil()`.

```typescript
// src/cache/read-repair.ts
import { Env } from '../types';
import { putVersioned, getVersioned } from './kv-versioned';

export async function getWithRepair<T>(
  key: string,
  kv: KVNamespace,
  fetchFromSource: () => Promise<{ value: T; version: number } | null>,
  ctx: ExecutionContext,
  options: { ttl?: number; maxStalenessSeconds?: number } = {}
): Promise<{ value: T; version: number; repaired: boolean } | null> {
  const { ttl = 300, maxStalenessSeconds = 60 } = options;

  const cached = await getVersioned<T>(kv, key);

  if (cached === null) {
    // Cache miss — fetch from source and populate KV
    const source = await fetchFromSource();
    if (!source) return null;

    ctx.waitUntil(putVersioned(kv, key, source.value, source.version, ttl));
    return { ...source, repaired: false };
  }

  // Check staleness: compare writtenAt age against the maxStalenessSeconds threshold
  // as a soft signal (does not guarantee freshness, but limits worst-case lag)
  const result = await kv.getWithMetadata<T, { version: number; writtenAt: string }>(key, { type: 'json' });
  const writtenAt = result.metadata?.writtenAt;
  const ageSeconds = writtenAt
    ? (Date.now() - new Date(writtenAt).getTime()) / 1000
    : Infinity;

  if (ageSeconds < maxStalenessSeconds) {
    // Value is fresh enough — serve from cache
    return { ...cached, repaired: false };
  }

  // Value may be stale — fetch authoritative value from source
  const source = await fetchFromSource();
  if (!source) return { ...cached, repaired: false };  // Source unavailable, serve stale

  if (source.version > cached.version) {
    // Stale detected — serve fresh value and repair KV in background
    ctx.waitUntil(putVersioned(kv, key, source.value, source.version, ttl));
    return { ...source, repaired: true };
  }

  // KV version is current — refresh TTL and writtenAt
  ctx.waitUntil(putVersioned(kv, key, cached.value, cached.version, ttl));
  return { ...cached, repaired: false };
}
```

## Wiring into a Workers Handler

```typescript
// src/handlers/product.ts
import { Env } from '../types';
import { getWithRepair } from '../cache/read-repair';

interface Product {
  id: string;
  name: string;
  price: number;
  inventoryCount: number;
}

export async function getProduct(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const productId = new URL(request.url).pathname.split('/').pop()!;

  const result = await getWithRepair<Product>(
    `product:${productId}`,
    env.PRODUCT_CACHE,
    () => fetchProductFromD1(productId, env),
    ctx,
    { ttl: 120, maxStalenessSeconds: 30 }
  );

  if (!result) {
    return new Response('Not Found', { status: 404 });
  }

  const headers = new Headers({ 'Content-Type': 'application/json' });
  if (result.repaired) {
    headers.set('X-Cache-Repaired', 'true');
    headers.set('X-Cache-Version', String(result.version));
  }

  return new Response(JSON.stringify(result.value), { headers });
}

async function fetchProductFromD1(
  productId: string,
  env: Env
): Promise<{ value: Product; version: number } | null> {
  const row = await env.DB.prepare(
    'SELECT id, name, price, inventory_count, version FROM products WHERE id = ?'
  ).bind(productId).first<Product & { version: number; inventory_count: number }>();

  if (!row) return null;

  return {
    value: {
      id: row.id,
      name: row.name,
      price: row.price,
      inventoryCount: row.inventory_count,
    },
    version: row.version,
  };
}
```

## Version Increment on Write

Writes to D1 must increment the `version` column atomically so the repair check has a reliable signal:

```typescript
// src/handlers/product-update.ts
export async function updateProduct(
  productId: string,
  update: Partial<Product>,
  env: Env
): Promise<void> {
  // Atomic version increment in D1
  await env.DB.prepare(
    `UPDATE products
     SET name = COALESCE(?, name),
         price = COALESCE(?, price),
         inventory_count = COALESCE(?, inventory_count),
         version = version + 1,
         updated_at = ?
     WHERE id = ?`
  ).bind(
    update.name ?? null,
    update.price ?? null,
    update.inventoryCount ?? null,
    new Date().toISOString(),
    productId
  ).run();

  // Invalidate KV immediately (repair will re-populate on next read)
  await env.PRODUCT_CACHE.delete(`product:${productId}`);
}
```

## Metrics and Observability

Track repair rate in Analytics Engine to detect regions with excessive KV lag or misconfigured TTLs:

```typescript
// src/cache/read-repair-metrics.ts
export function recordRepairMetric(
  env: Env,
  key: string,
  repaired: boolean,
  ageSeconds: number
): void {
  env.ANALYTICS.writeDataPoint({
    blobs: [key.split(':')[0]],  // entity type (e.g., "product")
    doubles: [repaired ? 1 : 0, ageSeconds],
    indexes: [repaired ? 'repaired' : 'fresh'],
  });
}
```

## Anti-patterns

- Using read repair as a substitute for cache invalidation on write—KV `delete()` after every D1 write is still the primary freshness mechanism; read repair is the safety net, not the first line of defense.
- Performing the repair write synchronously on the critical path—this doubles read latency. Always use `ctx.waitUntil()` for repair writes.
- Using wall-clock age alone without a version counter—clocks can drift and `writtenAt` can be wrong if the KV metadata was written by a Worker with a skewed clock. Version counters from D1 are authoritative.
- Setting `maxStalenessSeconds` to zero—this causes every read to hit D1, defeating the purpose of KV. Use a floor of at least 5–10 seconds.
- Calling `fetchFromSource()` without a circuit breaker—if D1 is degraded, every stale read triggers a D1 call and amplifies the load.

## Gotchas

- `kv.getWithMetadata()` counts as a separate read operation; two KV reads per request (one for the value, one for metadata) doubles KV billing on the repair path. Combine by using `getWithMetadata()` for every read.
- KV metadata has a size limit of 1 KB. Keep `VersionedMetadata` small; do not store the full entity in metadata.
- `ctx.waitUntil()` grants the Worker extra CPU time after the response is sent, but the wall-clock time limit (30 s on paid plans) still applies. If the repair write to KV itself fails, the next read will re-trigger the repair—eventual convergence is maintained.
- In Workers Unbound, `ctx.waitUntil()` is unbounded in CPU time, but standard Workers have a 30 s total wall-clock limit including `waitUntil()` tasks. For high-throughput repairs consider offloading to a Queue instead.
- If multiple PoPs simultaneously detect staleness and repair the same key, they all write the same `version` value back. This is safe (idempotent) but generates redundant KV writes during propagation windows.

## Verification

1. Write a product to D1 with `version = 1`. Manually insert a KV entry for the same key with `version = 0` and `writtenAt` set 60 seconds in the past.
2. Request the product via the handler. Confirm the response has `X-Cache-Repaired: true` and `X-Cache-Version: 1`.
3. Request again immediately. Confirm `X-Cache-Repaired` is absent (the repair already wrote the fresh value to KV).
4. Update the product in D1 (version increments to 2) and delete the KV key. Request the product—confirm a cache miss populates KV with `version = 2`.
5. Query Analytics Engine: confirm the `repaired` data point was recorded for step 2 and `fresh` for step 3.

## Related

- `caching-topology-cloudflare-native.md` — KV, Cache API, and Durable Objects in the Cloudflare caching stack
- `cache-stampede-prevention-workers-durable-objects.md` — preventing thundering herd on cache miss
- `kv-replication-lag-compensating-patterns.md` — compensating for KV eventual consistency in write-heavy flows
- `read-your-writes-consistency-workers-kv-d1.md` — ensuring a writer sees its own updates immediately

## Sources

- Amazon DynamoDB read repair documentation (pattern applies generically): https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html
- Cloudflare KV eventual consistency guarantees: https://developers.cloudflare.com/kv/reference/how-kv-works/
- "Designing Data-Intensive Applications" by Martin Kleppmann — Chapter 5 (Replication lag and read repair)
