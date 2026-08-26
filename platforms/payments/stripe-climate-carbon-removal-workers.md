# Stripe Climate Carbon Removal Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You want to embed Stripe Climate into your checkout flow so that a configurable percentage of every transaction automatically funds verified carbon removal projects, with contribution amounts logged to D1 for sustainability reporting.

## Context
Stripe Climate is a program that routes a fraction of revenue to carbon removal companies vetted by Stripe. It operates in two modes: (1) a platform-level toggle in the Stripe Dashboard that applies a fixed percentage to all charges, and (2) a per-charge `stripe_climate_order_amount` on the PaymentIntent metadata for session-level control. The Workers layer handles per-order climate contribution calculation, records contributions to D1, and exposes a reporting endpoint for your sustainability dashboard.

## Stripe Climate Contribution Calculation

```typescript
// src/climate.ts
export interface Env {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
  CLIMATE_CONTRIBUTION_BPS: string; // e.g. "100" = 1% (100 basis points)
}

export interface ClimateContribution {
  orderId: string;
  chargeCents: number;
  contributionCents: number;
  currency: string;
  projectAllocationId?: string; // returned by Stripe API if available
  createdAt: number;
}

/**
 * Compute the Stripe Climate contribution amount given a charge total.
 * Stripe recommends rounding down to avoid exceeding the intended percentage.
 */
export function computeContributionCents(
  chargeCents: number,
  contributionBps: number
): number {
  return Math.floor((chargeCents * contributionBps) / 10000);
}

/**
 * Create a PaymentIntent with Stripe Climate metadata attached.
 * Stripe will automatically route the contribution to carbon removal
 * if Climate is enabled on the account.
 */
export async function createClimateAwarePaymentIntent(
  env: Env,
  params: {
    orderId: string;
    amountCents: number;
    currency: string;
    customerId: string;
    paymentMethodId: string;
  }
): Promise<{ paymentIntentId: string; contributionCents: number }> {
  const bps = parseInt(env.CLIMATE_CONTRIBUTION_BPS, 10);
  const contributionCents = computeContributionCents(params.amountCents, bps);

  const body = new URLSearchParams({
    amount: String(params.amountCents),
    currency: params.currency,
    customer: params.customerId,
    payment_method: params.paymentMethodId,
    confirm: 'true',
    'metadata[order_id]': params.orderId,
    'metadata[climate_contribution_cents]': String(contributionCents),
    'metadata[climate_contribution_bps]': String(bps),
    // Stripe Climate reads this metadata key to register the contribution
    'metadata[stripe_climate]': 'true',
  });

  const res = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      'Stripe-Version': '2025-06-30',
    },
    body,
  });

  if (!res.ok) {
    const err = await res.json<{ error: { message: string } }>();
    throw new Error(`Stripe PI error: ${err.error.message}`);
  }

  const pi = await res.json<{ id: string }>();
  return { paymentIntentId: pi.id, contributionCents };
}
```

## D1 Schema and Contribution Recording

```sql
-- migrations/001_climate.sql
CREATE TABLE IF NOT EXISTS climate_contributions (
  id                    TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  order_id              TEXT NOT NULL UNIQUE,
  payment_intent_id     TEXT NOT NULL,
  charge_cents          INTEGER NOT NULL,
  contribution_cents    INTEGER NOT NULL,
  contribution_bps      INTEGER NOT NULL,
  currency              TEXT NOT NULL,
  project_name          TEXT,
  status                TEXT NOT NULL DEFAULT 'pending',  -- pending|confirmed|cancelled
  confirmed_at          INTEGER,
  created_at            INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_climate_created ON climate_contributions(created_at);
CREATE INDEX IF NOT EXISTS idx_climate_status  ON climate_contributions(status);
```

