# Payment Request API — Cloudflare Workers + Stripe Integration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want a native browser payment sheet (Apple Pay, Google Pay, saved cards) instead of
a custom card form, while keeping all sensitive Stripe operations server-side inside a
Cloudflare Worker. The challenge is wiring `PaymentRequest` in the browser to a Worker
that creates PaymentIntents and returns client secrets without ever leaking the Stripe
secret key to the client.

---

## Context

`PaymentRequest` is supported in all modern browsers and provides a consistent OS-level
payment sheet. Stripe's Payment Element wraps it, but you can drive the lower-level API
yourself for tighter control over UX. Cloudflare Workers hold the `STRIPE_SECRET_KEY`
secret, create PaymentIntents on demand, and confirm them server-side after the browser
returns a payment method ID. D1 logs orders; R2 stores receipts.

Stripe JS is loaded only at checkout time via dynamic import to avoid bloating the
initial bundle on Cloudflare Pages.

---

## Feature Detection

```typescript
// src/lib/paymentRequest.ts
export function isPaymentRequestSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'PaymentRequest' in window
  );
}

export async function canMakePayment(
  methodData: PaymentMethodData[]
): Promise<boolean> {
  if (!isPaymentRequestSupported()) return false;
  try {
    const pr = new PaymentRequest(methodData, {
      total: { label: 'Check', amount: { currency: 'USD', value: '0.00' } },
    });
    return await pr.canMakePayment() ?? false;
  } catch {
    return false;
  }
}
```

---

## Cloudflare Worker — PaymentIntent Endpoint

```typescript
// workers/checkout.ts
import { Hono } from 'hono';
import Stripe from 'stripe';

type Env = {
  STRIPE_SECRET_KEY: string;
  DB: D1Database;
};

const app = new Hono<{ Bindings: Env }>();

// POST /api/payment-intent
app.post('/api/payment-intent', async (c) => {
  const { amountCents, currency, orderId } = await c.req.json<{
    amountCents: number;
    currency: string;
    orderId: string;
  }>();

  const stripe = new Stripe(c.env.STRIPE_SECRET_KEY, {
    apiVersion: '2024-06-20',
    httpClient: Stripe.createFetchHttpClient(), // required in Workers
  });

  const intent = await stripe.paymentIntents.create({
    amount: amountCents,
    currency,
    metadata: { orderId },
    automatic_payment_methods: { enabled: true },
  });

  // record intent in D1
  await c.env.DB.prepare(
    'INSERT INTO payment_intents (id, order_id, status) VALUES (?, ?, ?)'
  )
    .bind(intent.id, orderId, intent.status)
    .run();

  return c.json({ clientSecret: <redacted-secret> });
});

// POST /api/payment-confirm  (server-side confirm, optional)
app.post('/api/payment-confirm', async (c) => {
  const { paymentIntentId, paymentMethodId } = await c.req.json<{
    paymentIntentId: string;
    paymentMethodId: string;
  }>();
  const stripe = new Stripe(c.env.STRIPE_SECRET_KEY, {
    apiVersion: '2024-06-20',
    httpClient: Stripe.createFetchHttpClient(),
  });
  const intent = await stripe.paymentIntents.confirm(paymentIntentId, {
    payment_method: paymentMethodId,
  });
  return c.json({ status: intent.status });
});

export default app;
```

---

## Browser — PaymentRequest Flow

```typescript
// src/checkout/PaymentButton.ts
import type { PaymentMethodData, PaymentDetailsInit } from 'payment-request';

const METHOD_DATA: PaymentMethodData[] = [
  {
    supportedMethods: 'https://apple.com/apple-pay',
    data: {
      version: 3,
      merchantIdentifier: 'merchant.com.example',
      merchantCapabilities: ['supports3DS'],
      supportedNetworks: ['visa', 'masterCard', 'amex'],
      countryCode: 'US',
    },
  },
  { supportedMethods: 'https://google.com/pay' },
  { supportedMethods: 'basic-card' },
];

export async function startPayment(
  amountCents: number,
  orderId: string
): Promise<'success' | 'cancelled' | 'error'> {
  // 1. Create PaymentIntent on the edge worker
  const res = await fetch('/api/payment-intent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amountCents, currency: 'usd', orderId }),
  });
  const { clientSecret } = (await res.json()) as { clientSecret: string };

  // 2. Build PaymentRequest
  const details: PaymentDetailsInit = {
    total: {
      label: 'Your Order',
      amount: { currency: 'USD', value: (amountCents / 100).toFixed(2) },
    },
  };

  const request = new PaymentRequest(METHOD_DATA, details);

  let response: PaymentResponse;
  try {
    response = await request.show();
  } catch (err) {
    // User closed the sheet
    return 'cancelled';
  }

  try {
    // 3. Confirm via Worker (keeps secret key off client)
    const confirmRes = await fetch('/api/payment-confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paymentIntentId: clientSecret.split('_secret_')[0],
        paymentMethodId: (response.details as { token?: { id?: string } }).token?.id
          ?? response.methodName,
      }),
    });
    const { status } = (await confirmRes.json()) as { status: string };

    if (status === 'succeeded') {
      await response.complete('success');
      return 'success';
    }
    await response.complete('fail');
    return 'error';
  } catch {
    await response.complete('fail');
    return 'error';
  }
}
```

