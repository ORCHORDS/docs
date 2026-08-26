# Revenue Leakage Detection Analytics Engine Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You want to automatically detect when revenue is lost through uncaptured authorizations, unprocessed subscription renewals, dunning failures, or uncollected usage-based billing — and surface these gaps in a real-time dashboard backed by Cloudflare Analytics Engine.

## Context
Revenue leakage is the gap between what customers owe and what you actually collect. Common sources include: uncaptured PaymentIntent authorizations expiring after 7 days, metered billing events that never reach Stripe, subscriptions that enter `past_due` and churn before being retried, and refunds issued without corresponding credit notes. Workers emit structured data points to Analytics Engine on every payment lifecycle event; a scheduled Worker runs daily reconciliation queries against D1 and writes leakage signals back to Analytics Engine for Grafana or your own dashboard.

## Analytics Engine Schema Design

Analytics Engine uses a schemaless write model. Define a consistent index/blob/double layout per event type using a naming convention rather than a DDL migration.

```typescript
// src/ae-schema.ts
export interface Env {
  AE: AnalyticsEngineDataset;
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
}

// Revenue Leakage event types written to Analytics Engine
export type LeakageEventType =
  | 'auth_expired_uncaptured'
  | 'invoice_voided_unpaid'
  | 'subscription_past_due_lapsed'
  | 'metered_event_missing'
  | 'refund_without_credit_note'
  | 'dunning_exhausted';

/**
 * Write a leakage signal to Analytics Engine.
 * Layout:
 *   indexes: [eventType, customerId, currency]
 *   blobs:   [orderId, subscriptionId, details]
 *   doubles: [leakageAmountCents, chargedAmountCents]
 */
export function writeLeakageEvent(
  ae: AnalyticsEngineDataset,
  event: {
    type: LeakageEventType;
    customerId: string;
    currency: string;
    orderId?: string;
    subscriptionId?: string;
    details?: string;
    leakageAmountCents: number;
    chargedAmountCents: number;
  }
): void {
  ae.writeDataPoint({
    indexes: [event.type, event.customerId, event.currency],
    blobs: [event.orderId ?? '', event.subscriptionId ?? '', event.details ?? ''],
    doubles: [event.leakageAmountCents, event.chargedAmountCents],
  });
}
```

## Real-Time Leakage Detection on Payment Events

Instrument your existing payment lifecycle endpoints to emit leakage signals immediately when a problematic event occurs.

```typescript
// src/payment-lifecycle.ts
import { writeLeakageEvent, Env, LeakageEventType } from './ae-schema';

interface StripePaymentIntent {
  id: string;
  status: string;
  amount: number;
  currency: string;
  customer: string;
  metadata: Record<string, string>;
}

/**
 * Called from a stripe webhook handler on payment_intent.canceled
 * Detect if the cancellation was due to an uncaptured authorization expiring.
 */
export async function handlePaymentIntentCanceled(
  env: Env,
  pi: StripePaymentIntent
): Promise<void> {
  // If the PI was authorized (captured=false) and is now canceled, it's a leakage event
  if (pi.status === 'canceled') {
    const row = await env.DB.prepare(
      `SELECT captured, order_id, customer_id FROM payment_intents
       WHERE stripe_pi_id = ? AND captured = 0`
    )
      .bind(pi.id)
      .first<{ captured: number; order_id: string; customer_id: string }>();

    if (row) {
      writeLeakageEvent(env.AE, {
        type: 'auth_expired_uncaptured',
        customerId: pi.customer ?? row.customer_id,
        currency: pi.currency,
        orderId: row.order_id,
        details: `PaymentIntent ${pi.id} authorized but never captured`,
        leakageAmountCents: pi.amount,
        chargedAmountCents: 0,
      });
    }
  }
}

/**
 * Called from invoice.voided webhook.
 * An invoice voided while still carrying an outstanding balance is a leakage event.
 */
export async function handleInvoiceVoided(
  env: Env,
  invoice: {
    id: string;
    customer: string;
    amount_due: number;
    amount_paid: number;
    currency: string;
    subscription: string | null;
  }
): Promise<void> {
  const uncollected = invoice.amount_due - invoice.amount_paid;
  if (uncollected > 0) {
    writeLeakageEvent(env.AE, {
      type: 'invoice_voided_unpaid',
      customerId: invoice.customer,
      currency: invoice.currency,
      subscriptionId: invoice.subscription ?? undefined,
      details: `Invoice ${invoice.id} voided with ${uncollected} cents uncollected`,
      leakageAmountCents: uncollected,
      chargedAmountCents: invoice.amount_paid,
    });
  }
}
```