```typescript
// src/climate-d1.ts
export async function recordContribution(
  db: D1Database,
  contribution: {
    orderId: string;
    paymentIntentId: string;
    chargeCents: number;
    contributionCents: number;
    contributionBps: number;
    currency: string;
  }
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO climate_contributions
         (order_id, payment_intent_id, charge_cents, contribution_cents, contribution_bps, currency)
       VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(order_id) DO NOTHING`
    )
    .bind(
      contribution.orderId,
      contribution.paymentIntentId,
      contribution.chargeCents,
      contribution.contributionCents,
      contribution.contributionBps,
      contribution.currency
    )
    .run();
}

export async function confirmContribution(
  db: D1Database,
  orderId: string,
  projectName?: string
): Promise<void> {
  await db
    .prepare(
      `UPDATE climate_contributions
       SET status = 'confirmed', project_name = ?, confirmed_at = unixepoch()
       WHERE order_id = ?`
    )
    .bind(projectName ?? null, orderId)
    .run();
}
```

## Webhook Handler for Charge Confirmation

Listen for `payment_intent.succeeded` to mark contributions confirmed. Stripe does not send a dedicated Climate event; you reconcile via the charge metadata.

```typescript
// src/climate-webhook.ts
import { confirmContribution } from './climate-d1';

interface StripeEvent {
  type: string;
  data: {
    object: {
      id: string;
      metadata: Record<string, string>;
      status: string;
    };
  };
}

export async function handleStripeWebhook(
  request: Request,
  env: Env & { STRIPE_WEBHOOK_SECRET: string }
): Promise<Response> {
  const body = await request.text();
  const sig = request.headers.get('stripe-signature') ?? '';

  // Signature verification using Web Crypto (HMAC-SHA256)
  const valid = await verifyStripeSignature(body, sig, env.STRIPE_WEBHOOK_SECRET);
  if (!valid) return new Response('Unauthorized', { status: 401 });

  const event: StripeEvent = JSON.parse(body);

  if (event.type === 'payment_intent.succeeded') {
    const pi = event.data.object;
    const orderId = pi.metadata['order_id'];
    const isClimate = pi.metadata['stripe_climate'] === 'true';

    if (orderId && isClimate) {
      // In production, fetch the Stripe Climate order from the API for project details
      await confirmContribution(env.DB, orderId);
    }
  }

  return new Response('OK');
}

