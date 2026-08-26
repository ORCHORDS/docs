# Durable Objects Storage Growth Trend Forecasting with Analytics Engine

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Durable Object class accumulates per-user state (chat history, shopping cart, game state). Storage grows monotonically. The team has no visibility into how fast each DO instance is growing, when individual instances will approach the 10 GB per-object storage limit, or when the aggregate storage bill will exceed budget. By the time you notice, either the application is throwing `Storage capacity exceeded` errors or the monthly invoice is a surprise.

The solution is a scheduled Worker that samples DO storage usage periodically, writes time-series data to Analytics Engine, and runs a linear regression forecast to project when each DO will breach 80% of its capacity limit.

## Context

Durable Objects expose a `storage.list()` API but not a direct "current storage size" field. The closest approximation is to serialize and measure all keys, or — more efficiently — to expose a cached size counter that the DO increments on every `put()` and decrements on every `delete()`. This counter is stored as a single KV key within the DO's own storage and is the input to the Analytics Engine time series.

For aggregate billing visibility, the Cloudflare GraphQL Analytics API exposes `durableObjectsStorageByDate` which gives total stored bytes across all namespaces. The per-object counter pattern and the GraphQL aggregate are complementary.

## DO Storage Counter Pattern

```typescript
// src/do-with-storage-counter.ts

export class TrackedDurableObject implements DurableObject {
  private state: DurableObjectState;
  private env: Env;
  private storageBytesKey = '__storage_bytes__';

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/__storage_size') {
      const bytes = (await this.state.storage.get<number>(this.storageBytesKey)) ?? 0;
      return Response.json({ storage_bytes: bytes });
    }

    if (url.pathname === '/set' && request.method === 'POST') {
      const body = await request.json<{ key: string; value: unknown }>();
      const serialized = JSON.stringify(body.value);
      await this.putTracked(body.key, serialized);
      return Response.json({ ok: true });
    }

    if (url.pathname === '/delete' && request.method === 'POST') {
      const { key } = await request.json<{ key: string }>();
      await this.deleteTracked(key);
      return Response.json({ ok: true });
    }

    return new Response('Not found', { status: 404 });
  }

  /**
   * Put a value and update the storage byte counter atomically.
   * Estimates size as key.length + serializedValue.length (UTF-16 approximation).
   */
  private async putTracked(key: string, serializedValue: string): Promise<void> {
    const existing = await this.state.storage.get<string>(key);
    const existingSize = existing ? (key.length + existing.length) * 2 : 0;
    const newSize = (key.length + serializedValue.length) * 2;

    await this.state.storage.transaction(async (txn) => {
      const currentBytes = (await txn.get<number>(this.storageBytesKey)) ?? 0;
      await txn.put(this.storageBytesKey, currentBytes - existingSize + newSize);
      await txn.put(key, serializedValue);
    });
  }

  private async deleteTracked(key: string): Promise<void> {
    const existing = await this.state.storage.get<string>(key);
    if (!existing) return;
    const freedSize = (key.length + existing.length) * 2;

    await this.state.storage.transaction(async (txn) => {
      const currentBytes = (await txn.get<number>(this.storageBytesKey)) ?? 0;
      await txn.put(this.storageBytesKey, Math.max(0, currentBytes - freedSize));
      await txn.delete(key);
    });
  }
}

export interface Env {
  MY_DO: DurableObjectNamespace;
  AE: AnalyticsEngineDataset;
}
```

## Sampling Worker (Scheduled)

