# Stripe Sigma Custom SQL Reports and Analytics

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

The Stripe Dashboard's built-in charts show high-level MRR, payment volume, and refund rates but cannot answer product-specific questions: "Which pricing plan has the highest 90-day retention?", "What is the revenue concentration across our top 20 customers?", "How many subscriptions churned in Q3 that were more than 6 months old?". Sigma is Stripe's built-in SQL environment that runs queries directly against your Stripe data — no ETL pipeline, no data warehouse, no API pagination loops. The data is available within hours of being created on Stripe's side and includes every object type: charges, subscriptions, invoices, customers, disputes, refunds, payouts, and Connect transfers.

## Context

Stripe Sigma is available on paid plans. It provides a read-only SQL environment (Presto / Athena dialect) pre-loaded with your Stripe account data as tables. You write queries in the Dashboard under Reports → Sigma, or schedule reports to run automatically and deliver to S3 / email.

Key tables:
- `charges` — every charge attempt (successful or not)
- `customers` — customer objects
- `subscriptions` — subscription records with their current status
- `subscription_items` — line items within subscriptions
- `invoices` — invoice records
- `invoice_line_items` — line items within invoices
- `refunds` — refund records
- `disputes` — dispute (chargeback) records
- `balance_transactions` — the definitive record of every movement in your Stripe balance
- `payouts` — payout records to bank accounts
- `transfers` — Connect platform transfers to connected accounts
- `connected_accounts` — metadata on all connected accounts

Data freshness: Most objects are available within 1–3 hours of creation. `balance_transactions` can lag up to 24 hours during peak periods.

## Monthly Recurring Revenue by Plan

The most common Sigma query: compute current MRR broken down by price/plan. This uses `subscription_items` joined to active `subscriptions` and normalizes the billing interval to a monthly figure.

```sql
-- Monthly Recurring Revenue by price (Stripe Sigma)
SELECT
  si.price_id,
  p.nickname                                          AS plan_name,
  p.currency,
  COUNT(DISTINCT s.id)                                AS active_subscriptions,
  SUM(
    CASE p.interval
      WHEN 'month' THEN si.quantity * p.unit_amount
      WHEN 'year'  THEN si.quantity * p.unit_amount / 12
      WHEN 'week'  THEN si.quantity * p.unit_amount * 4
      WHEN 'day'   THEN si.quantity * p.unit_amount * 30
      ELSE 0
    END
  ) / 100.0                                           AS mrr
FROM subscription_items si
JOIN subscriptions s ON s.id = si.subscription_id
JOIN prices p        ON p.id = si.price_id
WHERE s.status = 'active'
  AND s.cancel_at_period_end = FALSE
GROUP BY si.price_id, p.nickname, p.currency
ORDER BY mrr DESC;
```

## Churn Analysis: Subscriptions Canceled by Age Cohort

Understand whether churn is concentrated among new subscribers (product-fit problem) or longer-tenured ones (pricing or feature gap).

```sql
-- Canceled subscriptions by age at cancellation
SELECT
  DATE_TRUNC('month', s.canceled_at)                 AS canceled_month,
  CASE
    WHEN DATE_DIFF('month', s.created, s.canceled_at) < 1  THEN '0-1 months'
    WHEN DATE_DIFF('month', s.created, s.canceled_at) < 3  THEN '1-3 months'
    WHEN DATE_DIFF('month', s.created, s.canceled_at) < 6  THEN '3-6 months'
    WHEN DATE_DIFF('month', s.created, s.canceled_at) < 12 THEN '6-12 months'
    ELSE '12+ months'
  END                                                  AS age_at_churn,
  p.nickname                                           AS plan_name,
  COUNT(*)                                             AS canceled_count,
  SUM(
    CASE p.interval
      WHEN 'month' THEN p.unit_amount
      WHEN 'year'  THEN p.unit_amount / 12
      ELSE 0
    END
  ) / 100.0                                            AS lost_mrr
FROM subscriptions s
JOIN subscription_items si ON si.subscription_id = s.id
JOIN prices p               ON p.id = si.price_id
WHERE s.status = 'canceled'
  AND s.canceled_at >= DATE_ADD('month', -6, CURRENT_DATE)
GROUP BY 1, 2, 3
ORDER BY canceled_month DESC, lost_mrr DESC;
```

## Customer Revenue Concentration (Whale Analysis)

Identify revenue concentration risk: if your top 10 customers represent >40% of MRR, the business is fragile. This query shows each customer's MRR contribution and cumulative share.

