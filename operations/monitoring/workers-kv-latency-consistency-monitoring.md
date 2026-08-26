# Workers KV Latency and Consistency Monitoring

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A Cloudflare Worker reads feature flags or session tokens from KV and occasionally serves stale values seconds after a write, causing user-visible inconsistencies. In other cases, KV `get()` calls spike to 300 ms+ during high-traffic events, adding unacceptable latency to edge responses. Neither case surfaces in the default Cloudflare dashboard. You need per-operation latency histograms, staleness detection metrics, and error-rate tracking for KV operations emitted directly from your Worker.

---

## Context

Workers KV is an eventually consistent, globally replicated key-value store. Reads are served from the nearest PoP cache; writes propagate globally within ~60 seconds under normal conditions but can lag during incidents. The platform does not expose per-key propagation delay or per-PoP cache-hit ratio via any built-in dashboard — that data must be captured inside the Worker.

KV bindings do not throw on a cache miss (they return `null`); they throw on network errors or API limit exhaustion. Both cases must be tracked separately. KV metadata (`getWithMetadata`) adds a small overhead and is the mechanism by which staleness can be approximated: compare the `metadata.writtenAt` timestamp to `Date.now()`.

Analytics Engine is the right sink for high-cardinality per-request KV metrics because it is non-blocking, has no per-request write latency, and its SQL API supports time-series aggregation queries.

---

## Section 1: Wrapping KV Operations with Instrumentation

```typescript
// lib/kv-instrumented.ts
export interface KVMetrics {
  operation: "get" | "put" | "delete" | "list";
  key:        string;
  hitCache:   boolean;
  latencyMs:  number;
  error:       boolean;
  staleMs:    number; // ms since write; 0 if unknown
}

export interface KVWriteMetadata {
  writtenAt: number; // Unix ms
}

export async function kvGet<T>(
  namespace: KVNamespace,
  key:       string,
  ae:        AnalyticsEngineDataset,
): Promise<T | null> {
  const start = Date.now();
  let   error = false;
  let   staleMs = 0;
  let   hitCache = false;

  try {
    const { value, metadata } = await namespace.getWithMetadata<T, KVWriteMetadata>(
      key,
      { type: "json" }
    );

    hitCache = value !== null;

    if (metadata?.writtenAt) {
      staleMs = Date.now() - metadata.writtenAt;
    }

    return value;
  } catch (e) {
    error = true;
    console.error(JSON.stringify({ event: "kv_get_error", key, err: String(e) }));
    return null;
  } finally {
    const latencyMs = Date.now() - start;
    writeKVMetric(ae, { operation: "get", key, hitCache, latencyMs, error, staleMs });
  }
}

export async function kvPut<T>(
  namespace: KVNamespace,
  key:       string,
  value:     T,
  ae:        AnalyticsEngineDataset,
  ttl?:      number,
): Promise<void> {
  const start = Date.now();
  let   error = false;

  const metadata: KVWriteMetadata = { writtenAt: Date.now() };

  try {
    await namespace.put(key, JSON.stringify(value), {
      expirationTtl: ttl,
      metadata,
    });
  } catch (e) {
    error = true;
    console.error(JSON.stringify({ event: "kv_put_error", key, err: String(e) }));
    throw e;
  } finally {
    const latencyMs = Date.now() - start;
    writeKVMetric(ae, { operation: "put", key, hitCache: false, latencyMs, error, staleMs: 0 });
  }
}

function writeKVMetric(ae: AnalyticsEngineDataset, m: KVMetrics): void {
  ae.writeDataPoint({
    blobs:   [m.operation, m.key.slice(0, 64), m.hitCache ? "hit" : "miss", m.error ? "1" : "0"],
    doubles: [m.latencyMs, m.staleMs],
    indexes: ["kv_operation"],
  });
}
```

---

## Section 2: Integrating the Wrapper in a Worker

```typescript
// worker.ts
import { kvGet, kvPut } from "./lib/kv-instrumented";

export interface Env {
  FLAGS: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Read a feature flag
    const flag = await kvGet<{ enabled: boolean }>(
      env.FLAGS,
      "feature:dark-mode",
      env.ANALYTICS,
    );

    return Response.json({ darkMode: flag?.enabled ?? false });
  },
};
```

`wrangler.toml` bindings:

```toml
kv_namespaces = [
  { binding = "FLAGS", id = "YOUR_KV_NAMESPACE_ID" }
]

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "workers_kv_metrics"
```

---

## Section 3: SQL Queries for KV Latency Analysis

