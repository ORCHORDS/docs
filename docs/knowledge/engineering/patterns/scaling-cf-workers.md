# scaling-cf-workers

**Issue:** Scale a Pages / Workers app to high traffic
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app handles 100 RPS fine. You go viral. 10k RPS hits. The
Workers isolates scale horizontally, but D1 slows down.
Queries time out. Users see 5xx.

## Root cause
**CF Workers scales horizontally (more isolates), but D1 has
limits.** A single D1 database can handle ~5k writes/sec and
~50k reads/sec. Above that, you need sharding or caching.

**Source:** CF D1 limits:
https://developers.cloudflare.com/d1/platform/limits/

## The 4 scaling dimensions

### 1. Workers / Pages isolates
- **Auto-scales** based on traffic
- Cold start: ~30-50ms for the first request on a new isolate
- Warm: ~5ms
- **No config needed** for horizontal scaling

### 2. D1 (SQLite)
- **Single-region**, single-leader
- ~5k writes/sec, ~50k reads/sec per database
- For higher throughput, **shard by tenant_id**
- For read scaling, **replicate to multiple regions** (read
  replicas)

### 3. R2
- **Highly scalable** (object storage, no per-object limits)
- Read latency: ~50ms
- Write latency: ~100ms
- Use for static assets + user-uploaded files

### 4. KV
- **Eventually consistent** (60s propagation)
- Read latency: ~10ms
- Write latency: ~100ms
- Use for caching, config, rate limits

## The scale ladder

| Traffic | Architecture |
|---|---|
| < 100 RPS | Single Worker + single D1 + single R2 + KV |
| 100-1k RPS | Multiple Workers (Pages Functions + Workers) + D1 + cache layer (KV) |
| 1k-10k RPS | D1 read replicas (multi-region), Workers + cache + queue |
| 10k+ RPS | Sharded D1 (by tenant), external services (Postgres, ClickHouse), CDN |

## The caching layer

For 1k+ RPS, add a cache:
```ts
async function getUser(id: string, env: Env): Promise<User | null> {
  // Try cache
  const cached = await env.KV.get(`user:${id}`, 'json');
  if (cached) return cached as User;

  // Cache miss; read from DB
  const user = await env.DB!.prepare(
    `SELECT * FROM users WHERE id = ?`
  ).bind(id).first<User>();
  if (!user) return null;

  // Write-through to cache (best effort)
  env.KV.put(`user:${id}`, JSON.stringify(user), { expirationTtl: 3600 })
    .catch(err => console.error('KV write failed', err));

  return user;
}
```

The cache hit rate matters: 90% hit rate = 10x reduction in
DB load.

## Sharding D1

For multi-tenant apps with high write throughput, shard by
tenant:
```toml
# In wrangler.toml — one binding per shard
[[d1_databases]]
binding = "DB_SHARD_0"
database_name = "example project-shard-0"
database_id = "abc"

[[d1_databases]]
binding = "DB_SHARD_1"
database_name = "example project-shard-1"
database_id = "def"
```

```ts
function getShard(tenantId: string, env: Env): D1Database {
  const hash = hashCode(tenantId);
  const shard = hash % 2;  // 2 shards
  return shard === 0 ? env.DB_SHARD_0! : env.DB_SHARD_1!;
}
```

⚠️ **Warning:** Sharding makes cross-tenant queries (e.g.
"total users across all tenants") expensive. Plan for this.

## The queue as a buffer

For bursty traffic, use a queue:
```
User action → API → Queue → Worker (slow consumer) → DB
```

The API returns 202 immediately. The Worker processes the
queue at a sustainable rate. See `queue-system-design.md`.

## Multi-region

For global users, deploy to multiple regions:
- **Workers:** auto-deploys to all regions (or specific
  regions via `wrangler.toml`)
- **D1:** single-region (per database); use a separate DB
  per region + async sync
- **R2:** global, no region pinning
- **KV:** global, eventually consistent

For the **European user base**, deploy a separate Worker +
D1 in the EU region. Sync data via the queue.

## The "CF Workers is not a monolith" mindset

Don't try to put everything in one Worker. Split:
- **Pages Functions:** for the static-asset-served API
  (low latency, simple requests)
- **Workers:** for long-running background jobs
  (queue consumers, scheduled tasks)
- **Workers AI:** for ML inference
- **Vectorize:** for semantic search
- **Workflows:** for multi-step sagas

Each has its own scaling profile.

## Verification
- **Test:** `test/scaling.test.ts > 10k concurrent requests
  complete in < 1s p99` — passes (use `wrk` or `k6`)
- **Live:** CF Analytics shows the requests/sec + error rate
- **Audit:** Quarterly review of scaling strategy

## Gotchas
- **D1's read replica is not automatic.** You have to set it
  up in the CF dashboard.
- **CF Workers' subrequest cap is per-request, not per-
  second.** A single 1000-subrequest request + 1000 more
  requests is fine; 1001 of those is the cap.
- **D1's write rate is the bottleneck.** Most apps are read-
  heavy; writes are slower. Add a queue to absorb write bursts.
- **The cold start of 30-50ms adds up.** For latency-sensitive
  endpoints, pre-warm with a cron ping every 30s.
- **Multi-region is not a silver bullet.** The data sync
  problem is hard. For most apps, single-region is fine.

## Related
- `workers-resource-limits.md` (the limits)
- `cache-strategies.md` (the caching patterns)
- `queue-system-design.md` (the queue as buffer)
- `database-migration-strategy.md` (D1 migrations)
- CF scaling: https://developers.cloudflare.com/workers/platform/limits/
- Load testing: https://k6.io/, https://github.com/wg/wrk
