# feature-cookbook-caching-strategies

**Issue:** Caching — layers, invalidation, patterns
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your DB has 1M rows. Every request is 200ms. The
team complains. You wish you'd cached.

## Root cause
**A DB hit on every request is slow.** Use a cache.

**Source:** Various caching guides.

## The "cache layer" pattern

For a multi-layer cache:
```
Client (browser) → CDN (CF) → Worker (KV) → D1
```

Each layer catches the missed data.

## The "CDN cache" pattern

For CDN caching:
```ts
async function handleRequest(request: Request, env: Env): Promise<Response> {
  // 1. Check the cache
  const cache = caches.default;
  const cached = await cache.match(request);
  if (cached) return cached;

  // 2. Fetch from origin
  const response = await fetchFromOrigin(request, env);

  // 3. Cache the response
  const cacheable = new Response(response.body, {
    status: response.status,
    headers: { 'cache-control': 'public, max-age=300' },
  });
  await cache.put(request, cacheable.clone());

  return response;
}
```

The CDN caches the response.

## The "KV cache" pattern

For a KV cache:
```ts
async function getCachedOrFetch<T>(key: string, ttl: number, fetcher: () => Promise<T>): Promise<T> {
  const cached = await env.KV!.get<T>(key, 'json');
  if (cached) return cached;

  const fresh = await fetcher();
  await env.KV!.put(key, JSON.stringify(fresh), { expirationTtl: ttl });
  return fresh;
}
```

The KV caches the data.

## The "in-memory cache" pattern

For an in-memory cache (within a Worker):
```ts
const cache = new Map<string, { value: any; expiresAt: number }>();

async function getCached<T>(key: string, ttl: number, fetcher: () => Promise<T>): Promise<T> {
  const entry = cache.get(key);
  if (entry && entry.expiresAt > Date.now()) return entry.value;

  const fresh = await fetcher();
  cache.set(key, { value: fresh, expiresAt: Date.now() + ttl });
  return fresh;
}
```

The in-memory cache is fast.

## The "cache invalidation" pattern

For cache invalidation, the hard part:
```ts
// On update, invalidate the cache
async function updateUser(id: string, updates: Partial<User>, env: Env): Promise<void> {
  await env.DB!.prepare(`UPDATE users SET ... WHERE id = ?`).bind(...).run();
  await env.KV!.delete(`user:${id}`);
}

// On delete, invalidate the cache
async function deleteUser(id: string, env: Env): Promise<void> {
  await env.DB!.prepare(`DELETE FROM users WHERE id = ?`).bind(id).run();
  await env.KV!.delete(`user:${id}`);
}
```

The cache is invalidated on write.

## The "cache-aside" pattern

For cache-aside:
```ts
async function getUser(id: string, env: Env): Promise<User | null> {
  // 1. Check the cache
  const cached = await env.KV!.get<User>(`user:${id}`, 'json');
  if (cached) return cached;

  // 2. Fetch from DB
  const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first<User>();
  if (!user) return null;

  // 3. Cache the result
  await env.KV!.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 300 });
  return user;
}
```

The cache is checked first, then filled.

## The "read-through" pattern

For read-through, the cache is the source:
```ts
class CachedUserRepository {
  async getUser(id: string): Promise<User | null> {
    return getCached(`user:${id}`, 300, async () => {
      return this.db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first<User>();
    });
  }
}
```

The cache layer is transparent.

## The "write-through" pattern

For write-through, writes go through the cache:
```ts
async function updateUser(id: string, updates: Partial<User>): Promise<void> {
  // 1. Update the DB
  await this.db.prepare(`UPDATE users SET ... WHERE id = ?`).bind(...).run();

  // 2. Update the cache
  const user = await this.db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first<User>();
  await env.KV!.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 300 });
}
```

The cache is always fresh.

## The "write-behind" pattern

