# Recurring Donation Platform with Stripe, Workers, and D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A nonprofit or creator platform needs to accept recurring donations: donors choose an amount (preset or custom), a frequency (monthly, quarterly, annually), and optionally dedicate the gift. They must be able to update or cancel at any time from a self-service portal without contacting support. Tax receipts must be generated automatically at year-end. Donation history must be queryable for donor acknowledgment campaigns.

## Context

Recurring donations map cleanly onto Stripe Subscriptions with a few non-standard requirements: arbitrary amounts (no fixed price tiers), human-friendly cancellation flows that capture a reason, and annual aggregated receipts rather than per-invoice receipts. Use Stripe's `customer.balance` credit system for donation credits, `Subscription` with `billing_cycle_anchor` for consistent debit dates, and Workers + D1 to store extended donor metadata, receipt state, and campaign attribution that Stripe's data model doesn't carry natively.

---

## 1. D1 Schema

```sql
-- migrations/0013_donations.sql
CREATE TABLE IF NOT EXISTS donors (
  id              TEXT PRIMARY KEY,       -- Stripe customer id (cus_xxx)
  email           TEXT NOT NULL,
  display_name    TEXT,
  tax_id          TEXT,                   -- for gift-aid or EIN lookups
  created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS donation_subscriptions (
  id                TEXT PRIMARY KEY,     -- Stripe subscription id (sub_xxx)
  donor_id          TEXT NOT NULL,
  amount_cents      INTEGER NOT NULL,
  currency          TEXT NOT NULL DEFAULT 'usd',
  interval          TEXT NOT NULL,        -- 'month' | 'quarter' | 'year'
  campaign_id       TEXT,
  dedication        TEXT,                 -- optional dedication message
  status            TEXT NOT NULL,        -- mirrors Stripe status
  cancel_reason     TEXT,
  created_at        INTEGER NOT NULL,
  updated_at        INTEGER NOT NULL,
  FOREIGN KEY (donor_id) REFERENCES donors(id)
);

CREATE TABLE IF NOT EXISTS donation_payments (
  id              TEXT PRIMARY KEY,       -- Stripe invoice id (in_xxx)
  subscription_id TEXT NOT NULL,
  donor_id        TEXT NOT NULL,
  amount_cents    INTEGER NOT NULL,
  currency        TEXT NOT NULL,
  paid_at         INTEGER NOT NULL,
  receipt_sent    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_donations_donor ON donation_subscriptions (donor_id);
CREATE INDEX IF NOT EXISTS idx_payments_donor ON donation_payments (donor_id, paid_at DESC);
```

## 2. Checkout: Creating a Recurring Donation Subscription

```typescript
// src/create-donation.ts
import Stripe from 'stripe';
import { Env } from './types';

interface DonationRequest {
  email: string;
  displayName: string;
  amountCents: number;          // donor-chosen amount
  interval: 'month' | 'year';
  campaignId?: string;
  dedication?: string;
}

export async function createDonation(body: DonationRequest, env: Env): Promise<Response> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

  // Retrieve or create a Stripe customer
  let customer: Stripe.Customer;
  const existing = await stripe.customers.list({ email: body.email, limit: 1 });
  if (existing.data.length) {
    customer = existing.data[0];
  } else {
    customer = await stripe.customers.create({
      email: body.email,
      name: body.displayName,
      metadata: { source: 'donation-portal' },
    });

    await env.DB.prepare(
      'INSERT OR IGNORE INTO donors (id, email, display_name, created_at) VALUES (?, ?, ?, ?)'
    ).bind(customer.id, body.email, body.displayName, Math.floor(Date.now() / 1000)).run();
  }

  // Create an ad-hoc Price for the custom amount
  // Using lookup_key allows idempotent price creation per amount+interval
  const lookupKey = `donation_${body.amountCents}_${body.interval}`;
  let price: Stripe.Price;
  const priceList = await stripe.prices.list({ lookup_keys: [lookupKey], limit: 1 });

  if (priceList.data.length) {
    price = priceList.data[0];
  } else {
    price = await stripe.prices.create({
      unit_amount: body.amountCents,
      currency: 'usd',
      recurring: {
        interval: body.interval === 'month' ? 'month' : 'year',
      },
      product_data: { name: 'Recurring Donation' },
      lookup_key: lookupKey,
      transfer_lookup_key: false,
    });
  }

  // Create the subscription, collect payment via Checkout
  const session = await stripe.checkout.sessions.create({
    customer: customer.id,
    mode: 'subscription',
    line_items: [{ price: price.id, quantity: 1 }],
    subscription_data: {
      metadata: {
        campaign_id: body.campaignId ?? '',
        dedication: body.dedication ?? '',
      },
      billing_cycle_anchor_config: {
        // Bill on the 1st of each period for predictable debit dates
        day_of_month: 1,
      },
    },
    success_url: 'https://example.org/donate/thank-you?session_id={CHECKOUT_SESSION_ID}',
    cancel_url: 'https://example.org/donate',
  });

  return Response.json({ url: session.url });
}
```

