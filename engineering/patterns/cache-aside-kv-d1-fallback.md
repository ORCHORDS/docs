# Cache-Aside Pattern: Workers KV with TTL Fallback to D1

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A Cloudflare Worker reads the same D1 rows on every request — product catalogue, configuration records, user plan data. D1 round-trip latency is 1–15 ms per query; under load, repeated reads add up. Workers KV has ~1 ms read latency from cache after the first read in a region. You want reads to be served from KV when the data is fresh, fall back to D1 when the KV entry is absent or expired, and write through to KV after every D1 fetch — without coupling the Worker's business logic to caching concerns.

## Context

**Cache-aside** (also called lazy loading) places the caller — not the cache — in charge of population. The algorithm is:

```
  Read(key):
    1. Check KV cache
    2a. HIT  → return cached value
    2b. MISS → read from D1
              → write result to KV with TTL
              → return result

  Write(key, value):
    1. Write to D1 (source of truth)
    2. Delete (or update) KV entry          ← invalidate, do not write-through
```

On Cloudflare, Workers KV is globally distributed with eventual consistency. D1 is the authoritative source. KV stores the serialised row JSON with a TTL that determines maximum staleness.

```
  Worker
    │
    ├─── KV.get(key) ─────► KV Cache
    │         │ HIT                  └── return cached JSON
    │         │ MISS
    │         ▼
    │    D1.prepare(...)
    │         │
    │         ▼
    │    KV.put(key, json, TTL)      (populate cache)
    │         │
    └── return row to caller
```

## Section 1 — Generic CacheAsideStore

```typescript
// cache-aside.ts

export interface CacheAsideOptions {
  ttlSeconds:        number;     // KV entry lifetime
  staleOnDbError:    boolean;    // return stale KV value if D1 throws
  namespace:         string;     // prefix for KV keys to avoid collisions
}

export class CacheAsideStore<T> {
  private kv:      KVNamespace;
  private options: CacheAsideOptions;

  constructor(kv: KVNamespace, options: CacheAsideOptions) {
    this.kv      = kv;
    this.options = options;
  }

  /** Read from KV; on miss, call loader() and populate KV. */
  async get(key: string, loader: () => Promise<T | null>): Promise<T | null> {
    const kvKey = this.makeKey(key);

    // 1. Try KV cache
    const cached = await this.kv.get<T>(kvKey, 'json');
    if (cached !== null) {
      return cached;
    }

    // 2. KV miss — load from source of truth
    let value: T | null;
    try {
      value = await loader();
    } catch (err) {
      // If staleOnDbError, serve a stale KV value (even expired if platform kept it)
      if (this.options.staleOnDbError) {
        const stale = await this.kv.get<T>(kvKey, 'json'); // expired entries may still be readable
        if (stale !== null) {
          console.warn(JSON.stringify({ event: 'cache_stale_fallback', key, error: String(err) }));
          return stale;
        }
      }
      throw err;
    }

    // 3. Populate KV (skip for null — don't cache misses unless you want to)
    if (value !== null) {
      await this.kv.put(kvKey, JSON.stringify(value), {
        expirationTtl: this.options.ttlSeconds,
      });
    }

    return value;
  }

  /** Invalidate the KV entry after a write to D1. */
  async invalidate(key: string): Promise<void> {
    await this.kv.delete(this.makeKey(key));
  }

  /** Write through: update D1 via writer(), then invalidate KV. */
  async update(
    key:    string,
    writer: () => Promise<T>,
  ): Promise<T> {
    const result = await writer();
    await this.invalidate(key);
    return result;
  }

  private makeKey(key: string): string {
    return `${this.options.namespace}:${key}`;
  }
}
```

## Section 2 — Domain Usage: Product Catalogue

