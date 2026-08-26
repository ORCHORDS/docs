# SLI/SLO Definition and Error Budget Tracking with D1

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use Case

You need to define Service Level Indicators and Objectives for a Cloudflare Workers-based API, persist the SLO data (window start, good events, total events, error budget consumed), and query it over a rolling 28-day window without depending on an external time-series database. Cloudflare D1 provides a SQLite-compatible relational store that lives at the edge. You want to write SLI measurements into D1 from within your Worker, run scheduled jobs to aggregate them into SLO windows, expose an error budget endpoint for dashboards, and alert when the burn rate threatens to exhaust the monthly budget before the window closes.

---

## Context

The SRE model distinguishes:

- **SLI (Service Level Indicator):** A quantitative measurement of service behaviour (e.g., fraction of requests completing in < 500 ms with status < 500).
- **SLO (Service Level Objective):** A target for the SLI over a time window (e.g., 99.5% of requests are "good" over a rolling 28-day window).
- **Error budget:** `1 - SLO_target` expressed as a fraction. If your SLO target is 99.5%, your error budget is 0.5% of all requests for the window. Once exhausted, you stop feature work and focus on reliability.

Storing SLO data in D1 gives you:
- SQL queries for arbitrary time windows without PromQL/LogQL.
- Cheap long-term retention (D1's storage cost is minimal at typical SLO data volumes).
- Transactional writes from Workers without an external HTTP call to a metrics backend.
- A queryable source for the Cloudflare Workers dashboard or any HTTP client.

**Limitation:** D1 is not a time-series database. Do not write one row per request—aggregate to 1-minute buckets at write time. At 10,000 req/min that's still 10,000 rows/min → 432 million rows/month. Instead, aggregate in-memory within the Worker and flush minute-buckets once per cron invocation or via a Durable Object coordinator.

---

## D1 Schema

```sql
-- migrations/0001_slo_schema.sql

CREATE TABLE IF NOT EXISTS sli_buckets (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  service     TEXT NOT NULL,          -- e.g. "api", "checkout"
  sli_name    TEXT NOT NULL,          -- e.g. "availability", "latency_p99"
  bucket_ts   INTEGER NOT NULL,       -- Unix epoch seconds, truncated to minute
  good_events INTEGER NOT NULL DEFAULT 0,
  total_events INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

-- One row per service+sli+minute: unique constraint prevents duplicates on upsert
CREATE UNIQUE INDEX IF NOT EXISTS idx_sli_bucket
  ON sli_buckets (service, sli_name, bucket_ts);

-- Fast range scans for 28-day window queries
CREATE INDEX IF NOT EXISTS idx_bucket_ts
  ON sli_buckets (bucket_ts);

CREATE TABLE IF NOT EXISTS slo_config (
  service         TEXT NOT NULL,
  sli_name        TEXT NOT NULL,
  target          REAL NOT NULL,   -- e.g. 0.995 for 99.5%
  window_days     INTEGER NOT NULL DEFAULT 28,
  description     TEXT,
  updated_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (service, sli_name)
);

-- Pre-populate SLO configuration
INSERT OR REPLACE INTO slo_config (service, sli_name, target, window_days, description)
VALUES
  ('api', 'availability', 0.995, 28, 'Fraction of requests returning HTTP < 500'),
  ('api', 'latency_p95',  0.990, 28, 'Fraction of requests completing in < 500ms (proxy for P95 SLO)'),
  ('checkout', 'availability', 0.999, 28, 'Checkout availability');
```

Apply the migration:

```bash
wrangler d1 migrations apply slo-db --remote
```

---

## In-Worker SLI Measurement

```typescript
// src/sli.ts

interface Env {
  DB: D1Database;
}

export interface SliMeasurement {
  service: string;
  sliName: string;
  goodEvents: number;
  totalEvents: number;
  bucketTs: number; // Unix epoch seconds, truncated to minute
}

// Call once per request completion inside ctx.waitUntil()
export async function flushSliMeasurements(
  db: D1Database,
  measurements: SliMeasurement[]
): Promise<void> {
  if (measurements.length === 0) return;

  // Batch upserts: one statement per unique (service, sli_name, bucket_ts)
  // Merge measurements by key
  const merged = new Map<string, SliMeasurement>();
  for (const m of measurements) {
    const key = `${m.service}|${m.sliName}|${m.bucketTs}`;
    const existing = merged.get(key);
    if (existing) {
      existing.goodEvents += m.goodEvents;
      existing.totalEvents += m.totalEvents;
    } else {
      merged.set(key, { ...m });
    }
  }

  // D1 batch API
  const statements = Array.from(merged.values()).map((m) =>
    db.prepare(`
      INSERT INTO sli_buckets (service, sli_name, bucket_ts, good_events, total_events)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT (service, sli_name, bucket_ts)
      DO UPDATE SET
        good_events  = good_events  + excluded.good_events,
        total_events = total_events + excluded.total_events
    `).bind(m.service, m.sliName, m.bucketTs, m.goodEvents, m.totalEvents)
  );

  await db.batch(statements);
}

export function currentMinuteBucket(): number {
  return Math.floor(Date.now() / 60_000) * 60;
}

export function measureAvailability(status: number): SliMeasurement {
  return {
    service: "api",
    sliName: "availability",
    goodEvents: status < 500 ? 1 : 0,
    totalEvents: 1,
    bucketTs: currentMinuteBucket(),
  };
}

export function measureLatency(durationMs: number): SliMeasurement {
  return {
    service: "api",
    sliName: "latency_p95",
    goodEvents: durationMs < 500 ? 1 : 0,
    totalEvents: 1,
    bucketTs: currentMinuteBucket(),
  };
}
```

```typescript
// src/index.ts

import { flushSliMeasurements, measureAvailability, measureLatency } from "./sli";

interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const response = await handleRequest(request, env);
    const duration = Date.now() - start;

    ctx.waitUntil(
      flushSliMeasurements(env.DB, [
        measureAvailability(response.status),
        measureLatency(duration),
      ])
    );

    return response;
  },
};
```

> At high request rates this creates many concurrent D1 writes. For > 1,000 req/s, batch measurements in a Durable Object and flush once per second to avoid D1 write contention.

---

## Error Budget Query Worker

```typescript
// error-budget-api/src/index.ts
// GET /slo/:service/:sli_name → error budget status

interface Env {
  DB: D1Database;
}

interface ErrorBudgetStatus {
  service: string;
  sliName: string;
  windowDays: number;
  sloTarget: number;
  windowStartTs: number;
  windowEndTs: number;
  goodEvents: number;
  totalEvents: number;
  currentSli: number;
  errorBudgetTotal: number;      // total allowed bad events for the window
  errorBudgetConsumed: number;   // bad events so far
  errorBudgetRemaining: number;  // remaining budget
  errorBudgetRemainingFraction: number; // 0–1
  burnRate: number;              // current rate of budget consumption
  projectedExhaustionTs: number | null; // null if on track
  status: "OK" | "WARNING" | "EXHAUSTED";
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);

    if (parts[0] !== "slo" || parts.length < 3) {
      return new Response("Usage: GET /slo/:service/:sli_name", { status: 400 });
    }

    const service = parts[1];
    const sliName = parts[2];

    const status = await computeErrorBudget(env.DB, service, sliName);
    if (!status) {
      return new Response("SLO not found", { status: 404 });
    }

    return new Response(JSON.stringify(status, null, 2), {
      headers: { "Content-Type": "application/json" },
    });
  },
};

async function computeErrorBudget(
  db: D1Database,
  service: string,
  sliName: string
): Promise<ErrorBudgetStatus | null> {
  // Load SLO config
  const config = await db
    .prepare("SELECT * FROM slo_config WHERE service = ? AND sli_name = ?")
    .bind(service, sliName)
    .first<{ target: number; window_days: number; description: string }>();

  if (!config) return null;

  const windowEndTs = Math.floor(Date.now() / 1000);
  const windowStartTs = windowEndTs - config.window_days * 86_400;

  // Aggregate SLI over the window
  const agg = await db
    .prepare(`
      SELECT
        SUM(good_events)  AS good_events,
        SUM(total_events) AS total_events
      FROM sli_buckets
      WHERE service = ?
        AND sli_name = ?
        AND bucket_ts BETWEEN ? AND ?
    `)
    .bind(service, sliName, windowStartTs, windowEndTs)
    .first<{ good_events: number; total_events: number }>();

  const goodEvents = agg?.good_events ?? 0;
  const totalEvents = agg?.total_events ?? 0;
  const currentSli = totalEvents > 0 ? goodEvents / totalEvents : 1;

  const errorBudgetTotal = Math.floor(totalEvents * (1 - config.target));
  const errorBudgetConsumed = Math.max(0, totalEvents - goodEvents);
  const errorBudgetRemaining = Math.max(0, errorBudgetTotal - errorBudgetConsumed);
  const errorBudgetRemainingFraction =
    errorBudgetTotal > 0 ? errorBudgetRemaining / errorBudgetTotal : 1;

  // Burn rate: how fast are we consuming budget relative to normal?
  // Ideal burn rate = 1 (consuming budget at exactly the SLO depletion rate)
  const elapsedFraction =
    (windowEndTs - windowStartTs) / (config.window_days * 86_400);
  const budgetConsumedFraction =
    errorBudgetTotal > 0 ? errorBudgetConsumed / errorBudgetTotal : 0;
  const burnRate =
    elapsedFraction > 0 ? budgetConsumedFraction / elapsedFraction : 0;

  // Project exhaustion time
  let projectedExhaustionTs: number | null = null;
  if (burnRate > 1 && errorBudgetConsumed < errorBudgetTotal) {
    const remainingBudgetFraction = 1 - budgetConsumedFraction;
    const timeToExhaustionS =
      (remainingBudgetFraction * config.window_days * 86_400) / burnRate;
    projectedExhaustionTs = Math.floor(windowEndTs + timeToExhaustionS);
  }

  let status: "OK" | "WARNING" | "EXHAUSTED";
  if (errorBudgetRemainingFraction <= 0) status = "EXHAUSTED";
  else if (burnRate > 2) status = "WARNING";
  else status = "OK";

  return {
    service,
    sliName,
    windowDays: config.window_days,
    sloTarget: config.target,
    windowStartTs,
    windowEndTs,
    goodEvents,
    totalEvents,
    currentSli,
    errorBudgetTotal,
    errorBudgetConsumed,
    errorBudgetRemaining,
    errorBudgetRemainingFraction,
    burnRate,
    projectedExhaustionTs,
    status,
  };
}
```

---

## Scheduled Cleanup and Retention

```typescript
// cleanup/src/index.ts

interface Env {
  DB: D1Database;
  RETENTION_DAYS: string; // default 90
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const retentionDays = parseInt(env.RETENTION_DAYS ?? "90", 10);
    const cutoffTs = Math.floor(Date.now() / 1000) - retentionDays * 86_400;

    const result = await env.DB
      .prepare("DELETE FROM sli_buckets WHERE bucket_ts < ?")
      .bind(cutoffTs)
      .run();

    console.log(`SLI cleanup: deleted ${result.changes} rows older than ${retentionDays} days`);
  },
};
```

```toml
# cleanup/wrangler.toml
name = "slo-cleanup"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "slo-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[triggers]
crons = ["0 2 * * *"]  # Run daily at 02:00 UTC
```

---

## Burn Rate Alert (Multi-Window)

Following the Google SRE Workbook two-window burn rate approach:

```typescript
// alert-worker/src/index.ts

async function checkBurnRateAlert(db: D1Database, service: string, sliName: string): Promise<void> {
  const now = Math.floor(Date.now() / 1000);

  async function getBurnRate(windowSeconds: number): Promise<number> {
    const windowStart = now - windowSeconds;
    const agg = await db.prepare(`
      SELECT SUM(good_events) AS good, SUM(total_events) AS total
      FROM sli_buckets
      WHERE service = ? AND sli_name = ? AND bucket_ts > ?
    `).bind(service, sliName, windowStart).first<{ good: number; total: number }>();

    const good = agg?.good ?? 0;
    const total = agg?.total ?? 0;
    if (total === 0) return 0;

    const sloTarget = 0.995; // load from slo_config in production
    const errorBudgetFractionUsed = (total - good) / (total * (1 - sloTarget));
    const windowFractionOfMonth = windowSeconds / (28 * 86_400);
    return errorBudgetFractionUsed / windowFractionOfMonth;
  }

  const [burn1h, burn5min] = await Promise.all([
    getBurnRate(3600),   // 1-hour window
    getBurnRate(300),    // 5-minute window
  ]);

  // Page if: 1-hour burn rate > 14x AND 5-minute burn rate > 14x
  // Ticket if: 1-hour burn rate > 6x (only 1-hour needed)
  if (burn1h > 14 && burn5min > 14) {
    console.error("PAGE: Fast burn detected", { burn1h, burn5min, service, sliName });
    // → PagerDuty critical
  } else if (burn1h > 6) {
    console.warn("TICKET: Slow burn detected", { burn1h, service, sliName });
    // → Slack warning
  }
}
```

---

## Anti-Patterns

**Writing one D1 row per request.** At any meaningful traffic level this overwhelms D1's write throughput (roughly 250 writes/s per database) and inflates storage. Always aggregate to minute buckets.

**Defining SLIs on internal metrics only.** CPU time and memory usage are resources, not user-facing indicators. Define SLIs on what users observe: response success rate and latency from their perspective.

**Using a fixed calendar-month window for SLOs.** Rolling 28-day windows are more operationally useful than calendar months—they avoid artificial end-of-month crises.

**Not persisting SLO config in D1.** Hard-coding targets in Worker environment variables makes it impossible to audit which target applied at a given point in time. Store targets in `slo_config` with `updated_at`.

**Ignoring the minimum sample size.** In the first minutes of the month, 1 bad request out of 2 gives a 50% error rate. Gate alerts on a minimum event count.

---

## Gotchas

- **D1 is SQLite-based.** `unixepoch()` is a SQLite function. Standard SQL `NOW()` is not available—use `unixepoch()` for current time.
- **D1 write latency is ~10–30 ms** for single statements and ~50–100 ms for batch statements when the Worker and D1 database are in the same region. Cross-region D1 reads/writes add network RTT.
- **`db.batch()` is transactional** within the batch but does not support cross-batch atomicity. If the Worker crashes mid-flush, partial data is written; the upsert (`ON CONFLICT DO UPDATE`) handles idempotent retries safely.
- **D1 has a 100 MB database size limit** on the free plan and 2 GB on paid plans. At 1 minute bucket granularity for 3 SLIs retained 90 days = 90 × 1440 × 3 = 388,800 rows ≈ trivially small.
- **SQLite `INTEGER` is 64-bit signed.** Storing Unix epoch seconds as INTEGER is safe through 2038 and beyond (the Y2K38 problem does not apply to SQLite INTEGER storage, only to 32-bit C time_t).
- **D1 does not support partial indices or materialised views.** Pre-aggregate into a separate `slo_daily_summary` table with a cron job if your dashboard queries become slow.

---

## Verification

```bash
# 1. Apply migrations
wrangler d1 migrations apply slo-db --remote

# 2. Verify SLO config
wrangler d1 execute slo-db --remote --command \
  "SELECT * FROM slo_config"

# 3. Insert synthetic SLI data
wrangler d1 execute slo-db --remote --command "
  INSERT INTO sli_buckets (service, sli_name, bucket_ts, good_events, total_events)
  VALUES
    ('api', 'availability', unixepoch() - 3600, 9990, 10000),
    ('api', 'availability', unixepoch() - 7200, 9985, 10000)
"

# 4. Query error budget API
curl https://error-budget.example.workers.dev/slo/api/availability | jq .
# Expect: currentSli ~0.999, status OK, positive errorBudgetRemaining

# 5. Inject bad events to exhaust budget
wrangler d1 execute slo-db --remote --command "
  INSERT INTO sli_buckets (service, sli_name, bucket_ts, good_events, total_events)
  VALUES ('api', 'availability', unixepoch() - 60, 0, 10000)
  ON CONFLICT (service, sli_name, bucket_ts)
  DO UPDATE SET good_events = 0, total_events = 10000
"
curl https://error-budget.example.workers.dev/slo/api/availability | jq .status
# Expect: "WARNING" or "EXHAUSTED" depending on cumulative budget
```

---

## Related

- `slo-error-budget-workers-pages.md` — SLO error budget for Workers/Pages (Analytics Engine approach)
- `error-budget-calculation.md` — error budget formula reference
- `error-budget-policy.md` — organisational policy for exhausted budgets
- `slo-alerting-burn-rate.md` — burn rate alerting thresholds
- `multiwindow-burn-rate-slo-alerts.md` — multi-window burn rate alerts
- `cloudflare-logpush-d1-log-aggregation.md` — using D1 for log aggregation (related pattern)

---

## Sources

- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [Cloudflare D1 documentation](https://developers.cloudflare.com/d1/)
- [D1 REST API](https://developers.cloudflare.com/d1/platform/client-api/)
- [SQLite date and time functions](https://www.sqlite.org/lang_datefunc.html)
- Beyer, B. et al. (2016). *Site Reliability Engineering*. O'Reilly. Chapter 5: Eliminating Toil.