## 3. Webhook Handler: Subscription and Invoice Events

```typescript
// src/webhooks.ts
import Stripe from 'stripe';
import { Env } from './types';

export async function handleWebhook(req: Request, env: Env): Promise<Response> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
  const sig = req.headers.get('stripe-signature')!;
  const body = await req.text();

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig, env.STRIPE_WEBHOOK_SECRET);
  } catch {
    return new Response('Invalid signature', { status: 400 });
  }

  const now = Math.floor(Date.now() / 1000);

  switch (event.type) {
    case 'checkout.session.completed': {
      const session = event.data.object as Stripe.Checkout.Session;
      if (session.mode !== 'subscription') break;

      const sub = await stripe.subscriptions.retrieve(session.subscription as string);
      await env.DB.prepare(
        `INSERT OR IGNORE INTO donation_subscriptions
         (id, donor_id, amount_cents, currency, interval, campaign_id, dedication, status, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        sub.id,
        sub.customer as string,
        sub.items.data[0].price.unit_amount,
        sub.currency,
        sub.items.data[0].price.recurring!.interval,
        sub.metadata.campaign_id || null,
        sub.metadata.dedication || null,
        sub.status,
        now,
        now
      ).run();
      break;
    }

    case 'invoice.payment_succeeded': {
      const invoice = event.data.object as Stripe.Invoice;
      if (!invoice.subscription) break;

      await env.DB.prepare(
        `INSERT OR IGNORE INTO donation_payments (id, subscription_id, donor_id, amount_cents, currency, paid_at)
         VALUES (?, ?, ?, ?, ?, ?)`
      ).bind(
        invoice.id,
        invoice.subscription,
        invoice.customer,
        invoice.amount_paid,
        invoice.currency,
        invoice.status_transitions.paid_at ?? now
      ).run();
      break;
    }

    case 'customer.subscription.updated':
    case 'customer.subscription.deleted': {
      const sub = event.data.object as Stripe.Subscription;
      await env.DB.prepare(
        'UPDATE donation_subscriptions SET status = ?, updated_at = ? WHERE id = ?'
      ).bind(sub.status, now, sub.id).run();
      break;
    }
  }

  return new Response('ok');
}
```

## 4. Self-Service Portal: Cancel with Reason

```typescript
// src/portal.ts
export async function cancelDonation(
  subscriptionId: string,
  donorId: string,
  reason: string,
  env: Env
): Promise<Response> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });

  // Ownership check
  const row = await env.DB.prepare(
    'SELECT id FROM donation_subscriptions WHERE id = ? AND donor_id = ?'
  ).bind(subscriptionId, donorId).first();

  if (!row) return new Response('Not found', { status: 404 });

  // Cancel at period end so donor keeps the current period
  await stripe.subscriptions.update(subscriptionId, {
    cancel_at_period_end: true,
    metadata: { cancel_reason: reason },
  });

  await env.DB.prepare(
    'UPDATE donation_subscriptions SET cancel_reason = ?, updated_at = ? WHERE id = ?'
  ).bind(reason, Math.floor(Date.now() / 1000), subscriptionId).run();

  return Response.json({ cancelled: true, message: 'Your donation will end at the current billing period.' });
}
```

## 5. Year-End Receipt Query

```typescript
// src/receipts.ts
export async function getYearEndSummary(
  donorId: string,
  year: number,
  env: Env
): Promise<Response> {
  const start = Math.floor(new Date(`${year}-01-01T00:00:00Z`).getTime() / 1000);
  const end   = Math.floor(new Date(`${year}-12-31T23:59:59Z`).getTime() / 1000);

  const rows = await env.DB.prepare(
    `SELECT SUM(amount_cents) AS total_cents, currency, COUNT(*) AS payment_count
     FROM donation_payments
     WHERE donor_id = ? AND paid_at BETWEEN ? AND ?
     GROUP BY currency`
  ).bind(donorId, start, end).all<{
    total_cents: number;
    currency: string;
    payment_count: number;
  }>();

  const donor = await env.DB.prepare(
    'SELECT email, display_name FROM donors WHERE id = ?'
  ).bind(donorId).first<{ email: string; display_name: string }>();

  return Response.json({ year, donor, summary: rows.results });
}
```

---

## Anti-patterns

- **Creating a new Stripe Price for every checkout** — use `lookup_key` to retrieve or create prices idempotently, otherwise you accumulate thousands of archived prices.
- **Cancelling immediately instead of at period end** — donors lose access to any period-based benefits and feel punished for cancelling. Use `cancel_at_period_end: true` and clearly communicate when the last gift will be charged.
- **Storing PII (tax ID, bank details) in Stripe metadata** — Stripe metadata is not encrypted at rest and appears in webhook payloads. Keep sensitive donor data in D1 with access controls.
- **Sending year-end receipts from `invoice.payment_succeeded`** — this triggers per payment; batch receipts instead after Jan 1 using a cron Trigger that queries `donation_payments` for the prior year.

## Gotchas

- `billing_cycle_anchor_config.day_of_month: 1` creates a prorated first invoice covering the partial month to the 1st. Communicate this to donors or use `proration_behavior: 'none'` to skip it.
- Stripe's `amount_paid` on an invoice is after discounts and credits; `amount_due` is the gross amount. For tax receipts, use `amount_paid` as the actual transferred value.
- If a donor uses the same email to donate twice, `customers.list({ email })` returns the first match. Add a uniqueness constraint in D1 on email if you want one-customer-per-email semantics.
- `customer.subscription.deleted` fires immediately on `stripe.subscriptions.cancel()` but fires after the period ends when `cancel_at_period_end: true`. Make sure your webhook handler handles both the `cancel_at_period_end` flag and the eventual `deleted` event.

## Verification

```bash
# Trigger test donation flow
stripe trigger checkout.session.completed --add checkout_session:mode=subscription

# Check D1 records
wrangler d1 execute YOUR_DB \
  --command "SELECT * FROM donation_subscriptions ORDER BY created_at DESC LIMIT 5"

# Simulate year-end summary
curl https://your-worker.workers.dev/receipts/year?year=2025 \
  -H 'Authorization: Bearer donor-session-token'
```

## Related

- `stripe-subscription-lifecycle.md`
- `stripe-dunning-management.md`
- `stripe-billing-portal-workers-session-management.md`
- `stripe-customer-portal.md`
- `deferred-revenue-waterfall-d1.md`

## Sources

- https://docs.stripe.com/billing/subscriptions/overview
- https://docs.stripe.com/api/subscriptions/create#create_subscription-billing_cycle_anchor_config
- https://docs.stripe.com/payments/checkout/custom-success-page
- https://developers.cloudflare.com/d1/