```typescript
// products.ts
import { CacheAsideStore } from './cache-aside';

export interface Product {
  id:          string;
  slug:        string;
  name:        string;
  priceCents:  number;
  currency:    string;
  updatedAt:   string;
}

export interface Env {
  CACHE: KVNamespace;
  DB:    D1Database;
}

function makeProductCache(env: Env): CacheAsideStore<Product> {
  return new CacheAsideStore<Product>(env.CACHE, {
    ttlSeconds:     300,   // 5-minute TTL — tolerate 5-minute staleness
    staleOnDbError: true,  // serve stale on D1 outage
    namespace:      'product',
  });
}

export async function getProduct(slug: string, env: Env): Promise<Product | null> {
  const cache = makeProductCache(env);

  return cache.get(slug, async () => {
    const row = await env.DB
      .prepare('SELECT id, slug, name, price_cents, currency, updated_at FROM products WHERE slug = ? LIMIT 1')
      .bind(slug)
      .first<{ id: string; slug: string; name: string; price_cents: number; currency: string; updated_at: string }>();

    if (!row) return null;

    return {
      id:         row.id,
      slug:       row.slug,
      name:       row.name,
      priceCents: row.price_cents,
      currency:   row.currency,
      updatedAt:  row.updated_at,
    };
  });
}

export async function updateProduct(
  slug:    string,
  patch:   Partial<Pick<Product, 'name' | 'priceCents'>>,
  env:     Env,
): Promise<Product> {
  const cache = makeProductCache(env);

  return cache.update(slug, async () => {
    await env.DB
      .prepare('UPDATE products SET name = COALESCE(?, name), price_cents = COALESCE(?, price_cents), updated_at = ? WHERE slug = ?')
      .bind(patch.name ?? null, patch.priceCents ?? null, new Date().toISOString(), slug)
      .run();

    const updated = await getProduct(slug, env); // fresh read after write
    if (!updated) throw new Error(`Product ${slug} not found after update`);
    return updated;
  });
}
```

## Section 3 — Worker Handler

```typescript
// worker.ts
import { getProduct, updateProduct } from './products';

export interface Env {
  CACHE: KVNamespace;
  DB:    D1Database;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url  = new URL(request.url);
    const slug = url.pathname.split('/').pop();

    if (!slug) return Response.json({ error: 'Missing slug' }, { status: 400 });

    if (request.method === 'GET') {
      const product = await getProduct(slug, env);
      if (!product) return Response.json({ error: 'Not found' }, { status: 404 });

      return Response.json(product, {
        headers: {
          'Cache-Control': 'public, max-age=60', // edge CDN cache on top
        },
      });
    }

    if (request.method === 'PATCH') {
      const patch = await request.json<{ name?: string; priceCents?: number }>();
      const updated = await updateProduct(slug, patch, env);
      return Response.json(updated);
    }

    return new Response('Method Not Allowed', { status: 405 });
  },
};
```

## Section 4 — TTL Strategy and Cache Warming

**Choosing TTL:**

| Data type                     | Recommended TTL | Rationale                                   |
|-------------------------------|-----------------|---------------------------------------------|
| Product catalogue             | 300 s (5 min)   | Price changes tolerate minutes of staleness |
| User plan / subscription      | 60 s            | Plan downgrades should reflect quickly      |
| Feature flags                 | 30 s            | Near-real-time flag changes required        |
| Geolocation / currency config | 3600 s (1 hr)   | Changes infrequently                        |
| Auth token validation result  | 0 (no cache)    | Security-critical — never cache             |

**Cache warming** on deploy using a Cron Trigger:

```typescript
// warmer.ts
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    // Pre-populate KV with top-N most-read products
    const rows = await env.DB
      .prepare('SELECT slug FROM products ORDER BY view_count DESC LIMIT 200')
      .all<{ slug: string }>();

    await Promise.allSettled(
      rows.results.map(r => getProduct(r.slug, env)) // populates KV as a side effect
    );

    console.log(JSON.stringify({ event: 'cache_warmed', count: rows.results.length }));
  },
};
```

```toml
# wrangler.toml
[[triggers.crons]]
cron = "*/5 * * * *"   # Warm every 5 minutes
```

## Anti-patterns

**Caching mutable write results directly.** Writing the new value to KV in the `update()` path (write-through) introduces a race: a concurrent read between the D1 write and the KV write returns the old value. Invalidate instead; let the next read repopulate.

**Using KV `metadata` for cache headers.** KV metadata is limited to 1024 bytes and is read separately. Store all required fields inside the JSON value; reserve metadata for operational bookkeeping only.

