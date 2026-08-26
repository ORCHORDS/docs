# Durable Objects Alarm Miss Rate Monitoring

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Durable Objects that rely on `this.ctx.storage.setAlarm()` for scheduled work (heartbeats, session timeouts, saga steps, rate-limit resets) occasionally miss their scheduled fire time by tens of seconds or fail silently without any alarm handler execution. These misses are invisible in the Cloudflare dashboard and can silently corrupt business logic that depends on timely alarm delivery.

## Context

Cloudflare does not expose alarm delivery telemetry natively. Miss rate must be inferred by comparing the alarm's scheduled `targetTime` (written to storage at schedule time) with the actual `alarm()` invocation timestamp captured at runtime. Writing both values to Analytics Engine on every alarm execution allows you to compute miss frequency and drift percentiles over time. Misses above the platform's expected jitter window (typically < 5 seconds) indicate infrastructure problems, DO eviction, or application bugs resetting the alarm schedule.

## 1. Alarm Scheduling with Target-Time Bookkeeping

```typescript
// src/monitored-alarm-do.ts
import type { AnalyticsEngineDataset } from "@cloudflare/workers-types";

export interface Env {
  ALARM_METRICS: AnalyticsEngineDataset;
}

export class MonitoredAlarmDO implements DurableObject {
  private readonly state: DurableObjectState;
  private readonly env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/schedule") {
      await this.scheduleNextAlarm();
      return Response.json({ scheduled: true });
    }

    if (url.pathname === "/status") {
      const targetTime = await this.state.storage.get<number>("alarm_target_ms");
      const lastFiredAt = await this.state.storage.get<number>("alarm_last_fired_ms");
      return Response.json({ targetTime, lastFiredAt });
    }

    return new Response("Not Found", { status: 404 });
  }

  async alarm(): Promise<void> {
    const now = Date.now();
    const targetMs = await this.state.storage.get<number>("alarm_target_ms") ?? now;
    const driftMs = now - targetMs;
    const missed = driftMs > 10_000; // > 10 s drift = missed

    this.env.ALARM_METRICS.writeDataPoint({
      blobs: [
        this.state.id.toString().slice(0, 16), // abbreviated DO ID
        missed ? "miss" : "hit",
        this.doClassName(),
      ],
      doubles: [
        driftMs,
        now,
        missed ? 1 : 0,
      ],
      indexes: [this.doClassName()],
    });

    await this.state.storage.put("alarm_last_fired_ms", now);

    try {
      await this.doWork();
    } finally {
      // Always reschedule — if doWork throws, the alarm chain must continue
      await this.scheduleNextAlarm();
    }
  }

  private async scheduleNextAlarm(): Promise<void> {
    const intervalMs = 60_000; // 1-minute heartbeat
    const targetMs = Date.now() + intervalMs;
    await this.state.storage.put("alarm_target_ms", targetMs);
    await this.state.storage.setAlarm(targetMs);
  }

  private async doWork(): Promise<void> {
    // Replace with actual scheduled task (heartbeat, session cleanup, etc.)
    const existing = (await this.state.storage.get<number>("tick_count")) ?? 0;
    await this.state.storage.put("tick_count", existing + 1);
  }

  private doClassName(): string {
    return "MonitoredAlarmDO";
  }
}
```

## 2. wrangler.toml Configuration

```toml
name = "alarm-miss-monitor"
main = "src/worker.ts"
compatibility_date = "2024-09-23"

[[durable_objects.bindings]]
name = "MONITORED_DO"
class_name = "MonitoredAlarmDO"

[[migrations]]
tag = "v1"
new_classes = ["MonitoredAlarmDO"]

[[analytics_engine_datasets]]
binding = "ALARM_METRICS"
dataset = "do_alarm_metrics"
```

## 3. Worker Entry Point

```typescript
// src/worker.ts
import { MonitoredAlarmDO } from "./monitored-alarm-do";

export { MonitoredAlarmDO };

export interface WorkerEnv extends Env {
  MONITORED_DO: DurableObjectNamespace;
  ALARM_METRICS: AnalyticsEngineDataset;
}

export interface Env {
  ALARM_METRICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: WorkerEnv): Promise<Response> {
    const url = new URL(request.url);
    // Route to a named DO instance
    const id = env.MONITORED_DO.idFromName("singleton");
    const stub = env.MONITORED_DO.get(id);
    return stub.fetch(request);
  },
} satisfies ExportedHandler<WorkerEnv>;
```

## 4. Query Miss Rate and Drift Percentiles

