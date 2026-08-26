# KV Operation Rate Monitoring with Analytics Engine

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Workers KV namespaces have per-account write limits (1 write/s per key globally) and read limits that scale with plan tier. Burst traffic or fan-out write patterns silently hit these limits and return `429 Too Many Requests` errors, causing cache-miss storms or stale data reads. You need a real-time operation rate dashboard segmented by namespace and operation type before throttling events cause user-visible failures.

## Context

Workers KV does not expose operation counters in the dashboard with sub-minute granularity. Operation rates must be tracked at the application layer by wrapping KV bindings in a thin instrumentation proxy that writes to Analytics Engine on every call. Because KV operations are synchronous from the Worker's perspective, wrapping them adds negligible overhead.

## 1. KV Instrumentation Proxy

```typescript
// src/kv-instrumented.ts
export interface KvMetricsEnv {
  KV_OPS: AnalyticsEngineDataset;
}

type KvOperation = "get" | "put" | "delete" | "list";

export class InstrumentedKV {
  private readonly ns: KVNamespace;
  private readonly nsName: string;
  private readonly metrics: AnalyticsEngineDataset;

  constructor(ns: KVNamespace, nsName: string, metrics: AnalyticsEngineDataset) {
    this.ns = ns;
    this.nsName = nsName;
    this.metrics = metrics;
  }

  private record(op: KvOperation, durationMs: number, hit: boolean, error: boolean): void {
    this.metrics.writeDataPoint({
      blobs: [this.nsName, op, hit ? "hit" : "miss", error ? "error" : "ok"],
      doubles: [durationMs, 1],
      indexes: [this.nsName],
    });
  }

  async get(key: string, options?: KVNamespaceGetOptions<"text">): Promise<string | null> {
    const start = Date.now();
    let result: string | null = null;
    let error = false;
    try {
      result = await this.ns.get(key, options as KVNamespaceGetOptions<"text">);
      return result;
    } catch (err) {
      error = true;
      throw err;
    } finally {
      this.record("get", Date.now() - start, result !== null, error);
    }
  }

  async put(key: string, value: string, options?: KVNamespacePutOptions): Promise<void> {
    const start = Date.now();
    let error = false;
    try {
      await this.ns.put(key, value, options);
    } catch (err) {
      error = true;
      throw err;
    } finally {
      this.record("put", Date.now() - start, false, error);
    }
  }

  async delete(key: string): Promise<void> {
    const start = Date.now();
    let error = false;
    try {
      await this.ns.delete(key);
    } catch (err) {
      error = true;
      throw err;
    } finally {
      this.record("delete", Date.now() - start, false, error);
    }
  }

  async list(options?: KVNamespaceListOptions): Promise<KVNamespaceListResult<unknown>> {
    const start = Date.now();
    let error = false;
    try {
      return await this.ns.list(options);
    } catch (err) {
      error = true;
      throw err;
    } finally {
      this.record("list", Date.now() - start, false, error);
    }
  }
}
```

## 2. Usage in the Worker

```typescript
// src/index.ts
import { InstrumentedKV } from "./kv-instrumented";

export interface Env {
  SESSION_KV: KVNamespace;
  CONFIG_KV: KVNamespace;
  KV_OPS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const sessionKv = new InstrumentedKV(env.SESSION_KV, "session", env.KV_OPS);
    const configKv = new InstrumentedKV(env.CONFIG_KV, "config", env.KV_OPS);

    const sessionId = request.headers.get("x-session-id") ?? "";
    const [session, config] = await Promise.all([
      sessionKv.get(sessionId),
      configKv.get("global"),
    ]);

    return Response.json({ hasSession: session !== null, config });
  },
} satisfies ExportedHandler<Env>;
```

## 3. wrangler.toml Bindings

```toml
[[kv_namespaces]]
binding = "SESSION_KV"
id = "<SESSION_KV_ID>"

[[kv_namespaces]]
binding = "CONFIG_KV"
id = "<CONFIG_KV_ID>"

[[analytics_engine_datasets]]
binding = "KV_OPS"
dataset = "kv_operation_rate"
```

## 4. Query Operation Rates and Hit Rates

