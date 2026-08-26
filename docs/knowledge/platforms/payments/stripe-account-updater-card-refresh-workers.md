# Stripe Account Updater: Automatic Card Refresh with Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project subscribers with expired or replaced credit cards cause payment failures that trigger
unnecessary dunning sequences and churn. Stripe's Account Updater service automatically refreshes
stored card data — new expiry dates, replacement PANs, or account closures — and delivers the
results via `customer.updated` and `payment_method.automatically_updated` webhooks. Workers must
process these events to keep D1 subscription state accurate and avoid charging against stale cards.

## Context
Account Updater runs asynchronously in the background — Stripe submits stored card data to card
networks (Visa, Mastercard, Amex, Discover) and ingests updated data overnight before statement
cycles. Workers receive update events days before the next billing attempt, providing a clean window
to synchronize state. The feature is enabled per Stripe account and requires card-present or
card-not-present vault storage via `SetupIntent` or `PaymentMethod`.

## Section 1 — D1 Schema for Card Refresh Tracking
Store `payment_method_id` alongside subscription records. A `card_updates` audit table captures
every Account Updater event for compliance and monitoring.

```typescript
// migrations/0003_account_updater.sql
// ALTER TABLE subscriptions ADD COLUMN payment_method_id TEXT;
// ALTER TABLE subscriptions ADD COLUMN card_last4 TEXT;
// ALTER TABLE subscriptions ADD COLUMN card_exp_month INTEGER;
// ALTER TABLE subscriptions ADD COLUMN card_exp_year INTEGER;
// ALTER TABLE subscriptions ADD COLUMN card_updated_at INTEGER;
//
// CREATE TABLE card_updates (
//   id INTEGER PRIMARY KEY AUTOINCREMENT,
//   event_id TEXT UNIQUE NOT NULL,
//   customer_id TEXT NOT NULL,
//   payment_method_id TEXT NOT NULL,
//   update_type TEXT NOT NULL,   -- 'expiry_update' | 'account_change' | 'account_closed'
//   old_exp_month INTEGER,
//   old_exp_year INTEGER,
//   new_exp_month INTEGER,
//   new_exp_year INTEGER,
//   received_at INTEGER NOT NULL
// );
// CREATE INDEX idx_card_updates_customer ON card_updates(customer_id, received_at DESC);

interface Env {
  DB: D1Database;
  STRIPE_WEBHOOK_SECRET: string;
}

interface StripeWebhookEvent {
  id: string;
  type: string;
  created: number;
  data: { object: Record<string, unknown>; previous_attributes?: Record<string, unknown> };
}
```

## Section 2 — Webhook Handler for Account Updater Events
Stripe delivers two event types for Account Updater: `payment_method.automatically_updated`
(expiry/PAN change applied) and `customer.updated` (default payment method changed). Process both
to keep subscription records current.

