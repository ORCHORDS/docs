# build-time-vs-runtime

**Issue:** When to compute at build time vs runtime
**Date:** 2026-08-09
**Status:** documented

## Symptom
You compute the user count at runtime on every page load. 10k
users, 100 RPS = 1M queries per second. The D1 is slow. You
wish you'd cached it. Or, you cache the user count at build
time. The count is stale (off by 100). The dashboard shows
the wrong number. You get bug reports.

## Root cause
**Build time and runtime are different.** Some data should
be computed at build time (rarely changes, expensive to
compute). Some should be at runtime (changes often, must be
fresh). Choosing wrong is a perf bug or a correctness bug.

**Source:** Jamstack principles:
https://jamstack.org/

## The decision framework

### Compute at build time when:
- **The data changes rarely** (a config, a static list)
- **The data is expensive to compute** (an aggregation across
  millions of rows)
- **The data is the same for all users** (no personalization)
- **The freshness tolerance is high** (minutes, hours, days)

### Compute at runtime when:
- **The data changes often** (real-time metrics, live prices)
- **The data is per-user** (personalized recommendations)
- **The data is expensive to cache** (too many variations)
- **The freshness tolerance is low** (seconds)

### Compute at request time, cache it when:
- **The data is somewhat dynamic** (changes every few minutes)
- **The cost of recomputing is moderate** (a few DB queries)
- **The number of users reading it is high** (cache amortizes)

## Examples

### Build time
- **Static pages** (homepage, about, pricing)
- **Per-locale JSON** (translations baked in at build)
- **Asset hashing** (`main.abc123.js`)
- **Schema migrations** (DB schema at deploy time)
- **API documentation** (OpenAPI from code annotations)

### Runtime, with cache
- **User profile** (cached in KV for 1 hour)
- **Search results** (cached in KV for 5 minutes)
- **Aggregations** (cached in KV for 1 hour, recomputed on
  data change)
- **Recommendations** (cached per-user in KV)

### Runtime, no cache
- **Auth check** (every request)
- **Live data** (chat messages, real-time prices)
- **Per-request personalized** (current user's feed)
- **Idempotency keys** (every POST/PATCH)

## The "build-time + revalidate" pattern

For data that's "expensive + rarely changes" but "must be
fresh-ish," use a hybrid:
1. Compute at build time (fast page load)
2. Revalidate at runtime (when data actually changes)
3. Serve the cache until the revalidation completes

```ts
let cachedUserCount: { value: number; updatedAt: number } | null = null;
const TTL_MS = 60_000;  // 1 minute

async function getUserCount(env: Env): Promise<number> {
  if (cachedUserCount && Date.now() - cachedUserCount.updatedAt < TTL_MS) {
    return cachedUserCount.value;
  }
  // Recompute
  const result = await env.DB!.prepare(`SELECT COUNT(*) AS count FROM users`).first<{ count: number }>();
  cachedUserCount = { value: result!.count, updatedAt: Date.now() };
  return cachedUserCount.value;
}
```

## The "stale-while-revalidate" pattern

For data that can be slightly stale but must be fast:
1. Serve the cached version (fast)
2. Revalidate in the background
3. Update the cache for next request

```ts
async function getUserCountWithSWR(env: Env): Promise<number> {
  if (cachedUserCount) {
    // Serve cached value immediately
    if (Date.now() - cachedUserCount.updatedAt > TTL_MS) {
      // Revalidate in background
      env.CTX.waitUntil(refreshUserCount(env));
    }
    return cachedUserCount.value;
  }
  // No cache; compute now
  return refreshUserCount(env);
}
```

## The "CDN + cache + revalidate" combo

For static + dynamic + real-time, layer them:
1. **CDN** (Cloudflare) caches the HTML at the edge
2. **KV** caches the data behind the HTML
3. **D1** is the source of truth
4. **Background worker** revalidates KV from D1

```
User → CDN (HTML cached) → Worker → KV (data cached) → D1 (source of truth)
                              ↓
                         Background worker (revalidates KV from D1)
```

The user sees the cached HTML (fast). The data behind it is
cached (fast). The source is fresh (D1). The background
worker keeps the cache warm.

## The "build time trade-off"

Build time computation has a cost:
- **Build time:** longer builds = slower deploys
- **Cache invalidation:** when the underlying data changes,
  the cache must be invalidated
- **Cold start:** a fresh deploy has a cold cache (slower
  first requests)

For most apps, the trade-off is worth it. A 5-second build
saves 100ms per request × 1M requests/day = significant.

For very dynamic data, build time is wrong. Use runtime.

## Verification
- **Test:** `test/build-time.test.ts > build-time data is
  pre-computed, not recomputed at runtime` — passes
- **Live:** p99 latency for cached endpoints < 50ms
- **Audit:** Quarterly review of build time + cache hit rate

## Gotchas
- **Build time computation is global.** If a single user has
  per-user data, don't pre-compute it (it'll be wrong for
  other users).
- **The "stale" data is wrong data.** If the dashboard shows
  "100 users" when there are 1M, that's a bug, not a
  feature. Cache wisely.
- **The cache invalidation must be correct.** If the cache
  is stale, the data is wrong. If the cache is revalidated
  too often, you lose the benefit.
- **Build time is not "free."** A build that takes 5 minutes
  is a 5-minute delay in deploys. Profile and optimize.
- **Static data is not "always" static.** A config that
  changes once a year is still 1 change. Have a way to
  re-deploy or update without a code change.

## Related
- `cache-strategies.md`
- `next-static-export-pages.md` (build-time + CDN)
- `feature-flags.md` (build-time + runtime)
- `content-delivery-network.md` (CDN caching)
- Jamstack: https://jamstack.org/
- Next.js ISR: https://nextjs.org/docs/basic-features/data-fetching/incremental-static-regeneration