async function verifyStripeSignature(
  payload: string,
  header: string,
  secret: string
): Promise<boolean> {
  const parts = Object.fromEntries(header.split(',').map((p) => p.split('=')));
  const timestamp = parts['t'];
  const signature = parts['v1'];
  if (!timestamp || !signature) return false;

  const signedPayload = `${timestamp}.${payload}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(signedPayload));
  const hex = Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return hex === signature;
}
```

## Sustainability Reporting Endpoint

```typescript
// src/climate-report.ts
export interface ClimateReport {
  totalContributionCents: number;
  totalChargesCents: number;
  effectiveBps: number;
  contributionsByMonth: { month: string; contributionCents: number }[];
  status: { pending: number; confirmed: number; cancelled: number };
}

export async function getClimateReport(db: D1Database): Promise<ClimateReport> {
  const [totals, monthly, statuses] = await db.batch([
    db.prepare(
      `SELECT
         SUM(contribution_cents) AS total_contribution,
         SUM(charge_cents)       AS total_charges,
         ROUND(SUM(contribution_cents) * 10000.0 / NULLIF(SUM(charge_cents), 0), 1) AS effective_bps
       FROM climate_contributions
       WHERE status != 'cancelled'`
    ),
    db.prepare(
      `SELECT
         strftime('%Y-%m', datetime(created_at, 'unixepoch')) AS month,
         SUM(contribution_cents) AS contribution_cents
       FROM climate_contributions
       WHERE status != 'cancelled'
       GROUP BY month
       ORDER BY month DESC
       LIMIT 12`
    ),
    db.prepare(
      `SELECT status, COUNT(*) AS cnt FROM climate_contributions GROUP BY status`
    ),
  ]);

  const t = (totals.results[0] ?? {}) as {
    total_contribution: number;
    total_charges: number;
    effective_bps: number;
  };

  const statusMap: Record<string, number> = {};
  for (const row of statuses.results as { status: string; cnt: number }[]) {
    statusMap[row.status] = row.cnt;
  }

  return {
    totalContributionCents: t.total_contribution ?? 0,
    totalChargesCents: t.total_charges ?? 0,
    effectiveBps: t.effective_bps ?? 0,
    contributionsByMonth: monthly.results as { month: string; contributionCents: number }[],
    status: {
      pending: statusMap['pending'] ?? 0,
      confirmed: statusMap['confirmed'] ?? 0,
      cancelled: statusMap['cancelled'] ?? 0,
    },
  };
}
```

## Worker Entry Point

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env & { STRIPE_WEBHOOK_SECRET: string }): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/checkout' && request.method === 'POST') {
      const params = await request.json<Parameters<typeof createClimateAwarePaymentIntent>[1]>();
      const result = await createClimateAwarePaymentIntent(env, params);
      await recordContribution(env.DB, {
        orderId: params.orderId,
        paymentIntentId: result.paymentIntentId,
        chargeCents: params.amountCents,
        contributionCents: result.contributionCents,
        contributionBps: parseInt(env.CLIMATE_CONTRIBUTION_BPS, 10),
        currency: params.currency,
      });
      return Response.json(result, { status: 201 });
    }

    if (url.pathname === '/webhook/stripe' && request.method === 'POST') {
      return handleStripeWebhook(request, env);
    }

    if (url.pathname === '/reports/climate' && request.method === 'GET') {
      const report = await getClimateReport(env.DB);
      return Response.json(report);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Anti-patterns
- Do not use the Dashboard toggle and per-charge metadata simultaneously without understanding double-counting — the platform-level setting routes at Stripe's side independent of your metadata.
- Avoid setting `CLIMATE_CONTRIBUTION_BPS` above 100 (1%) without confirming the account plan; higher rates require explicit Stripe approval.
- Never hard-code carbon project names in your D1 schema — Stripe allocates across projects dynamically; treat project attribution as informational, not contractual.
- Do not expose raw contribution details in public-facing APIs without confirming Stripe's data sharing policy for Climate participants.
- Avoid skipping webhook confirmation step; a PaymentIntent can be created but never paid (abandoned checkout), leaving the contribution row stuck in `pending` indefinitely.

## Gotchas
- Stripe Climate is only available in specific countries and currencies; charges in unsupported currencies are silently excluded from Climate routing.
- The `stripe_climate` metadata key is not an official Stripe API parameter — it is a convention used to tag your own records; Stripe Climate routing is configured separately in the Dashboard.
- Contribution amounts must be tracked in your own D1 because Stripe does not expose per-charge Climate contribution breakdowns in the PaymentIntent object directly.
- When a charge is refunded, the Climate contribution is not automatically reversed by Stripe; you need a `charge.refunded` webhook handler to cancel or adjust the contribution record.
- D1 `strftime` requires the datetime to be in a valid SQLite format; always store timestamps as Unix epoch integers and use `datetime(col, 'unixepoch')` in queries.

## Verification
1. Set `CLIMATE_CONTRIBUTION_BPS=100` (1%) and create a charge for $50.00; confirm `contributionCents = 50` in D1.
2. Trigger a `payment_intent.succeeded` webhook event via Stripe CLI (`stripe trigger payment_intent.succeeded`) and confirm the D1 row transitions to `confirmed`.
3. Call `GET /reports/climate` and verify `totalContributionCents` and `effectiveBps` are non-zero.
4. Create a charge and immediately refund it; confirm your `charge.refunded` handler updates the contribution status to `cancelled`.
5. Run `SELECT SUM(contribution_cents) / 100.0 FROM climate_contributions WHERE status = 'confirmed'` and compare against your Stripe Climate Dashboard balance.

## Related
- `stripe-checkout-session-cloudflare-workers.md`
- `stripe-webhook-idempotency-d1-event-log.md`
- `stripe-revenue-recognition-d1-reporting.md`
- `payment-analytics-cohort-retention-d1.md`

## Sources
- https://stripe.com/climate
- https://stripe.com/docs/climate
- https://stripe.com/docs/webhooks/signature-verification
