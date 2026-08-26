# SaaS Revenue Recognition Tracking with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Subscription revenue is not recognised at the point of cash collection — ASC 606 and IFRS 15 require recognising revenue as the performance obligation is delivered, typically ratably over each subscription period. Finance teams need an automated ledger that creates deferred revenue entries on subscription start, amortises them monthly, classifies churn and expansion revenue, and produces an MRR/ARR report on demand.

## Context

Workers acts as the event receiver (from Stripe webhooks or internal APIs) and query endpoint. D1 stores the revenue ledger. The accounting model is: cash received → deferred revenue liability; then each month a scheduled Worker moves a slice from deferred to recognised revenue. MRR and ARR are derived from the recognised entries.

## Solution

### 1. D1 schema

```sql
-- migrations/003_revenue_recognition.sql

CREATE TABLE IF NOT EXISTS subscriptions (
  id            TEXT PRIMARY KEY,   -- Stripe subscription ID
  customer_id   TEXT NOT NULL,
  plan_name     TEXT NOT NULL,
  mrr_cents     INTEGER NOT NULL,   -- monthly recurring revenue in cents
  currency      TEXT NOT NULL,
  started_at    TEXT NOT NULL,      -- ISO-8601
  cancelled_at  TEXT,
  status        TEXT NOT NULL CHECK(status IN ('active','cancelled','paused'))
);

-- One row per month per subscription for recognised revenue
CREATE TABLE IF NOT EXISTS revenue_entries (
  id              TEXT PRIMARY KEY,
  subscription_id TEXT NOT NULL,
  customer_id     TEXT NOT NULL,
  period          TEXT NOT NULL,           -- 'YYYY-MM' e.g. '2026-08'
  recognised_cents INTEGER NOT NULL,
  entry_type      TEXT NOT NULL CHECK(entry_type IN ('new','expansion','contraction','churn','reactivation')),
  recognised_at   TEXT NOT NULL,
  FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_revenue_sub_period
  ON revenue_entries(subscription_id, period);

CREATE INDEX IF NOT EXISTS idx_revenue_period ON revenue_entries(period);

-- Deferred revenue liability tracking
CREATE TABLE IF NOT EXISTS deferred_revenue (
  id              TEXT PRIMARY KEY,
  subscription_id TEXT NOT NULL,
  invoice_id      TEXT NOT NULL,          -- Stripe invoice ID
  total_cents     INTEGER NOT NULL,
  remaining_cents INTEGER NOT NULL,
  invoice_date    TEXT NOT NULL,
  period_start    TEXT NOT NULL,
  period_end      TEXT NOT NULL,
  FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);
```

### 2. Deferred revenue entry on subscription start / invoice paid

```typescript
// src/revenue/defer.ts
export interface Env {
  DB: D1Database;
}

export async function recordDeferredRevenue(params: {
  subscriptionId: string;
  customerId: string;
  invoiceId: string;
  totalCents: number;
  periodStart: string;  // ISO-8601 date
  periodEnd: string;    // ISO-8601 date
}, env: Env): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO deferred_revenue
       (id, subscription_id, invoice_id, total_cents, remaining_cents, invoice_date, period_start, period_end)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO NOTHING`
  ).bind(
    `def_${params.invoiceId}`,
    params.subscriptionId,
    params.invoiceId,
    params.totalCents,
    params.totalCents,          // starts fully deferred
    new Date().toISOString(),
    params.periodStart,
    params.periodEnd
  ).run();
}
```

### 3. Monthly revenue recognition (Cron Trigger)

```typescript
// src/revenue/recognize.ts

/**
 * Runs on the 1st of each month at 01:00 UTC.
 * Recognises revenue for the just-completed period.
 */
