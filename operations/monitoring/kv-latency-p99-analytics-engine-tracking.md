# KV Operation Latency p99 Analytics Engine Tracking

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Workers that depend on KV for configuration or cache warming start experiencing
elevated tail latency — p99 GET times rise from ~10 ms to 200 ms+ — but
Workers Metrics only exposes aggregate CPU time, not per-KV-operation latency.
You need per-key-namespace, per-operation-type (get/put/delete/list) p50 and
p99 latency tracked in Analytics Engine so you can alert on regressions and
correlate KV slowdowns with Worker response time degradation.

---

## Context

Cloudflare KV is eventually consistent and globally distributed. Latency
characteristics depend on:

- **Cache hit on the serving colo** — typically 1–10 ms.
- **Regional cache miss** — round-trip to the nearest edge PoP with cached
  state — typically 30–80 ms.
- **Global miss** — round-trip to the central store — 100–300 ms.

None of these tiers expose latency metrics out of the box. The only way to
track KV operation latency is to instrument your Worker: wrap each KV call
in a `performance.now()` pair and emit `writeDataPoint` to Analytics Engine.

Analytics Engine's `quantile()` aggregation (available in the SQL API) can
then answer p50/p99 queries across any namespace, key prefix, or colo.

---

## Instrumentation Pattern

### wrangler.toml

```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

kv_namespaces = [
  { binding = "CONFIG", id = "abc123..." }
]

[[analytics_engine_datasets]]
binding = "KV_METRICS"
dataset = "kv_latency"
```

### src/kv-instrumented.ts

```typescript
export interface Env {
  CONFIG: KVNamespace;
  KV_METRICS: AnalyticsEngineDataset;
}

type KVOperation = "get" | "put" | "delete" | "list";

/**
 * Wraps a KV call, measures wall-clock duration, and emits a datapoint.
 * Returns the KV result unchanged.
 */
export async function tracedKV<T>(
  namespace: KVNamespace,
  dataset: AnalyticsEngineDataset,
  namespaceName: string,
  op: KVOperation,
  fn: () => Promise<T>,
): Promise<T> {
  const start = performance.now();
  let outcome: "hit" | "miss" | "ok" | "error" = "ok";
  let result: T;

  try {
    result = await fn();
    // Distinguish cache hit vs miss for GET
    if (op === "get") {
      outcome = result === null ? "miss" : "hit";
    }
  } catch (err) {
    outcome = "error";
    dataset.writeDataPoint({
      blobs: [namespaceName, op, outcome, String(err)],
      doubles: [performance.now() - start],
      indexes: [namespaceName],
    });
    throw err;
  }

  dataset.writeDataPoint({
    blobs: [namespaceName, op, outcome, ""],
    doubles: [performance.now() - start],
    indexes: [namespaceName],
  });

  return result!;
}
```

### src/index.ts

```typescript
import { tracedKV } from "./kv-instrumented";

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const config = await tracedKV(
      env.CONFIG,
      env.KV_METRICS,
      "CONFIG",
      "get",
      () => env.CONFIG.get("feature-flags", "json"),
    );

    // ...business logic...

    await tracedKV(
      env.CONFIG,
      env.KV_METRICS,
      "CONFIG",
      "put",
      () => env.CONFIG.put("last-seen", new Date().toISOString()),
    );

    return new Response(JSON.stringify(config));
  },
};
```

---

## Analytics Engine Schema

Each `writeDataPoint` call uses the following layout:

| Field | Type | Value |
|-------|------|-------|
| `blob1` | string | KV namespace binding name |
| `blob2` | string | operation: `get` / `put` / `delete` / `list` |
| `blob3` | string | outcome: `hit` / `miss` / `ok` / `error` |
| `blob4` | string | error message (empty string on success) |
| `double1` | number | duration in milliseconds (float) |
| `index1` | string | namespace name (used for fast filtering) |

---

## SQL API Queries

### p50 and p99 GET latency per namespace, last 1 hour

