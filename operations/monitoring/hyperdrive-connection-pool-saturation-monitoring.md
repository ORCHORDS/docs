# Hyperdrive Connection Pool Saturation Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Workers using Hyperdrive to connect to a PostgreSQL or MySQL database start seeing elevated
query latency with no change in database load. The root cause is Hyperdrive's connection
pool reaching its per-PoP concurrency limit, causing new queries to queue behind in-flight
ones. Without per-query wait-time instrumentation you cannot distinguish "slow database"
from "pool saturation" and may scale the wrong resource.

## Context

Hyperdrive maintains a persistent connection pool per Cloudflare Point of Presence. Each
Worker invocation acquires a connection from the pool for the duration of the query. When
all pool slots are occupied, subsequent `query()` calls block in a wait queue internal to
the Hyperdrive binding. The wait time is not exposed by any Hyperdrive API today (2026-Q3),
so it must be inferred by comparing total query time (measured in the Worker) against
expected database execution time (measured via `EXPLAIN ANALYZE` baselines).

Tracking `query_wait_ms` (total − baseline) per connection string and correlating with
request concurrency reveals saturation before it causes user-visible timeout errors.

---

## 1. Wrapping the Hyperdrive Client with Latency Tracking

```typescript
// src/lib/hyperdrive-tracked.ts
import { Pool } from 'pg';

export interface QueryRecord {
  query: string;
  rowCount: number;
  totalMs: number;
  // When totalMs >> baseline we infer pool wait time
}

export async function trackedQuery<T = unknown>(
  pool: ReturnType<typeof createPool>,
  sql: string,
  params: unknown[] = []
): Promise<{ rows: T[]; record: QueryRecord }> {
  const start = performance.now();
  const result = await pool.query(sql, params);
  const totalMs = performance.now() - start;

  return {
    rows: result.rows as T[],
    record: {
      query: sql.slice(0, 120).replace(/\s+/g, ' '),
      rowCount: result.rowCount ?? 0,
      totalMs,
    },
  };
}

export function createPool(hyperdrive: Hyperdrive): Pool {
  return new Pool({ connectionString: hyperdrive.connectionString, max: 5 });
}
```

## 2. Emitting Pool Saturation Signals to Analytics Engine

```typescript
// src/index.ts
import { createPool, trackedQuery } from './lib/hyperdrive-tracked';

export interface Env {
  DB: Hyperdrive;
  ANALYTICS: AnalyticsEngineDataset;
  // Baseline p50 query time (ms) stored in a KV for each query fingerprint
  QUERY_BASELINES: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const pool = createPool(env.DB);

    const { rows, record } = await trackedQuery(
      pool,
      'SELECT id, name FROM products WHERE category = $1 LIMIT 100',
      ['electronics']
    );

    const fingerprint = 'products_by_category';
    const baselineStr = await env.QUERY_BASELINES.get(fingerprint);
    const baselineMs = baselineStr ? parseFloat(baselineStr) : 0;
    const estimatedWaitMs = Math.max(0, record.totalMs - baselineMs);
    const isSaturated = estimatedWaitMs > 200; // >200ms inferred wait = saturation

    ctx.waitUntil(
      Promise.resolve(
        env.ANALYTICS.writeDataPoint({
          blobs: [fingerprint, isSaturated ? 'saturated' : 'ok', env.DB.id ?? 'default'],
          doubles: [
            record.totalMs,       // double1: total query ms
            estimatedWaitMs,      // double2: estimated pool wait ms
            isSaturated ? 1 : 0,  // double3: saturation flag
          ],
          indexes: [fingerprint],
        })
      )
    );

    return Response.json({ count: rows.length });
  },
};
```

## 3. Baseline Calibration Worker (Runs Nightly)

```typescript
// calibrate/index.ts — scheduled cron, runs at low-traffic hours
export interface Env {
  DB: Hyperdrive;
  QUERY_BASELINES: KVNamespace;
}

const FINGERPRINTS: Array<{ id: string; sql: string; params: unknown[] }> = [
  { id: 'products_by_category', sql: 'SELECT id, name FROM products WHERE category = $1 LIMIT 100', params: ['electronics'] },
  { id: 'orders_recent',        sql: 'SELECT id FROM orders WHERE created_at > NOW() - INTERVAL \'1 day\'', params: [] },
];

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const { Pool } = await import('pg');
    const pool = new Pool({ connectionString: env.DB.connectionString, max: 1 });

    for (const fp of FINGERPRINTS) {
      const samples: number[] = [];
      for (let i = 0; i < 5; i++) {
        const t0 = performance.now();
        await pool.query(fp.sql, fp.params);
        samples.push(performance.now() - t0);
      }
      samples.sort((a, b) => a - b);
      const p50 = samples[Math.floor(samples.length / 2)];
      await env.QUERY_BASELINES.put(fp.id, String(p50), { expirationTtl: 86400 * 7 });
      console.log(`[calibrate] ${fp.id} p50=${p50.toFixed(1)}ms`);
    }

    await pool.end();
  },
};
```

## 4. Analytics Engine SQL — Pool Saturation Rate