export async function runMonthlyRecognition(env: Env): Promise<void> {
  const now = new Date();
  // The period we are recognising is the previous month
  const prevMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const period = `${prevMonth.getFullYear()}-${String(prevMonth.getMonth() + 1).padStart(2, '0')}`;

  // Find active subscriptions that existed during the previous month
  const activeSubs = await env.DB.prepare(
    `SELECT s.id, s.customer_id, s.mrr_cents, s.currency, s.started_at, s.cancelled_at
     FROM subscriptions s
     WHERE s.started_at <= ?
       AND (s.cancelled_at IS NULL OR s.cancelled_at > ?)
       AND s.status != 'paused'`
  )
    .bind(`${period}-28`, `${period}-01`)
    .all<any>();

  if (activeSubs.results.length === 0) {
    console.log(`No active subscriptions for period ${period}`);
    return;
  }

  // Determine entry type by comparing to previous period MRR
  const insertStmts = await Promise.all(
    activeSubs.results.map(async (sub) => {
      const prevEntry = await env.DB.prepare(
        `SELECT recognised_cents FROM revenue_entries
         WHERE subscription_id = ?
         ORDER BY period DESC LIMIT 1 OFFSET 1`
      ).bind(sub.id).first<{ recognised_cents: number }>();

      const prevMrr = prevEntry?.recognised_cents ?? 0;
      let entryType: string;

      if (prevMrr === 0) {
        entryType = 'new';
      } else if (sub.mrr_cents > prevMrr) {
        entryType = 'expansion';
      } else if (sub.mrr_cents < prevMrr) {
        entryType = sub.mrr_cents === 0 ? 'churn' : 'contraction';
      } else {
        entryType = 'new'; // steady state, still record
      }

      return env.DB.prepare(
        `INSERT INTO revenue_entries
           (id, subscription_id, customer_id, period, recognised_cents, entry_type, recognised_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(subscription_id, period) DO UPDATE
           SET recognised_cents = excluded.recognised_cents,
               entry_type = excluded.entry_type`
      ).bind(
        `rev_${sub.id}_${period}`,
        sub.id,
        sub.customer_id,
        period,
        sub.mrr_cents,
        entryType,
        new Date().toISOString()
      );
    })
  );

  // Batch all inserts in one round-trip
  const batchSize = 100;
  for (let i = 0; i < insertStmts.length; i += batchSize) {
    await env.DB.batch(insertStmts.slice(i, i + batchSize));
  }

  console.log(`Recognised revenue for ${insertStmts.length} subscriptions in period ${period}`);
}
```

### 4. MRR / ARR calculation queries

```typescript
// src/revenue/metrics.ts
export interface MrrReport {
  period: string;
  total_mrr_cents: number;
  arr_cents: number;
  new_mrr_cents: number;
  expansion_mrr_cents: number;
  contraction_mrr_cents: number;
  churn_mrr_cents: number;
  net_new_mrr_cents: number;
}

export async function getMrrReport(period: string, env: Env): Promise<MrrReport> {
  const row = await env.DB.prepare(
    `SELECT
       ? AS period,
       COALESCE(SUM(recognised_cents), 0)                                          AS total_mrr_cents,
       COALESCE(SUM(CASE WHEN entry_type = 'new'         THEN recognised_cents ELSE 0 END), 0) AS new_mrr_cents,
       COALESCE(SUM(CASE WHEN entry_type = 'expansion'   THEN recognised_cents ELSE 0 END), 0) AS expansion_mrr_cents,
       COALESCE(SUM(CASE WHEN entry_type = 'contraction' THEN recognised_cents ELSE 0 END), 0) AS contraction_mrr_cents,
       COALESCE(SUM(CASE WHEN entry_type = 'churn'       THEN recognised_cents ELSE 0 END), 0) AS churn_mrr_cents
     FROM revenue_entries
     WHERE period = ?`
  )
    .bind(period, period)
    .first<any>();

  const totalMrr = row?.total_mrr_cents ?? 0;
  const netNew = (row?.new_mrr_cents ?? 0)
    + (row?.expansion_mrr_cents ?? 0)
    - (row?.contraction_mrr_cents ?? 0)
    - (row?.churn_mrr_cents ?? 0);

  return {
    ...row,
    arr_cents: totalMrr * 12,
    net_new_mrr_cents: netNew,
  };
}
```

### 5. Revenue report API endpoint

```typescript
// src/revenue/api.ts
export async function handleRevenueReport(request: Request, env: Env): Promise<Response> {
  const { searchParams } = new URL(request.url);
  const period = searchParams.get('period'); // e.g. '2026-08'

  if (!period || !/^\d{4}-\d{2}$/.test(period)) {
    return new Response('period must be YYYY-MM', { status: 400 });
  }

  const report = await getMrrReport(period, env);
  return Response.json(report);
}
```

### 6. wrangler.toml cron for monthly recognition

```toml
[[d1_databases]]
binding = "DB"
database_name = "billing"
database_id = "<your-d1-id>"

