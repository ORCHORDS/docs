# D1 Query Result Caching KV Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project feed and profile pages repeat identical D1 SELECT queries across hundreds of concurrent
anonymous users — trending posts, top tags, public user counts — spending D1 row-read quota and
adding 10–40 ms per request for data that changes at most every 30 seconds. Without a caching
layer the platform wastes D1 read units and inflates p99 latency during traffic spikes.

## Context

Cloudflare D1 is a serverless SQLite database with per-account row-read limits and latency that
varies with result set size. KV is Cloudflare's globally-distributed key-value store with
sub-millisecond reads from every PoP, making it ideal for materialised query results. The
standard pattern is a write-through or stale-while-revalidate cache: serve stale KV data
immediately, refresh from D1 in the background or on expiry.

## Section 1 — Identify Cacheable Queries

Not all D1 queries benefit from KV caching. Profile the query mix using D1 analytics and Workers
tail logs to identify high-frequency, low-mutation reads.

```typescript
// src/lib/d1-tracer.ts
export interface QueryTrace {
  sql: string;
  durationMs: number;
  rowsRead: number;
}

export async function tracedQuery<T>(
  db: D1Database,
  stmt: D1PreparedStatement,
  label: string,
  ctx: ExecutionContext
): Promise<T[]> {
  const start = Date.now();
  const result = await stmt.all<T>();
  const durationMs = Date.now() - start;

  // Emit to Analytics Engine for cardinality analysis
  ctx.waitUntil(
    fetch("https://workers.cloudflare.com/analytics", {
      method: "POST",
      body: JSON.stringify({
        label,
        durationMs,
        rowsRead: result.meta.rows_read ?? 0,
      }),
    })
  );

  return result.results ?? [];
}
```

Queries returning the same rows for many users within a short window are prime cache candidates:
trending posts (TTL 30 s), global tag cloud (TTL 60 s), site-wide post counts (TTL 120 s).

## Section 2 — Cache-aside Pattern with KV

Implement a generic cache-aside helper that checks KV first, falls back to D1, then writes the
result back to KV with a TTL.

```typescript
// src/lib/kv-d1-cache.ts
export interface CacheOptions {
  ttlSeconds: number;
  /** Optional cache-buster suffix (e.g. deploy hash) */
  version?: string;
}

export async function cachedQuery<T>(
  kv: KVNamespace,
  db: D1Database,
  cacheKey: string,
  queryFn: (db: D1Database) => Promise<T>,
  opts: CacheOptions
): Promise<{ data: T; source: "kv" | "d1" }> {
  const key = opts.version ? `${cacheKey}:${opts.version}` : cacheKey;

  // 1. Try KV cache first
  const cached = await kv.get<T>(key, "json");
  if (cached !== null) {
    return { data: cached, source: "kv" };
  }

  // 2. Cache miss — query D1
  const data = await queryFn(db);

  // 3. Write back to KV asynchronously (don't block response)
  // NOTE: kv.put is not awaited here; caller must use ctx.waitUntil
  void kv.put(key, JSON.stringify(data), {
    expirationTtl: opts.ttlSeconds,
  });

  return { data, source: "d1" };
}
```

Usage in a Worker handler:

```typescript
// src/handlers/feed.ts
import { cachedQuery } from "../lib/kv-d1-cache.js";

export async function handleFeed(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const { data: posts, source } = await cachedQuery(
    env.CACHE_KV,
    env.DB,
    "feed:trending:global",
    async (db) => {
      return db
        .prepare(
          `SELECT post_id, score, created_at
           FROM posts
           WHERE is_public = 1
           ORDER BY score DESC
           LIMIT 50`
        )
        .all()
        .then((r) => r.results);
    },
    { ttlSeconds: 30, version: env.DEPLOY_VERSION }
  );

  return Response.json(posts, {
    headers: {
      "X-Cache-Source": source,
      "Cache-Control": "public, max-age=15",
    },
  });
}
```

## Section 3 — Stale-While-Revalidate with waitUntil

For feeds where slightly stale data is acceptable, serve the cached value immediately and refresh
in the background so the next request always hits KV.