## Daily Reconciliation Job

A scheduled Worker runs nightly to identify systemic leakage patterns that are not caught event-by-event: subscriptions that never retried after dunning exhaustion, and usage records that should have generated invoices but did not.

```typescript
// src/reconciliation.ts
import { writeLeakageEvent, Env } from './ae-schema';

export async function runDailyReconciliation(env: Env): Promise<void> {
  await Promise.all([
    reconcileDunningExhausted(env),
    reconcileSubscriptionLapsed(env),
    detectMissingMeteredEvents(env),
  ]);
}

async function reconcileDunningExhausted(env: Env): Promise<void> {
  // Find invoices still unpaid 30+ days after dunning_start_at
  const stale = await env.DB.prepare(
    `SELECT invoice_id, customer_id, amount_due_cents, currency, subscription_id
     FROM invoices
     WHERE status = 'open'
       AND dunning_exhausted_at IS NOT NULL
       AND dunning_exhausted_at < unixepoch() - 86400 * 30
       AND leakage_reported = 0
     LIMIT 200`
  ).all<{
    invoice_id: string;
    customer_id: string;
    amount_due_cents: number;
    currency: string;
    subscription_id: string;
  }>();

  for (const row of stale.results) {
    writeLeakageEvent(env.AE, {
      type: 'dunning_exhausted',
      customerId: row.customer_id,
      currency: row.currency,
      subscriptionId: row.subscription_id,
      details: `Invoice ${row.invoice_id} dunning exhausted, 30+ days unpaid`,
      leakageAmountCents: row.amount_due_cents,
      chargedAmountCents: 0,
    });

    await env.DB.prepare(
      'UPDATE invoices SET leakage_reported = 1 WHERE invoice_id = ?'
    )
      .bind(row.invoice_id)
      .run();
  }
}

async function reconcileSubscriptionLapsed(env: Env): Promise<void> {
  // Subscriptions that entered past_due > 14 days ago and have no recent payment attempt
  const lapsed = await env.DB.prepare(
    `SELECT s.id, s.customer_id, s.plan_amount_cents, s.currency
     FROM subscriptions s
     WHERE s.status = 'past_due'
       AND s.past_due_since < unixepoch() - 86400 * 14
       AND NOT EXISTS (
         SELECT 1 FROM payment_attempts pa
         WHERE pa.subscription_id = s.id
           AND pa.created_at > unixepoch() - 86400 * 7
       )
     LIMIT 100`
  ).all<{
    id: string;
    customer_id: string;
    plan_amount_cents: number;
    currency: string;
  }>();

  for (const row of lapsed.results) {
    writeLeakageEvent(env.AE, {
      type: 'subscription_past_due_lapsed',
      customerId: row.customer_id,
      currency: row.currency,
      subscriptionId: row.id,
      details: `Subscription past_due 14+ days with no retry`,
      leakageAmountCents: row.plan_amount_cents,
      chargedAmountCents: 0,
    });
  }
}

async function detectMissingMeteredEvents(env: Env): Promise<void> {
  // Usage-based subscriptions that have zero meter events in the last billing period
  const silent = await env.DB.prepare(
    `SELECT s.id, s.customer_id, s.currency, s.plan_amount_cents
     FROM subscriptions s
     WHERE s.billing_scheme = 'metered'
       AND s.status = 'active'
       AND s.current_period_start < unixepoch() - 86400 * 7
       AND (
         SELECT COUNT(*)
         FROM meter_events me
         WHERE me.subscription_id = s.id
           AND me.timestamp > s.current_period_start
       ) = 0
     LIMIT 100`
  ).all<{
    id: string;
    customer_id: string;
    currency: string;
    plan_amount_cents: number;
  }>();

  for (const row of silent.results) {
    writeLeakageEvent(env.AE, {
      type: 'metered_event_missing',
      customerId: row.customer_id,
      currency: row.currency,
      subscriptionId: row.id,
      details: 'No meter events in 7+ days on active metered subscription',
      leakageAmountCents: row.plan_amount_cents,
      chargedAmountCents: 0,
    });
  }
}
```

## Analytics Engine Query API

