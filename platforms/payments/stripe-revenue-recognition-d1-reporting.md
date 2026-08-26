# Stripe Revenue Recognition and Financial Reporting with D1

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

SaaS platforms billing through Stripe need to recognise revenue in compliance with ASC 606 / IFRS 15 — booking cash to deferred revenue on invoice creation and releasing it into earned revenue pro-rata over the service period. Manual spreadsheet-based recognition breaks down past a few hundred subscriptions and introduces audit risk.

## Context

Cloudflare D1 provides a serverless SQL store that lives at the edge alongside your Workers. By syncing Stripe Invoice and Charge events into D1 at webhook time, you can run period-end recognition queries, calculate MRR/ARR, and export GAAP-compliant journals — all without standing up a separate data warehouse. A Workers cron trigger drives nightly and month-end batch jobs.

## Storing Stripe Invoices and Charges in D1

Create the schema once via a migration. Every Stripe `invoice.paid` and `charge.succeeded` webhook upserts a row, capturing the service period dates Stripe embeds in subscription line items.

```typescript
// schema.sql (run via wrangler d1 execute)
// CREATE TABLE stripe_invoices (
//   id TEXT PRIMARY KEY,
//   customer_id TEXT NOT NULL,
//   subscription_id TEXT,
//   amount_paid INTEGER NOT NULL,   -- cents
//   currency TEXT NOT NULL,
//   status TEXT NOT NULL,
//   period_start INTEGER NOT NULL,  -- unix timestamp
//   period_end INTEGER NOT NULL,
//   invoice_date INTEGER NOT NULL,
//   created_at INTEGER NOT NULL DEFAULT (unixepoch())
// );
// CREATE INDEX idx_si_period ON stripe_invoices(period_start, period_end);
// CREATE INDEX idx_si_customer ON stripe_invoices(customer_id);

// src/webhooks/stripe.ts
import Stripe from 'stripe';

export async function handleStripeWebhook(
  request: Request,
  env: Env,
): Promise<Response> {
  const sig = request.headers.get('stripe-signature') ?? '';
  const body = await request.text();

  let event: Stripe.Event;
  try {
    const stripe = new Stripe(env.STRIPE_SECRET_KEY);
    event = await stripe.webhooks.constructEventAsync(
      body,
      sig,
      env.STRIPE_WEBHOOK_SECRET,
    );
  } catch {
    return new Response('Bad signature', { status: 400 });
  }

  if (event.type === 'invoice.paid') {
    const inv = event.data.object as Stripe.Invoice;
    const line = inv.lines.data[0];
    const periodStart = line?.period?.start ?? Math.floor(Date.now() / 1000);
    const periodEnd = line?.period?.end ?? periodStart;

    await env.DB.prepare(
      `INSERT OR REPLACE INTO stripe_invoices
         (id, customer_id, subscription_id, amount_paid, currency,
          status, period_start, period_end, invoice_date)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        inv.id,
        inv.customer as string,
        inv.subscription as string | null,
        inv.amount_paid,
        inv.currency,
        inv.status,
        periodStart,
        periodEnd,
        inv.created,
      )
      .run();
  }

  return new Response('ok');
}
```

## ASC 606 Deferred Revenue Recognition

Revenue earned in a period equals the fraction of each invoice's service window that falls within that period. The query below returns the recognised amount for a given calendar month.

```typescript
// src/revenue/recognition.ts
export interface RecognitionRow {
  invoice_id: string;
  customer_id: string;
  recognised_cents: number;
  currency: string;
}

export async function recognisedRevenue(
  db: D1Database,
  periodStart: Date,
  periodEnd: Date,
): Promise<RecognitionRow[]> {
  const ps = Math.floor(periodStart.getTime() / 1000);
  const pe = Math.floor(periodEnd.getTime() / 1000);

  // overlap = min(period_end, pe) - max(period_start, ps)
  // recognised = amount_paid * overlap / (period_end - period_start)
  const { results } = await db
    .prepare(
      `SELECT
         id                                                           AS invoice_id,
         customer_id,
         currency,
         CAST(
           amount_paid *
           CAST(MIN(period_end, ?) - MAX(period_start, ?) AS REAL) /
           CAST(period_end - period_start AS REAL)
           AS INTEGER
         )                                                           AS recognised_cents
       FROM stripe_invoices
       WHERE status = 'paid'
         AND period_start < ?
         AND period_end   > ?
         AND period_end  != period_start`,
    )
    .bind(pe, ps, pe, ps)
    .all<RecognitionRow>();

  return results;
}