```typescript
// src/kv-query.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

export async function fetchKvRates(): Promise<void> {
  const sql = `
    SELECT
      toStartOfInterval(timestamp, INTERVAL '1' MINUTE) AS ts,
      blob1 AS namespace,
      blob2 AS operation,
      countIf(blob3 = 'hit') AS hits,
      countIf(blob3 = 'miss') AS misses,
      countIf(blob4 = 'error') AS errors,
      count() AS total_ops,
      avg(double1) AS avg_latency_ms
    FROM kv_operation_rate
    WHERE timestamp > now() - INTERVAL '30' MINUTE
    GROUP BY ts, namespace, operation
    ORDER BY ts ASC, namespace, operation
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  console.log(JSON.stringify(await resp.json(), null, 2));
}
```

## 5. Alert on Error Rate or Write Rate Spike

```typescript
// src/kv-alert.ts
const WRITE_RATE_WARN_PER_MIN = 50;   // warns before approaching 1/s per-key limit
const ERROR_RATE_THRESHOLD = 0.01;    // 1 % error rate

interface KvRow {
  namespace: string;
  operation: string;
  errors: number;
  total_ops: number;
}

export async function alertOnKvAnomaly(
  webhookUrl: string,
  rows: KvRow[]
): Promise<void> {
  const lines: string[] = [];

  for (const row of rows) {
    const errorRate = row.total_ops > 0 ? row.errors / row.total_ops : 0;
    if (errorRate > ERROR_RATE_THRESHOLD) {
      lines.push(
        `KV error: ${row.namespace}.${row.operation} error_rate=${(errorRate * 100).toFixed(2)}%`
      );
    }
    if (row.operation === "put" && row.total_ops > WRITE_RATE_WARN_PER_MIN) {
      lines.push(
        `KV write spike: ${row.namespace} put_ops/min=${row.total_ops}`
      );
    }
  }

  if (lines.length === 0) return;

  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: `KV anomaly detected:\n${lines.join("\n")}` }),
  });
}
```

## 6. Cache Hit Rate Trend Query

```sql
SELECT
  blob1 AS namespace,
  sum(hits) / (sum(hits) + sum(misses)) AS hit_rate,
  sum(total_ops) AS ops
FROM (
  SELECT
    blob1,
    countIf(blob3 = 'hit') AS hits,
    countIf(blob3 = 'miss') AS misses,
    count() AS total_ops
  FROM kv_operation_rate
  WHERE timestamp > now() - INTERVAL '1' HOUR
    AND blob2 = 'get'
  GROUP BY blob1
)
GROUP BY namespace
ORDER BY hit_rate ASC
```

## Anti-patterns

- **Wrapping only `get` calls**: write throttles manifest on `put` and `delete`; instrument all four operation types.
- **Logging every KV key as a blob**: key names can be PII or high-cardinality; log only namespace and operation type.
- **Treating a miss as an error**: KV returns `null` for cache misses without throwing; the hit/miss blob tracks this separately from network errors.
- **Instrumenting inside a Tail Worker**: KV operations inside a Tail Worker are not reported to the same Tail Worker (circular); instrument at the application layer instead.

## Gotchas

- KV `get` with a TTL-expired key returns `null` and counts as a miss; this is indistinguishable from a key that was never written.
- Workers KV read operations in edge caches are extremely fast (<1 ms); the recorded latency includes serialisation and binding overhead, not true network latency.
- The `list` operation can be slow for large namespaces; its latency outlier will skew p99 if mixed with `get` latencies in a single aggregation.
- Analytics Engine write rate is capped per dataset; high-traffic Workers should sample KV metrics (e.g. write 1 in 10 data points) to stay within limits.

## Verification

1. Deploy the Worker and make 100 `get` requests, half with keys that exist, half without.
2. Query Analytics Engine and confirm `hits ≈ 50` and `misses ≈ 50` for the namespace.
3. Make 60 `put` calls in one minute, confirm the write spike alert fires.
4. Introduce a `throw new Error("simulated")` in the proxy and confirm `errors > 0` appears in the query.

## Related

- `workers-kv-latency-consistency-monitoring.md`
- `cache-hit-rate-monitoring.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `analytics-engine-write-limits-and-backpressure.md`
- `analytics-engine-sql-api-programmatic-querying.md`

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/kv/api/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/kv/platform/limits/