**Caching null / not-found results without care.** Caching a KV miss means a subsequent `INSERT` in D1 is shadowed by the cached null until TTL expires. Either do not cache null, or invalidate the key on insert.

**Not handling KV eventual consistency on writes.** After `kv.put()`, Workers in other regions may still see the old value for up to 60 seconds (KV's global propagation delay). Design consumers to tolerate this staleness window.

**Sharing one KV namespace across all entity types without a prefix.** Key collisions corrupt unrelated records. Always namespace: `product:my-slug`, `user:u_123`, `config:feature-flags`.

## Gotchas

- **`kv.get()` with `'json'` returns `null` if the key does not exist** and also if the stored string is the literal `"null"`. Use a sentinel wrapper `{ v: <value> }` if you need to cache explicit nulls.
- **KV TTL minimum is 60 seconds.** Values put with `expirationTtl < 60` are rejected with an error. For sub-minute freshness requirements, use a Durable Object instead of KV.
- **KV read-after-write consistency is not guaranteed** within the same Worker request across different datacenter edges. Do not read from KV immediately after `kv.put()` expecting to see the new value everywhere.
- **D1 has a 10-second query timeout.** If a complex query regularly takes > 5 s, the KV cache Miss path degrades the user experience. Optimise the D1 query and add an index before relying on caching to mask it.
- **`staleOnDbError` safety net.** KV retains expired entries for an implementation-defined grace period, but this is not guaranteed. The stale fallback is best-effort, not a strong availability guarantee.

## Verification

```bash
# 1. Cold read — should hit D1 and populate KV
curl https://api.example.com/products/my-widget | jq .

# 2. Warm read — should be served from KV (observe latency drop in CF logs)
curl https://api.example.com/products/my-widget | jq .

# 3. Inspect KV entry
wrangler kv:key get --namespace-id=<CACHE_NS_ID> "product:my-widget"

# 4. Update product (invalidates KV)
curl -X PATCH https://api.example.com/products/my-widget \
  -H "Content-Type: application/json" \
  -d '{"name":"My Updated Widget"}'

# 5. Next read repopulates from D1
curl https://api.example.com/products/my-widget | jq .name
```

Integration test:

```typescript
// test/cache-aside.test.ts
import { describe, it, expect, vi } from 'vitest';
import { CacheAsideStore } from '../src/cache-aside';

describe('CacheAsideStore', () => {
  it('calls loader only on KV miss', async () => {
    const mockKv   = createMockKv();
    const store    = new CacheAsideStore<string>(mockKv, { ttlSeconds: 60, staleOnDbError: false, namespace: 'test' });
    const loader   = vi.fn(async () => 'value-from-db');

    const first  = await store.get('key', loader);
    const second = await store.get('key', loader);

    expect(first).toBe('value-from-db');
    expect(second).toBe('value-from-db');
    expect(loader).toHaveBeenCalledTimes(1); // second call served from KV
  });

  it('serves stale value on D1 error when staleOnDbError=true', async () => {
    const mockKv = createMockKvWithStale('stale-value');
    const store  = new CacheAsideStore<string>(mockKv, { ttlSeconds: 60, staleOnDbError: true, namespace: 'test' });
    const loader = vi.fn(async () => { throw new Error('D1 timeout'); });

    const val = await store.get('key', loader);
    expect(val).toBe('stale-value');
  });
});
```

## Related

- `caching-strategies-detail.md` — write-through, write-behind, read-through comparison
- `graceful-degradation.md` — serving stale content during outages
- `circuit-breaker-workers-d1-fetch.md` — open circuit when D1 is down, use KV stale
- `kv-rate-limiting.md` — other KV usage patterns
- `feature-cookbook-caching.md` — caching cookbook entries

## Sources

- Cloudflare Workers KV documentation — developers.cloudflare.com/kv/
- Cloudflare D1 documentation — developers.cloudflare.com/d1/
- "Cache-Aside Pattern", Microsoft Azure Architecture Center — learn.microsoft.com/azure/architecture/patterns/cache-aside
- Redis documentation, "Cache-Aside" — redis.io/learn/howtos/patterns/cache-aside