```typescript
async function verifyStripeWebhook(
  body: string,
  sig: string,
  secret: string
): Promise<StripeWebhookEvent | null> {
  try {
    const parts = sig.split(',').reduce<Record<string, string>>((acc, p) => {
      const [k, v] = p.split('='); acc[k] = v; return acc;
    }, {});
    const key = await crypto.subtle.importKey(
      'raw', new TextEncoder().encode(secret),
      { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
    );
    const mac = await crypto.subtle.sign(
      'HMAC', key, new TextEncoder().encode(`${parts['t']}.${body}`)
    );
    const computed = Array.from(new Uint8Array(mac))
      .map(b => b.toString(16).padStart(2, '0')).join('');
    return computed === parts['v1'] ? JSON.parse(body) as StripeWebhookEvent : null;
  } catch { return null; }
}

interface StripePaymentMethod {
  id: string;
  customer: string;
  card: {
    last4: string;
    exp_month: number;
    exp_year: number;
    brand: string;
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.text();
    const sig = request.headers.get('stripe-signature') ?? '';
    const event = await verifyStripeWebhook(body, sig, env.STRIPE_WEBHOOK_SECRET);
    if (!event) return new Response('Invalid signature', { status: 400 });

    // Idempotency guard
    const dup = await env.DB
      .prepare('SELECT id FROM card_updates WHERE event_id = ?')
      .bind(event.id)
      .first();
    if (dup) return new Response('Already processed', { status: 200 });

    switch (event.type) {
      case 'payment_method.automatically_updated':
        await handlePaymentMethodUpdated(env, event);
        break;
      case 'customer.updated':
        await handleCustomerDefaultPmChanged(env, event);
        break;
    }

    return new Response('OK', { status: 200 });
  },
};

async function handlePaymentMethodUpdated(
  env: Env,
  event: StripeWebhookEvent
): Promise<void> {
  const pm = event.data.object as StripePaymentMethod;
  const prev = event.data.previous_attributes as Partial<StripePaymentMethod> | undefined;

  const oldExpMonth = (prev?.card?.exp_month) ?? null;
  const oldExpYear = (prev?.card?.exp_year) ?? null;

  // Determine update type: closed accounts have no new card data
  const updateType = pm.card
    ? (oldExpMonth !== pm.card.exp_month || oldExpYear !== pm.card.exp_year
        ? 'expiry_update'
        : 'account_change')
    : 'account_closed';

  await env.DB.batch([
    // Audit log
    env.DB.prepare(
      `INSERT INTO card_updates
         (event_id, customer_id, payment_method_id, update_type,
          old_exp_month, old_exp_year, new_exp_month, new_exp_year, received_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      event.id,
      pm.customer,
      pm.id,
      updateType,
      oldExpMonth,
      oldExpYear,
      pm.card?.exp_month ?? null,
      pm.card?.exp_year ?? null,
      Date.now()
    ),

    // Sync subscription table for quick reads
    env.DB.prepare(
      `UPDATE subscriptions
       SET card_last4        = ?,
           card_exp_month    = ?,
           card_exp_year     = ?,
           card_updated_at   = ?
       WHERE payment_method_id = ?`
    ).bind(
      pm.card?.last4 ?? null,
      pm.card?.exp_month ?? null,
      pm.card?.exp_year ?? null,
      Date.now(),
      pm.id
    ),
  ]);

  if (updateType === 'account_closed') {
    console.warn(JSON.stringify({
      level: 'warn',
      service: 'stripe-account-updater',
      alert: 'card_account_closed',
      payment_method_id: pm.id,
      customer_id: pm.customer,
      ts: new Date().toISOString(),
    }));
  }
}

async function handleCustomerDefaultPmChanged(
  env: Env,
  event: StripeWebhookEvent
): Promise<void> {
  const customer = event.data.object as { id: string; invoice_settings: { default_payment_method: string } };
  const prev = event.data.previous_attributes as {
    invoice_settings?: { default_payment_method?: string }
  } | undefined;

  const newPm = customer.invoice_settings?.default_payment_method;
  const oldPm = prev?.invoice_settings?.default_payment_method;

  if (!newPm || newPm === oldPm) return;

  // Update subscriptions for this customer to track new default payment method
  await env.DB
    .prepare(
      `UPDATE subscriptions
       SET payment_method_id = ?, card_updated_at = ?
       WHERE customer_id = ? AND status IN ('active', 'trialing', 'past_due')`
    )
    .bind(newPm, Date.now(), customer.id)
    .run();
}
```

## Section 3 — Preemptive Dunning Skip for Updated Cards
Before initiating a dunning sequence for a failed payment, check whether a card update has been
received in the last 48 hours. If so, skip the first dunning step — the next automatic retry will
succeed.

```typescript
async function shouldSkipDunning(env: Env, customerId: string): Promise<boolean> {
  const FORTY_EIGHT_HOURS_AGO = Date.now() - 48 * 60 * 60 * 1000;

  const recentUpdate = await env.DB
    .prepare(
      `SELECT id FROM card_updates
       WHERE customer_id = ?
         AND update_type IN ('expiry_update', 'account_change')
         AND received_at > ?
       LIMIT 1`
    )
    .bind(customerId, FORTY_EIGHT_HOURS_AGO)
    .first();

  return recentUpdate !== null;
}

