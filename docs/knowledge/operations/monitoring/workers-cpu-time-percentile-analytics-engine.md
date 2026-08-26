# Workers CPU Time Percentile Distribution with Analytics Engine

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A Workers deployment passes p50 CPU latency checks but intermittently exceeds the
50ms CPU time limit. The built-in Workers Metrics tab shows only mean CPU time per
route, masking the long tail. You need p95 and p99 CPU time distributions per
route and per deployment version to distinguish a regression from a one-off spike,
and to justify the move from Bundled to Unbound billing.

---

## Context

CPU time in Cloudflare Workers is the actual time spent executing JavaScript,
excluding I/O await time. It is reported by the Tail Worker via
`event.outcome`, `event.scriptName`, `event.cpuTime`, and per-subrequest timings.
Writing these samples to Analytics Engine creates a dense distribution dataset
queryable with `quantileExact` or `quantile` (approximate) in the SQL API.

Key distinction: `cpuTime` in a Tail Worker event is the **total CPU ms for the
invocation**. Wall-clock time includes I/O wait and is available as
`event.eventTimestamp` vs `event.response.end`. Both are worth tracking.

---

## 1. Tail Worker — Capture CPU Time Samples

```toml
# wrangler.toml (Tail Worker)
name = "cpu-time-tail"
compatibility_date = "2025-01-01"

[[analytics_engine_datasets]]
binding = "CPU_METRICS"
dataset = "workers_cpu_time"

[[tail_consumers]]
# Attach this Tail Worker to your production Worker from the main wrangler.toml
service = "my-production-worker"
```

```typescript
// src/tail.ts
import type {
  TailEvent,
  TailEventMessage,
  AnalyticsEngineDataset,
} from "@cloudflare/workers-types";

interface Env {
  CPU_METRICS: AnalyticsEngineDataset;
}

// Map Tail Worker outcome string to a numeric status
function outcomeCode(outcome: string): number {
  return outcome === "ok" ? 1 : 0;
}

export default {
  async tail(events: TailEventMessage[], env: Env): Promise<void> {
    for (const event of events) {
      // cpuTime is available in Workers Trace Events (Tail Workers v2)
      const cpuTimeMs = (event as TailEvent & { cpuTime?: number }).cpuTime ?? 0;
      const wallTimeMs =
        event.eventTimestamp && event.response?.end
          ? event.response.end - event.eventTimestamp
          : 0;

      // Extract route from URL path (first two segments to limit cardinality)
      let route = "unknown";
      if (event.event?.request?.url) {
        try {
          const u = new URL(event.event.request.url);
          const segments = u.pathname.split("/").filter(Boolean).slice(0, 2);
          route = "/" + segments.join("/");
        } catch {
          route = "/parse-error";
        }
      }

      const version = event.scriptVersion?.id ?? "unknown";
      const outcome = event.outcome ?? "unknown";

      env.CPU_METRICS.writeDataPoint({
        blobs: [
          event.scriptName ?? "unknown", // index 1: worker name
          route,                          // index 2: route prefix
          version,                        // index 3: script version id
          outcome,                        // index 4: ok | exception | canceled | etc.
        ],
        doubles: [
          cpuTimeMs,                       // index 1: cpu_time_ms
          wallTimeMs,                      // index 2: wall_time_ms
          outcomeCode(outcome),            // index 3: success (1|0)
        ],
        indexes: [event.scriptName ?? "unknown"],
      });
    }
  },
};
```

---

## 2. Query CPU Time Percentiles by Route

```bash
# p50 / p95 / p99 CPU time per route, last 24 hours
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{
    "query": "
      SELECT
        blob2                              AS route,
        count()                            AS invocations,
        quantileExact(0.50)(double1)       AS p50_cpu_ms,
        quantileExact(0.95)(double1)       AS p95_cpu_ms,
        quantileExact(0.99)(double1)       AS p99_cpu_ms,
        max(double1)                       AS max_cpu_ms,
        sum(1 - double3) / count()         AS error_rate
      FROM workers_cpu_time
      WHERE
        timestamp >= now() - INTERVAL 1 DAY
        AND double1 > 0
      GROUP BY route
      ORDER BY p95_cpu_ms DESC
      LIMIT 50
    "
  }'
```

---

## 3. Compare CPU Time Across Deployment Versions

```bash
# Side-by-side version comparison — useful during gradual rollouts
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{
    "query": "
      SELECT
        blob3                              AS version,
        count()                            AS invocations,
        quantileExact(0.95)(double1)       AS p95_cpu_ms,
        quantileExact(0.99)(double1)       AS p99_cpu_ms,
        avg(double3)                       AS success_rate
      FROM workers_cpu_time
      WHERE
        timestamp >= now() - INTERVAL 6 HOUR
        AND double1 > 0
      GROUP BY version
      ORDER BY invocations DESC
    "
  }'
```

