# Workers Error Rate Anomaly Detection with D1 Rolling Baselines

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Workers error rate spikes transiently during deploys, quota exhaustion, or upstream failures,
but static threshold alerts fire too often during expected traffic fluctuations. You need an adaptive
baseline that compares current error rates against recent history to surface genuine anomalies.

## Context
A Tail Worker captures every request outcome from your production Workers and writes error counts
and request totals to a D1 database in 1-minute buckets. A separate cron Worker computes a rolling
baseline (mean + standard deviation over the prior N windows) and raises an alert when the current
error rate deviates more than Z standard deviations from that baseline — a simple Z-score anomaly
detector that adapts to diurnal patterns without manual threshold tuning.

---

## Section 1 — D1 Schema and Tail Worker Ingestion

```sql
-- Run once via wrangler d1 execute <db> --file schema.sql
CREATE TABLE IF NOT EXISTS error_rate_windows (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  worker_name TEXT    NOT NULL,
  window_start INTEGER NOT NULL,  -- Unix epoch seconds, truncated to the minute
  requests    INTEGER NOT NULL DEFAULT 0,
  errors      INTEGER NOT NULL DEFAULT 0,
  cpu_exceeded INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_worker_window
  ON error_rate_windows (worker_name, window_start);

CREATE INDEX IF NOT EXISTS idx_window_start
  ON error_rate_windows (window_start);
```

```typescript
// tail-worker.ts — ingests error events into D1
export interface Env {
  ERROR_BASELINE_DB: D1Database;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    // Aggregate by worker + 1-minute window within this batch
    const buckets = new Map<
      string,
      { requests: number; errors: number; cpuExceeded: number }
    >();

    for (const event of events) {
      const windowStart = Math.floor(event.eventTimestamp / 1000 / 60) * 60;
      const key = `${event.scriptName}::${windowStart}`;

      const bucket = buckets.get(key) ?? { requests: 0, errors: 0, cpuExceeded: 0 };
      bucket.requests += 1;

      if (event.outcome === "exception" || event.outcome === "unknown") {
        bucket.errors += 1;
      }
      if (event.outcome === "exceeded-cpu") {
        bucket.cpuExceeded += 1;
        bucket.errors += 1;
      }

      buckets.set(key, bucket);
    }

    // Upsert aggregated buckets into D1 with additive increments
    const stmts = [...buckets.entries()].map(([key, counts]) => {
      const [workerName, windowStart] = key.split("::");
      return env.ERROR_BASELINE_DB.prepare(
        `INSERT INTO error_rate_windows (worker_name, window_start, requests, errors, cpu_exceeded)
         VALUES (?, ?, ?, ?, ?)
         ON CONFLICT (worker_name, window_start)
         DO UPDATE SET
           requests    = requests    + excluded.requests,
           errors      = errors      + excluded.errors,
           cpu_exceeded = cpu_exceeded + excluded.cpu_exceeded`
      ).bind(workerName, Number(windowStart), counts.requests, counts.errors, counts.cpuExceeded);
    });

    if (stmts.length > 0) {
      await env.ERROR_BASELINE_DB.batch(stmts);
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 2 — Cron Worker: Z-Score Anomaly Detection

```typescript
// anomaly-detector.ts — runs every minute via cron trigger
export interface Env {
  ERROR_BASELINE_DB: D1Database;
  ALERT_WEBHOOK_URL: string; // Slack/PagerDuty/etc
}

const BASELINE_MINUTES = 60; // look-back window for baseline
const Z_THRESHOLD = 3.0;     // flag if current rate is 3σ above baseline mean
const MIN_REQUESTS = 10;     // ignore windows with too few requests

interface WindowRow {
  worker_name: string;
  window_start: number;
  requests: number;
  errors: number;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const now = Math.floor(Date.now() / 1000);
    const currentWindowStart = Math.floor(now / 60) * 60 - 60; // previous complete minute
    const baselineStart = currentWindowStart - BASELINE_MINUTES * 60;

    // Fetch current window and baseline windows for all workers
    const { results } = await env.ERROR_BASELINE_DB.prepare(
      `SELECT worker_name, window_start, requests, errors
       FROM error_rate_windows
       WHERE window_start >= ? AND window_start <= ?
       ORDER BY worker_name, window_start ASC`
    )
      .bind(baselineStart, currentWindowStart)
      .all<WindowRow>();

    // Group by worker
    const byWorker = new Map<string, WindowRow[]>();
    for (const row of results) {
      const arr = byWorker.get(row.worker_name) ?? [];
      arr.push(row);
      byWorker.set(row.worker_name, arr);
    }

    const alerts: string[] = [];

