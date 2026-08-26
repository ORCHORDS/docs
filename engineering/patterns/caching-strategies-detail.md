# caching-strategies-detail

**Issue:** Caching patterns — read-through, write-through, write-behind
**Date:** 2026-08-09
**Status:** documented

## Symptom
You add a cache to your app. Every request hits the DB on
miss. The DB is slow. You add a cache write on every miss.
The cache is mostly empty because every cache key is unique
(per-user). You think caching is broken.

## Root cause
**Caching is not a one-size-fits-all.** The right pattern
depends on the access pattern, the staleness tolerance, and
the data shape.

**Source:** Various caching guides.

## The 5 main caching patterns

### 1. Cache-aside (lazy loading)
- **What:** App reads from cache; on miss, reads from DB
  and populates cache
- **When:** Most common; works for most apps

```ts
async function getUser(id: string, ctx: McContext): Promise<User | null> {
  // 1. Check cache
  const cached = await ctx.env.KV.get(`user:${ctx.tenant.id}:${id}`);
  if (cached) {
    return JSON.parse(cached);
  }

  // 2. Miss: read from DB
  const user = await ctx.env.DB!.prepare(
    `SELECT * FROM users WHERE id = ? AND tenant_id = ?`
  ).bind(id, ctx.tenant.id).first<User>();

  // 3. Populate cache
  if (user) {
    await ctx.env.KV.put(`user:${ctx.tenant.id}:${id}`, JSON.stringify(user), {
      expirationTtl: 300,  // 5 minutes
    });
  }

  return user;
}
```

