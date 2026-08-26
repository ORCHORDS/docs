# scaling-strategies-detail

**Issue:** Scaling — vertical vs horizontal, CF specifics
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app is slow. You have 1 CF Worker. You add more
memory. The Worker still has 128MB. The code is still
slow. The DB is the bottleneck. You scale the DB. The DB
is now fast. The Worker is the bottleneck. You can't
"scale" a Worker like a server.

## Root cause
**CF Workers are auto-scaling.** You don't add more
Workers; CF spins up more isolates. The bottleneck is
usually the DB or the vendor API, not the Worker.

**Source:** CF Workers scaling:
https://developers.cloudflare.com/workers/platform/limits/

> "Workers scale automatically based on request volume.
> ... Each request is handled by a separate isolate."

## The "vertical vs horizontal" choice

### Vertical scaling (bigger machine)
- **What:** Add CPU, RAM, disk to a single server
- **Pros:** Simple; no code changes
- **Cons:** Hardware limits; single point of failure
- **For:** Databases (Postgres, MySQL)

### Horizontal scaling (more machines)
- **What:** Add more servers
- **Pros:** Unlimited; fault-tolerant
- **Cons:** Complexity; coordination
- **For:** Stateless services (Workers)

For most apps, **horizontal** is the answer.

## The "CF Workers scaling" model

CF Workers scale automatically:
- **Each request** is handled by an isolate
- **Isolates are spun up** as needed (cold start ~5-50ms)
- **No upper limit** on concurrent requests
- **Costs scale linearly** with usage

You don't "scale" Workers. You pay for what you use.

## The "D1 scaling" model

D1 has limits:
- **Database size:** 10 GB (Pro plan); 1 GB (Free)
- **Reads:** Unlimited (replicated)
- **Writes:** Limited by primary region

For larger databases:
- **Sharding:** Multiple D1 databases; route by tenant_id
- **Migrate to Postgres** (Neon, Supabase, etc.)
- **Use a different store** (e.g. Turso for distributed
  SQLite)

## The "R2 scaling" model

R2 has limits:
- **Object size:** 5 TB per object
- **Storage:** Unlimited
- **Bandwidth:** Unlimited (egress free)

For most apps, R2 scales to petabytes without changes.

## The "KV scaling" model

KV is eventually consistent, but scales:
- **Reads:** Unlimited, global
- **Writes:** Eventually propagated (60s)
- **Storage:** Unlimited

For most apps, KV is fine. For real-time consistency, use
D1 or DO.

## The "DO scaling" model

DOs scale per name:
- **One DO per name** (by design)
- **Concurrent requests to the same DO** are serialized
- **Throughput per DO** is limited (~1k req/sec)

For high-traffic apps:
- **Use multiple names** (e.g. shard by user_id)
- **Use a different primitive** (e.g. KV for high-volume)

## The "vendor scaling" model

For vendor APIs (Stripe, OpenAI, etc.):
- **Rate limits:** Most vendors have rate limits (per sec,
  per day)
- **Throttling:** Spread the load
- **Queue:** Use CF Queues to batch requests
- **Cache:** Cache the vendor response

## The "caching for scale" pattern

Caching is the #1 scaling technique:
- **CF Cache:** At the edge (free, fast)
- **KV:** Per-isolate (cheap, fast)
- **DO memory:** Per-instance (fast, ephemeral)
- **D1 query cache:** Reduce DB load

A 90% cache hit rate = 10x reduction in DB load.

## The "DB connection pooling" pattern

For Postgres, connections are expensive:
- **Direct:** New connection per request (slow)
- **Pool:** Reuse connections (fast)

For CF Workers + Postgres, use **Hyperdrive** (CF's
connection pooler):
```toml
# wrangler.toml
[[hyperdrive]]
binding = "HYPERDRIVE"
id = "..."
```

```ts
// In the Worker
const psql = new Client(env.HYPERDRIVE.connectionString);
```

Hyperdrive pools connections + caches queries.

## The "read replicas" pattern

For read-heavy apps, add read replicas:
```sql
-- Postgres: create a read replica
CREATE PUBLICATION my_pub FOR TABLE users, posts;
-- On the replica, subscribe
CREATE SUBSCRIPTION my_sub CONNECTION '...' PUBLICATION my_pub;
```

The primary handles writes; replicas handle reads. D1 has
read replicas built-in (eventually consistent).

## The "sharding" pattern

For huge databases (1B+ rows), shard by tenant:
```ts
function getDbForTenant(tenantId: string, env: Env): D1Database {
  const shard = parseInt(sha256(tenantId).slice(0, 1), 16) % 4;  // 4 shards
  return [env.DB_SHARD_0, env.DB_SHARD_1, env.DB_SHARD_2, env.DB_SHARD_3][shard];
}
```

Each tenant's data is on one shard. The code is unchanged
(it just routes by tenant_id).

## The "queue for load shedding" pattern

For bursty load, use a queue:
```ts
async function processRequest(request: Request, env: Env): Promise<Response> {
  // Quick checks
  if (request.method === 'GET' && cache.has(request)) return cache.get(request);

  // Long work → queue
  if (isLongRunning(request)) {
    await env.QUEUE.send({ request: request.url, body: await request.text() });
    return new Response(JSON.stringify({ status: 'queued' }), { status: 202 });
  }

  // Normal work
  return handleRequest(request, env);
}
```

The user gets a "queued" response; the worker processes
the queue.

## The "auto-scaling" patterns

For auto-scaling (CF does this automatically):
- **CPU-bound:** CF spins up more isolates
- **I/O-bound:** CF waits for the I/O; isolates are reused
- **Burst:** CF handles the spike (pay for what you use)

## The "scaling ceiling" pattern

Every system has a ceiling. Find it:
1. **Load test** to find the bottleneck
2. **Optimize** the bottleneck
3. **Repeat** until the ceiling is acceptable

The ceiling is:
- **D1:** Limited by primary write throughput
- **R2:** Limited by network bandwidth
- **KV:** Limited by write propagation (60s)
- **DO:** Limited by per-DO throughput
- **Worker:** Limited by CPU/IO

## The "scale down" pattern

Scaling down is also important:
- **Right-size Workers:** Unbundled if high traffic
- **Right-size D1:** Drop unused data
- **Right-size R2:** Use lifecycle rules
- **Right-size KV:** Drop unused keys

The bill should scale with usage, not with provisioned
capacity.

## Verification
- **Test:** Load test at expected + 2x traffic
- **Live:** Dashboards show scaling metrics
- **Audit:** Quarterly capacity review

## Gotchas
- **The "scale by adding memory" anti-pattern.** Memory
  doesn't fix slow code.
- **The "scale by adding servers" anti-pattern.** A
  stateless service is already scaled. Find the real
  bottleneck.
- **The "scale forever" anti-pattern.** Every system has
  a ceiling. Plan for it.
- **The "scale down ignored" anti-pattern.** A
  over-provisioned system wastes money. Right-size
  regularly.
- **The "no monitoring" anti-pattern.** Without monitoring,
  you don't know if scaling worked.

## Related
- `cloudflare/workers-resource-limits.md`
- `cloudflare/cost-optimization-cloudflare.md`
- `scaling-cf-workers.md`
- `load-testing.md`
- `error-budget-slo.md`
- `caching-strategies-detail.md`
- CF scaling: https://developers.cloudflare.com/workers/platform/limits/
- Hyperdrive: https://developers.cloudflare.com/hyperdrive/