    for (const [workerName, windows] of byWorker) {
      const current = windows.find((w) => w.window_start === currentWindowStart);
      if (!current || current.requests < MIN_REQUESTS) continue;

      const baseline = windows.filter((w) => w.window_start < currentWindowStart);
      if (baseline.length < 5) continue; // need enough history

      // Compute error rates for baseline windows
      const baselineRates = baseline
        .filter((w) => w.requests >= MIN_REQUESTS)
        .map((w) => w.errors / w.requests);

      if (baselineRates.length < 5) continue;

      const mean = baselineRates.reduce((a, b) => a + b, 0) / baselineRates.length;
      const variance =
        baselineRates.reduce((a, b) => a + (b - mean) ** 2, 0) / baselineRates.length;
      const stddev = Math.sqrt(variance);

      const currentRate = current.errors / current.requests;
      const zScore = stddev > 0 ? (currentRate - mean) / stddev : 0;

      if (zScore > Z_THRESHOLD) {
        alerts.push(
          `[ANOMALY] ${workerName}: error_rate=${(currentRate * 100).toFixed(2)}% ` +
            `baseline=${(mean * 100).toFixed(2)}% z=${zScore.toFixed(1)} ` +
            `(${current.errors}/${current.requests} errors)`
        );
      }
    }

    if (alerts.length > 0) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: alerts.join("\n") }),
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — Maintenance: Pruning Old Baseline Data

D1 storage is billed per GB; prune windows older than 7 days to avoid unbounded growth.

```typescript
// Add to the cron Worker's scheduled handler, after anomaly detection:

async function pruneOldWindows(db: D1Database): Promise<void> {
  const cutoff = Math.floor(Date.now() / 1000) - 7 * 24 * 60 * 60;
  const { meta } = await db
    .prepare("DELETE FROM error_rate_windows WHERE window_start < ?")
    .bind(cutoff)
    .run();
  console.log(`[prune] deleted ${meta.changes} old baseline rows`);
}
```

```sql
-- Manual inspection: view current error rates and baseline summary
SELECT
  worker_name,
  round(CAST(errors AS REAL) / requests * 100, 2) AS error_pct,
  requests,
  window_start,
  datetime(window_start, 'unixepoch') AS window_time
FROM error_rate_windows
WHERE window_start > unixepoch() - 3600
ORDER BY error_pct DESC
LIMIT 30;

-- Baseline mean/stddev per worker (last 60 minutes)
SELECT
  worker_name,
  round(avg(CAST(errors AS REAL) / requests) * 100, 3) AS mean_error_pct,
  round(
    sqrt(avg(
      power(CAST(errors AS REAL) / requests -
        (SELECT avg(CAST(e2.errors AS REAL) / e2.requests)
         FROM error_rate_windows e2
         WHERE e2.worker_name = e1.worker_name
           AND e2.window_start > unixepoch() - 3600
           AND e2.requests >= 10), 2)
    )) * 100, 3
  ) AS stddev_error_pct,
  count() AS windows_sampled
FROM error_rate_windows e1
WHERE window_start > unixepoch() - 3600
  AND requests >= 10
GROUP BY worker_name;
```

---

## Anti-patterns
- Using a global static threshold (e.g., "alert if error rate > 1%") — this fires constantly
  during low-traffic hours where 2 errors out of 50 requests is 4% but perfectly normal.
- Running the anomaly query in the Tail Worker itself — Tail Workers have a 50ms CPU budget;
  keep analytics logic in the cron Worker.
- Not filtering windows with fewer than `MIN_REQUESTS` — a 100% error rate on 1 request in
  the baseline will catastrophically inflate the mean.
- Forgetting to index `(worker_name, window_start)` in D1 — without it, the range scan over
  60+ minutes of windows is a full table scan.

## Gotchas
- D1 `batch()` is limited to 100 statements per call; chunk the Tail Worker upserts if a single
  Tail event covers many workers across many time windows.
- The cron Worker's scheduled time may drift by ±30 seconds; align `window_start` to wall-clock
  minutes via `Math.floor(now / 60) * 60` rather than relying on `event.scheduledTime`.
- Tail Workers receive events asynchronously; a window bucket may receive late-arriving events
  after the cron has already evaluated it — add 1 minute of grace by evaluating `currentWindowStart - 60`.
- D1 SQLite `STDDEV` is not available; compute variance manually or use the Workers runtime to
  calculate it in JavaScript as shown above.

## Verification
```bash
# Seed test errors and verify D1 row insertion
wrangler tail my-worker --format json | jq 'select(.outcome == "exception")'

# Query D1 directly for the last 5 minutes of buckets
wrangler d1 execute error-baseline-db \
  --command "SELECT * FROM error_rate_windows WHERE window_start > unixepoch() - 300 ORDER BY window_start DESC LIMIT 20"

# Trigger the cron manually to test anomaly logic
wrangler dev --test-scheduled
```

## Related
- `tail-worker-structured-error-classification-d1.md`
- `tail-worker-exception-deduplication-fingerprinting-d1.md`
- `workers-request-size-anomaly-detection-d1.md`
- `workers-error-alerting-pagerduty-integration.md`
- `sli-slo-error-budget-d1-tracking.md`
- `d1-write-transaction-contention-monitoring.md`

## Sources
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/worker-api/d1-client-api/#batch-statements
