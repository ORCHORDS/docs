# D1 Cache-Aside with Workers KV

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
A read-heavy endpoint repeatedly queries the same D1 rows (product catalogue, user profile,
feature flags), driving unnecessary D1 read-unit billing and adding 10–50 ms of SQLite
round-trip latency on every request.

## Context
Workers KV is a globally distributed key-value store with sub-millisecond read latency from
Cloudflare's edge PoPs. Used as a cache-aside layer in front of D1, KV absorbs the majority
of read traffic for slowly-changing data. The pattern is: check KV first; on a miss, read
from D1, write the result to KV with a TTL, and return it. Writes always go to D1 first and
then invalidate (or update) the KV entry. This keeps D1 as the authoritative source of truth
while KV serves as a read accelerator. The TTL strategy determines the staleness window and
must be chosen deliberately per data type.

## KV Namespace and D1 Binding

```toml
# wrangler.toml
name = "cache-aside-demo"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding       = "DB"
database_name = "prod-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "CACHE"
id      = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
```

## Cache Key Convention

```typescript
// src/cache-keys.ts
export const CacheKey = {
  product:  (id: string)  => `product:v1:${id}`,
  userProfile: (id: string) => `user:profile:v1:${id}`,
  featureFlags: (tenantId: string) => `ff:v1:${tenantId}`,
} as const;

// TTLs in seconds
export const TTL = {
  product:      300,   // 5 min — changes infrequently
  userProfile:  60,    // 1 min — changes on profile edits
  featureFlags: 30,    // 30 s  — near real-time flag rollout
} as const;
```

## Generic Cache-Aside Helper

```typescript
// src/cache.ts
export interface CacheOptions {
  kv:  KVNamespace;
  db:  D1Database;
  ttl: number;
}

export async function cacheAside<T>(
  key: string,
  options: CacheOptions,
  fetchFromDb: () => Promise<T | null>
): Promise<T | null> {
  // 1. Check KV cache
  const cached = await options.kv.get<T>(key, 'json');
  if (cached !== null) return cached;

  // 2. Miss — query D1
  const fresh = await fetchFromDb();
  if (fresh === null) return null;

  // 3. Populate cache (fire-and-forget via waitUntil is not available here;
  //    use ctx.waitUntil in the Worker entrypoint for non-blocking writes)
  await options.kv.put(key, JSON.stringify(fresh), { expirationTtl: options.ttl });

  return fresh;
}
```

## Worker Entrypoint with waitUntil

```typescript
// src/index.ts
import { CacheKey, TTL } from './cache-keys';

export interface Env {
  DB:    D1Database;
  CACHE: KVNamespace;
}

interface Product {
  id: string; name: string; price: number; updated_at: number;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // ── GET /products/:id ─────────────────────────────────────────────────
    const getMatch = url.pathname.match(/^\/products\/([^/]+)$/);
    if (getMatch && request.method === 'GET') {
      const id = getMatch[1];
      const cacheKey = CacheKey.product(id);

      const cached = await env.CACHE.get<Product>(cacheKey, 'json');
      if (cached) {
        return Response.json(cached, {
          headers: { 'X-Cache': 'HIT' },
        });
      }

      const row = await env.DB.prepare(
        'SELECT id, name, price, updated_at FROM products WHERE id = ?1'
      ).bind(id).first<Product>();

      if (!row) return new Response('Not found', { status: 404 });

      // Write to KV without blocking the response
      ctx.waitUntil(
        env.CACHE.put(cacheKey, JSON.stringify(row), { expirationTtl: TTL.product })
      );

      return Response.json(row, { headers: { 'X-Cache': 'MISS' } });
    }

    // ── PUT /products/:id ─────────────────────────────────────────────────
    const putMatch = url.pathname.match(/^\/products\/([^/]+)$/);
    if (putMatch && request.method === 'PUT') {
      const id = putMatch[1];
      const body = await request.json<Partial<Product>>();

      const result = await env.DB.prepare(`
        UPDATE products
           SET name       = COALESCE(?2, name),
               price      = COALESCE(?3, price),
               updated_at = unixepoch()
         WHERE id = ?1
        RETURNING id, name, price, updated_at
      `).bind(id, body.name ?? null, body.price ?? null).first<Product>();

      if (!result) return new Response('Not found', { status: 404 });

      // Invalidate cache synchronously — callers must see fresh data immediately.
      await env.CACHE.delete(CacheKey.product(id));

      return Response.json(result);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Bulk Warm-Up on Deploy

```typescript
// scripts/warm-cache.ts  (run with: npx tsx scripts/warm-cache.ts)
// Pre-populate KV for the top-N most-read products to avoid cold-start misses.
import { execSync } from 'node:child_process';

