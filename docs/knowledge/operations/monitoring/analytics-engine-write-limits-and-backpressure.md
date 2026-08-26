# Analytics Engine Write Limits and Backpressure

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Custom metrics written via `env.AE.writeDataPoint()` silently disappear under burst traffic because the Analytics Engine dataset exceeds per-Worker or per-account write limits, leaving dashboards with unexpected gaps.

## Context
Analytics Engine (AE) imposes hard limits: 25 doubles and 25 blobs per data point, each blob at most 1 KB, and a maximum of 25 `writeDataPoint` calls per Worker invocation. Exceeding these limits causes the call to be silently dropped — no exception is thrown. At high request rates the aggregate throughput limit (varies by plan) can also be hit, dropping entire batches without any error surface.

## Understanding the Limits

| Dimension | Limit |
|---|---|
| Doubles per data point | 25 |
| Blobs per data point | 25 |
| Blob size | 1 024 bytes |
| `writeDataPoint` calls per invocation | 25 |
| Index (blob[0]) max length | 96 bytes |

Design schemas upfront — you cannot alter a dataset's double/blob slot assignments after the first write without creating a new dataset.

```typescript
// src/ae-schema.ts — centralise slot assignments
export const SCHEMA = {
  doubles: {
    latencyMs:    0,
    statusCode:   1,
    cpuTimeUs:    2,
    requestBytes: 3,
    responseBytes:4,
  },
  blobs: {
    // blob[0] is the "index" — keep it short and high-cardinality
    requestId:   0,
    route:       1,
    country:     2,
    scriptName:  3,
    outcome:     4,
  },
} as const;
```

## Safe writeDataPoint Wrapper

Wrap `writeDataPoint` to validate the payload before calling the binding, logging a warning on violation instead of silently dropping.

```typescript
// src/ae-writer.ts
import { SCHEMA } from './ae-schema';

interface DataPoint {
  doubles: Partial<Record<keyof typeof SCHEMA['doubles'], number>>;
  blobs:   Partial<Record<keyof typeof SCHEMA['blobs'],   string>>;
}

export function writeMetric(
  ae: AnalyticsEngineDataset,
  point: DataPoint,
  logger: Console = console,
): void {
  const doubles = new Array<number>(25).fill(0);
  const blobs   = new Array<string>(25).fill('');

  for (const [key, val] of Object.entries(point.doubles)) {
    doubles[SCHEMA.doubles[key as keyof typeof SCHEMA['doubles']]] = val ?? 0;
  }

  for (const [key, val] of Object.entries(point.blobs)) {
    const slot = SCHEMA.blobs[key as keyof typeof SCHEMA['blobs']];
    const truncated = (val ?? '').slice(0, slot === 0 ? 96 : 1024);
    if (truncated !== val) {
      logger.warn(`ae-writer: blob "${key}" truncated from ${val?.length} to ${truncated.length} bytes`);
    }
    blobs[slot] = truncated;
  }

  ae.writeDataPoint({ doubles, blobs, indexes: [blobs[0]] });
}
```

## Invocation-level Budget Tracking

Workers reset the 25-call counter per invocation. Track usage so you never silently exceed the cap in a hot path.

```typescript
// src/ae-budget.ts
export class AEBudget {
  private used = 0;
  private readonly cap: number;

  constructor(cap = 25) { this.cap = cap; }

  canWrite(): boolean { return this.used < this.cap; }

  write(ae: AnalyticsEngineDataset, point: AnalyticsEngineDataPoint): void {
    if (!this.canWrite()) {
      console.warn(`ae-budget: write limit (${this.cap}) reached, dropping data point`);
      return;
    }
    ae.writeDataPoint(point);
    this.used++;
  }

  get remaining(): number { return this.cap - this.used; }
}

// usage in a Worker handler
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const budget = new AEBudget();
    // ... handle request
    budget.write(env.AE, { doubles: [Date.now()], blobs: [req.url], indexes: [req.url] });
    return new Response('ok');
  },
} satisfies ExportedHandler<Env>;
```

## Fallback to Logpush on Budget Exhaustion

When the AE budget is exhausted, buffer remaining telemetry in a KV side-channel or emit a structured log line captured by Logpush.

```typescript
// src/ae-with-fallback.ts
export async function writeWithFallback(
  ae: AnalyticsEngineDataset,
  budget: AEBudget,
  point: AnalyticsEngineDataPoint,
  ctx: ExecutionContext,
): Promise<void> {
  if (budget.canWrite()) {
    budget.write(ae, point);
  } else {
    // structured log line picked up by Logpush workers_trace_events
    console.log(JSON.stringify({
      type: 'ae_overflow',
      doubles: point.doubles,
      blobs: point.blobs,
    }));
  }
}
```

## Detecting Silent Drops via a Canary Dataset

Write a monotonically increasing counter to a dedicated `canary` dataset from every request. Query AE SQL API to detect gaps.

```typescript
// src/ae-canary.ts
let seq = 0;

export function writeCanary(ae: AnalyticsEngineDataset): void {
  ae.writeDataPoint({
    doubles: [++seq, Date.now()],
    blobs:   ['canary'],
    indexes: ['canary'],
  });
}
```

```sql
-- AE SQL API: detect minutes with below-expected canary writes
SELECT
  toStartOfMinute(timestamp)  AS minute,
  count()                     AS writes
FROM canary
WHERE timestamp > now() - INTERVAL '1' HOUR
GROUP BY minute
HAVING writes < 50   -- tune to expected RPS
ORDER BY minute;
```

## Anti-patterns
- Putting high-cardinality values (UUIDs, full URLs) in `blob[0]` (the index) — the 96-byte limit truncates them silently and skews index-based queries
- Writing a new data point per sub-operation within a single request — batch measurements into one data point per request
- Ignoring the 25-call-per-invocation cap in Durable Object alarm handlers — alarms count as invocations
- Storing metric schema in Workers KV and reading it per-request — embed the schema as a constant to avoid KV latency

## Gotchas
- `writeDataPoint` never throws — violations are always silent; wrap and validate
- AE datasets are per-account, not per-Worker; high-traffic Workers on the same account share the aggregate throughput budget
- The SQL API only exposes data with a ~1-minute lag; use Tail Workers for real-time alerting
- Changing which slot a double or blob occupies without migrating the dataset corrupts historical queries

## Verification
1. Deploy the canary write and query the SQL API after 5 minutes: `SELECT count() FROM canary WHERE timestamp > now() - INTERVAL '5' MINUTE`
2. Intentionally exceed 25 calls in a test invocation and verify the warning log appears via `wrangler tail`
3. Send a blob longer than 96 bytes as the index field; confirm the truncation warning is emitted and query by the truncated value succeeds

## Related
- [cloudflare-analytics-engine.md](cloudflare-analytics-engine.md)
- [cloudflare-analytics-engine-custom-metrics.md](cloudflare-analytics-engine-custom-metrics.md)
- [analytics-engine-sql-api-programmatic-querying.md](analytics-engine-sql-api-programmatic-querying.md)
- [workers-tail-real-time-log-streaming.md](workers-tail-real-time-log-streaming.md)

## Sources
- https://developers.cloudflare.com/analytics/analytics-engine/limits/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/get-started/