**p50 / p95 / p99 GET latency over the last hour, by key prefix:**

```sql
SELECT
  substring(blob2, 1, 20)                               AS key_prefix,
  quantileExact(0.50)(double1)                          AS p50_ms,
  quantileExact(0.95)(double1)                          AS p95_ms,
  quantileExact(0.99)(double1)                          AS p99_ms,
  countIf(blob4 = '1')                                  AS error_count,
  count()                                               AS total
FROM   workers_kv_metrics
WHERE  index1 = 'kv_operation'
  AND  blob1  = 'get'
  AND  timestamp > now() - INTERVAL '1' HOUR
GROUP  BY key_prefix
ORDER  BY p95_ms DESC
LIMIT  20
```

**Staleness distribution (seconds) for cache hits:**

```sql
SELECT
  blob2                                                 AS key,
  quantileExact(0.50)(double2 / 1000)                  AS p50_stale_s,
  quantileExact(0.95)(double2 / 1000)                  AS p95_stale_s,
  max(double2 / 1000)                                  AS max_stale_s,
  count()                                               AS reads
FROM   workers_kv_metrics
WHERE  index1 = 'kv_operation'
  AND  blob1  = 'get'
  AND  blob3  = 'hit'
  AND  double2 > 0
  AND  timestamp > now() - INTERVAL '15' MINUTE
GROUP  BY key
HAVING count() > 10
ORDER  BY max_stale_s DESC
LIMIT  20
```

**Error rate per 5-minute window:**

```sql
SELECT
  toStartOfFiveMinutes(timestamp)                       AS bucket,
  countIf(blob4 = '1') / count() * 100                 AS error_pct
FROM   workers_kv_metrics
WHERE  index1 = 'kv_operation'
  AND  timestamp > now() - INTERVAL '1' HOUR
GROUP  BY bucket
ORDER  BY bucket ASC
```

---

## Section 4: Grafana Dashboard Setup

Create a Grafana dashboard using the Cloudflare Analytics Engine data source (configured per `cloudflare-analytics-engine-grafana-dashboard.md`).

**Recommended panels:**

| Panel | Type | Query metric |
|---|---|---|
| KV GET p95 latency | Time series | `p95_ms` from Section 3 query 1 |
| KV staleness p95 | Stat | `p95_stale_s` from query 2, threshold ≥ 30 s = red |
| KV error rate % | Bar gauge | `error_pct` from query 3, threshold ≥ 1 % = yellow, ≥ 5 % = red |
| Cache hit ratio | Stat | `countIf(blob3='hit') / count()` |
| Slowest keys | Table | Top 10 by `p99_ms` |

Set the dashboard refresh to 1 minute. Add a template variable `$namespace` bound to `blob2` prefix to filter by key group.

---

## Section 5: Alerting on KV Degradation

Use a Grafana alert rule to page when p95 GET latency exceeds 200 ms over a 5-minute window:

```yaml
# grafana/provisioning/alerts/kv-latency.yaml
apiVersion: 1
groups:
  - name: kv-latency
    folder: Workers
    interval: 1m
    rules:
      - uid: kv-p95-latency-high
        title: "KV GET p95 Latency > 200ms"
        condition: C
        data:
          - refId: A
            datasourceUid: cloudflare-ae
            model:
              rawSql: |
                SELECT quantileExact(0.95)(double1) AS p95
                FROM   workers_kv_metrics
                WHERE  index1 = 'kv_operation'
                  AND  blob1  = 'get'
                  AND  timestamp > now() - INTERVAL '5' MINUTE
          - refId: C
            datasourceUid: __expr__
            model:
              type: threshold
              conditions:
                - evaluator: { type: gt, params: [200] }
                  query:     { params: [A] }
        noDataState: OK
        execErrState: Alerting
        for: 5m
```

For staleness alerts, fire when `p95_stale_s > 120` (2 minutes beyond expected propagation):

```yaml
      - uid: kv-staleness-high
        title: "KV Staleness p95 > 120s"
        condition: C
        data:
          - refId: A
            datasourceUid: cloudflare-ae
            model:
              rawSql: |
                SELECT quantileExact(0.95)(double2 / 1000) AS p95_stale
                FROM   workers_kv_metrics
                WHERE  index1 = 'kv_operation'
                  AND  blob1  = 'get'
                  AND  blob3  = 'hit'
                  AND  double2 > 0
                  AND  timestamp > now() - INTERVAL '5' MINUTE
          - refId: C
            datasourceUid: __expr__
            model:
              type: threshold
              conditions:
                - evaluator: { type: gt, params: [120] }
                  query:     { params: [A] }
```

