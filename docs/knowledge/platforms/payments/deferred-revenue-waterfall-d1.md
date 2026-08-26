# Deferred Revenue Waterfall Tracking with D1

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A SaaS platform collects annual or multi-month subscription payments upfront. Under accrual accounting (ASC 606 / IFRS 15), that cash cannot be recognized as revenue immediately — it must be "earned" month by month over the service period. Without a proper deferred revenue ledger, the income statement is wrong, tax reporting is incorrect, and investor metrics (ARR, NRR) are meaningless. The challenge is maintaining a per-subscription waterfall that releases the right amount each period without double-counting partial months, upgrades, downgrades, or refunds.

## Context

Deferred revenue is a liability on the balance sheet representing obligations not yet fulfilled. When a customer pays $1,200 for an annual plan on March 15, $100 is recognizable each complete month (March 15 – April 14, April 15 – May 14, …), with the day-count method used for partial months at the edges.

The recognition engine runs as a Cloudflare Worker on a scheduled Cron Trigger (daily at 00:05 UTC), reading Stripe subscription data and writing waterfall entries into a D1 database. A second scheduled job at month-end produces the recognition journal entry.

Schema design choices:
- One `deferred_revenue_schedules` row per subscription period (created at payment time)
- One `revenue_recognition_entries` row per period per subscription (written by the nightly job)
- All amounts in the subscription's currency, stored as integer cents
- A `recognized_through` column on the schedule tracks the last date processed so the nightly job is idempotent

## D1 Schema Setup

```sql
-- migrations/0010_deferred_revenue.sql

CREATE TABLE IF NOT EXISTS deferred_revenue_schedules (
  id                    TEXT PRIMARY KEY,               -- uuid
  stripe_subscription_id TEXT NOT NULL,
  stripe_invoice_id     TEXT NOT NULL,
  customer_id           TEXT NOT NULL,
  plan_id               TEXT NOT NULL,
  currency              TEXT NOT NULL DEFAULT 'usd',
  total_amount_cents    INTEGER NOT NULL,               -- amount paid
  service_start_date    TEXT NOT NULL,                  -- ISO date YYYY-MM-DD
  service_end_date      TEXT NOT NULL,                  -- ISO date YYYY-MM-DD
  recognized_cents      INTEGER NOT NULL DEFAULT 0,
  deferred_cents        INTEGER NOT NULL,               -- total_amount_cents - recognized_cents
  recognized_through    TEXT,                           -- last date processed (ISO date)
  status                TEXT NOT NULL DEFAULT 'active', -- active | completed | voided
  created_at            TEXT NOT NULL,
  updated_at            TEXT NOT NULL
);

CREATE INDEX idx_drs_subscription ON deferred_revenue_schedules (stripe_subscription_id);
CREATE INDEX idx_drs_status       ON deferred_revenue_schedules (status, recognized_through);

CREATE TABLE IF NOT EXISTS revenue_recognition_entries (
  id               TEXT PRIMARY KEY,
  schedule_id      TEXT NOT NULL REFERENCES deferred_revenue_schedules (id),
  period_start     TEXT NOT NULL,  -- ISO date: first day of recognition window
  period_end       TEXT NOT NULL,  -- ISO date: last day of recognition window (inclusive)
  amount_cents     INTEGER NOT NULL,
  currency         TEXT NOT NULL,
  journal_batch_id TEXT,           -- set when included in a month-end journal
  created_at       TEXT NOT NULL,
  UNIQUE (schedule_id, period_start)
);

CREATE INDEX idx_rre_schedule ON revenue_recognition_entries (schedule_id);
CREATE INDEX idx_rre_batch    ON revenue_recognition_entries (journal_batch_id);
```

## Creating a Schedule at Invoice Payment

When Stripe fires `invoice.payment_succeeded`, a Worker reads the invoice to extract the billing period and creates a deferred revenue schedule.

