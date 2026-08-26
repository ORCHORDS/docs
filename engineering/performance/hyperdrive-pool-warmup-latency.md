# Hyperdrive Connection Pool Warmup Latency

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Workers API backed by Hyperdrive + PostgreSQL shows a 500–1500 ms latency
spike on the first few requests after a deploy, after low-traffic periods (late night),
or when traffic first arrives at a Cloudflare PoP that has not served a request in
minutes. Subsequent requests to the same PoP drop to 10–30 ms database round-trip time.
The spikes appear in P99 but not P50, making them easy to miss until a monitoring alert
fires for a specific region.

## Context

Hyperdrive maintains a pool of persistent TCP + TLS connections between the Cloudflare
PoP and the origin PostgreSQL instance. When a Worker calls `env.DB.prepare(...).all()`,
it connects to the local Hyperdrive pool endpoint (sub-millisecond, same datacenter) and
Hyperdrive forwards the query over an existing persistent connection to the origin.

The warmup problem occurs at three levels:

| Level | Trigger | Added latency |
|-------|---------|---------------|
| Pool cold | PoP has never connected to origin, or pool expired | Full TCP + TLS + PG auth round-trip (~100–500 ms) |
| Pool drained | No traffic for `keepalives_idle` seconds, OS closed connections | Reconnect cost per query |
| Worker isolate cold | New Worker isolate, `env.DB` object freshly constructed | ~0 ms — Hyperdrive binding is lightweight |

Warmup latency is not the Worker's cold-start cost — it is Hyperdrive's pool reestablishing
origin connections. The fix is to keep pool connections alive (server and client TCP
keepalives) and, for latency-sensitive applications, prime the pool before traffic
arrives using Cloudflare Cron Triggers or monitoring probes.

## Configuring keepalives in Hyperdrive

Set TCP keepalive parameters in the Hyperdrive config to prevent OS from closing idle
connections before the pool considers them dead:

```bash
# Create or update Hyperdrive config with keepalive options
npx wrangler hyperdrive create my-db \
  --connection-string="postgresql://user:pass@db.example.com:5432/mydb" \
  --max-age=0 \
  --sslmode=require

# Hyperdrive respects PostgreSQL keepalive parameters passed in the connection string
npx wrangler hyperdrive create my-db \
  --connection-string="postgresql://user:pass@db.example.com:5432/mydb\
?keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=3"
```

```toml
# wrangler.toml
name = "api-worker"
compatibility_date = "2025-06-01"

[[hyperdrive]]
binding = "DB"
id = "your-hyperdrive-id"
# Hyperdrive caches read queries locally at the PoP
# caching.disabled = false  (default)
# caching.max_age = 60       (seconds to cache SELECT results)
```

## Pool-Priming Cron Trigger

Send a lightweight query on a schedule to keep Hyperdrive's pool alive at active PoPs.
A cron trigger fires from Cloudflare's infrastructure and hits the same pool as user
traffic, preventing the idle-connection drain:

```typescript
// src/warmup.ts — separate entry point or combined with main worker
interface Env {
  DB: Hyperdrive;
}

export default {
  // Main fetch handler
  async fetch(request: Request, env: Env): Promise<Response> {
    const result = await env.DB.prepare('SELECT NOW() AS ts').first<{ ts: string }>();
    return Response.json({ time: result?.ts });
  },

  // Cron trigger to keep the pool warm
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil((async () => {
      try {
        // Minimal query — just enough to keep a connection alive in each PoP that
        // receives the cron invocation. Cloudflare distributes cron events to multiple
        // PoPs when the cron fires, priming pools globally.
        await env.DB.prepare('SELECT 1').first();
      } catch (err) {
        console.error('Warmup ping failed:', err);
      }
    })());
  },
};
```

```toml
# wrangler.toml — run warmup every 5 minutes
[triggers]
crons = ["*/5 * * * *"]
```

## Detecting Pool State with P99 Alerting

Pool warmup spikes are P99 problems. Use Workers Analytics Engine to record per-request
database latency and alert on P99 deviations:

```typescript
interface Env {
  DB: Hyperdrive;
  AE: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const dbStart = Date.now();
    const rows = await env.DB
      .prepare('SELECT id, name FROM products WHERE active = TRUE LIMIT 20')
      .all();
    const dbMs = Date.now() - dbStart;

    ctx.waitUntil(
      env.AE.writeDataPoint({
        blobs: [new URL(request.url).pathname, request.cf?.colo as string ?? 'unknown'],
        doubles: [dbMs],
        indexes: ['db_latency'],
      }),
    );

    // Tag responses with latency so upstream monitors can detect pool misses
    return Response.json(rows.results, {
      headers: { 'X-DB-Ms': String(dbMs) },
    });
  },
};
```

Query P99 latency via the Analytics Engine GraphQL API to pinpoint which PoPs experience
warmup spikes:

```graphql
{
  viewer {
    accounts(filter: { accountTag: "YOUR_ACCOUNT_TAG" }) {
      workersAnalyticsEngineAdaptiveGroups(
        filter: { datetimeGeq: "2026-08-23T00:00:00Z", index: "db_latency" }
        limit: 100
        orderBy: [sum_double1_DESC]
      ) {
        dimensions { blob1 blob2 }  # path, colo
        quantiles { double1P99 double1P50 }
      }
    }
  }
}
```

## Origin PostgreSQL Keepalive Configuration