[triggers]
crons = ["0 1 1 * *"]  # 01:00 UTC on the 1st of each month
```

## Implementation Details

- `revenue_entries` has a unique index on `(subscription_id, period)` enforcing at-most-one entry per subscription per month. `ON CONFLICT ... DO UPDATE` makes the recognition job idempotent and safely re-runnable.
- MRR is stored in cents (integers) to avoid floating-point rounding errors when summing across large subscriber bases.
- ARR is derived on read (`total_mrr_cents * 12`) — never stored redundantly.
- Entry type classification (`new`, `expansion`, `contraction`, `churn`) follows the standard SaaS MRR waterfall.
- Deferred revenue rows track remaining balance for GAAP balance sheet reporting; update `remaining_cents` as recognition runs.
- Batch size of 100 prevents D1 `batch()` from hitting its 1 000-statement limit while keeping round-trips low.

## Anti-patterns

- **Recognising all revenue on the invoice date** — violates ASC 606; revenue must be recognised over the delivery period.
- **Using `FLOAT` for money columns in D1** — SQLite `REAL` is IEEE-754 double; store amounts as `INTEGER` cents.
- **Running recognition in the same transaction as invoice payment** — payment and recognition are separate accounting events; keep them decoupled.
- **No `ON CONFLICT` guard on recognition inserts** — the Cron Trigger can fire twice in rare cases; make the job idempotent.

## Gotchas

- `new Date(year, month - 1, 1)` in JavaScript where `month` is `1`–`12`; be explicit with month indexing.
- Stripe `invoice.period_start` and `invoice.period_end` are Unix timestamps; convert with `new Date(ts * 1000).toISOString()`.
- D1 `batch()` wraps statements in a single transaction on the primary; the 1 000-statement cap is per batch call, not per Worker invocation.
- Subscriptions with mid-month start dates need prorated MRR for the first period; divide `mrr_cents` by days in the month and multiply by days remaining.
- The Cron Trigger fires at most once per minute globally; `0 1 1 * *` fires at 01:00 UTC on the 1st — verify your timezone offset for any cut-off reporting requirements.

## Verification

```bash
# Insert a test subscription
wrangler d1 execute billing --command \
  "INSERT INTO subscriptions VALUES ('sub_test','cus_1','Pro',9900,'usd','2026-07-01',NULL,'active')"

# Trigger recognition manually
curl -X POST https://<worker>/internal/recognize-revenue \
  -H "Authorization: Bearer $INTERNAL_KEY"

# Fetch MRR report
curl "https://<worker>/revenue/report?period=2026-07"
# Expected: { period: '2026-07', total_mrr_cents: 9900, arr_cents: 118800, ... }

# Verify D1 entry
wrangler d1 execute billing --command \
  "SELECT * FROM revenue_entries WHERE period='2026-07'"
```

## Related

- `documentation/docs/policies/payments/workers-billing-usage-metering-d1.md`
- `documentation/docs/policies/payments/workers-subscription-dunning-workflow.md`
- `documentation/docs/policies/payments/workers-stripe-webhook-idempotency.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://stripe.com/docs/billing/subscriptions/overview
- https://www.fasb.org/jsp/FASB/Page/LandingPage&cid=1175804764014  (ASC 606)
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