For write-behind, writes are async:
```ts
async function updateUser(id: string, updates: Partial<User>, env: Env): Promise<void> {
  // 1. Update the cache
  const user = await getCached(`user:${id}`, 300, ...);
  Object.assign(user, updates);
  await env.KV!.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 300 });

  // 2. Queue the DB write
  await env.QUEUE.send({ type: 'update_user', id, updates });
}
```

The cache is updated immediately; the DB is async.

## The "TTL" pattern

For TTL (time to live):
- **Short TTL (1-60s):** Hot data, frequent changes
- **Long TTL (1-24h):** Cold data, rare changes
- **No TTL:** Static data (e.g. config)

```ts
await env.KV!.put('config', JSON.stringify(config), { expirationTtl: 86400 });
```

The TTL is appropriate.

## The "stale-while-revalidate" pattern

For SWR (stale-while-revalidate):
```ts
async function getCachedSWR<T>(key: string, staleTtl: number, fetcher: () => Promise<T>): Promise<T> {
  const entry = await env.KV!.get<{ value: T; expiresAt: number }>(key, 'json');

  if (entry && entry.expiresAt > Date.now()) {
    return entry.value;  // Fresh
  }

  if (entry) {
    // Stale: revalidate in the background
    env.waitUntil(fetcher().then(fresh => env.KV!.put(key, JSON.stringify({ value: fresh, expiresAt: Date.now() + staleTtl }))));
    return entry.value;  // Return stale
  }

  // Miss: fetch
  const fresh = await fetcher();
  await env.KV!.put(key, JSON.stringify({ value: fresh, expiresAt: Date.now() + staleTtl }));
  return fresh;
}
```

The user gets stale data; the cache is refreshed.

## The "cache stampede" pattern

For cache stampede (multiple workers miss the cache
simultaneously):
```ts
class LockedCache {
  private locks = new Map<string, Promise<any>>();

  async get<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
    const cached = await this.getCached<T>(key);
    if (cached) return cached;

    // Acquire a lock
    if (this.locks.has(key)) {
      return this.locks.get(key)!;
    }

    const promise = fetcher().then(value => {
      this.locks.delete(key);
      this.setCached(key, value);
      return value;
    });

    this.locks.set(key, promise);
    return promise;
  }
}
```

The stampede is prevented.

## The "cache warming" pattern

For cache warming (pre-populate):
```ts
async function warmCache(env: Env): Promise<void> {
  // Fetch the popular data
  const popular = await env.DB!.prepare(
    `SELECT * FROM items ORDER BY views DESC LIMIT 100`
  ).all();

  for (const item of popular.results) {
    await env.KV!.put(`item:${item.id}`, JSON.stringify(item), { expirationTtl: 3600 });
  }
}
```

The cache is pre-populated.

## The "cache anti-pattern" anti-patterns

### 1. No cache
- **Issue:** Every request hits the DB
- **Fix:** Use a cache

### 2. Cache invalidation bugs
- **Issue:** Stale data
- **Fix:** Invalidate on write

### 3. Cache stampede
- **Issue:** Multiple workers fetch simultaneously
- **Fix:** Use a lock

### 4. No TTL
- **Issue:** Stale data forever
- **Fix:** Set a TTL

### 5. Cache everything
- **Issue:** Memory pressure
- **Fix:** Cache the hot data only

### 6. No monitoring
- **Issue:** Cache hit rate unknown
- **Fix:** Monitor

## Verification
- **Test:** Cache hits
- **Test:** Cache invalidation works
- **Test:** TTL works
- **Live:** Hit rate is monitored
- **Audit:** Quarterly cache review

## Gotchas
- **The "no cache" anti-pattern.** Use a cache.
- **The "no invalidation" anti-pattern.** Invalidate on
  write.
- **The "no TTL" anti-pattern.** Set a TTL.
- **The "cache stampede" anti-pattern.** Use a lock.

## Related
- `caching-strategies-detail.md`
- `cache-strategies-detail.md`
- `cloudflare/workers-cache-api.md`
- `feature-cookbook-caching.md`
- `feature-cookbook-rate-limiting.md`
- `feature-cookbook-data-import.md`
