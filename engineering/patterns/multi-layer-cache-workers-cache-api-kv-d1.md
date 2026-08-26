# Multi-Layer Tiered Cache: Cache API (L1) → KV (L2) → D1 (L3)

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Workers KV already provides sub-millisecond reads for hot keys, but `KVNamespace.get()`
still incurs a network hop to the KV edge data store even on cache hits. The
Cloudflare Cache API stores responses in the same PoP as the Worker, avoiding that
hop entirely. You have high-read-frequency data (exchange rates, feature-flag sets,
price lists) that should be served from the fastest possible tier while remaining
consistent with D1 as the source of truth.

This pattern layers three caches: Cache API as L1 (in-PoP, fastest), KV as L2
(global edge, ~1 ms), and D1 as L3 (source of truth, 1–15 ms). Reads fall through
tiers on miss; writes invalidate all tiers above D1.

---

## Context

```
                      ┌──────────────┐
                      │ Cache API    │  L1 — PoP-local, ~0 ms
                      │ (caches.open)│       TTL: 10–60 s
                      └──────┬───────┘
                             │ MISS
                      ┌──────▼───────┐
                      │ Workers KV   │  L2 — global edge, ~1 ms
                      │              │       TTL: 60–600 s
                      └──────┬───────┘
                             │ MISS
                      ┌──────▼───────┐
                      │ D1 Database  │  L3 — authoritative source
                      └─────────────-┘
```

Because Cache API entries are scoped to a synthetic `Request` URL, the pattern uses
a stable internal URL scheme (`https://cache.internal/<namespace>/<key>`) as the
cache key — the URL never leaves the Worker runtime.

---

## Section 1 — TieredCache Implementation

```typescript
// lib/tiered-cache.ts

export interface TieredCacheOptions {
  namespace:      string;
  l1TtlSeconds:   number;   // Cache API TTL (PoP-local)
  l2TtlSeconds:   number;   // KV TTL (global edge)
}

export class TieredCache<T> {
  private readonly cacheBase = 'https://cache.internal';

  constructor(
    private readonly kv:      KVNamespace,
    private readonly loader:  (key: string) => Promise<T | null>,
    private readonly options: TieredCacheOptions,
  ) {}

  async get(key: string): Promise<T | null> {
    const url    = this.cacheUrl(key);
    const kvKey  = this.kvKey(key);
    const cache  = await caches.open(`tiered:${this.options.namespace}`);

    // L1: Cache API (PoP-local)
    const l1 = await cache.match(url);
    if (l1) {
      return l1.json() as Promise<T>;
    }

    // L2: Workers KV (global edge)
    const l2 = await this.kv.get<T>(kvKey, 'json');
    if (l2 !== null) {
      // Back-fill L1 from L2 so next request in this PoP is instant
      await this.putL1(cache, url, l2);
      return l2;
    }

    // L3: D1 (source of truth)
    const value = await this.loader(key);
    if (value !== null) {
      await Promise.all([
        this.putL1(cache, url, value),
        this.putL2(kvKey, value),
      ]);
    }

    return value;
  }

  /** Invalidate all cache tiers for a key. Call after every D1 write. */
  async invalidate(key: string): Promise<void> {
    const url   = this.cacheUrl(key);
    const cache = await caches.open(`tiered:${this.options.namespace}`);

    await Promise.allSettled([
      cache.delete(url),
      this.kv.delete(this.kvKey(key)),
    ]);
  }

  private async putL1(cache: Cache, url: string, value: T): Promise<void> {
    const response = new Response(JSON.stringify(value), {
      headers: {
        'Content-Type':  'application/json',
        'Cache-Control': `public, max-age=${this.options.l1TtlSeconds}`,
      },
    });
    await cache.put(url, response);
  }

  private async putL2(kvKey: string, value: T): Promise<void> {
    await this.kv.put(kvKey, JSON.stringify(value), {
      expirationTtl: this.options.l2TtlSeconds,
    });
  }

  private cacheUrl(key: string): string {
    return `${this.cacheBase}/${this.options.namespace}/${encodeURIComponent(key)}`;
  }

  private kvKey(key: string): string {
    return `${this.options.namespace}:${key}`;
  }
}
```

---

## Section 2 — Domain Example: Exchange Rate Cache

```typescript
// repos/fx-rates.ts
import { TieredCache } from '../lib/tiered-cache';

export interface FxRate {
  base:      string;
  quote:     string;
  rate:      number;
  updatedAt: string;
}

export interface Env {
  KV_CACHE: KVNamespace;
  DB:       D1Database;
}

function makeFxCache(env: Env): TieredCache<FxRate> {
  return new TieredCache<FxRate>(
    env.KV_CACHE,
    async (pair) => {
      const [base, quote] = pair.split('-');
      const row = await env.DB
        .prepare('SELECT base, quote, rate, updated_at FROM fx_rates WHERE base = ? AND quote = ?')
        .bind(base, quote)
        .first<{ base: string; quote: string; rate: number; updated_at: string }>();

      if (!row) return null;

      return { base: row.base, quote: row.quote, rate: row.rate, updatedAt: row.updated_at };
    },
    {
      namespace:    'fx',
      l1TtlSeconds: 15,    // L1 PoP cache for 15 s
      l2TtlSeconds: 120,   // L2 KV for 2 min
    },
  );
}

export async function getRate(pair: string, env: Env): Promise<FxRate | null> {
  return makeFxCache(env).get(pair);
}

export async function updateRate(pair: string, rate: number, env: Env): Promise<void> {
  const [base, quote] = pair.split('-');
  await env.DB
    .prepare('UPDATE fx_rates SET rate = ?, updated_at = ? WHERE base = ? AND quote = ?')
    .bind(rate, new Date().toISOString(), base, quote)
    .run();

  // Invalidate both L1 and L2 so next read fetches fresh from D1
  await makeFxCache(env).invalidate(pair);
}
```