```typescript
// src/alarm-miss-query.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

export interface AlarmMissRow {
  do_class: string;
  total_alarms: number;
  miss_count: number;
  miss_rate_pct: number;
  p50_drift_ms: number;
  p99_drift_ms: number;
}

export async function fetchAlarmMissRate(
  intervalHours = 24
): Promise<AlarmMissRow[]> {
  const sql = `
    SELECT
      blob3 AS do_class,
      count() AS total_alarms,
      sum(double3) AS miss_count,
      round(100.0 * sum(double3) / count(), 2) AS miss_rate_pct,
      quantileWeighted(0.50)(double1, 1) AS p50_drift_ms,
      quantileWeighted(0.99)(double1, 1) AS p99_drift_ms
    FROM do_alarm_metrics
    WHERE timestamp > now() - INTERVAL '${intervalHours}' HOUR
    GROUP BY do_class
    ORDER BY miss_rate_pct DESC
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

  if (!resp.ok) throw new Error(`SQL API error: ${resp.status}`);
  const json = (await resp.json()) as { data: AlarmMissRow[] };
  return json.data ?? [];
}
```

## 5. Alerting Cron Worker

```typescript
// src/miss-alert.ts
import { fetchAlarmMissRate } from "./alarm-miss-query";

const MISS_RATE_THRESHOLD_PCT = 1.0; // alert if > 1% of alarms are late
const P99_DRIFT_THRESHOLD_MS = 15_000; // alert if p99 drift > 15 s

export async function checkAlarmHealth(webhookUrl: string): Promise<void> {
  const rows = await fetchAlarmMissRate(1); // last hour
  const violations: string[] = [];

  for (const row of rows) {
    if (row.miss_rate_pct > MISS_RATE_THRESHOLD_PCT) {
      violations.push(
        `\`${row.do_class}\` miss rate=${row.miss_rate_pct}% (${row.miss_count}/${row.total_alarms} alarms)`
      );
    }
    if (row.p99_drift_ms > P99_DRIFT_THRESHOLD_MS) {
      violations.push(
        `\`${row.do_class}\` p99 drift=${row.p99_drift_ms}ms > ${P99_DRIFT_THRESHOLD_MS}ms`
      );
    }
  }

  if (violations.length === 0) return;

  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `DO alarm miss alert:\n${violations.join("\n")}`,
    }),
  });
}
```

## 6. Drift Trend Query for Dashboard

```sql
SELECT
  toStartOfInterval(timestamp, INTERVAL '10' MINUTE) AS ts,
  blob3 AS do_class,
  quantileWeighted(0.50)(double1, 1) AS p50_drift_ms,
  quantileWeighted(0.99)(double1, 1) AS p99_drift_ms,
  sum(double3) AS misses,
  count() AS total
FROM do_alarm_metrics
WHERE timestamp > now() - INTERVAL '48' HOUR
GROUP BY ts, do_class
ORDER BY ts ASC
```

## Anti-patterns

- **Rescheduling inside `doWork` only on success**: if `doWork` throws an uncaught exception, the alarm chain breaks permanently and no future alarms fire; always reschedule in a `finally` block.
- **Using wall clock `Date.now()` for `targetMs` without persisting it**: if the DO is evicted between `setAlarm()` and `alarm()`, the `targetMs` is lost from memory; always persist `alarm_target_ms` to storage.
- **Defining "miss" as any non-zero drift**: Cloudflare's platform adds up to ~5 seconds of jitter on alarm delivery; set the miss threshold to at least 10 seconds to avoid false positives.
- **Writing the full DO ID as a blob**: DO IDs are 64-character hex strings with high cardinality; truncate to 16 characters or use a logical name as the index field.
- **Measuring drift only in the happy path**: errors inside `alarm()` that prevent the data point write create systematic gaps in the miss-rate calculation.

## Gotchas

- `this.ctx.storage.setAlarm()` silently replaces any existing alarm; if two code paths both call `setAlarm`, only the last one takes effect — there is no queue of pending alarms per DO instance.
- Alarm delivery is guaranteed at-least-once but not exactly-once; a DO that crashes mid-`alarm()` will have the alarm re-invoked, which can produce duplicate `writeDataPoint` calls and inflate `total_alarms`.
- The `alarm()` method has a 30-second CPU time limit; long-running work must be split across multiple alarm invocations using incremental state in storage.
- Analytics Engine data is available with up to ~2 minutes of ingestion latency; a miss that occurred 90 seconds ago may not yet appear in SQL API queries.
- Cloudflare can hibernate a DO between requests; the `targetMs` stored in memory is lost on hibernation — always read from `this.state.storage` at the start of `alarm()`.

## Verification

1. Deploy the Worker and bootstrap the DO by calling `GET /schedule`.
2. Confirm via `GET /status` that `targetTime` is set ~60 seconds in the future.
3. Wait 70 seconds; call `GET /status` again and confirm `lastFiredAt` is populated.
4. Query the Analytics Engine SQL API for the last 10 minutes; confirm one row with `blob2 = 'hit'` and `double1 < 10000`.
5. Artificially set `alarm_target_ms` in storage to `Date.now() - 60_000` (past time), then trigger an alarm; confirm the metric row shows `blob2 = 'miss'` and `double3 = 1`.

## Related

- `durable-objects-alarm-heartbeat-monitoring.md`
- `durable-objects-memory-tail-workers.md`
- `durable-objects-capacity-planning.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `cloudflare-notifications-pagerduty-webhook.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/durable-objects/reference/in-memory-state/
- https://developers.cloudflare.com/analytics/analytics-engine/