Hyperdrive's pool also depends on the origin PostgreSQL server keeping idle connections
alive. Ensure the origin's `tcp_keepalives_*` and `idle_in_transaction_session_timeout`
are compatible with Hyperdrive's expected idle period:

```sql
-- Check current keepalive settings on origin
SHOW tcp_keepalives_idle;      -- seconds before first keepalive probe
SHOW tcp_keepalives_interval;  -- seconds between probes
SHOW tcp_keepalives_count;     -- max failed probes before disconnect

-- Recommended for Hyperdrive: keep idle connections alive for at least 5 minutes
-- Set in postgresql.conf or per-session:
ALTER SYSTEM SET tcp_keepalives_idle = 120;
ALTER SYSTEM SET tcp_keepalives_interval = 10;
ALTER SYSTEM SET tcp_keepalives_count = 6;
SELECT pg_reload_conf();

-- Prevent idle-in-transaction connections from blocking the pool
ALTER SYSTEM SET idle_in_transaction_session_timeout = '30s';
SELECT pg_reload_conf();
```

## Disabling Caching for Write-Heavy Workloads

Hyperdrive's query cache reduces origin round-trips for reads but adds a cache-lookup
overhead for writes. For write-heavy workers, disable caching to reduce per-query
overhead:

```typescript
// Bypass Hyperdrive cache for write queries
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'POST') {
      // Hyperdrive bypasses cache for non-SELECT statements automatically,
      // but wrapping in a transaction guarantees no cache interaction.
      await env.DB.prepare('BEGIN').run();
      try {
        const body = await request.json<{ name: string; price: number }>();
        await env.DB.prepare('INSERT INTO products (name, price) VALUES (?, ?)')
          .bind(body.name, body.price).run();
        await env.DB.prepare('COMMIT').run();
        return new Response('Created', { status: 201 });
      } catch (err) {
        await env.DB.prepare('ROLLBACK').run();
        return new Response('Error', { status: 500 });
      }
    }
    const rows = await env.DB.prepare('SELECT * FROM products').all();
    return Response.json(rows.results);
  },
};
```

## Anti-patterns

- **No cron warmup for latency-sensitive APIs**: traffic that arrives at a dormant PoP
  always pays the pool cold-start cost. A 5-minute cron keeps pools alive at active PoPs.
- **Short `keepalives_idle` on the origin**: if the origin closes idle connections after
  30 seconds but Hyperdrive's pool considers them valid for 60 seconds, queries on those
  connections fail with a connection reset and Hyperdrive must reconnect.
- **Using transactions for all queries**: Hyperdrive routes transactions to a dedicated
  pooled connection and cannot cache their results. Over-using transactions increases
  pool saturation and adds per-query latency.
- **Ignoring regional P99 spikes**: alerting only on global P50 hides PoP-level warmup
  events. Segment latency metrics by Cloudflare colo code (`request.cf.colo`).

## Gotchas

- Hyperdrive pools are per-PoP, not global. A warmup cron ping reaches one or a few PoPs
  per firing, not all PoPs simultaneously. For global warming, rely on steady background
  traffic or accept occasional warmup latency in low-traffic regions.
- Hyperdrive's `max_age` config controls the query result cache TTL, not the connection
  pool lifetime. Setting `max_age = 0` disables query caching but does not affect how
  long pool connections are maintained.
- The Hyperdrive binding (`env.DB`) is a Cloudflare Workers binding object, not a
  standard PostgreSQL driver. `env.DB.prepare()` uses the D1-compatible `Statement` API,
  not `node-postgres` (`pg`) or `postgres.js`. Mixing driver APIs will cause type errors.
- The Workers subrequest to Hyperdrive is local (same PoP) but still counts toward the
  50-simultaneous-subrequest limit per invocation.

## Verification

1. Deploy a preview Worker and measure cold latency:
   ```bash
   # First request after deploy (cold pool)
   time curl -s https://my-worker.workers.dev/api/products > /dev/null
   # Wait 10 minutes then measure again (warm pool)
   time curl -s https://my-worker.workers.dev/api/products > /dev/null
   ```
2. Use `wrangler tail` with `--format json` to see per-request database latency from the
   `X-DB-Ms` header or custom log lines.
3. Check Hyperdrive metrics in the Cloudflare Dashboard → Workers → Hyperdrive → your
   config → Metrics. The "Connection Pool Reuse Rate" metric should be >95% in steady
   state. Low reuse rates indicate pool drain between requests.
4. Verify origin keepalive compatibility by connecting directly with psql:
   ```sql
   SELECT client_addr, state, state_change, query_start
   FROM pg_stat_activity
   WHERE application_name LIKE 'hyperdrive%';
   ```
   Connections should show `state = idle` and a recent `state_change` time.

## Related

- `hyperdrive-connection-pooling-workers.md`
- `database-connection-pool-sizing.md`
- `workers-cold-start-optimization.md`
- `workers-module-initialization-lazy-loading.md`
- `d1-query-optimization.md`

## Sources

- Hyperdrive Overview — https://developers.cloudflare.com/hyperdrive/
- Hyperdrive Configuration — https://developers.cloudflare.com/hyperdrive/configuration/
- Hyperdrive Limits — https://developers.cloudflare.com/hyperdrive/platform/limits/
- Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- PostgreSQL Connection Settings — https://www.postgresql.org/docs/current/runtime-config-connection.html