Expose a `/reports/leakage` endpoint that queries Analytics Engine via the REST API for aggregated leakage data.

```typescript
// src/leakage-report.ts
export async function queryLeakageSummary(
  accountId: string,
  datasetName: string,
  apiToken: string,
  sinceHours = 168 // default: last 7 days
): Promise<Response> {
  const sql = `
    SELECT
      index1                                         AS event_type,
      index3                                         AS currency,
      COUNT()                                        AS occurrences,
      SUM(double1)                                   AS total_leakage_cents,
      SUM(double2)                                   AS total_charged_cents
    FROM ${datasetName}
    WHERE timestamp > NOW() - INTERVAL '${sinceHours}' HOUR
    GROUP BY index1, index3
    ORDER BY total_leakage_cents DESC
  `;

  return fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );
}
```

## Worker Entry Point

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env & {
    CF_ACCOUNT_ID: string;
    CF_API_TOKEN: string;
    AE_DATASET: string;
  }): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/webhook/stripe' && request.method === 'POST') {
      const event = await request.json<{
        type: string;
        data: { object: Record<string, unknown> };
      }>();

      if (event.type === 'payment_intent.canceled') {
        await handlePaymentIntentCanceled(env, event.data.object as StripePaymentIntent);
      } else if (event.type === 'invoice.voided') {
        await handleInvoiceVoided(env, event.data.object as Parameters<typeof handleInvoiceVoided>[1]);
      }

      return new Response('OK');
    }

    if (url.pathname === '/reports/leakage') {
      const hours = parseInt(url.searchParams.get('hours') ?? '168', 10);
      const upstreamRes = await queryLeakageSummary(
        env.CF_ACCOUNT_ID,
        env.AE_DATASET,
        env.CF_API_TOKEN,
        hours
      );
      const data = await upstreamRes.json();
      return Response.json(data);
    }

    return new Response('Not Found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await runDailyReconciliation(env);
  },
};
```

## Anti-patterns
- Do not query D1 in real-time to aggregate leakage for dashboards — D1 is not designed for analytical fan-out queries; always use Analytics Engine or Hyperdrive + Postgres for reporting.
- Avoid writing duplicate leakage events for the same source record; use the `leakage_reported` flag in D1 or a KV deduplication key with a 24-hour TTL.
- Never rely solely on Stripe webhooks for leakage detection — events can be delayed or missed; always back them with a scheduled reconciliation job.
- Do not emit a leakage event for every retry attempt; debounce by checking final state after the last retry before writing to Analytics Engine.
- Avoid mixing financial amounts with non-financial signals in the same Analytics Engine dataset; the `doubles` array is fixed-position and mixing semantics corrupts aggregations.

## Gotchas
- Analytics Engine data is eventually consistent and may lag by up to 60 seconds; do not use it for real-time fraud checks, only for trend analysis.
- The Analytics Engine SQL API `index1/index2/index3` naming is positional — if you reorder the `writeDataPoint` call's `indexes` array, historical queries break silently.
- Cloudflare Analytics Engine has a maximum of 20 data points per `writeDataPoint` call across all blobs and doubles combined.
- Workers environment bindings named `AE` require `type = "analytics_engine"` in `wrangler.toml` with a matching `dataset` name — forgetting the binding type causes a `TypeError` at runtime.
- Scheduled Workers run in a separate isolate from the fetch handler; bindings like `AE` must be declared in `[triggers]` context, not just the fetch handler.

## Verification
1. Trigger a `payment_intent.canceled` event via Stripe CLI and confirm a leakage data point appears in Analytics Engine within 60 seconds.
2. Manually run `runDailyReconciliation` and verify `leakage_reported` is set to `1` on qualifying invoice rows.
3. Call `GET /reports/leakage?hours=1` and confirm the response includes the test events written in steps 1-2.
4. Insert a subscription row with `status=past_due` and `past_due_since` 15 days ago and re-run reconciliation; confirm `subscription_past_due_lapsed` events appear.
5. Verify Analytics Engine dataset columns with: `SELECT * FROM dataset WHERE timestamp > NOW() - INTERVAL '1' HOUR LIMIT 10`.

## Related
- `payment-analytics-cohort-retention-d1.md`
- `payment-audit-logging.md`
- `stripe-metered-billing.md`
- `payment-dunning-management-cloudflare-queues.md`
- `payment-reconciliation-settlement.md`

## Sources
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://stripe.com/docs/billing/revenue-recovery
