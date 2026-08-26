# Stripe Billing Credits Consumption Tracking with D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You grant customers prepaid credits that are applied automatically against future Stripe invoices,
and you need a reliable edge-side ledger to answer "how many credits remain?", enforce credit
ceilings before checkout, and emit analytics events — all without round-tripping to the Stripe API
on every page load.

---

## Context

Stripe introduced the **Billing Credits** object (beta 2024, GA 2025) as a first-class way to grant
monetary credits that Stripe itself deducts from invoices before charging the card. The lifecycle is:

```
CreditGrant created  →  credit balance grows
Invoice finalized    →  Stripe applies credits, emits credit.granted / credit.applied webhooks
Balance exhausted    →  normal card charge or invoice_payment_failed
```

On the example project platform we shadow this ledger in **Cloudflare D1** so the edge can serve
real-time balance lookups and block purchases that would exceed available credit without a Stripe
API call. Stripe remains the source of truth; D1 is the read-through cache + audit trail.

---

## D1 Schema

```sql
-- migrations/0018_credit_ledger.sql
CREATE TABLE IF NOT EXISTS credit_grants (
  id            TEXT PRIMARY KEY,           -- stripe CreditGrant id (credgr_...)
  customer_id   TEXT NOT NULL,
  amount        INTEGER NOT NULL,           -- amount in smallest currency unit
  currency      TEXT NOT NULL DEFAULT 'usd',
  effective_at  INTEGER NOT NULL,           -- unix epoch seconds
  expires_at    INTEGER,
  category      TEXT NOT NULL,              -- 'promotional' | 'paid'
  status        TEXT NOT NULL DEFAULT 'active', -- active | expired | voided
  created_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS credit_applications (
  id            TEXT PRIMARY KEY,           -- stripe CreditBalanceTransaction id
  grant_id      TEXT NOT NULL REFERENCES credit_grants(id),
  customer_id   TEXT NOT NULL,
  invoice_id    TEXT NOT NULL,
  applied_amount INTEGER NOT NULL,          -- positive = credit consumed
  created_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_credit_grants_customer
  ON credit_grants(customer_id, status);

CREATE INDEX IF NOT EXISTS idx_credit_applications_customer
  ON credit_applications(customer_id);
```

---

## Stripe SDK Helpers

```typescript
// src/lib/stripe-credits.ts
import Stripe from 'stripe';

export interface CreditSummary {
  available: number;   // sum of active unexpired grants minus applied
  currency: string;
  grants: Stripe.Billing.CreditGrant[];
}

export async function fetchCreditSummary(
  stripe: Stripe,
  customerId: string,
): Promise<CreditSummary> {
  const grants = await stripe.billing.creditGrants.list({
    customer: customerId,
    limit: 100,
  });

  const balance = await stripe.billing.creditBalanceSummary.retrieve({
    customer: customerId,
    currency: 'usd',
    // expand credit_balance_summary for breakdown per grant
    expand: ['data.balance.available_balance'],
  });

  const available = balance.balance?.available_balance?.monetary?.value ?? 0;

  return {
    available,
    currency: balance.balance?.available_balance?.monetary?.currency ?? 'usd',
    grants: grants.data,
  };
}

export async function grantCredits(
  stripe: Stripe,
  customerId: string,
  amountCents: number,
  opts: {
    category: 'promotional' | 'paid';
    expiresAt?: Date;
    metadata?: Record<string, string>;
  },
): Promise<Stripe.Billing.CreditGrant> {
  return stripe.billing.creditGrants.create({
    customer: customerId,
    amount: {
      type: 'monetary',
      monetary: { value: amountCents, currency: 'usd' },
    },
    applicability_config: {
      scope: { price_type: 'metered' },
    },
    category: opts.category,
    effective_at: Math.floor(Date.now() / 1000),
    expires_at: opts.expiresAt
      ? Math.floor(opts.expiresAt.getTime() / 1000)
      : undefined,
    metadata: opts.metadata ?? {},
  });
}
```

---

## Syncing Grants into D1

