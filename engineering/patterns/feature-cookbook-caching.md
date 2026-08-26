# feature-cookbook-caching

**Issue:** Caching recipes — HTTP, in-memory, multi-tier
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app is slow. The DB is overwhelmed. Every request
hits the DB. You add a cache. The cache is empty on the
first request. The first user has a slow experience. The
cache fills up. Subsequent users are fast. The cache
expires. The DB is hit again. You're stuck in a cycle.

## Root cause
**Caching is not a one-time fix.** It requires care.

**Source:** Various caching guides.

## The "cache key" pattern

A good cache key includes all relevant dimensions:
```ts
function getCacheKey(input: { tenantId: string; userId: string; resourceId: string }): string {
  return `${input.tenantId}:${input.userId}:${input.resourceId}`;
}
```

Missing a dimension is a data leak (e.g. two tenants see
each other's data).

## The "TTL" pattern

For a TTL, set the expiration:
```ts
await env.KV.put(key, value, {
  expirationTtl: 300,  // 5 minutes
});
```

A TTL prevents stale data from living forever.

## The "cache invalidation" pattern

For invalidation, delete on write:
```ts
async function updateUser(userId: string, data: UserUpdate, env: Env): Promise<User> {
  const user = await updateUserInDB(userId, data, env);

  // Invalidate the cache
  const keys = await env.KV.list({ prefix: `user:${userId}` });
  for (const key of keys.keys) {
    await env.KV.delete(key.name);
  }

  return user;
}
```

The cache is invalidated on every write.

## The "cache aside" pattern

For read-through, check the cache first:
```ts
async function getUser(userId: string, env: Env): Promise<User | null> {
  // 1. Check the cache
  const cached = await env.KV.get(`user:${userId}`);
  if (cached) return JSON.parse(cached);

  // 2. Read from DB
  const user = await env.DB!.prepare(
    `SELECT * FROM users WHERE id = ?`
  ).bind(userId).first<User>();

  // 3. Populate the cache
  if (user) {
    await env.KV.put(`user:${userId}`, JSON.stringify(user), {
      expirationTtl: 300,
    });
  }

  return user;
}
```

The first call hits the DB; subsequent calls hit the cache.

## The "write through" pattern

For write-through, update the cache on every write:
```ts
async function updateUser(userId: string, data: UserUpdate, env: Env): Promise<User> {
  const user = await updateUserInDB(userId, data, env);

  // Update the cache
  await env.KV.put(`user:${userId}`, JSON.stringify(user), {
    expirationTtl: 300,
  });

  return user;
}
```

The cache is always fresh after a write.

## The "cache stampede" prevention

For a popular key, prevent the stampede:
```ts
class CacheWithLock {
  private locks = new Map<string, Promise<any>>();

  async get<T>(key: string, fetcher: () => Promise<T>, env: Env): Promise<T> {
    // 1. Check the cache
    const cached = await env.KV.get(key);
    if (cached) return JSON.parse(cached);

    // 2. Check if a fetch is in progress
    if (this.locks.has(key)) {
      return this.locks.get(key);
    }

    // 3. Fetch and lock
    const promise = (async () => {
      const value = await fetcher();
      await env.KV.put(key, JSON.stringify(value), { expirationTtl: 300 });
      this.locks.delete(key);
      return value;
    })();

    this.locks.set(key, promise);
    return promise;
  }
}
```

The first request fetches; subsequent requests wait.

## The "negative cache" pattern

For "not found" results, cache them too:
```ts
async function getUser(userId: string, env: Env): Promise<User | null> {
  const cached = await env.KV.get(`user:${userId}`);
  if (cached === 'null') return null;  // Cached "not found"
  if (cached) return JSON.parse(cached);

  const user = await readUserFromDB(userId, env);

  // Cache the result (including "not found")
  await env.KV.put(`user:${userId}`, user ? JSON.stringify(user) : 'null', {
    expirationTtl: 60,  // Shorter TTL for negative
  });

  return user;
}
```

A flood of requests for non-existent users doesn't hit the
DB.

## The "stale-while-revalidate" pattern

For background refresh:
```ts
async function getDataWithSWR(key: string, env: Env): Promise<Data> {
  // 1. Check the cache
  const cached = await env.KV.get<Data>(key, 'json');

  if (cached) {
    // 2. If stale, refresh in background
    if (Date.now() - cached.fetchedAt > cached.ttl) {
      env.CTX.waitUntil(refreshCache(key, env));
    }
    return cached.data;
  }

  // 3. No cache; fetch
  return refreshCache(key, env);
}
```

The user always gets a fast response; the cache is kept
fresh.

## The "tiered cache" pattern

For high-traffic apps, multiple tiers:
```ts
async function getUser(userId: string, env: Env): Promise<User | null> {
  // 1. In-memory cache (per isolate)
  const memCached = memCache.get(`user:${userId}`);
  if (memCached) return memCached;

  // 2. KV cache
  const kvCached = await env.KV.get(`user:${userId}`);
  if (kvCached) {
    const user = JSON.parse(kvCached);
    memCache.set(`user:${userId}`, user, 30_000);
    return user;
  }

  // 3. DB
  const user = await readUserFromDB(userId, env);
  if (user) {
    await env.KV.put(`user:${userId}`, JSON.stringify(user), { expirationTtl: 300 });
    memCache.set(`user:${userId}`, user, 30_000);
  }
  return user;
}
```

The tiers are: in-memory (fastest), KV (fast), D1 (slow).

## The "cache warming" pattern

For popular data, pre-warm the cache:
```ts
// In a cron
export async function handleScheduled(event: ScheduledEvent, env: Env): Promise<void> {
  const popular = await env.DB!.prepare(`
    SELECT id FROM users WHERE login_count > 100 ORDER BY login_count DESC LIMIT 1000
  `).all<{ id: string }>();

  for (const user of popular.results) {
    const userData = await readUserFromDB(user.id, env);
    if (userData) {
      await env.KV.put(`user:${user.id}`, JSON.stringify(userData), { expirationTtl: 3600 });
    }
  }
}
```

The popular users are always in the cache.

## The "cache analytics" pattern

For monitoring:
```ts
let cacheHits = 0;
let cacheMisses = 0;

function recordCacheEvent(event: 'hit' | 'miss'): void {
  if (event === 'hit') cacheHits++;
  else cacheMisses++;
  metrics.increment('cache.events_total', { result: event });
}

async function getUser(userId: string, env: Env): Promise<User | null> {
  const cached = await env.KV.get(`user:${userId}`);
  if (cached) {
    recordCacheEvent('hit');
    return JSON.parse(cached);
  }
  recordCacheEvent('miss');
  // ... rest
}
```

The cache hit rate is tracked.

## Verification
- **Test:** Cache hit returns the cached value
- **Test:** Cache miss returns the fresh value
- **Live:** Cache hit rate is > 80%
- **Audit:** Quarterly review of cache TTLs

## Gotchas
- **The "no cache key for tenant" anti-pattern.** Two
  tenants see each other's data. Always include
  `tenant_id` in the key.
- **The "no invalidation on write" anti-pattern.** The
  cache is stale. Invalidate.
- **The "no TTL" anti-pattern.** A cache without TTL is a
  memory leak.
- **The "cache without error handling" anti-pattern.** A
  cache failure should not break the request. Try/except
  the cache.
- **The "cache high-cardinality data" anti-pattern.** A
  cache that holds millions of keys is expensive. Cache
  aggregates, not raw data.

## Related
- `cache-strategies.md`
- `cache-strategies-detail.md`
- `caching-strategies-detail.md`
- `cloudflare/kv-eventually-consistent.md`
- `cloudflare/workers-cache-api.md`
- `multi-tenant-data-isolation.md`
- `idempotency-keys.md`