---

## Stripe Webhook — Cloudflare Worker

```typescript
// workers/stripe-webhook.ts
import Stripe from 'stripe';

type Env = { STRIPE_WEBHOOK_SECRET: string; STRIPE_SECRET_KEY: string; RECEIPTS: R2Bucket; DB: D1Database };

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const sig = req.headers.get('stripe-signature') ?? '';
    const body = await req.text();

    const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
      apiVersion: '2024-06-20',
      httpClient: Stripe.createFetchHttpClient(),
    });

    let event: Stripe.Event;
    try {
      event = await stripe.webhooks.constructEventAsync(
        body, sig, env.STRIPE_WEBHOOK_SECRET
      );
    } catch {
      return new Response('Bad signature', { status: 400 });
    }

    if (event.type === 'payment_intent.succeeded') {
      const pi = event.data.object as Stripe.PaymentIntent;
      // update D1
      await env.DB.prepare(
        'UPDATE payment_intents SET status = ? WHERE id = ?'
      ).bind('succeeded', pi.id).run();
      // store receipt JSON in R2
      await env.RECEIPTS.put(
        `receipts/${pi.metadata.orderId}.json`,
        JSON.stringify(pi),
        { httpMetadata: { contentType: 'application/json' } }
      );
    }

    return new Response(null, { status: 200 });
  },
};
```

---

## React Integration Component

```tsx
// src/components/CheckoutButton.tsx
import { useState } from 'react';
import { startPayment, canMakePayment, isPaymentRequestSupported } from '../lib/paymentRequest';

const METHOD_DATA = [{ supportedMethods: 'basic-card' }];

export function CheckoutButton({
  amountCents,
  orderId,
}: {
  amountCents: number;
  orderId: string;
}) {
  const [state, setState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');

  const handleClick = async () => {
    setState('loading');
    const result = await startPayment(amountCents, orderId);
    setState(result === 'success' ? 'done' : result === 'cancelled' ? 'idle' : 'error');
  };

  if (!isPaymentRequestSupported()) {
    return <a >Enter card details</a>;
  }

  return (
    <button onClick={handleClick} disabled={state === 'loading' || state === 'done'}>
      {state === 'loading' ? 'Processing…' : state === 'done' ? 'Paid ✓' : 'Pay Now'}
    </button>
  );
}
```

---

## Anti-patterns

- **Storing `STRIPE_SECRET_KEY` in `wrangler.toml` plaintext** — use `wrangler secret put STRIPE_SECRET_KEY`.
- **Confirming PaymentIntents from the browser** — always confirm server-side to prevent amount tampering.
- **Calling `request.show()` outside a user gesture** — browsers block it; tie it to a click handler.
- **Skipping `canMakePayment()`** — the sheet may open but show no methods; check first and fall back.
- **Not calling `response.complete()`** — leaving the sheet spinning confuses users; always complete or fail.

---

## Gotchas

- `Stripe.createFetchHttpClient()` is mandatory in Workers; the default Node.js HTTP client crashes.
- Apple Pay requires a domain verification file at `/.well-known/apple-developer-merchantid-domain-association` — serve it from a Cloudflare Pages `_headers` rule or a Worker route.
- `PaymentRequest` is blocked on cross-origin iframes without `allowpaymentrequest` attribute.
- The `clientSecret` returned from a PaymentIntent must NOT be logged or stored in D1; it grants the ability to confirm the payment.
- Google Pay in a Cloudflare Pages SPA requires `https` even on `localhost` — use `wrangler pages dev --local-protocol https`.

---

## Verification

```bash
# 1. Deploy worker with test stripe key
wrangler secret put STRIPE_SECRET_KEY --env staging

# 2. Smoke-test intent creation
curl -X POST https://staging.example.workers.dev/api/payment-intent \
  -H 'Content-Type: application/json' \
  -d '{"amountCents":1000,"currency":"usd","orderId":"test-1"}'
# expect: {"clientSecret":"pi_..._secret_..."}

# 3. Stripe CLI forward webhooks
stripe listen --forward-to https://staging.example.workers.dev/stripe-webhook

# 4. Trigger test payment
stripe trigger payment_intent.succeeded
```

---

## Related

- `hono-cloudflare-workers-frontend-api.md`
- `credential-management-api-cloudflare-workers.md`
- `cloudflare-pages-middleware-auth-gating.md`
- `progressive-enhancement-workers-form-actions.md`
- `form-validation-zod-workers-endpoint.md`

---

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/Payment_Request_API
- https://stripe.com/docs/payments/accept-a-payment
- https://stripe.com/docs/stripe-js/elements/payment-request-button
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/r2/