```typescript
// src/workers/credit-sync.ts
import { Env } from '../types';
import Stripe from 'stripe';

export async function upsertCreditGrant(
  db: D1Database,
  grant: Stripe.Billing.CreditGrant,
): Promise<void> {
  const monetary = grant.amount.monetary;
  if (!monetary) return;

  await db
    .prepare(
      `INSERT INTO credit_grants
         (id, customer_id, amount, currency, effective_at, expires_at, category, status, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
       ON CONFLICT(id) DO UPDATE SET
         status     = excluded.status,
         expires_at = excluded.expires_at,
         updated_at = unixepoch()`,
    )
    .bind(
      grant.id,
      grant.customer as string,
      monetary.value,
      monetary.currency,
      grant.effective_at,
      grant.expires_at ?? null,
      grant.category,
      grant.status,
    )
    .run();
}

export async function upsertCreditApplication(
  db: D1Database,
  txn: Stripe.Billing.CreditBalanceTransaction,
): Promise<void> {
  if (txn.type !== 'credits_applied') return;
  const credit = txn.credits_applied;
  if (!credit) return;

  await db
    .prepare(
      `INSERT OR IGNORE INTO credit_applications
         (id, grant_id, customer_id, invoice_id, applied_amount, created_at)
       VALUES (?, ?, ?, ?, ?, unixepoch())`,
    )
    .bind(
      txn.id,
      credit.credit_grant as string,
      txn.customer as string,
      credit.invoice as string,
      credit.amount.monetary?.value ?? 0,
    )
    .run();
}
```

---

## Webhook Handler

```typescript
// src/handlers/stripe-credits-webhook.ts
import Stripe from 'stripe';
import { Env } from '../types';
import { upsertCreditGrant, upsertCreditApplication } from '../workers/credit-sync';

const HANDLED_EVENTS = new Set([
  'billing.credit_grant.created',
  'billing.credit_grant.updated',
  'billing.credit_balance_transaction.created',
]);

export async function handleCreditWebhook(
  request: Request,
  env: Env,
): Promise<Response> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2025-01-27.acacia' });
  const body = await request.text();
  const sig = request.headers.get('stripe-signature') ?? '';

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig, env.STRIPE_CREDITS_WEBHOOK_SECRET);
  } catch {
    return new Response('Bad signature', { status: 400 });
  }

  if (!HANDLED_EVENTS.has(event.type)) {
    return new Response('Ignored', { status: 200 });
  }

  // idempotency guard
  const already = await env.DB.prepare(
    'SELECT 1 FROM processed_events WHERE event_id = ?',
  )
    .bind(event.id)
    .first();
  if (already) return new Response('Duplicate', { status: 200 });

  await env.DB.prepare(
    'INSERT OR IGNORE INTO processed_events (event_id, processed_at) VALUES (?, unixepoch())',
  )
    .bind(event.id)
    .run();

  switch (event.type) {
    case 'billing.credit_grant.created':
    case 'billing.credit_grant.updated': {
      const grant = event.data.object as Stripe.Billing.CreditGrant;
      await upsertCreditGrant(env.DB, grant);
      break;
    }
    case 'billing.credit_balance_transaction.created': {
      const txn = event.data.object as Stripe.Billing.CreditBalanceTransaction;
      await upsertCreditApplication(env.DB, txn);
      break;
    }
  }

  return new Response('OK', { status: 200 });
}
```

---

## Edge Balance Query

```typescript
// src/handlers/credit-balance.ts
import { Env } from '../types';

interface BalanceRow {
  available: number;
  currency: string;
}

export async function getEdgeCreditBalance(
  customerId: string,
  env: Env,
): Promise<{ available: number; currency: string }> {
  // Sum active grants, subtract applied amounts, respect expiry
  const row = await env.DB.prepare(
    `SELECT
       COALESCE(SUM(cg.amount), 0) -
       COALESCE((
         SELECT SUM(ca.applied_amount)
         FROM   credit_applications ca
         WHERE  ca.customer_id = ?
       ), 0) AS available,
       MAX(cg.currency) AS currency
     FROM credit_grants cg
     WHERE cg.customer_id = ?
       AND cg.status = 'active'
       AND (cg.expires_at IS NULL OR cg.expires_at > unixepoch())`,
  )
    .bind(customerId, customerId)
    .first<BalanceRow>();

  return {
    available: row?.available ?? 0,
    currency: row?.currency ?? 'usd',
  };
}
```

---

## Pre-checkout Credit Enforcement

```typescript
// src/middleware/credit-gate.ts
import { getEdgeCreditBalance } from '../handlers/credit-balance';
import { Env } from '../types';

/**
 * Returns true if the customer has enough credit to cover amountCents.
 * If creditsOnly=true the purchase is blocked when credits fall short.
 */
export async function creditGate(
  customerId: string,
  amountCents: number,
  env: Env,
  opts: { creditsOnly?: boolean } = {},
): Promise<{ allowed: boolean; creditApplied: number; remainder: number }> {
  const { available } = await getEdgeCreditBalance(customerId, env);
  const creditApplied = Math.min(available, amountCents);
  const remainder = amountCents - creditApplied;

  if (opts.creditsOnly && remainder > 0) {
    return { allowed: false, creditApplied, remainder };
  }

  return { allowed: true, creditApplied, remainder };
}
```

---

## Anti-patterns

- **Reading balance only from D1 at checkout**: D1 is the cache. For high-value purchases,
  call `stripe.billing.creditBalanceSummary.retrieve` to confirm, then let Stripe apply credits
  server-side. Never adjust the balance yourself.
- **Creating a `credits_applied` row before Stripe confirms**: Always write `credit_applications`
  only from the `billing.credit_balance_transaction.created` webhook, never speculatively.
- **Ignoring `expires_at` in queries**: Expired grants still appear with `status = 'active'` until
  Stripe runs its nightly expiry job. Always add `expires_at IS NULL OR expires_at > unixepoch()`.
- **Granting credits without `applicability_config`**: Without a scope, credits apply to all
  invoice line items including one-off charges. Scope to `price_type: metered` or a specific price
  list to avoid unintended consumption.
- **Voiding a grant instead of expiring it**: `void` is permanent and non-refundable. Prefer
  setting a near-term `expires_at` when you need a soft-cancel.

---

## Gotchas

- `billing.credit_balance_transaction.created` fires *after* invoice finalization, not at creation.
  The D1 balance can show credits as "available" for a window while Stripe is computing the
  invoice; gate high-stakes decisions on the Stripe live balance endpoint.
- `creditBalanceSummary` returns balances per currency. If you support multi-currency, run a
  separate query per currency or force single-currency credit grants.
- Stripe applies credits to the *oldest* eligible invoices first. You cannot control ordering.
- The Billing Credits API is still versioned behind `stripe-version: 2025-01-27.acacia` (or later).
  Pin the version in your Stripe SDK initializer.
- `stripe.billing.creditGrants.list` paginates; use `autoPagingToArray` when a customer may have
  many historical grants.

---

## Verification

```bash
# 1. Create a test grant via Stripe CLI
stripe billing credit-grants create \
  --customer=cus_TEST123 \
  --amount='{"type":"monetary","monetary":{"value":5000,"currency":"usd"}}' \
  --category=promotional \
  --applicability-config='{"scope":{"price_type":"metered"}}'

# 2. Check D1 shadow row
wrangler d1 execute example project-db \
  --command "SELECT * FROM credit_grants WHERE customer_id='cus_TEST123'"

# 3. Trigger a metered invoice and verify credit_applications row appears
stripe billing meters event-summaries create ...

# 4. Compare D1 available vs Stripe live balance
curl https://api.stripe.com/v1/billing/credit_balance_summary \
  -u $STRIPE_SECRET_KEY: \
  -d customer=cus_TEST123 \
  -d currency=usd
```

---

## Related

- `/payments/stripe-metered-billing.md`
- `/payments/stripe-meter-event-v2-idempotency-and-lag.md`
- `/payments/deferred-revenue-waterfall-d1.md`
- `/payments/stripe-webhook-idempotency-d1-event-log.md`
- `/payments/credits-system-implementation.md`

---

## Sources

- Stripe Billing Credits API reference: https://docs.stripe.com/api/billing/credit-grant
- Stripe Credit Balance Summary: https://docs.stripe.com/api/billing/credit-balance-summary
- Stripe Billing Credits guide: https://docs.stripe.com/billing/subscriptions/credits
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