async function triggerDunning(env: Env, customerId: string): Promise<void> {
  const skip = await shouldSkipDunning(env, customerId);
  if (skip) {
    console.log(JSON.stringify({
      level: 'info',
      service: 'stripe-account-updater',
      event: 'dunning_skip_card_updated',
      customer_id: customerId,
      ts: new Date().toISOString(),
    }));
    return;
  }
  // Proceed with normal dunning sequence
}
```

## Section 4 — Monitoring Update Coverage and Closed Accounts
A scheduled Worker surfaces the rate of Account Updater events relative to the total active
subscription count, and surfaces closed-account cards that need subscriber outreach.

```typescript
export async function monitorAccountUpdater(env: Env): Promise<void> {
  const THIRTY_DAYS_AGO = Date.now() - 30 * 24 * 60 * 60 * 1000;

  const [updates, closed, activeCount] = await Promise.all([
    env.DB
      .prepare(
        `SELECT COUNT(*) AS count FROM card_updates
         WHERE received_at > ? AND update_type != 'account_closed'`
      )
      .bind(THIRTY_DAYS_AGO)
      .first<{ count: number }>(),
    env.DB
      .prepare(
        `SELECT customer_id, payment_method_id, received_at FROM card_updates
         WHERE update_type = 'account_closed' AND received_at > ?
         ORDER BY received_at DESC LIMIT 20`
      )
      .bind(THIRTY_DAYS_AGO)
      .all<{ customer_id: string; payment_method_id: string; received_at: number }>(),
    env.DB
      .prepare(
        `SELECT COUNT(*) AS count FROM subscriptions WHERE status = 'active'`
      )
      .first<{ count: number }>(),
  ]);

  console.log(JSON.stringify({
    level: 'info',
    service: 'stripe-account-updater',
    active_subscriptions: activeCount?.count ?? 0,
    card_updates_30d: updates?.count ?? 0,
    closed_accounts_30d: closed.results.length,
    sample_closed: closed.results.slice(0, 3),
    ts: new Date().toISOString(),
  }));
}
```

## Anti-patterns
- Relying solely on Account Updater without also handling `invoice.payment_failed` — some cards (e.g. prepaid, international) are excluded from the service
- Treating a `customer.updated` event as a card update — it fires for any customer field change, not just payment methods
- Updating the displayed card last4/expiry only in the UI layer without persisting to D1 — the next payment path will use stale data
- Initiating immediate dunning on `account_closed` card status without first checking whether the customer has an alternate payment method
- Assuming Account Updater covers all card networks — Discover and Amex have lower participation rates than Visa/Mastercard

## Gotchas
- Account Updater is enabled by default on Stripe accounts but only activates for cards stored via Stripe's vault (SetupIntent or `save` on PaymentIntent)
- `payment_method.automatically_updated` carries `previous_attributes` only if the expiry changed; a full PAN replacement appears as a new `card.fingerprint` without `previous_attributes`
- The `customer.updated` event fired by Account Updater does not contain card details — fetch the PaymentMethod separately if needed
- Account Updater runs on a batch cycle (typically overnight); events may arrive days after the underlying card change

## Verification
1. Create a Stripe test card with expiry `01/25`, vault it, then use the `account_updater` test helper to simulate a refresh
2. Confirm `card_updates` row is inserted in D1 with correct `update_type`
3. Assert `subscriptions.card_exp_year` is updated to the new value
4. Simulate an `account_closed` event and verify the monitoring query surfaces it and triggers a warning log

## Related
- /documentation/docs/policies/payments/account-updater-service.md
- /documentation/docs/policies/payments/stripe-smart-retries.md
- /documentation/docs/policies/payments/stripe-dunning-management.md
- /documentation/docs/policies/payments/stripe-webhook-idempotency-d1-event-log.md

## Sources
- https://docs.stripe.com/saving-cards#automatic-card-updates
- https://docs.stripe.com/api/events/types#event_types-payment_method.automatically_updated
- https://docs.stripe.com/api/events/types#event_types-customer.updated
- https://docs.stripe.com/testing#account-updater