```sql
-- Customer revenue concentration with running total
WITH customer_mrr AS (
  SELECT
    c.id                                              AS customer_id,
    COALESCE(c.email, c.id)                          AS customer_email,
    c.name,
    SUM(
      CASE p.interval
        WHEN 'month' THEN si.quantity * p.unit_amount
        WHEN 'year'  THEN si.quantity * p.unit_amount / 12
        ELSE 0
      END
    ) / 100.0                                         AS mrr
  FROM customers c
  JOIN subscriptions s    ON s.customer_id = c.id
  JOIN subscription_items si ON si.subscription_id = s.id
  JOIN prices p           ON p.id = si.price_id
  WHERE s.status = 'active'
  GROUP BY c.id, c.email, c.name
),
total AS (
  SELECT SUM(mrr) AS total_mrr FROM customer_mrr
),
ranked AS (
  SELECT
    cm.*,
    t.total_mrr,
    cm.mrr / t.total_mrr * 100                       AS pct_of_total,
    SUM(cm.mrr) OVER (ORDER BY cm.mrr DESC
                      ROWS UNBOUNDED PRECEDING) / t.total_mrr * 100
                                                      AS cumulative_pct,
    ROW_NUMBER() OVER (ORDER BY cm.mrr DESC)          AS rank
  FROM customer_mrr cm
  CROSS JOIN total t
)
SELECT
  rank,
  customer_email,
  name,
  ROUND(mrr, 2)                                       AS mrr,
  ROUND(pct_of_total, 2)                              AS pct_of_total,
  ROUND(cumulative_pct, 2)                            AS cumulative_pct
FROM ranked
WHERE rank <= 50
ORDER BY rank;
```

## Dispute Rate by Payment Method and Country

Dispute rate is a key risk signal. Payment networks penalize merchants whose dispute rate exceeds 0.75% (Visa) or 1% (Mastercard). This query surfaces dispute concentration.

```sql
-- Dispute rate by payment method type and billing country
SELECT
  c.payment_method_details_type                       AS payment_method,
  ch.billing_details_address_country                  AS billing_country,
  COUNT(DISTINCT ch.id)                               AS total_charges,
  COUNT(DISTINCT d.charge_id)                         AS disputed_charges,
  ROUND(
    COUNT(DISTINCT d.charge_id) * 100.0
    / NULLIF(COUNT(DISTINCT ch.id), 0),
    3
  )                                                   AS dispute_rate_pct,
  SUM(d.amount) / 100.0                              AS total_disputed_usd
FROM charges ch
LEFT JOIN disputes d ON d.charge_id = ch.id
  AND d.status NOT IN ('won', 'warning_closed')
WHERE ch.created >= DATE_ADD('month', -3, CURRENT_DATE)
  AND ch.currency = 'usd'
  AND ch.captured = TRUE
GROUP BY 1, 2
HAVING COUNT(DISTINCT ch.id) >= 50  -- filter noise from low-volume combinations
ORDER BY dispute_rate_pct DESC
LIMIT 30;
```

## Scheduled Report Delivery (Stripe → S3)

Sigma reports can be scheduled to run automatically. Configure via the Dashboard under Reports → Sigma → Scheduled Reports. For programmatic setup, use the Stripe API:

```typescript
// workers/sigma-schedule.ts
import Stripe from "stripe";

interface SigmaScheduleConfig {
  reportType: string;     // e.g. "sigma.scheduled_query_run/1"
  parameters: {
    interval: "day" | "week" | "month";
    interval_count?: number;
    reporting_category?: string;
  };
}

export async function listScheduledReports(
  stripe: Stripe
): Promise<Stripe.Reporting.ReportType[]> {
  const reports = await stripe.reporting.reportTypes.list();
  return reports.data;
}

export async function runReportNow(
  stripe: Stripe,
  reportType: string,
  parameters: Record<string, string>
): Promise<Stripe.Reporting.ReportRun> {
  const run = await stripe.reporting.reportRuns.create({
    report_type: reportType,
    parameters: {
      ...parameters,
      // interval_start and interval_end must be Unix timestamps
    },
  });
  return run;
}

// Poll report run until complete, then fetch the result file
export async function waitForReport(
  stripe: Stripe,
  runId: string,
  pollIntervalMs = 5000
): Promise<string | null> {
  for (let i = 0; i < 60; i++) {
    const run = await stripe.reporting.reportRuns.retrieve(runId);
    if (run.status === "succeeded" && run.result?.url) {
      // Download the CSV from run.result.url using the secret key as bearer token
      return run.result.url;
    }
    if (run.status === "failed") return null;
    await new Promise((r) => setTimeout(r, pollIntervalMs));
  }
  return null;
}
```

## Exporting Sigma Results to D1 for Dashboards

Pull Stripe reporting API output into D1 for fast dashboard queries without hitting Stripe's API on each page load.

