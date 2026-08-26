# 3D Secure Authentication Flow in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Strong Customer Authentication (SCA) under PSD2 requires 3D Secure for European card transactions. When a payment intent transitions to `requires_action`, your client must redirect the cardholder to the issuer's authentication page. Your Worker must persist intent state, handle the post-auth webhook, and implement exemption logic for low-risk or low-value transactions to minimise friction.

---

## Context

Stripe's 3DS2 flow works as follows:
1. Client calls your Worker to create a PaymentIntent.
2. Stripe returns `status: requires_action` with an `action.redirect_to_url` (3DS2) or `action.use_stripe_sdk` (3DS2 native).
3. Client completes the challenge in the card network iframe.
4. Stripe fires `payment_intent.succeeded` or `payment_intent.payment_failed` via webhook.
5. Your Worker updates the order in D1 and unlocks fulfilment.

For low-risk transactions (Stripe's built-in radar score < 65) or amounts under €30, you request an SCA exemption via `payment_method_options.card.request_three_d_secure: 'automatic'` and let Stripe decide whether the issuer will soft-decline.

---

## Solution

```typescript
// workers-3ds/src/index.ts

import { Env } from './types';
import { createPaymentIntent } from './create-intent';
import { handleWebhook } from './webhook';
import { getIntentStatus } from './status';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/payment-intents') {
      return createPaymentIntent(request, env);
    }

    if (request.method === 'POST' && url.pathname === '/webhook') {
      return handleWebhook(request, env, ctx);
    }

    const match = url.pathname.match(/^\/payment-intents\/([^/]+)\/status$/);
    if (request.method === 'GET' && match) {
      return getIntentStatus(match[1], env);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

```typescript
// workers-3ds/src/create-intent.ts

import Stripe from 'stripe';
import { Env } from './types';

export interface CreateIntentRequest {
  amountCents: number;
  currency: string;
  customerId: string;
  paymentMethodId: string;
  orderId: string;
  billingCountry: string;
  returnUrl: string;          // where Stripe redirects after 3DS
  requestExemption?: boolean; // caller hints: try SCA exemption
}

export async function createPaymentIntent(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<CreateIntentRequest>();
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-04-10' });

  // SCA exemption criteria: amount < €3000 (30 00 cents) OR caller requests it
  const tryExemption = body.requestExemption || body.amountCents < 3_000;

  const pi = await stripe.paymentIntents.create({
    amount: body.amountCents,
    currency: body.currency,
    customer: body.customerId,
    payment_method: body.paymentMethodId,
    confirm: true,
    return_url: body.returnUrl,
    automatic_payment_methods: { enabled: true },
    payment_method_options: {
      card: {
        // 'automatic': Stripe decides whether to request 3DS based on risk
        // 'any': always request 3DS
        request_three_d_secure: tryExemption ? 'automatic' : 'any',
      },
    },
    metadata: { order_id: body.orderId },
    use_stripe_sdk: true,
  });

  // Persist intent state so the client can poll and the webhook can find the order
  await env.DB
    .prepare(
      `INSERT INTO payment_intents
         (intent_id, order_id, customer_id, amount_cents, currency,
          status, three_ds_required, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`,
    )
    .bind(
      pi.id,
      body.orderId,
      body.customerId,
      body.amountCents,
      body.currency,
      pi.status,
      pi.status === 'requires_action' ? 1 : 0,
    )
    .run();

  return Response.json(buildClientResponse(pi));
}

function buildClientResponse(pi: Stripe.PaymentIntent) {
  const base = { intentId: pi.id, status: pi.status };

  if (pi.status === 'requires_action') {
    const action = pi.next_action;
    if (action?.type === 'redirect_to_url' && action.redirect_to_url) {
      return { ...base, action: 'redirect', redirectUrl: action.redirect_to_url.url };
    }
    if (action?.type === 'use_stripe_sdk') {
      // Client uses stripe.js handleNextAction() with the client_secret
      return { ...base, action: 'stripe_sdk', clientSecret: <redacted-secret> };
    }
  }

  if (pi.status === 'requires_confirmation') {
    // 3DS1 fallback: client must confirm after redirect
    return { ...base, action: 'confirm', clientSecret: <redacted-secret> };
  }

  return { ...base, action: 'none' };
}
```

```typescript
// workers-3ds/src/webhook.ts

import Stripe from 'stripe';
import { Env } from './types';
import { verifyStripeSignature } from './stripe-sig';

export async function handleWebhook(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
): Promise<Response> {
  const body = await request.text();
  const sig = request.headers.get('stripe-signature') ?? '';
  const event = verifyStripeSignature(body, sig, env.STRIPE_WEBHOOK_SECRET);
  if (!event) return new Response('Bad signature', { status: 400 });

  // Idempotency
  const seen = await env.DB
    .prepare('SELECT 1 FROM processed_events WHERE event_id = ?')
    .bind(event.id)
    .first();
  if (seen) return new Response('Duplicate', { status: 200 });

  ctx.waitUntil(processEvent(env, event));
  return new Response('OK');
}

async function processEvent(env: Env, event: Stripe.Event): Promise<void> {
  await env.DB
    .prepare('INSERT INTO processed_events (event_id, processed_at) VALUES (?, CURRENT_TIMESTAMP)')
    .bind(event.id)
    .run();

  if (event.type === 'payment_intent.succeeded') {
    const pi = event.data.object as Stripe.PaymentIntent;
    await updateIntentStatus(env.DB, pi.id, 'succeeded');
    await unlockFulfilment(env.DB, pi.metadata?.order_id);
    return;
  }

  if (event.type === 'payment_intent.payment_failed') {
    const pi = event.data.object as Stripe.PaymentIntent;
    const reason = pi.last_payment_error?.code ?? 'unknown';
    await updateIntentStatus(env.DB, pi.id, `failed:${reason}`);

    // If 3DS failed due to authentication (not the card itself), log for retry UI
    if (reason === 'authentication_required') {
      await env.DB
        .prepare(
          `UPDATE payment_intents SET three_ds_failed = 1 WHERE intent_id = ?`,
        )
        .bind(pi.id)
        .run();
    }
    return;
  }

  // 3DS2 challenge result — Stripe resolves to succeeded/failed above;
  // payment_intent.requires_action fires only in rare issuer-abort scenarios.
  if (event.type === 'payment_intent.requires_action') {
    const pi = event.data.object as Stripe.PaymentIntent;
    await updateIntentStatus(env.DB, pi.id, 'requires_action');
  }
}

async function updateIntentStatus(db: D1Database, intentId: string, status: string): Promise<void> {
  await db
    .prepare('UPDATE payment_intents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE intent_id = ?')
    .bind(status, intentId)
    .run();
}

async function unlockFulfilment(db: D1Database, orderId: string | undefined): Promise<void> {
  if (!orderId) return;
  await db
    .prepare(`UPDATE orders SET fulfilment_status = 'unlocked', paid_at = CURRENT_TIMESTAMP WHERE id = ?`)
    .bind(orderId)
    .run();
}
```

```typescript
// workers-3ds/src/status.ts

import { Env } from './types';

export async function getIntentStatus(intentId: string, env: Env): Promise<Response> {
  const row = await env.DB
    .prepare(
      `SELECT status, three_ds_required, three_ds_failed, updated_at
         FROM payment_intents WHERE intent_id = ?`,
    )
    .bind(intentId)
    .first<{
      status: string;
      three_ds_required: number;
      three_ds_failed: number;
      updated_at: string;
    }>();

  if (!row) return new Response('Not Found', { status: 404 });

  return Response.json({
    intentId,
    status: row.status,
    threeDsRequired: Boolean(row.three_ds_required),
    threeDs_failed: Boolean(row.three_ds_failed),
    updatedAt: row.updated_at,
  });
}
```

```typescript
// workers-3ds/src/stripe-sig.ts

import Stripe from 'stripe';

export function verifyStripeSignature(
  body: string,
  signature: string,
  secret: string,
): Stripe.Event | null {
  try {
    const stripe = new Stripe('', { apiVersion: '2024-04-10' });
    return stripe.webhooks.constructEvent(body, signature, secret);
  } catch {
    return null;
  }
}
```

---

## Implementation Details

**D1 schema**:
```sql
CREATE TABLE payment_intents (
  intent_id        TEXT PRIMARY KEY,
  order_id         TEXT NOT NULL,
  customer_id      TEXT NOT NULL,
  amount_cents     INTEGER NOT NULL,
  currency         TEXT NOT NULL,
  status           TEXT NOT NULL,
  three_ds_required INTEGER NOT NULL DEFAULT 0,
  three_ds_failed   INTEGER NOT NULL DEFAULT 0,
  created_at        TEXT NOT NULL,
  updated_at        TEXT
);
CREATE INDEX idx_pi_order ON payment_intents (order_id);

CREATE TABLE processed_events (
  event_id     TEXT PRIMARY KEY,
  processed_at TEXT NOT NULL
);
```

**wrangler.toml**:
```toml
[[d1_databases]]
binding = "DB"
database_name = "payments"
database_id   = "<D1_ID>"

[vars]
STRIPE_SECRET_KEY      = "<secret>"
STRIPE_WEBHOOK_SECRET  = "<secret>"
```

**SCA exemption decision tree**:
- Amount < €30: request `automatic` — Stripe applies TRA (Transaction Risk Analysis) exemption if issuer supports it.
- Amount €30–€100: use `automatic`; Stripe selects the path.
- Amount > €100 or `requestExemption = false`: use `any` — always prompt 3DS.
- Issuer soft-declines the exemption → Stripe retries as a full 3DS flow transparently.

**3DS1 fallback** — when `next_action.type === 'use_stripe_sdk'` fails and the issuer only supports 3DS1, Stripe redirects to `return_url` with `payment_intent` and `payment_intent_client_secret` query params. The client confirms via `stripe.confirmCardPayment(clientSecret)` and the webhook completes the flow.

---

## Anti-patterns

- **Do not store `client_secret` server-side beyond the request** — it is short-lived, sensitive, and only needed by the client SDK; log it nowhere.
- **Do not set `request_three_d_secure: 'any'` for all transactions globally** — frictionless authentication (3DS2 with risk-based auth) has higher approval rates than a forced challenge; use `automatic` unless compliance mandates `any`.
- **Do not fulfil orders on `payment_intent.created`** — fulfil only on `payment_intent.succeeded` received via webhook, after 3DS completes.
- **Do not rely on client-side redirect to confirm success** — redirect `return_url` is user-navigable and can be spoofed; always wait for the webhook before updating order state.

---

## Gotchas

- Stripe's `use_stripe_sdk = true` enables the Payment Element 3DS2 native flow (no full-page redirect). Set it only when your frontend uses `stripe.js` v3+.
- `payment_intent.requires_action` webhook is not fired on initial creation; it only fires on subsequent actions (e.g., a recurring charge that suddenly requires SCA). The status is visible immediately in the API response.
- The `authentication_required` decline code means 3DS was attempted but the cardholder did not complete it — distinct from `card_declined` (issuer hard-declined). Build separate UI copy for each.
- In test mode, use Stripe's 3DS test cards: `4000002500003155` (always 3DS), `4000002760003184` (3DS2 frictionless), `4000008260003178` (3DS1 fallback).
- PSD2 SCA applies to transactions where both the merchant and card issuer are in the EEA. MIT (merchant-initiated transactions) for subscriptions are exempt — pass `off_session: true` and a stored mandate.

---

## Verification

```bash
# Create a 3DS-triggering payment intent
curl -X POST https://3ds-worker.example.com/payment-intents \
  -H 'Content-Type: application/json' \
  -d '{
    "amountCents": 4999,
    "currency": "eur",
    "customerId": "cus_test",
    "paymentMethodId": "pm_card_threeDSecure2Required",
    "orderId": "ord_3ds_test",
    "billingCountry": "DE",
    "returnUrl": "https://example.com/checkout/complete"
  }'
# Expected: { status: "requires_action", action: "stripe_sdk", clientSecret: "pi_..._secret_..." }

# Poll status after client completes 3DS
curl https://3ds-worker.example.com/payment-intents/pi_test123/status
# Expected: { status: "succeeded", threeDsRequired: true, threeDs_failed: false }
```

---

## Related

- `documentation/categories/payments/stripe-webhook-idempotency.md`
- `documentation/categories/payments/workers-payment-fraud-detection.md`
- `documentation/categories/payments/subscription-lifecycle-manager.md`
- Stripe 3D Secure guide: https://stripe.com/docs/payments/3d-secure
- Stripe SCA guide: https://stripe.com/docs/strong-customer-authentication

---

## Sources

- https://stripe.com/docs/payments/3d-secure
- https://stripe.com/docs/strong-customer-authentication
- https://stripe.com/docs/payments/payment-intents/migration/three-ds
- https://developers.cloudflare.com/d1/
- https://stripe.com/docs/api/payment_intents/object#payment_intent_object-next_action
