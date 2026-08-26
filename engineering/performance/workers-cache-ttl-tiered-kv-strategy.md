# Three-Tier Caching: Cache API → KV → D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker reads from D1 on every request, saturating the database with queries for data that rarely changes. Introducing a single cache layer helps, but cache stampedes at TTL expiry cause latency spikes. A three-tier strategy (Cache API → KV → D1) provides low-latency reads, durable intermediate caching, and orderly invalidation without thundering-herd effects.

## Context

- Runtime: Cloudflare Workers
- Storage: Cloudflare Cache API (L1, ~5 ms), Cloudflare KV (L2, ~15-30 ms), Cloudflare D1 (L3, ~10-50 ms read replica)
- Pattern: stale-while-revalidate (SWR) at every tier
- Binding names (wrangler.toml): `CACHE_KV` (KVNamespace), `DB` (D1Database)

---

## Section 1 — TTL Laddering and Stale-While-Revalidate

Each tier has a shorter TTL than the one below it, so stale reads are served fast while revalidation happens in the background.

| Tier | Store | Fresh TTL | SWR window |
|------|-------|-----------|------------|
| L1 | Cache API | 30 s | 120 s |
| L2 | KV | 5 min | 30 min |
| L3 | D1 | source of truth | — |

```typescript
export interface Env {
  CACHE_KV: KVNamespace;
  DB: D1Database;
}

const L1_TTL = 30;       // seconds — Cache API fresh window
const L1_SWR = 120;      // seconds — serve stale, revalidate in background
const L2_TTL = 300;      // seconds — KV fresh window (5 min)
const L2_SWR = 1800;     // seconds — KV stale window (30 min)

interface CachedValue<T> {
  data: T;
  cachedAt: number; // Unix ms
  ttl: number;      // ms
  swr: number;      // ms — extra window to serve stale
}

function isStale<T>(entry: CachedValue<T>): boolean {
  return Date.now() > entry.cachedAt + entry.ttl;
}

function isExpired<T>(entry: CachedValue<T>): boolean {
  return Date.now() > entry.cachedAt + entry.ttl + entry.swr;
}
```

---

## Section 2 — Full Three-Tier Read Path with SWR

```typescript
async function readL1(cacheKey: Request): Promise<CachedValue<unknown> | null> {
  const cache = caches.default;
  const hit = await cache.match(cacheKey);
  if (!hit) return null;
  try {
    return (await hit.json()) as CachedValue<unknown>;
  } catch {
    return null;
  }
}

async function writeL1(
  cacheKey: Request,
  value: CachedValue<unknown>,
): Promise<void> {
  const cache = caches.default;
  // Cache API requires Cache-Control to store the entry
  const headers = new Headers({
    'Content-Type': 'application/json',
    // max-age drives L1 TTL + SWR window
    'Cache-Control': `public, max-age=${L1_TTL}, stale-while-revalidate=${L1_SWR}`,
  });
  await cache.put(cacheKey, new Response(JSON.stringify(value), { headers }));
}

async function readL2(env: Env, key: string): Promise<CachedValue<unknown> | null> {
  const raw = await env.CACHE_KV.get(key, 'json');
  return raw as CachedValue<unknown> | null;
}

async function writeL2(
  env: Env,
  key: string,
  value: CachedValue<unknown>,
): Promise<void> {
  await env.CACHE_KV.put(key, JSON.stringify(value), {
    expirationTtl: Math.ceil((value.ttl + value.swr) / 1000),
  });
}

async function readL3(env: Env, id: string): Promise<unknown> {
  const { results } = await env.DB
    .prepare('SELECT * FROM items WHERE id = ?1 LIMIT 1')
    .bind(id)
    .all();
  return results[0] ?? null;
}

async function getItem(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  id: string,
): Promise<unknown> {
  const cacheKey = new Request(`https://cache.internal/items/${id}`);
  const kvKey = `items:${id}`;

  // --- L1: Cache API ---
  const l1 = await readL1(cacheKey);
  if (l1 && !isExpired(l1)) {
    if (isStale(l1)) {
      // Serve stale, revalidate in background
      ctx.waitUntil(revalidateFromL2OrL3(env, cacheKey, kvKey, id));
    }
    return l1.data;
  }

  // --- L2: KV ---
  const l2 = await readL2(env, kvKey);
  if (l2 && !isExpired(l2)) {
    // Populate L1 from L2
    const l1Entry: CachedValue<unknown> = {
      data: l2.data,
      cachedAt: Date.now(),
      ttl: L1_TTL * 1000,
      swr: L1_SWR * 1000,
    };
    ctx.waitUntil(writeL1(cacheKey, l1Entry));
    if (isStale(l2)) {
      ctx.waitUntil(revalidateFromL3(env, cacheKey, kvKey, id));
    }
    return l2.data;
  }

  // --- L3: D1 ---
  return revalidateFromL3(env, cacheKey, kvKey, id);
}