```sql
SELECT
  blob1                          AS namespace,
  blob2                          AS operation,
  blob3                          AS outcome,
  quantileWeighted(0.5)(double1, 1)  AS p50_ms,
  quantileWeighted(0.99)(double1, 1) AS p99_ms,
  count()                        AS n
FROM kv_latency
WHERE
  timestamp > NOW() - INTERVAL '1' HOUR
  AND blob2 = 'get'
GROUP BY namespace, operation, outcome
ORDER BY p99_ms DESC
```

### Hourly p99 trend for alerting

```sql
SELECT
  toStartOfInterval(timestamp, INTERVAL '5' MINUTE) AS bucket,
  quantileWeighted(0.99)(double1, 1)                AS p99_ms,
  countIf(blob3 = 'miss')                            AS misses,
  count()                                             AS total
FROM kv_latency
WHERE
  timestamp > NOW() - INTERVAL '6' HOUR
  AND blob2 = 'get'
  AND blob1 = 'CONFIG'
GROUP BY bucket
ORDER BY bucket ASC
```

---

## Alerting: Workers Cron + Notifications

Poll Analytics Engine every 5 minutes with a Cron Worker and POST to a
Cloudflare Notification webhook when p99 exceeds a threshold.

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const sql = `
      SELECT quantileWeighted(0.99)(double1, 1) AS p99
      FROM   kv_latency
      WHERE  timestamp > NOW() - INTERVAL '5' MINUTE
        AND  blob2 = 'get'
    `;

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
        body: sql,
      },
    );

    const { data } = await res.json<{ data: Array<{ p99: number }> }>();
    const p99 = data[0]?.p99 ?? 0;

    if (p99 > 150) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `KV GET p99 latency is ${p99.toFixed(1)} ms (threshold 150 ms)`,
        }),
      });
    }
  },
};
```

---

## Anti-patterns

**Using `Date.now()` instead of `performance.now()`.**
`Date.now()` has 1 ms resolution; `performance.now()` has sub-millisecond
resolution and is monotonic within the isolate.

**Wrapping only GET and ignoring PUT/DELETE.**
PUT latency matters for write-heavy workflows like session stores. Instrument
all four operations.

**Emitting one datapoint per request aggregating all KV calls.**
Aggregate points hide per-call variance. Emit one datapoint per KV call so
you can compute true p99 across individual operations.

**Cardinality explosion on `index1` with per-key values.**
Never use the actual KV key as an index or blob if you have high key
cardinality. Use the namespace name only.

---

## Gotchas

- `performance.now()` resets to 0 at the start of each Worker invocation; it
  measures time elapsed within one request, not wall-clock time.
- Analytics Engine `quantileWeighted(p)(col, weight)` uses a t-digest; results
  are approximate (±1%) but accurate enough for alerting.
- KV operations inside a Tail Worker context do count toward the upstream
  Worker's KV limits if the Tail Worker uses its own bindings separately.
- The SQL API endpoint requires the **Account Analytics: Read** permission on
  the API token.

---

## Verification

1. Send 50+ requests to your Worker, mixing keys that exist and keys that
   don't.
2. Query the `kv_latency` dataset and confirm `blob3` shows both `hit` and
   `miss` rows.
3. Confirm `double1` values are in the millisecond range (not microseconds or
   seconds).
4. Run the p99 query; values < 10 ms indicate a local cache hit; values
   50–150 ms indicate a regional miss; values > 150 ms suggest a global miss
   or KV degradation.

---

## Related

- `kv-operation-rate-analytics-engine.md`
- `kv-stale-read-ratio-slo-analytics-engine.md`
- `analytics-engine-write-limits-and-backpressure.md`
- `workers-cpu-time-percentile-analytics-engine.md`

---

## Sources

- KV limits and caching tiers — https://developers.cloudflare.com/kv/platform/limits/
- Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Workers performance API — https://developers.cloudflare.com/workers/runtime-apis/performance/