✅ Simple
✅ Lazy (only caches what's read)
❌ Cold start (cache empty on first request)
❌ Stale data (until TTL expires)

### 2. Write-through
- **What:** App writes to cache + DB together
- **When:** Cache must be fresh on every write

```ts
async function updateUser(id: string, data: UserUpdate, ctx: McContext): Promise<User> {
  // 1. Update DB
  const user = await ctx.env.DB!.prepare(
    `UPDATE users SET ... WHERE id = ? AND tenant_id = ? RETURNING *`
  ).bind(..., id, ctx.tenant.id).first<User>();

  // 2. Update cache
  await ctx.env.KV.put(`user:${ctx.tenant.id}:${id}`, JSON.stringify(user), {
    expirationTtl: 300,
  });

  return user;
}
```

✅ Fresh on every write
❌ Writes are slower (two writes)
❌ Cache failures cause DB inconsistency

### 3. Write-behind (write-back)
- **What:** App writes to cache; cache writes to DB async
- **When:** Writes are bursty; DB is slow

```ts
async function updateUser(id: string, data: UserUpdate, ctx: McContext): Promise<void> {
  // 1. Update cache
  await ctx.env.KV.put(`user:${ctx.tenant.id}:${id}`, JSON.stringify(data), {
    expirationTtl: 300,
  });

  // 2. Queue DB write
  await ctx.env.QUEUE.send({ type: 'update_user', id, data, tenantId: ctx.tenant.id });
}

// Background worker:
async function processQueue(batch: Message[], env: Env): Promise<void> {
  for (const msg of batch) {
    if (msg.type === 'update_user') {
      await env.DB.prepare(`UPDATE users SET ... WHERE id = ?`).bind(...).run();
    }
  }
}
```

✅ Fast writes
❌ Risk of data loss (if cache fails before DB write)
❌ Complex (need a queue + worker)

### 4. Refresh-ahead
- **What:** Cache refreshes itself before expiration
- **When:** Latency is critical; can't afford cold reads

```ts
async function getUser(id: string, ctx: McContext): Promise<User | null> {
  const cached = await ctx.env.KV.get<User>(`user:${ctx.tenant.id}:${id}`);
  if (cached) {
    // Background refresh if cache is > 50% old
    if (Date.now() - cached.cachedAt > 150_000) {  // 2.5 min
      ctx.env.CTX.waitUntil(refreshUser(id, ctx));
    }
    return cached.data;
  }
  return refreshUser(id, ctx);
}
```

✅ Always fresh
❌ Hard to implement
❌ Background refreshes add load

### 5. Read-through (CF Cache API)
For HTML / static:
```ts
const cache = caches.default;
const cached = await cache.match(request);
if (cached) return cached;

const response = await fetch(request);
const cachedResponse = new Response(response.body, response);
cachedResponse.headers.set('Cache-Control', 'public, max-age=300');
ctx.env.CTX.waitUntil(cache.put(request, cachedResponse.clone()));
return cachedResponse;
```

CF's edge cache is a read-through cache at the network
level.

## The "cache invalidation" patterns

### 1. TTL (time-to-live)
- **What:** Cache expires after N seconds
- **Pros:** Simple
- **Cons:** Data may be stale until TTL expires

### 2. Event-based invalidation
- **What:** When the data changes, the cache is invalidated
- **Pros:** Always fresh
- **Cons:** Requires the cache invalidation to be wired up

```ts
async function updateUser(id: string, data: UserUpdate, ctx: McContext): Promise<User> {
  const user = await updateUserInDB(id, data, ctx);
  await ctx.env.KV.delete(`user:${ctx.tenant.id}:${id}`);  // Invalidate
  return user;
}
```

### 3. Tag-based invalidation
- **What:** Cache entries are tagged; invalidate by tag
- **Pros:** Bulk invalidation
- **Cons:** Requires tag-aware cache

CF doesn't support tag-based KV invalidation natively. Use
a separate index:
```ts
// On write
await ctx.env.KV.put(`user:${id}`, JSON.stringify(user));
await ctx.env.KV.put(`tag:user:${id}:tenant:${tenantId}`, '1');

// On invalidation
const keys = await ctx.env.KV.list({ prefix: `tag:user:` });
for (const key of keys.keys) {
  await ctx.env.KV.delete(key.name);
}
```

## The "cache key" design

The cache key must include all relevant context:
```ts
// ❌ Bad: no tenant_id
const key = `user:${userId}`;
// Two tenants would see each other's data!

// ✅ Good: tenant_id included
const key = `user:${tenantId}:${userId}`;

// ✅ Better: includes version for cache busting
const key = `user:v2:${tenantId}:${userId}`;
```

The key should be:
- **Unique:** Different inputs = different keys
- **Reproducible:** Same input = same key
- **Compact:** Short keys are faster

## The "cache stampede" problem

When a popular key expires, multiple requests hit the DB at
once. The DB is overwhelmed.

**Solution: Lock or jitter**
```ts
async function getUser(id: string, ctx: McContext): Promise<User | null> {
  const cached = await ctx.env.KV.get(`user:${id}`);
  if (cached) return JSON.parse(cached);

  // Use a DO as a lock
  const lockId = ctx.env.LOCK.idFromName(`user:${id}`);
  const lock = ctx.env.LOCK.get(lockId);
  await lock.fetch('https://lock/acquire');

  // Re-check (another request may have populated)
  const reCached = await ctx.env.KV.get(`user:${id}`);
  if (reCached) {
    await lock.fetch('https://lock/release');
    return JSON.parse(reCached);
  }

  // Read from DB
  const user = await readUserFromDB(id, ctx);
  await ctx.env.KV.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 300 });
  await lock.fetch('https://lock/release');
  return user;
}
```

## The "cache hierarchy" pattern

For high-traffic apps, layer the caches:
```
Browser cache (5-60s)
↓
CDN edge cache (1-60 min)
↓
CF Worker + KV cache (5-60 min)
↓
D1 (source of truth)
```

Each layer catches more requests:
- Browser: 30% hit rate (some users refresh)
- CDN: 80% hit rate
- KV: 95% hit rate
- D1: 100% (only on misses above)

## The "warm the cache" pattern

For known-popular data, pre-warm the cache:
```ts
// Cron: every 5 minutes
async function warmCache(env: Env): Promise<void> {
  const popular = await env.DB.prepare(`
    SELECT id FROM users ORDER BY login_count DESC LIMIT 100
  `).all<{ id: string }>();

  for (const row of popular.results) {
    const user = await env.DB.prepare(`SELECT * FROM users WHERE id = ?`).bind(row.id).first<User>();
    if (user) {
      await env.KV.put(`user:${user.tenant_id}:${user.id}`, JSON.stringify(user), {
        expirationTtl: 600,
      });
    }
  }
}
```

The cron runs every 5 minutes; the popular users are always
in the cache.

## Verification
- **Test:** `test/cache.test.ts > getUser reads from cache on
  second call` — passes
- **Live:** Cache hit rate is monitored; alerts if < 80%
- **Audit:** Quarterly review of cache TTLs

## Gotchas
- **The cache key must include tenant_id** (multi-tenant
  apps). A missing tenant_id is a security bug.
- **The cache invalidation must be wired up.** A write that
  doesn't invalidate the cache is a bug.
- **The "cache everything" anti-pattern.** Not every query
  benefits from caching. Long-tail data (per-user,
  per-request) doesn't cache well.
- **The "no TTL" anti-pattern.** A cache without TTL is a
  memory leak. Always set an expiration.
- **The "stale-while-revalidate" pattern** is the best
  default. Fast reads + fresh data.
- **CF KV is eventually consistent.** A write may not be
  visible for up to 60 seconds globally. Don't rely on
  read-after-write consistency.

## Related
- `cache-strategies.md`
- `kv-eventually-consistent.md`
- `content-delivery-network.md`
- `multi-tenant-data-isolation.md` (tenant_id in cache key)
- `connection-pooling.md` (later)
- Facebook memcache paper: https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final130_update.pdf