export async function deferredRevenueBalance(
  db: D1Database,
  asOf: Date,
): Promise<number> {
  const ts = Math.floor(asOf.getTime() / 1000);
  const row = await db
    .prepare(
      `SELECT SUM(
         CAST(amount_paid *
           CAST(period_end - MAX(period_start, ?) AS REAL) /
           CAST(period_end - period_start AS REAL)
         AS INTEGER)
       ) AS deferred
       FROM stripe_invoices
       WHERE status = 'paid'
         AND period_end > ?
         AND period_end != period_start`,
    )
    .bind(ts, ts)
    .first<{ deferred: number }>();

  return row?.deferred ?? 0;
}
```

## MRR / ARR Queries and Cron Export

A Workers cron scheduled trigger runs nightly, calculates MRR, and appends a snapshot row to `mrr_snapshots`. A separate endpoint exports CSV for upload to QuickBooks or Xero.

```typescript
// src/revenue/mrr.ts
export async function calculateMRR(
  db: D1Database,
  asOf: Date,
): Promise<number> {
  const ts = Math.floor(asOf.getTime() / 1000);
  // Active subscriptions: invoices whose service window straddles asOf
  const row = await db
    .prepare(
      `SELECT SUM(
         CAST(amount_paid * 2592000.0 /
           (period_end - period_start)
         AS INTEGER)
       ) AS mrr
       FROM stripe_invoices
       WHERE status = 'paid'
         AND period_start <= ?
         AND period_end   >  ?
         AND (period_end - period_start) > 0`,
    )
    .bind(ts, ts)
    .first<{ mrr: number }>();

  return row?.mrr ?? 0;
}

// wrangler.toml cron: "0 2 * * *"
export async function cronHandler(env: Env): Promise<void> {
  const now = new Date();
  const mrr = await calculateMRR(env.DB, now);
  const arr = mrr * 12;

  await env.DB.prepare(
    `INSERT INTO mrr_snapshots (snapshot_date, mrr_cents, arr_cents)
     VALUES (?, ?, ?)`,
  )
    .bind(Math.floor(now.getTime() / 1000), mrr, arr)
    .run();

  // Period-end: if first day of month, emit recognition journal
  if (now.getUTCDate() === 1) {
    const monthStart = new Date(
      Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1),
    );
    const monthEnd = new Date(
      Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1),
    );
    const rows = await recognisedRevenue(env.DB, monthStart, monthEnd);
    const csv = [
      'invoice_id,customer_id,currency,recognised_cents',
      ...rows.map(
        (r) =>
          `${r.invoice_id},${r.customer_id},${r.currency},${r.recognised_cents}`,
      ),
    ].join('\n');

    await env.EXPORT_BUCKET.put(
      `revenue-journals/${monthStart.toISOString().slice(0, 7)}.csv`,
      csv,
      { httpMetadata: { contentType: 'text/csv' } },
    );
  }
}
```

## Anti-patterns

- Recognising 100% of an invoice's value on the cash receipt date violates ASC 606 for multi-period subscriptions and overstates current-period revenue.
- Joining Stripe's `/invoices` REST endpoint in real-time during period-end reporting — fetch rates become prohibitive at scale; store events at webhook time instead.
- Using `FLOAT` columns for monetary amounts in D1; rounding errors accumulate — always store cents as `INTEGER`.

## Gotchas

- Stripe subscription line items carry `period.start` / `period.end` but one-off invoice items do not; guard with a fallback (e.g. `invoice_date` to `invoice_date`) and treat the full amount as immediately recognised.
- Month-length variance (28–31 days) means using a fixed 2 592 000-second month for MRR normalisation introduces small distortions; document this assumption in your accounting policy.

## Verification

```bash
# Run schema migration
wrangler d1 execute example project-db --file=schema.sql

# Query deferred revenue as of today
wrangler d1 execute example project-db \
  --command "SELECT SUM(amount_paid) FROM stripe_invoices WHERE period_end > unixepoch();"

# Trigger cron locally
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+2+*+*+*"
```

## Related

- `payments/deferred-revenue-waterfall-d1.md`
- `payments/stripe-webhook-idempotency-d1-event-log.md`
- `payments/mrr-arr-calculation.md`
- `payments/stripe-metered-billing.md`

## Sources

- https://stripe.com/docs/revenue-recognition
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
- https://asc.fasb.org/606