```sql
-- Saturation rate per query fingerprint over the last 10 minutes
SELECT
  blob1                                            AS query_fingerprint,
  SUM(_sample_interval * double3)                  AS saturated_count,
  SUM(_sample_interval)                            AS total_queries,
  SUM(_sample_interval * double3)
    / SUM(_sample_interval)                        AS saturation_rate,
  quantileWeighted(0.95)(double2, _sample_interval) AS p95_wait_ms,
  quantileWeighted(0.99)(double1, _sample_interval) AS p99_total_ms
FROM hyperdrive_pool_metrics
WHERE timestamp >= NOW() - INTERVAL '10' MINUTE
GROUP BY blob1
ORDER BY saturation_rate DESC
```

## 5. Alerting on Sustained Pool Saturation

```typescript
// monitor/pool-alert.ts — scheduled every 5 minutes
export interface Env {
  ANALYTICS_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  PAGERDUTY_ROUTING_KEY: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const query = `
      SELECT blob1 AS fingerprint,
             blob3 AS hyperdrive_id,
             SUM(_sample_interval * double3) / SUM(_sample_interval) AS sat_rate,
             quantileWeighted(0.95)(double2, _sample_interval)        AS p95_wait_ms
      FROM hyperdrive_pool_metrics
      WHERE timestamp >= NOW() - INTERVAL '5' MINUTE
      GROUP BY blob1, blob3
      HAVING sat_rate > 0.25
    `;

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${env.ANALYTICS_API_TOKEN}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      }
    );
    const { data } = (await res.json()) as {
      data: Array<{ fingerprint: string; hyperdrive_id: string; sat_rate: number; p95_wait_ms: number }>;
    };

    for (const row of data) {
      await fetch('https://events.pagerduty.com/v2/enqueue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          routing_key: env.PAGERDUTY_ROUTING_KEY,
          event_action: 'trigger',
          dedup_key: `hyperdrive-sat-${row.hyperdrive_id}-${row.fingerprint}`,
          payload: {
            summary: `Hyperdrive pool saturation: ${row.fingerprint} sat_rate=${(row.sat_rate * 100).toFixed(0)}% p95_wait=${row.p95_wait_ms.toFixed(0)}ms`,
            severity: row.sat_rate > 0.5 ? 'critical' : 'warning',
            source: 'hyperdrive-monitor',
          },
        }),
      });
    }
  },
};
```

## 6. Hyperdrive Config Tuning Reference

```typescript
// wrangler.toml — increase max_connections to reduce saturation
// [[hyperdrive]]
// id = "my-hyperdrive"
// name = "DB"
// [hyperdrive.caching]
//   disabled = false
//   max_age = 60
//   stale_while_revalidate = 15
//
// Note: max_connections per PoP is set on the Hyperdrive config via the API,
// not in wrangler.toml.

async function updateHyperdriveMaxConnections(
  accountId: string,
  hyperdriveId: string,
  apiToken: string,
  maxConnections: number
): Promise<void> {
  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/hyperdrive/configs/${hyperdriveId}`,
    {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${apiToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ origin: { max_pool_size: maxConnections } }),
    }
  );
}
```

---

## Anti-patterns

- **Using `pool.query()` without timing wrappers**: you cannot distinguish pool saturation
  from slow database queries without measuring both total time and a baseline.
- **Setting `max` connections per Worker equal to max_pool_size on Hyperdrive**: multiple
  concurrent Worker isolates at the same PoP each create their own `Pool` instance, so the
  effective total connections = `max_pool_size × active_isolates`. Keep Worker-side `max` at
  1–2 and let Hyperdrive manage pooling.
- **Alerting on p99 total query time alone**: query time spikes can be caused by table locks,
  index misses, or pool saturation — the estimated wait dimension separates these.
- **Re-creating `Pool` inside every request handler**: constructing a `new Pool()` per
  request defeats connection reuse. Create the pool once at module scope or cache it.

## Gotchas

- Hyperdrive caches query results for read queries; a cache hit returns in <1ms and will
  not register as pool saturation even under high load. Filter out cached responses when
  computing baselines by checking `result.command === 'SELECT' && result.rowCount === 0`
  is not a reliable proxy — use a `/* no-cache */` comment to bypass.
- The Workers runtime resets module-scope state between isolate evictions; pool objects
  created at module scope are recreated after a cold start, causing a latency spike that
  looks like pool saturation on calibration dashboards.
- `performance.now()` in Workers measures wall-clock time and includes time spent in the
  Hyperdrive binding's own overhead (TLS, framing). The baseline calibration absorbs this,
  so do not subtract it manually.

## Verification

```bash
# Check Hyperdrive config (current max_pool_size)
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/hyperdrive/configs/$HYPERDRIVE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.result.origin.max_pool_size'

# Query saturation rate from Analytics Engine
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query":"SELECT blob1, AVG(double3) AS sat_rate FROM hyperdrive_pool_metrics WHERE timestamp >= NOW() - INTERVAL '\''30'\'' MINUTE GROUP BY blob1"}'
```

## Related

- `connection-pool-monitoring.md`
- `d1-query-latency-histogram-analytics-engine.md`
- `d1-write-transaction-contention-monitoring.md`
- `workers-cpu-time-percentile-analytics-engine.md`
- `distributed-tracing-workers-d1-durable-objects-otel.md`

## Sources

- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/configuration/connect-to-postgres/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/performance/