```typescript
// workers/deferred-revenue-schedule.ts
import Stripe from "stripe";
import { v4 as uuid } from "uuid";

export async function createScheduleFromInvoice(
  stripe: Stripe,
  db: D1Database,
  invoiceId: string,
  connectedAccountId?: string
): Promise<void> {
  const invoice = await stripe.invoices.retrieve(invoiceId, {
    expand: ["lines.data.period"],
    ...(connectedAccountId
      ? { stripeAccount: connectedAccountId }
      : {}),
  });

  if (!invoice.subscription || invoice.status !== "paid") return;

  const now = new Date().toISOString();

  // An invoice can have multiple line items (proration, add-ons)
  // Create one schedule per line item with a service period
  for (const line of invoice.lines.data) {
    if (!line.period || !line.period.start || !line.period.end) continue;

    // Stripe period timestamps are Unix seconds
    const serviceStart = new Date(line.period.start * 1000)
      .toISOString()
      .slice(0, 10);
    const serviceEnd = new Date(line.period.end * 1000)
      .toISOString()
      .slice(0, 10);

    // Avoid duplicate schedules on webhook retries
    const existing = await db
      .prepare(
        `SELECT id FROM deferred_revenue_schedules
         WHERE stripe_invoice_id = ? AND service_start_date = ?`
      )
      .bind(invoiceId, serviceStart)
      .first<{ id: string }>();

    if (existing) continue;

    const scheduleId = uuid();
    const totalCents = line.amount; // can be negative for credits

    await db
      .prepare(
        `INSERT INTO deferred_revenue_schedules
         (id, stripe_subscription_id, stripe_invoice_id, customer_id, plan_id,
          currency, total_amount_cents, service_start_date, service_end_date,
          recognized_cents, deferred_cents, recognized_through, status,
          created_at, updated_at)
         VALUES (?,?,?,?,?,?,?,?,?,0,?,NULL,'active',?,?)`
      )
      .bind(
        scheduleId,
        invoice.subscription as string,
        invoiceId,
        invoice.customer as string,
        line.price?.id ?? "unknown",
        invoice.currency,
        totalCents,
        serviceStart,
        serviceEnd,
        totalCents,
        now,
        now
      )
      .run();
  }
}
```

## Nightly Recognition Job (Cron Worker)

The nightly job advances each active schedule, computing the pro-rata amount to recognize from `recognized_through` (or `service_start_date`) through yesterday. It uses a day-count method: `amount_per_day = total_cents / total_days`.

```typescript
// workers/recognition-cron.ts

interface Schedule {
  id: string;
  total_amount_cents: number;
  service_start_date: string;
  service_end_date: string;
  recognized_cents: number;
  deferred_cents: number;
  recognized_through: string | null;
}

export async function runNightlyRecognition(
  db: D1Database,
  asOfDate: string // YYYY-MM-DD, typically "yesterday"
): Promise<{ schedulesProcessed: number; totalRecognizedCents: number }> {
  const schedules = await db
    .prepare(
      `SELECT id, total_amount_cents, service_start_date, service_end_date,
              recognized_cents, deferred_cents, recognized_through
       FROM deferred_revenue_schedules
       WHERE status = 'active'
         AND service_start_date <= ?
         AND (recognized_through IS NULL OR recognized_through < ?)
         AND service_end_date > COALESCE(recognized_through, service_start_date)`
    )
    .bind(asOfDate, asOfDate)
    .all<Schedule>();

  let totalRecognizedCents = 0;

  for (const schedule of schedules.results) {
    const periodStart = schedule.recognized_through
      ? addDays(schedule.recognized_through, 1)
      : schedule.service_start_date;

    // Do not recognize beyond the service end date or asOfDate
    const periodEnd = minDate(asOfDate, schedule.service_end_date);
    if (periodStart > periodEnd) continue;

    const totalDays = daysBetween(
      schedule.service_start_date,
      schedule.service_end_date
    );
    const recognizingDays = daysBetween(periodStart, periodEnd) + 1;
    const amountCents = Math.round(
      (schedule.total_amount_cents / totalDays) * recognizingDays
    );

    const newRecognized = schedule.recognized_cents + amountCents;
    const newDeferred = schedule.total_amount_cents - newRecognized;
    const isComplete = periodEnd >= schedule.service_end_date;
    const now = new Date().toISOString();

    // Write recognition entry (UNIQUE constraint makes this idempotent)
    await db
      .prepare(
        `INSERT OR IGNORE INTO revenue_recognition_entries
         (id, schedule_id, period_start, period_end, amount_cents, currency, created_at)
         VALUES (lower(hex(randomblob(16))), ?, ?, ?, ?, 'usd', ?)`
      )
      .bind(schedule.id, periodStart, periodEnd, amountCents, now)
      .run();

    // Advance the waterfall pointer
    await db
      .prepare(
        `UPDATE deferred_revenue_schedules
         SET recognized_cents = ?,
             deferred_cents = ?,
             recognized_through = ?,
             status = ?,
             updated_at = ?
         WHERE id = ?`
      )
      .bind(
        newRecognized,
        newDeferred,
        periodEnd,
        isComplete ? "completed" : "active",
        now,
        schedule.id
      )
      .run();

    totalRecognizedCents += amountCents;
  }

  return { schedulesProcessed: schedules.results.length, totalRecognizedCents };
}

function daysBetween(a: string, b: string): number {
  return Math.round(
    (new Date(b).getTime() - new Date(a).getTime()) / 86_400_000
  );
}

function addDays(date: string, n: number): string {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function minDate(a: string, b: string): string {
  return a < b ? a : b;
}
```

## Month-End Journal Batch Query

At the end of each calendar month, generate a journal entry grouping all recognition entries for that month. Export to your accounting system (QuickBooks, Xero, NetSuite) via their API.