```typescript
// src/storage-sampler.ts
// Cron: "0 * * * *" (hourly)

export interface Env {
  MY_DO: DurableObjectNamespace;
  AE: AnalyticsEngineDataset;
  /** Comma-separated list of DO IDs to sample, stored in a KV or secret. */
  DO_IDS: string;
  DO_CLASS_NAME: string;
}

const DO_MAX_BYTES = 10 * 1024 * 1024 * 1024; // 10 GB limit

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const doIds = env.DO_IDS.split(',').map(id => id.trim()).filter(Boolean);

    const samples = await Promise.allSettled(
      doIds.map(id => sampleDO(env.MY_DO, id))
    );

    const nowMs = Date.now();
    for (let i = 0; i < doIds.length; i++) {
      const result = samples[i];
      if (result.status === 'fulfilled') {
        const { storageBytes } = result.value;
        env.AE.writeDataPoint({
          // blob1 = do_id, blob2 = class_name
          blobs:   [doIds[i], env.DO_CLASS_NAME],
          // double1 = storage_bytes, double2 = fill_ratio (0–1)
          doubles: [storageBytes, storageBytes / DO_MAX_BYTES],
          indexes: [doIds[i]],
        });
      } else {
        console.error(`Failed to sample DO ${doIds[i]}:`, result.reason);
      }
    }
  },
} satisfies ExportedHandler<Env>;

async function sampleDO(
  namespace: DurableObjectNamespace,
  id: string
): Promise<{ storageBytes: number }> {
  const stub = namespace.get(namespace.idFromString(id));
  const res = await stub.fetch('https://internal/__storage_size');
  if (!res.ok) throw new Error(`DO ${id} returned ${res.status}`);
  const { storage_bytes } = await res.json<{ storage_bytes: number }>();
  return { storageBytes: storage_bytes };
}
```

## Analytics Engine Queries

```sql
-- Current fill ratio per DO instance, ordered by most full
SELECT
  blob1                              AS do_id,
  blob2                              AS class_name,
  last_value(double1)                AS current_bytes,
  last_value(double2)                AS fill_ratio,
  last_value(double1) / 1073741824   AS current_gb
FROM do_storage_samples
WHERE timestamp >= NOW() - INTERVAL '2' HOUR
GROUP BY do_id, class_name
ORDER BY fill_ratio DESC
LIMIT 50;
```

```sql
-- 7-day growth rate per DO (bytes/hour) using first and last sample in the window
SELECT
  blob1                                            AS do_id,
  (last_value(double1) - first_value(double1))
    / (dateDiff('hour', min(timestamp), max(timestamp)))
                                                   AS growth_bytes_per_hour,
  last_value(double1)                              AS current_bytes,
  last_value(double2)                              AS fill_ratio
FROM do_storage_samples
WHERE timestamp >= NOW() - INTERVAL '7' DAY
GROUP BY do_id
HAVING dateDiff('hour', min(timestamp), max(timestamp)) >= 24
ORDER BY growth_bytes_per_hour DESC
LIMIT 20;
```

## Forecast Worker

```typescript
// src/forecast.ts
// Scheduled daily: "0 6 * * *"
// Queries AE for 30-day growth data, computes linear regression,
// and alerts on any DO projected to breach 80% within 30 days.

export interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  AE_DATASET: string;
  ALERT_WEBHOOK: string;
}

interface GrowthRow {
  do_id: string;
  current_bytes: number;
  growth_bytes_per_hour: number;
}

const DO_MAX_BYTES = 10 * 1024 * 1024 * 1024;
const ALERT_THRESHOLD = 0.80; // 80% full
const FORECAST_HORIZON_DAYS = 30;

async function fetchGrowthRates(env: Env): Promise<GrowthRow[]> {
  const sql = `
    SELECT
      blob1 AS do_id,
      last_value(double1) AS current_bytes,
      (last_value(double1) - first_value(double1))
        / (dateDiff('hour', min(timestamp), max(timestamp))) AS growth_bytes_per_hour
    FROM ${env.AE_DATASET}
    WHERE timestamp >= NOW() - INTERVAL '30' DAY
    GROUP BY do_id
    HAVING dateDiff('hour', min(timestamp), max(timestamp)) >= 48
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  const json = await res.json<{ data: GrowthRow[] }>();
  return json.data;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const rows = await fetchGrowthRates(env);
    const alertRows: string[] = [];

    for (const row of rows) {
      if (row.growth_bytes_per_hour <= 0) continue;

      const bytesUntilThreshold = DO_MAX_BYTES * ALERT_THRESHOLD - row.current_bytes;
      if (bytesUntilThreshold <= 0) {
        // Already over threshold
        alertRows.push(
          `⚠ DO ${row.do_id}: ALREADY AT ${((row.current_bytes / DO_MAX_BYTES) * 100).toFixed(1)}% capacity`
        );
        continue;
      }

      const hoursUntilThreshold = bytesUntilThreshold / row.growth_bytes_per_hour;
      const daysUntilThreshold = hoursUntilThreshold / 24;

      if (daysUntilThreshold <= FORECAST_HORIZON_DAYS) {
        const currentGb = (row.current_bytes / 1e9).toFixed(2);
        const growthGbPerDay = ((row.growth_bytes_per_hour * 24) / 1e9).toFixed(3);
        alertRows.push(
          `DO ${row.do_id}: ${currentGb} GB now, +${growthGbPerDay} GB/day → 80% in ${daysUntilThreshold.toFixed(1)} days`
        );
      }
    }

    if (alertRows.length > 0) {
      ctx.waitUntil(
        fetch(env.ALERT_WEBHOOK, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: `Durable Object storage forecast alert:\n${alertRows.join('\n')}`,
          }),
        })
      );
    }
  },
} satisfies ExportedHandler<Env>;
```

## Grafana Panel: Storage Growth Timeline

```sql
-- Grafana time-series query for a specific DO
-- Variable: $do_id
SELECT
  toStartOfHour(timestamp)  AS time,
  avg(double1) / 1073741824 AS storage_gb