const TOP_N = 200;

const rows: Array<{ id: string; name: string; price: number; updated_at: number }> =
  JSON.parse(
    execSync(
      `npx wrangler d1 execute prod-db --json ` +
      `--command "SELECT id, name, price, updated_at FROM products ` +
      `ORDER BY view_count DESC LIMIT ${TOP_N};"`
    ).toString()
  )[0].results;

for (const row of rows) {
  execSync(
    `npx wrangler kv key put --namespace-id=<id> "product:v1:${row.id}" ` +
    `'${JSON.stringify(row)}' --expiration-ttl=300`
  );
  process.stdout.write('.');
}
console.log(`\nWarmed ${rows.length} keys`);
```

## Anti-patterns
- Caching mutable user-specific data (e.g. shopping cart) — a shared KV key for per-user state leads to data leaks.
- Forgetting to delete or update the KV key on every write path — stale reads persist until the TTL expires.
- Using KV TTL as the primary consistency mechanism without explicit invalidation — tolerable only for immutable/append-only data.
- Caching `null` (not-found) results without a sentinel value — every 404 triggers a D1 read on each request until a real row exists.
- Setting TTL to 0 (no expiry) on frequently updated data — the cache grows unbounded and serves permanently stale values.
- Using KV for data that must be consistent across viewers in the same second — KV eventual consistency can lag up to 60 s globally.

## Gotchas
- KV `get()` returns `null` for both a missing key and a key whose value is the JSON string `null` — store a sentinel object `{ exists: false }` for negative caching.
- `ctx.waitUntil()` keeps the Worker alive after the response is sent, but if the runtime is terminated early the KV write may not complete.
- KV namespace IDs differ between `preview` and `production` environments — bind separate namespaces in `[env.staging]` blocks.
- KV has a 25 MiB per-key value limit; large JSON blobs (e.g. full product catalogues) should be stored in R2 and the KV value used only for the URL.
- Cache key versioning (`v1`, `v2`) in the key string is required when the serialisation schema changes — stale keys under the old schema silently parse into broken objects otherwise.

## Verification

```bash
# First request — expect MISS
curl -v https://<worker>.workers.dev/products/abc123 2>&1 | grep X-Cache
# < X-Cache: MISS

# Second request — expect HIT
curl -v https://<worker>.workers.dev/products/abc123 2>&1 | grep X-Cache
# < X-Cache: HIT

# Update product and verify cache invalidation
curl -X PUT https://<worker>.workers.dev/products/abc123 \
     -H 'Content-Type: application/json' \
     -d '{"price": 9.99}'

# Next GET must be a MISS (cache invalidated)
curl -v https://<worker>.workers.dev/products/abc123 2>&1 | grep X-Cache
# < X-Cache: MISS

# Inspect KV key directly
npx wrangler kv key get --namespace-id=<id> "product:v1:abc123"
```

## Related
- [d1-sessions-api-read-your-writes-workers.md](d1-sessions-api-read-your-writes-workers.md)
- [d1-read-replicas-mobile-latency.md](d1-read-replicas-mobile-latency.md)
- [query-caching-patterns.md](query-caching-patterns.md)
- [redis-caching-patterns.md](redis-caching-patterns.md)

## Sources
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- https://developers.cloudflare.com/d1/