```typescript
// workers/month-end-journal.ts

interface JournalLine {
  plan_id: string;
  currency: string;
  total_recognized_cents: number;
  entry_count: number;
}

export async function buildMonthEndJournal(
  db: D1Database,
  year: number,
  month: number // 1-based
): Promise<JournalLine[]> {
  const periodStart = `${year}-${String(month).padStart(2, "0")}-01`;
  const lastDay = new Date(year, month, 0).getDate();
  const periodEnd = `${year}-${String(month).padStart(2, "0")}-${lastDay}`;
  const batchId = `journal_${year}_${String(month).padStart(2, "0")}`;

  // Mark entries as part of this batch
  await db
    .prepare(
      `UPDATE revenue_recognition_entries
       SET journal_batch_id = ?
       WHERE period_start >= ? AND period_end <= ? AND journal_batch_id IS NULL`
    )
    .bind(batchId, periodStart, periodEnd)
    .run();

  // Aggregate by plan for the journal entry
  const lines = await db
    .prepare(
      `SELECT s.plan_id, r.currency,
              SUM(r.amount_cents) AS total_recognized_cents,
              COUNT(*) AS entry_count
       FROM revenue_recognition_entries r
       JOIN deferred_revenue_schedules s ON s.id = r.schedule_id
       WHERE r.journal_batch_id = ?
       GROUP BY s.plan_id, r.currency`
    )
    .bind(batchId)
    .all<JournalLine>();

  return lines.results;
}
```

## Anti-patterns

- **Recognizing the full invoice amount at payment time**: Violates ASC 606. Cash receipt does not equal revenue recognition; the obligation must be fulfilled first.
- **Using calendar months instead of service period day-count**: Recognizing exactly 1/12 per month ignores partial months at the start and end of a subscription and breaks mid-cycle upgrades.
- **Not voiding schedules on refund or cancellation**: When an invoice is refunded, create a negative adjustment entry and set the schedule status to `voided`. Leaving it active causes phantom revenue.
- **Running the recognition job once per month**: Day-granularity recognition is needed to accurately represent the balance sheet on any given date, not just month-end. The nightly job keeps the ledger continuously current.
- **Failing to handle prorated line items**: Stripe emits separate line items for prorations when a plan is upgraded mid-cycle. Each must get its own schedule with its own service period.

## Gotchas

- Stripe's `invoice.lines.data[].period.start` and `period.end` timestamps are **exclusive** at the end — the period is `[start, end)`. Add 1 second to `end` and take the date part to get the inclusive end date, or subtract one day after converting.
- For annual plans, `service_end_date` is 365 or 366 days after `service_start_date`. Use actual day counts, not `total_amount / 12` per month, to avoid drift due to leap years.
- The D1 `UNIQUE (schedule_id, period_start)` constraint on `revenue_recognition_entries` ensures the nightly job is idempotent — re-running after a crash will not double-count.
- Deferred revenue decreases as a liability over time; if `deferred_cents` goes negative (rounding), clamp it to zero and absorb the penny into the final recognition entry.
- Multi-currency schedules: never convert amounts during recognition. Store the original currency and cents; convert only at reporting time using the exchange rate as of the reporting date.

## Verification

```bash
# Check total deferred liability as of today
wrangler d1 execute example project-db --command="
  SELECT currency,
         SUM(deferred_cents)/100.0 AS deferred_revenue_total
  FROM deferred_revenue_schedules
  WHERE status = 'active'
  GROUP BY currency;"

# Verify recognized + deferred = total for all active schedules
wrangler d1 execute example project-db --command="
  SELECT COUNT(*) AS bad_rows FROM deferred_revenue_schedules
  WHERE recognized_cents + deferred_cents != total_amount_cents;"
# Should return 0

# List this month's recognition entries
wrangler d1 execute example project-db --command="
  SELECT period_start, period_end, SUM(amount_cents)/100.0 AS recognized
  FROM revenue_recognition_entries
  WHERE period_start >= '2026-08-01'
  GROUP BY period_start, period_end
  ORDER BY period_start;"
```

## Related

- `revenue-recognition-saas.md` — general ASC 606 concepts for SaaS
- `stripe-revenue-recognition-input-governance.md` — Stripe's built-in revenue recognition product
- `stripe-proration-logic.md` — how Stripe computes mid-cycle proration amounts
- `stripe-subscription-lifecycle.md` — subscription state transitions
- `double-entry-ledger-payments.md` — double-entry ledger patterns in D1

## Sources

- https://stripe.com/docs/billing/revenue-recognition
- https://www.fasb.org/Page/BlobServer?blobkey=id&blobwhere=1175835492504 (ASC 606)
- https://developers.cloudflare.com/d1/
- https://stripe.com/docs/api/invoices/line_item#invoice_line_item_object-period