---

## Section 3 — Worker Handler and wrangler.toml

```typescript
// worker.ts
import { getRate, updateRate } from './repos/fx-rates';

export interface Env {
  KV_CACHE: KVNamespace;
  DB:       D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url  = new URL(request.url);
    const pair = url.searchParams.get('pair');   // e.g. "USD-EUR"
    if (!pair) return Response.json({ error: 'pair required' }, { status: 400 });

    if (request.method === 'GET') {
      const rate = await getRate(pair, env);
      if (!rate) return Response.json({ error: 'Not found' }, { status: 404 });
      return Response.json(rate);
    }

    if (request.method === 'PUT') {
      const { rate } = await request.json<{ rate: number }>();
      await updateRate(pair, rate, env);
      return Response.json({ ok: true });
    }

    return new Response('Method Not Allowed', { status: 405 });
  },
};
```

```toml
# wrangler.toml
name = "fx-rate-worker"

[[kv_namespaces]]
binding = "KV_CACHE"
id      = "<your-kv-namespace-id>"

[[d1_databases]]
binding  = "DB"
database_name = "fx-db"
database_id   = "<your-d1-db-id>"
```

---

## Section 4 — TTL Layering Strategy

L1 TTL must be shorter than L2 TTL, and both must be shorter than D1 write
frequency. This ensures the upper tiers do not serve data that is more stale
than your consistency budget allows.

| Layer | Store       | Typical TTL | Staleness budget | Notes                                      |
|-------|-------------|-------------|------------------|--------------------------------------------|
| L1    | Cache API   | 10–30 s     | Smallest         | Resets per PoP on each L2 back-fill        |
| L2    | Workers KV  | 60–600 s    | Medium           | Global; eventual consistency up to 60 s   |
| L3    | D1          | Authoritative | Zero           | Source of truth; invalidation triggers here |

On invalidation, both L1 and L2 are evicted. The next read in any PoP falls
through to D1, populates L2, then back-fills L1 for that PoP.

---

## Anti-patterns

**Using Cache API as the only tier** — Cache API entries are PoP-local. A new PoP
or a cold PoP after a deploy sees no L1 entries and hammers D1 until L1 warms up.
KV as L2 provides the warm baseline globally.

**Invalidating only L1 on write** — L2 KV will still serve stale data to all PoPs
until its TTL expires. Always invalidate both tiers in `Promise.allSettled()`.

**Using the same Cache API cache name for different entity types** — Cache API caches
are keyed by URL only. A namespace in the URL (`fx/USD-EUR`) prevents collisions;
a single shared cache without namespacing creates subtle bugs.

**Setting L1 TTL longer than L2 TTL** — a request that back-fills L1 from L2 with
an L1 TTL of 600 s while L2 TTL is 60 s will serve stale L1 data for 540 s after
L2 has expired and been refreshed. Always `L1 TTL ≤ L2 TTL`.

---

## Gotchas

- **`caches.open()` is not available in Miniflare v2** — local dev with older tooling
  sees no-op or error. Use Wrangler's `--remote` flag or mock the Cache API in tests.
- **Cache API `cache.delete()` only evicts entries in the current PoP.** Cross-PoP
  L1 eviction is not available. Other PoPs will continue to serve L1 until their
  own TTL expires. L1 TTL should be short enough to accept this.
- **KV `expirationTtl` minimum is 60 s.** Set `l2TtlSeconds ≥ 60`.
- **Cache API responses must be cacheable.** The `Cache-Control: public, max-age=N`
  header is required. A response without `Cache-Control` or with `no-store` will not
  be stored by `cache.put()`.

---

## Verification

```bash
# 1. Cold read — falls through all tiers to D1
curl "https://fx.example.com/?pair=USD-EUR" | jq .rate

# 2. Repeat immediately — L1 Cache API hit (check wrangler tail for 'l1_hit' log)
curl "https://fx.example.com/?pair=USD-EUR" | jq .rate

# 3. Update rate — invalidates L1 and L2
curl -X PUT "https://fx.example.com/?pair=USD-EUR" \
  -H "Content-Type: application/json" \
  -d '{"rate": 0.9201}'

# 4. Read again — should fall through to D1 and return new rate
curl "https://fx.example.com/?pair=USD-EUR" | jq .rate
```

---

## Related

- `read-through-cache-workers-kv-d1.md` — two-tier read-through (KV → D1 only)
- `stale-while-revalidate-workers-kv.md` — SWR pattern for background refresh
- `cache-aside-kv-d1-fallback.md` — caller-driven cache-aside with KV
- `request-coalescing-cache-stampede.md` — deduplicate concurrent D1 misses
- `caching-strategies-detail.md` — comparison of all caching strategy types

---

## Sources

- Cloudflare Cache API — developers.cloudflare.com/workers/runtime-apis/cache/
- Cloudflare Workers KV — developers.cloudflare.com/kv/
- Cloudflare D1 — developers.cloudflare.com/d1/
- "Caching best practices and max-age gotchas", web.dev — web.dev/http-cache/