---

## 4. CPU Time Histogram Bucket Distribution

```bash
# Bucket distribution: how many requests fall in each CPU time band
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{
    "query": "
      SELECT
        multiIf(
          double1 < 1,   '<1ms',
          double1 < 5,   '1-5ms',
          double1 < 10,  '5-10ms',
          double1 < 25,  '10-25ms',
          double1 < 50,  '25-50ms',
                         '>50ms'
        ) AS bucket,
        count()         AS count
      FROM workers_cpu_time
      WHERE timestamp >= now() - INTERVAL 1 DAY AND double1 > 0
      GROUP BY bucket
      ORDER BY min(double1)
    "
  }'
```

---

## 5. Scheduled Regression Detector

```typescript
// Compares p95 CPU time of current 1-hour window vs previous 1-hour window
interface Env {
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  SLACK_WEBHOOK: string;
  CPU_P95_THRESHOLD_MS: string; // alert if p95 exceeds this
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const threshold = parseFloat(env.CPU_P95_THRESHOLD_MS ?? "40");

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: `
            SELECT
              blob2 AS route,
              quantileExactIf(0.95)(double1, timestamp >= now() - INTERVAL 1 HOUR) AS p95_now,
              quantileExactIf(0.95)(double1,
                timestamp >= now() - INTERVAL 2 HOUR
                AND timestamp < now() - INTERVAL 1 HOUR
              ) AS p95_prev
            FROM workers_cpu_time
            WHERE timestamp >= now() - INTERVAL 2 HOUR AND double1 > 0
            GROUP BY route
            HAVING p95_now > ${threshold}
          `,
        }),
      }
    );

    const json = await res.json<{ data: Array<Record<string, number | string>> }>();
    const regressions = json.data.filter(
      (r) => Number(r.p95_now) > Number(r.p95_prev) * 1.25
    );

    if (regressions.length > 0) {
      await fetch(env.SLACK_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `CPU time regression detected:\n` +
            regressions
              .map((r) => `  ${r.route}: p95 ${r.p95_prev}ms → ${r.p95_now}ms`)
              .join("\n"),
        }),
      });
    }
  },
};
```

---

## 6. Grafana Panel — CPU Time Heatmap

```sql
-- Hourly p95 CPU time per route for time-series heatmap
SELECT
  toStartOfHour(timestamp) AS time,
  blob2                    AS route,
  quantileExact(0.95)(double1) AS p95_cpu_ms
FROM workers_cpu_time
WHERE
  timestamp BETWEEN $__fromTime AND $__toTime
  AND double1 > 0
GROUP BY time, route
ORDER BY time
```

---

## Anti-patterns

- **Alerting only on mean CPU time** — means hide the long tail. Always track p95
  and p99; a 2ms mean with 45ms p99 is a ticking billing problem.
- **Sampling Tail Worker events too aggressively** — if you sample at 1%, your
  p99 estimate needs ~100× more samples to be accurate. For CPU time distributions
  sample at minimum 10%, or use reservoir sampling on the Tail Worker side.
- **Conflating CPU time with wall time** — I/O-heavy Workers show low CPU time
  but high wall time. Track both `double1` (cpu) and `double2` (wall) and alert
  separately.
- **Using `scriptVersion.tag` as cardinality key** — tags are optional and
  user-set; use `scriptVersion.id` (a UUID) for guaranteed uniqueness.

---

## Gotchas

- `cpuTime` on the `TailEventMessage` is only populated when the Worker has
  opted into the **Workers Trace Events** format (Tail Workers v2). The field is
  absent on legacy tail format — check for `undefined` before writing.
- The 50ms CPU time limit applies to **Bundled** plan Workers per invocation.
  Unbound Workers have a 30,000ms wall-clock limit and CPU is metered separately.
  Your p99 alert threshold should differ by plan.
- Analytics Engine has a hard limit of **20 writes per request per dataset** in a
  single Worker invocation. A Tail Worker receiving a burst of 100 events must
  batch or accept that some are dropped.
- `quantileExact` scans all matching rows; switch to `quantile(0.95)` (approximate)
  when the dataset exceeds ~10M rows to avoid query timeouts.

---

## Verification

```bash
# Confirm cpu_time_ms values are non-zero for a known Worker
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query": "SELECT max(double1), avg(double1), count() FROM workers_cpu_time WHERE timestamp >= now() - INTERVAL 1 HOUR"}'

# Cross-check: compare Analytics Engine p95 with Workers Metrics tab in dashboard
# Allow up to 5% variance from sampling differences
```

---

## Related

- `worker-cpu-monitoring.md`
- `workers-tail-real-time-log-streaming.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `tail-worker-otel-span-export.md`

---

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/platform/limits/#cpu-time
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
