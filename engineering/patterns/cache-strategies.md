# cache-strategies

**Issue:** Cache-aside, read-through, write-through — when to use which
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your DB query is slow (200ms). You add a KV cache. Reads are
fast now. But the cache is stale; users see old data. You
invalidate the cache on every write. Now writes are slow. You
add a write-through cache. Now you have 2 caches. You have
"cache invalidation" bugs everywhere.

## Root cause
**Caching is a tradeoff between freshness, latency, and
complexity.** The right strategy depends on the data's
characteristics.

**Source:** AWS — Caching patterns:
https://docs.aws.amazon.com/whitepapers/latest/database-caching-strategies-at-scale/

## The 4 main strategies

### 1. Cache-aside (lazy loading)
- **Read:** Try cache; if miss, read from DB; populate cache
- **Write:** Write to DB; invalidate cache

```ts
async function getUser(id: string, env: Env): Promise<User> {
  const cached = await env.KV.get(`user:${id}`, 'json');
  if (cached) return cached as User;
  const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first<User>();
  if (!user) throw new Error('Not found');
  await env.KV.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 3600 });
  return user;
}

async function updateUser(id: string, changes: Partial<User>, env: Env): Promise<void> {
  await env.DB!.prepare(`UPDATE users SET ... WHERE id = ?`).bind(...).run();
  await env.KV.delete(`user:${id}`);  // invalidate
}
```

✅ Use when: read-heavy, can tolerate some staleness
❌ Drawback: cache miss is slow (DB round trip), thundering herd
on invalidation

### 2. Read-through
- **Read:** Cache is the source of truth; on miss, cache
  populates from DB
- **Write:** Cache writes through to DB

```ts
class ReadThroughCache {
  async get(id: string): Promise<User> {
    const cached = await this.kv.get(`user:${id}`, 'json');
    if (cached) return cached as User;
    const user = await this.db.first<User>(`SELECT * FROM users WHERE id = ?`, id);
    await this.kv.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 3600 });
    return user;
  }
  async set(id: string, user: User): Promise<void> {
    await this.kv.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 3600 });
    await this.db.run(`UPDATE users SET ... WHERE id = ?`, ...);
  }
}
```

✅ Use when: high cache hit rate, simple read patterns
❌ Drawback: cache is on the critical path

### 3. Write-through
- **Write:** Write to cache + DB synchronously
- **Read:** Always from cache

```ts
class WriteThroughCache {
  async set(id: string, user: User): Promise<void> {
    await this.db.run(`UPDATE users SET ... WHERE id = ?`, ...);
    await this.kv.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 3600 });
  }
  async get(id: string): Promise<User> {
    return await this.kv.get(`user:${id}`, 'json') as User;
  }
}
```

✅ Use when: must always be fresh, write-heavy
❌ Drawback: write is slow (2 round trips), cache failure = write
failure

### 4. Write-behind (write-back)
- **Write:** Write to cache; async flush to DB
- **Read:** Always from cache

```ts
class WriteBehindCache {
  async set(id: string, user: User): Promise<void> {
    await this.kv.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 3600 });
    // Queue the DB write
    this.queue.enqueue({ action: 'update', id, user });
  }
  // A worker processes the queue
}
```

✅ Use when: high write volume, can tolerate eventual DB write
❌ Drawback: DB failure = data loss (if cache is in-memory)

## When to use which

| Pattern | Read-heavy? | Need freshness? | Failure tolerance? |
|---|---|---|---|
| Cache-aside | Yes | Some staleness OK | Cache miss OK |
| Read-through | Yes | Fresh | Cache miss OK |
| Write-through | No | Must be fresh | Cache must succeed |
| Write-behind | No (write-heavy) | Eventual consistency | Data loss OK |

## CF-specific considerations

- **KV is eventually consistent** (60s window). Don't use for
  data that must be fresh.
- **D1 is strongly consistent** but slow for repeated reads.
  Use D1 + KV (cache-aside) for most cases.
- **Durable Objects** have in-memory state. Use as a write-
  through cache for hot data.
- **Workers Cache API** (newer) is edge-native. Use for static
  or rarely-changing data.

## Verification
- **Test:** `test/cache.test.ts > cache-aside populates on
  miss, invalidates on write` — passes
- **Live:** Cache hit rate > 80% in production
- **Audit:** Quarterly review of cache TTLs + invalidation
  patterns

## Gotchas
- **Cache invalidation is one of the 2 hard problems in CS.**
  Be conservative with TTLs; aggressive invalidation leads to
  bugs.
- **Stale-while-revalidate** is a good pattern for slow-to-
  change data: serve stale, fetch fresh in background, update
  cache.
- **Cache stampede:** if 1000 requests miss the cache
  simultaneously, all 1000 hit the DB. Use a single-flight
  pattern (only the first request reads; others wait).
- **The cache key should include the version.** A schema
  change invalidates all old keys.
- **Monitor the cache hit rate.** A sudden drop signals a
  problem (invalidation bug, traffic shift, etc.).

## Related
- `kv-eventually-consistent.md` (CF KV consistency)
- `patterns/per-tenant-durable-object.md` (DO as a cache)
- AWS: https://docs.aws.amazon.com/whitepapers/latest/database-caching-strategies-at-scale/
- "Caching at Reddit" (engineering blog): https://www.reddit.com/r/RedditEng/