```typescript
// src/lib/swr-cache.ts
interface SWREntry<T> {
  data: T;
  cachedAt: number; // epoch ms
}

export async function swrCachedQuery<T>(
  kv: KVNamespace,
  db: D1Database,
  ctx: ExecutionContext,
  cacheKey: string,
  queryFn: (db: D1Database) => Promise<T>,
  staleTtlMs: number,   // serve stale if younger than this
  hardTtlSeconds: number // KV expiration
): Promise<T> {
  const raw = await kv.get<SWREntry<T>>(cacheKey, "json");
  const now = Date.now();

  if (raw !== null) {
    const age = now - raw.cachedAt;
    if (age < staleTtlMs) {
      // Fresh enough — return immediately
      return raw.data;
    }
    // Stale — return old data but revalidate in background
    ctx.waitUntil(refreshCache(kv, db, cacheKey, queryFn, hardTtlSeconds));
    return raw.data;
  }

  // No cache entry — synchronous fetch
  const data = await queryFn(db);
  ctx.waitUntil(refreshCache(kv, db, cacheKey, queryFn, hardTtlSeconds));
  return data;
}

async function refreshCache<T>(
  kv: KVNamespace,
  db: D1Database,
  key: string,
  queryFn: (db: D1Database) => Promise<T>,
  ttlSeconds: number
): Promise<void> {
  const data = await queryFn(db);
  const entry: SWREntry<T> = { data, cachedAt: Date.now() };
  await kv.put(key, JSON.stringify(entry), { expirationTtl: ttlSeconds });
}
```

## Section 4 — Cache Invalidation on Write

When a example project user creates or deletes a post the affected cache keys must be purged so the
next read reflects reality. Colocate invalidation with the write path.

```typescript
// src/handlers/post-create.ts
export async function handleCreatePost(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const body = await request.json<{ content: string; tags: string[] }>();

  // Write to D1
  const result = await env.DB.prepare(
    "INSERT INTO posts (content, is_public, created_at) VALUES (?, 1, unixepoch())"
  )
    .bind(body.content)
    .run();

  if (!result.success) {
    return Response.json({ error: "insert failed" }, { status: 500 });
  }

  // Invalidate stale caches — fire and forget
  ctx.waitUntil(
    Promise.all([
      env.CACHE_KV.delete("feed:trending:global"),
      env.CACHE_KV.delete(`feed:tags:${body.tags[0]}`),
      env.CACHE_KV.delete("stats:post-count"),
    ])
  );

  return Response.json({ id: result.meta.last_row_id }, { status: 201 });
}
```

For bulk invalidations (e.g. moderator wipe), use KV list + delete in a Queue consumer so the
Worker does not exceed its CPU budget:

```typescript
// src/queues/cache-invalidator.ts
export async function handleCacheInvalidation(
  batch: MessageBatch<{ prefix: string }>,
  env: Env
): Promise<void> {
  for (const msg of batch.messages) {
    const listed = await env.CACHE_KV.list({ prefix: msg.body.prefix });
    await Promise.all(listed.keys.map((k) => env.CACHE_KV.delete(k.name)));
    msg.ack();
  }
}
```

## Anti-patterns

- Caching user-specific data (DMs, private profiles) under a shared key — leaks private content
- Setting TTL to 0 (never expires) for mutable data — causes permanent stale state
- Awaiting `kv.put()` in the hot path — adds 20–80 ms; always use `ctx.waitUntil`
- Skipping version/deploy suffix — stale schema data survives Worker deployments
- Caching large result sets (> 25 MB) — KV value limit is 25 MB; chunk or summarise
- Using KV for per-user session data under high write load — KV is optimised for reads

## Gotchas

- KV reads are eventually consistent across PoPs; a freshly invalidated key may still return
  stale data for up to 60 seconds from distant PoPs — acceptable for trending feeds, not for
  balance-sensitive data
- `kv.get("key", "json")` returns `null` (not undefined) on a miss — always check `!== null`
- D1 row-read billing applies even when the Worker crashes after the query — cache reduces units
  even if only 80% of responses are served from KV
- KV `expirationTtl` minimum is 60 seconds — for sub-60 s TTLs store `cachedAt` in the value
  and enforce freshness in application code (SWR pattern above)

## Verification

```bash
# Compare D1 row-read units before/after via Cloudflare dashboard
# Workers > D1 > Analytics > Rows Read (compare 24h windows)

# Check cache hit rate via X-Cache-Source header in production
npx wrangler tail --format=json \
  | jq 'select(.logs[].message | contains("X-Cache-Source"))' \
  | jq -r '.logs[].message' | sort | uniq -c

# KV metrics — reads vs writes in Cloudflare dashboard
# Workers > KV > Namespace > Metrics
```

## Related

- `/documentation/docs/policies/performance/kv-read-performance.md`
- `/documentation/docs/policies/performance/kv-bulk-get-batching.md`
- `/documentation/docs/policies/performance/kv-eventual-consistency-stale-data.md`
- `/documentation/docs/policies/performance/d1-prepared-statement-reuse.md`
- `/documentation/docs/policies/performance/workers-cache-api-stale-while-revalidate.md`

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/observability/metrics-analytics/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiration
- https://developers.cloudflare.com/d1/platform/limits/