---

## Section 6: Detecting KV Propagation Lag During Deploys

After a KV write (e.g., a configuration deploy), poll a canary endpoint from a Cloudflare Scheduled Worker across multiple regions and track `staleMs` until it reaches 0:

```typescript
// propagation-check-worker.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Write a sentinel key with a known timestamp
    const sentinel = { writtenAt: Date.now(), build: env.BUILD_ID };
    await env.FLAGS.put("deploy:sentinel", JSON.stringify(sentinel), {
      expirationTtl: 300,
      metadata: { writtenAt: sentinel.writtenAt },
    });

    // Read it back; staleMs > 0 means the local PoP has not yet seen the write
    const { value, metadata } = await env.FLAGS.getWithMetadata<typeof sentinel, { writtenAt: number }>(
      "deploy:sentinel",
      { type: "json" }
    );

    const staleMs = metadata?.writtenAt ? Date.now() - metadata.writtenAt : -1;

    env.ANALYTICS.writeDataPoint({
      blobs:   ["kv_propagation", env.CF_REGION ?? "unknown"],
      doubles: [staleMs],
      indexes: ["kv_propagation"],
    });
  },
};
```

---

## Anti-patterns

- **Using `get()` without `getWithMetadata()` when staleness tracking is required** — `get()` returns the value only; you cannot compute staleness without the `writtenAt` metadata written at put-time.
- **Logging every KV key verbatim in high-cardinality namespaces** — storing full keys as blobs with millions of unique values will exhaust Analytics Engine cardinality limits. Truncate or hash keys (`key.slice(0, 64)` or a prefix group).
- **Treating a `null` return as an error** — KV returns `null` for a cache miss, not for an error. Track them as separate metrics (`hitCache = false` vs. `error = true`).
- **Wrapping every single KV call individually without batching metrics** — Analytics Engine `writeDataPoint` is non-blocking but still adds minor overhead. Batch metrics for bulk KV operations (e.g., `list()` + multiple `get()` calls) with a single summary datapoint.
- **Alerting on absolute latency without accounting for cold start** — a freshly cold-started Worker's first KV read may be slower due to connection setup. Use `p95` over a 5-minute window rather than per-request threshold alerts.

---

## Gotchas

- `getWithMetadata()` returns `{ value: null, metadata: null }` on a miss — both fields are `null`, not thrown.
- KV `put()` is acknowledged as soon as it reaches the primary datacenter; global propagation is async. `staleMs > 0` on a read immediately after a write is expected and not necessarily an error.
- The `metadata` field in `put()` must be a JSON-serializable object. Storing a `Date` object will fail silently (dates serialize to strings in JSON but only if the serialization path handles it explicitly).
- Analytics Engine has a limit of 20 blobs, 20 doubles, and 1 index per `writeDataPoint` call. Exceeding limits silently drops the excess fields.
- KV list operations return up to 1000 keys per call; each call counts as a separate KV operation for billing and should be instrumented separately.

---

## Verification

1. Deploy the instrumented Worker and trigger several `get()` and `put()` calls.
2. Query the Analytics Engine SQL API and confirm `workers_kv_metrics` rows appear with correct `blob1 = 'get'`, latency values in `double1`, and `double2 > 0` for reads following a write.
3. Introduce a deliberate KV error (e.g., invalid namespace binding) and verify `blob4 = '1'` appears in the dataset.
4. Deploy the propagation check Scheduled Worker with a 1-minute cron and confirm `kv_propagation` rows show decreasing `double1` (staleMs approaching 0) within 60 seconds.
5. Trigger the Grafana alert by simulating a slow KV operation (test harness returning a delayed response via a mocked binding in a staging environment).

---

## Related

- `cloudflare-analytics-engine-custom-metrics.md`
- `cloudflare-analytics-engine-grafana-dashboard.md`
- `workers-tail-real-time-log-streaming.md`
- `cold-start-latency-monitoring.md`
- `feature-flag-impact-monitoring.md`

---

## Sources

- Workers KV API reference: https://developers.cloudflare.com/kv/api/
- KV `getWithMetadata`: https://developers.cloudflare.com/kv/api/read-key-value-pairs/#metadata
- Analytics Engine `writeDataPoint`: https://developers.cloudflare.com/analytics/analytics-engine/worker-binding-api/
- KV Limits: https://developers.cloudflare.com/kv/platform/limits/
- Cloudflare KV eventual consistency model: https://developers.cloudflare.com/kv/concepts/consistency/