```typescript
// workers/sigma-to-d1.ts

export async function syncBalanceTransactionsToD1(
  stripe: Stripe,
  db: D1Database,
  sinceTimestamp: number
): Promise<number> {
  let page = await stripe.balanceTransactions.list({
    created: { gte: sinceTimestamp },
    limit: 100,
    expand: ["data.source"],
  });

  let synced = 0;

  for await (const txn of page.autoPagingEach ? page : []) {
    await db
      .prepare(
        `INSERT OR REPLACE INTO balance_transactions
         (id, type, amount_cents, fee_cents, net_cents, currency,
          description, source_id, created_at)
         VALUES (?,?,?,?,?,?,?,?,?)`
      )
      .bind(
        txn.id,
        txn.type,
        txn.amount,
        txn.fee,
        txn.net,
        txn.currency,
        txn.description ?? null,
        typeof txn.source === "string" ? txn.source : txn.source?.id ?? null,
        new Date(txn.created * 1000).toISOString()
      )
      .run();
    synced++;
  }

  return synced;
}
```

## Anti-patterns

- **Using `charges` as the revenue truth table**: `charges` shows gross charge amounts but does not account for refunds, disputes, or fees. Use `balance_transactions` with `type = 'charge'` net of `type = 'refund'` for accurate revenue figures.
- **Treating Sigma as a real-time data source**: Sigma data lags 1–3 hours. Never serve live pricing or subscription status from a Sigma query result; use the Stripe API directly for real-time reads.
- **Running expensive Sigma queries on page load**: Sigma queries count against a per-account compute quota. Cache results in D1 or KV and refresh on a schedule, not on user demand.
- **Forgetting to filter by `captured = TRUE` on charges**: Failed or uncaptured authorizations appear in the `charges` table. Always filter `captured = TRUE AND status = 'succeeded'` for revenue queries.
- **Using `unit_amount` without accounting for `unit_amount_decimal`**: For high-precision prices (e.g., fractions of a cent in metered billing), Stripe uses `unit_amount_decimal`. If the price was created with a decimal amount, `unit_amount` is null. Use `COALESCE(unit_amount, CAST(unit_amount_decimal AS BIGINT))`.

## Gotchas

- Sigma uses **Presto SQL dialect**, not standard PostgreSQL or MySQL. Window functions (`ROW_NUMBER() OVER`, `SUM() OVER`) work, but some PostgreSQL-specific syntax (`::type` casts, `ILIKE`, `RETURNING`) does not.
- `DATE_ADD` in Sigma takes `('interval', count, date)` — the interval is a string, not a keyword. `DATE_ADD('month', -3, CURRENT_DATE)` subtracts 3 months; in Postgres this would be `CURRENT_DATE - INTERVAL '3 months'`.
- Connected account data (Express, Custom) is **not** automatically available in the platform's Sigma workspace. You must query connected account data from that account's own Sigma workspace or via the Stripe API with `Stripe-Account` header.
- `balance_transactions.net` is in the account's default currency. For multi-currency accounts, filter by `currency` or use `exchange_rate` to convert before aggregating.
- Sigma scheduled reports run in UTC. If your business reporting cycle is in a different timezone, adjust the `interval_start` and `interval_end` timestamps accordingly.
- The `invoices` table includes both subscription invoices and standalone invoices. Filter `subscription_id IS NOT NULL` to restrict to subscription billing.

## Verification

```bash
# List available report types via CLI
stripe reporting report_types list

# Trigger a balance summary report for last month
stripe reporting report_runs create \
  --report-type="balance.summary.1" \
  --parameters[interval_start]=$(date -d 'last month' '+%s') \
  --parameters[interval_end]=$(date -d 'today' '+%s')

# Retrieve the report run and download result
stripe reporting report_runs retrieve rrr_xxx
# When status = succeeded, download run.result.url with:
curl -u sk_live_xxx: "https://files.stripe.com/v1/files/FILE_ID/contents" -o report.csv
```

```sql
-- Quick sanity check: total gross charge volume last 30 days
SELECT
  DATE_TRUNC('day', created)  AS day,
  currency,
  COUNT(*)                    AS charge_count,
  SUM(amount) / 100.0        AS gross_usd
FROM charges
WHERE created >= DATE_ADD('day', -30, CURRENT_DATE)
  AND captured = TRUE
  AND status = 'succeeded'
GROUP BY 1, 2
ORDER BY 1 DESC;
```

## Related

- `mrr-arr-calculation.md` — MRR/ARR calculation patterns
- `churn-calculation.md` — cohort-level churn rate methodology
- `payment-analytics-dashboard.md` — building analytics dashboards on payment data
- `ltv-calculation.md` — customer lifetime value from subscription data
- `subscription-metrics-tracking.md` — tracking subscription health metrics
- `revenue-recognition-saas.md` — revenue recognition under ASC 606

## Sources

- https://stripe.com/docs/stripe-reports/sigma
- https://stripe.com/docs/reports/api
- https://stripe.com/docs/reports/reporting-categories
- https://stripe.com/docs/api/reporting/report_runs/create
- https://prestodb.io/docs/current/functions/datetime.html
