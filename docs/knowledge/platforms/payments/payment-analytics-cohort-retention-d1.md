# Payment Cohort Retention Analytics in D1 on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to measure whether paying customers return to make additional purchases in subsequent months (cohort retention) and calculate revenue retention rates — how much of the revenue from a cohort's first purchase month is still generated in later months. All data lives in a Cloudflare D1 database and the analytics endpoint is served by a Workers function without any external BI tool.

## Context

Cohort retention analysis groups customers by the month of their first successful payment (acquisition cohort) and then tracks what percentage of them made at least one additional payment in each subsequent month (retention) and how much revenue they generated (revenue retention). The schema stores one row per payment in a `payments` table with `customer_id`, `amount_cents`, and `paid_at`. Workers runs the SQL at query time; results are cached in KV for 1 hour to avoid repeated D1 scans on large tables. A second query computes the retention matrix (cohort × period offset → retained customers and revenue).

## D1 Schema and Seed Migration

```sql
-- migrations/0001_payments_cohort.sql
CREATE TABLE IF NOT EXISTS payments (
  id            TEXT PRIMARY KEY,
  customer_id   TEXT NOT NULL,
  amount_cents  INTEGER NOT NULL,
  currency      TEXT NOT NULL DEFAULT 'usd',
  paid_at       INTEGER NOT NULL,  -- Unix timestamp
  status        TEXT NOT NULL DEFAULT 'paid'
);

CREATE INDEX IF NOT EXISTS idx_payments_customer_paid
  ON payments (customer_id, paid_at);

CREATE INDEX IF NOT EXISTS idx_payments_paid_status
  ON payments (paid_at, status);

-- Materialised cohort assignments (rebuilt nightly via Cron Trigger)
CREATE TABLE IF NOT EXISTS customer_cohorts (
  customer_id    TEXT PRIMARY KEY,
  cohort_month   TEXT NOT NULL,  -- 'YYYY-MM'
  first_paid_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cohorts_month
  ON customer_cohorts (cohort_month);
```

## Rebuild Cohort Assignments (Nightly Cron)

```typescript
// src/jobs/rebuild-cohorts.ts
export interface Env {
  DB: D1Database;
  ANALYTICS_KV: KVNamespace;
}

export async function rebuildCohorts(env: Env): Promise<void> {
  // Upsert each customer's earliest successful payment as their cohort month
  await env.DB.prepare(`
    INSERT INTO customer_cohorts (customer_id, cohort_month, first_paid_at)
    SELECT
      customer_id,
      strftime('%Y-%m', datetime(MIN(paid_at), 'unixepoch')) AS cohort_month,
      MIN(paid_at) AS first_paid_at
    FROM payments
    WHERE status = 'paid'
    GROUP BY customer_id
    ON CONFLICT (customer_id) DO UPDATE SET
      cohort_month  = excluded.cohort_month,
      first_paid_at = excluded.first_paid_at
  `).run();

  // Invalidate cached cohort data
  await env.ANALYTICS_KV.delete("cohort_retention_matrix");

  console.log("Cohort assignments rebuilt");
}

// Cron entry point — wire in wrangler.toml [triggers] crons = ["0 3 * * *"]
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await rebuildCohorts(env);
  },
};
```

## Query the Retention Matrix