async function revalidateFromL3(
  env: Env,
  cacheKey: Request,
  kvKey: string,
  id: string,
): Promise<unknown> {
  const fresh = await readL3(env, id);
  const now = Date.now();

  const l2Entry: CachedValue<unknown> = {
    data: fresh,
    cachedAt: now,
    ttl: L2_TTL * 1000,
    swr: L2_SWR * 1000,
  };
  const l1Entry: CachedValue<unknown> = {
    data: fresh,
    cachedAt: now,
    ttl: L1_TTL * 1000,
    swr: L1_SWR * 1000,
  };

  await Promise.all([writeL2(env, kvKey, l2Entry), writeL1(cacheKey, l1Entry)]);
  return fresh;
}

async function revalidateFromL2OrL3(
  env: Env,
  cacheKey: Request,
  kvKey: string,
  id: string,
): Promise<void> {
  const l2 = await readL2(env, kvKey);
  if (l2 && !isStale(l2)) {
    await writeL1(cacheKey, { ...l2, cachedAt: Date.now(), ttl: L1_TTL * 1000, swr: L1_SWR * 1000 });
  } else {
    await revalidateFromL3(env, cacheKey, kvKey, id);
  }
}
```

---

## Section 3 — Invalidation Propagation and Cache Stampede Prevention

On a write (mutation), explicitly delete from KV and Cache API before or after the D1 write. Use a short random jitter on TTLs to spread expiry across time.

```typescript
async function invalidateItem(
  env: Env,
  id: string,
): Promise<void> {
  const cacheKey = new Request(`https://cache.internal/items/${id}`);
  const kvKey = `items:${id}`;

  // Delete from both upper tiers — next read falls through to D1
  await Promise.all([
    env.CACHE_KV.delete(kvKey),
    caches.default.delete(cacheKey),
  ]);
}

// Jitter helper: spreads TTL expiry to prevent stampedes
function jitterTtl(baseTtlMs: number, jitterFraction = 0.1): number {
  const jitter = baseTtlMs * jitterFraction * Math.random();
  return Math.round(baseTtlMs + jitter);
}

// Use jittered TTL when writing:
// l2Entry.ttl = jitterTtl(L2_TTL * 1000);

async function upsertItem(
  env: Env,
  id: string,
  data: Record<string, unknown>,
): Promise<void> {
  // 1. Write to D1
  await env.DB
    .prepare('INSERT OR REPLACE INTO items (id, payload, updated_at) VALUES (?1, ?2, ?3)')
    .bind(id, JSON.stringify(data), Date.now())
    .run();

  // 2. Invalidate upper tiers
  await invalidateItem(env, id);
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const id = url.searchParams.get('id');
    if (!id) return new Response('Missing id', { status: 400 });

    if (request.method === 'GET') {
      const item = await getItem(request, env, ctx, id);
      if (!item) return new Response('Not found', { status: 404 });
      return Response.json(item);
    }

    if (request.method === 'PUT') {
      const body = await request.json<Record<string, unknown>>();
      await upsertItem(env, id, body);
      return new Response('OK', { status: 200 });
    }

    return new Response('Method not allowed', { status: 405 });
  },
};
```

---

## Anti-patterns

- Using the same TTL for all tiers — defeats the purpose of tiering; L1 must expire before L2
- Not handling `isExpired` separately from `isStale` — expired entries must not be served, stale ones may be
- Invalidating only KV but not the Cache API on writes — stale Cache API entries serve outdated data for up to L1_SWR seconds
- Writing to D1 inside `waitUntil` revalidation without retry logic — a failed D1 write silently leaves caches in a stale state
- Using KV for sub-100ms latency requirements — Cache API is ~5 ms, KV is ~15-30 ms; use the right tier

## Gotchas

- `caches.default.delete()` only deletes the Cache API entry at the current PoP — other PoPs evict naturally at TTL
- KV consistency is eventual; a write is not visible to all Workers globally for up to 60 seconds
- D1 read replicas have up to 100 ms replication lag from the primary — factor this into your SWR windows
- `KVNamespace.get()` returns `null` for missing keys AND for keys with expired `expirationTtl` — distinguish with metadata if needed

## Verification

```bash
# Read-path latency across tiers
WORKER="https://your-worker.workers.dev"

# Cold read (L3 hit, populates L1+L2)
time curl -s "$WORKER/?id=test-1" > /dev/null

# Warm read (L1 hit)
time curl -s "$WORKER/?id=test-1" > /dev/null

# Invalidate via PUT, then measure cold again
curl -X PUT -H 'Content-Type: application/json' \
  -d '{"name":"updated"}' "$WORKER/?id=test-1"
time curl -s "$WORKER/?id=test-1" > /dev/null

# Wrangler tail to observe revalidation logs
wrangler tail --format pretty
```

## Related

- `documentation/categories/performance/workers-d1-index-covering-query-optimization.md`
- `documentation/categories/performance/workers-connection-keep-alive-upstream-fetch.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/kv/api/
- https://developers.cloudflare.com/d1/
- https://web.dev/articles/stale-while-revalidate