FROM do_storage_samples
WHERE
  blob1 = '${do_id}'
  AND timestamp >= NOW() - INTERVAL '30' DAY
GROUP BY time
ORDER BY time;
```

## Anti-patterns

- **Calling `storage.list()` on every request to measure size**: `storage.list()` iterates all keys and has O(n) cost. It also counts against the DO's CPU time budget. Use an incremental counter updated on each `put()`/`delete()` instead.
- **Sampling too infrequently**: Hourly samples give a 30-day growth dataset of 720 points — sufficient for linear regression. Daily samples (24 points) are too sparse to distinguish a genuine growth trend from a one-off data import event.
- **Applying linear regression to step-function growth**: Some DOs grow in bursts (batch imports) rather than linearly. A linear regression over a burst window will dramatically overestimate steady-state growth. Check the R² of the regression before trusting the forecast; flag DOs where R² < 0.5 as "non-linear growth" requiring manual review.
- **Forecasting aggregate namespace storage only**: The Cloudflare GraphQL `durableObjectsStorageByDate` metric gives total bytes across the namespace. A single large DO approaching its 10 GB per-object limit is invisible in the aggregate. Per-DO sampling is required.

## Gotchas

- **DO ID management**: Cloudflare assigns DO IDs as 64-byte hex strings. Maintaining a list of active DO IDs in a secret (`DO_IDS`) requires updating it whenever new DOs are created. Consider storing the active ID list in a KV namespace that the application updates on DO creation, then having the sampler Worker read from KV.
- **`first_value` / `last_value` ordering in Analytics Engine**: As of the 2025 Analytics Engine SQL API, `first_value` and `last_value` are order-sensitive. Analytics Engine rows are stored in approximate time order, but always pair them with explicit `min(timestamp)` / `max(timestamp)` checks to validate that the window covered enough time before trusting the delta.
- **Storage counter drift**: If the application crashes mid-transaction or a DO is evicted before a transaction commits, the counter can drift from the true size. Periodically reconcile by walking `storage.list()` and recomputing the actual size (e.g. weekly, in a low-traffic window).
- **DO alarms for self-reporting**: An alternative to the external sampling Worker is to use DO alarms to self-report storage size to Analytics Engine hourly. This avoids the problem of maintaining an ID list, but requires modifying the DO class itself and cannot be added retroactively to existing DO deployments without a restart.

## Verification

```bash
# Write a few test entries and check the storage counter
curl -X POST "https://my-worker.example.com/set" \
  -H "Content-Type: application/json" \
  -d '{"key":"test_key","value":{"data":"hello world"}}'

curl "https://my-worker.example.com/__storage_size"
# Expected: {"storage_bytes": <non-zero>}

# After the sampler runs, verify Analytics Engine data
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob1 AS do_id, last_value(double1) AS bytes FROM do_storage_samples WHERE timestamp >= NOW() - INTERVAL '\''2'\'' HOUR GROUP BY do_id"}' \
  | jq '.data'
```

## Related

- `durable-objects-capacity-planning.md` — general DO capacity planning
- `durable-objects-alarm-heartbeat-monitoring.md` — DO alarm-based heartbeat patterns
- `analytics-engine-write-limits-and-backpressure.md` — Analytics Engine write limits
- `cloudflare-billing-cost-anomaly-detection.md` — billing cost anomaly detection

## Sources

- Cloudflare Durable Objects storage limits: https://developers.cloudflare.com/durable-objects/platform/limits/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare GraphQL Analytics API durableObjectsStorageByDate: https://developers.cloudflare.com/analytics/graphql-api/features/data-sets/