```typescript
// src/handlers/cohort-retention.ts
export interface Env {
  DB: D1Database;
  ANALYTICS_KV: KVNamespace;
}

export interface RetentionRow {
  cohortMonth: string;
  periodOffset: number; // months after acquisition (0 = acquisition month)
  cohortSize: number;
  retainedCustomers: number;
  retentionRate: number;     // 0–1
  revenueCents: number;
  revenueRetentionRate: number; // relative to period 0 revenue
}

const CACHE_KEY = "cohort_retention_matrix";
const CACHE_TTL = 3600; // seconds

export async function getCohortRetention(env: Env): Promise<RetentionRow[]> {
  const cached = await env.ANALYTICS_KV.get(CACHE_KEY, "json");
  if (cached) return cached as RetentionRow[];

  // Build retention matrix: cohort × months offset
  const { results } = await env.DB.prepare(`
    WITH cohort_periods AS (
      SELECT
        cc.customer_id,
        cc.cohort_month,
        -- Month offset: 0 = acquisition month, 1 = next month, etc.
        (
          (strftime('%Y', datetime(p.paid_at, 'unixepoch')) * 12 +
           strftime('%m', datetime(p.paid_at, 'unixepoch')))
          -
          (strftime('%Y', cc.cohort_month || '-01') * 12 +
           strftime('%m', cc.cohort_month || '-01'))
        ) AS period_offset,
        SUM(p.amount_cents) AS period_revenue
      FROM customer_cohorts cc
      JOIN payments p ON p.customer_id = cc.customer_id AND p.status = 'paid'
      GROUP BY cc.customer_id, cc.cohort_month, period_offset
    ),
    cohort_sizes AS (
      SELECT cohort_month, COUNT(*) AS cohort_size
      FROM customer_cohorts
      GROUP BY cohort_month
    ),
    period_0_revenue AS (
      SELECT cohort_month, SUM(period_revenue) AS base_revenue
      FROM cohort_periods
      WHERE period_offset = 0
      GROUP BY cohort_month
    )
    SELECT
      cp.cohort_month,
      cp.period_offset,
      cs.cohort_size,
      COUNT(DISTINCT cp.customer_id)       AS retained_customers,
      ROUND(1.0 * COUNT(DISTINCT cp.customer_id) / cs.cohort_size, 4) AS retention_rate,
      SUM(cp.period_revenue)               AS revenue_cents,
      ROUND(1.0 * SUM(cp.period_revenue) / p0r.base_revenue, 4) AS revenue_retention_rate
    FROM cohort_periods cp
    JOIN cohort_sizes cs ON cs.cohort_month = cp.cohort_month
    JOIN period_0_revenue p0r ON p0r.cohort_month = cp.cohort_month
    GROUP BY cp.cohort_month, cp.period_offset, cs.cohort_size, p0r.base_revenue
    ORDER BY cp.cohort_month, cp.period_offset
  `).all<{
    cohort_month: string;
    period_offset: number;
    cohort_size: number;
    retained_customers: number;
    retention_rate: number;
    revenue_cents: number;
    revenue_retention_rate: number;
  }>();

  const matrix: RetentionRow[] = results.map((r) => ({
    cohortMonth: r.cohort_month,
    periodOffset: r.period_offset,
    cohortSize: r.cohort_size,
    retainedCustomers: r.retained_customers,
    retentionRate: r.retention_rate,
    revenueCents: r.revenue_cents,
    revenueRetentionRate: r.revenue_retention_rate,
  }));

  await env.ANALYTICS_KV.put(CACHE_KEY, JSON.stringify(matrix), {
    expirationTtl: CACHE_TTL,
  });

  return matrix;
}

export async function handleCohortRetention(
  _request: Request,
  env: Env
): Promise<Response> {
  const matrix = await getCohortRetention(env);
  return new Response(JSON.stringify({ data: matrix }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

## Pivot to Triangle Format for Dashboard

```typescript
// src/utils/pivot-cohorts.ts
import type { RetentionRow } from "../handlers/cohort-retention";

export interface CohortTriangle {
  cohortMonth: string;
  cohortSize: number;
  periods: Array<{
    offset: number;
    retentionRate: number;
    revenueRetentionRate: number;
  }>;
}

export function pivotToTriangle(rows: RetentionRow[]): CohortTriangle[] {
  const map = new Map<string, CohortTriangle>();

  for (const row of rows) {
    if (!map.has(row.cohortMonth)) {
      map.set(row.cohortMonth, {
        cohortMonth: row.cohortMonth,
        cohortSize: row.cohortSize,
        periods: [],
      });
    }
    map.get(row.cohortMonth)!.periods.push({
      offset: row.periodOffset,
      retentionRate: row.retentionRate,
      revenueRetentionRate: row.revenueRetentionRate,
    });
  }

  return Array.from(map.values()).sort((a, b) =>
    a.cohortMonth.localeCompare(b.cohortMonth)
  );
}
```

## Anti-patterns

- Do not run the retention matrix query on every request against a large `payments` table; D1 has per-query row limits and the GROUP BY fan-out can be expensive — always cache in KV.
- Do not derive `period_offset` in application code by loading all payment rows into memory; push the arithmetic into SQL so only the aggregate result crosses the Workers/D1 boundary.
- Do not use `cohort_month` as a plain `YYYY-MM` string without normalising it to the first of the month before date arithmetic; `strftime('%Y-%m', ...)` returns a two-component string that cannot be directly added.

## Gotchas

- D1's SQLite dialect does not have a `DATE_DIFF` function; month offset must be computed with the year×12+month formula shown above.
- The `customer_cohorts` rebuild upsert will silently skip customers whose earliest payment predates your `payments` table history if you imported partial data; backfill detection requires checking `first_paid_at` against your import boundary.
- KV `expirationTtl` is in seconds and must be an integer; passing a float (e.g. `3600.5`) causes KV to silently ignore the TTL and store the value without expiry.

## Verification

```bash
# Insert sample data and run cohort rebuild locally
wrangler d1 execute DB --local \
  --command "INSERT INTO payments VALUES ('p1','c1',5000,'usd',1704067200,'paid'),('p2','c1',5000,'usd',1706745600,'paid'),('p3','c2',3000,'usd',1704067200,'paid')"

wrangler dev --local
curl http://localhost:8787/analytics/cohort-retention | jq .

# Verify the nightly cron fires
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+3+*+*+*"
```

## Related

- `payments/payment-analytics-dashboard.md`
- `payments/mrr-arr-calculation.md`
- `payments/churn-calculation.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://www.reforge.com/blog/retention-engagement-growth-silent-killer
