# Stripe Payment Link Webhook Fulfillment on Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You use Stripe Payment Links to sell products without a custom checkout UI and need a Cloudflare Worker to listen for `checkout.session.completed` events, mark orders fulfilled in D1, and dispatch confirmation emails via MailChannels - all idempotently so that Stripe's retry mechanism never double-fulfills an order.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Database: D1 for order log and processed-event deduplication
- Email: MailChannels Send API (Workers-native, no API key required on Cloudflare)
- Stripe SDK: `stripe` npm package (lightweight fetch-based subset works in Workers)
- Webhook: `checkout.session.completed`

---

## Step 1 - D1 Schema

```sql
-- migrations/0001_stripe_fulfillment.sql
CREATE TABLE IF NOT EXISTS fulfilled_orders (
  session_id   TEXT PRIMARY KEY,
  customer_email TEXT,
  amount_total   INTEGER NOT NULL,
  currency       TEXT NOT NULL,
  fulfilled_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processed_stripe_events (
  event_id     TEXT PRIMARY KEY,
  session_id   TEXT NOT NULL,
  processed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## Step 2 - Stripe Webhook Signature Verification

```typescript
// src/stripe/verify.ts
export async function verifyStripeWebhook(
  body: string,
  stripeSignatureHeader: string | null,
  webhookSecret: string,
  toleranceSeconds = 300
): Promise<void> {
  if (!stripeSignatureHeader) {
    throw new Error('Missing Stripe-Signature header');
  }

  const parts = Object.fromEntries(
    stripeSignatureHeader.split(',').flatMap((part) => {
      const [k, v] = part.split('=');
      return [[k.trim(), v?.trim()]];
    })
  );

  const timestamp = parseInt(parts['t'] ?? '0', 10);
  const expectedSig = parts['v1'];

  if (!timestamp || !expectedSig) {
    throw new Error('Malformed Stripe-Signature header');
  }

  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - timestamp) > toleranceSeconds) {
    throw new Error('Stripe webhook timestamp too old (replay attack?)');
  }

  const signedPayload = `${timestamp}.${body}`;
  const encoder = new TextEncoder();

  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(webhookSecret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const sig = await crypto.subtle.sign('HMAC', key, encoder.encode(signedPayload));
  const computed = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

  if (computed !== expectedSig) {
    throw new Error('Stripe signature mismatch');
  }
}
```

---

## Step 3 - MailChannels Confirmation Email

```typescript
// src/email/confirmation.ts
interface OrderDetails {
  customerEmail: string;
  customerName?: string;
  amountTotal: number;
  currency: string;
  sessionId: string;
}

export async function sendConfirmationEmail(
  order: OrderDetails
): Promise<void> {
  const amount = (order.amountTotal / 100).toFixed(2);
  const currency = order.currency.toUpperCase();

  const body = {
    personalizations: [
      {
        to: [{ email: order.customerEmail, name: order.customerName ?? '' }],
      },
    ],
    from: { email: 'orders@example.com', name: 'Orchords' },
    subject: `Your order confirmation - ${currency} ${amount}`,
    content: [
      {
        type: 'text/plain',
        value:
          `Hi ${order.customerName ?? 'there'},\n\n` +
          `Thank you for your purchase of ${currency} ${amount}.\n` +
          `Your order reference is: ${order.sessionId}\n\n` +
          `We will process your order shortly.\n\nOrchords Team`,
      },
    ],
  };

  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`MailChannels error ${res.status}: ${text}`);
  }
}
```

---

## Step 4 - Webhook Handler

```typescript
// src/index.ts
import { verifyStripeWebhook } from './stripe/verify';
import { sendConfirmationEmail } from './email/confirmation';

interface Env {
  DB: D1Database;
  STRIPE_WEBHOOK_SECRET: string;
}

interface CheckoutSession {
  id: string;
  customer_email: string | null;
  customer_details?: { name?: string; email?: string };
  amount_total: number;
  currency: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.text();

    try {
      await verifyStripeWebhook(
        body,
        request.headers.get('Stripe-Signature'),
        env.STRIPE_WEBHOOK_SECRET
      );
    } catch (err) {
      console.error('Signature verification failed:', err);
      return new Response('Unauthorized', { status: 401 });
    }

    const event = JSON.parse(body) as {
      id: string;
      type: string;
      data: { object: CheckoutSession };
    };

    if (event.type !== 'checkout.session.completed') {
      return new Response('Ignored', { status: 200 });
    }

    const alreadyDone = await env.DB
      .prepare('SELECT event_id FROM processed_stripe_events WHERE event_id = ?')
      .bind(event.id)
      .first();
    if (alreadyDone) {
      console.log(`Skipping duplicate event ${event.id}`);
      return new Response('Already processed', { status: 200 });
    }

    const session = event.data.object;
    const email =
      session.customer_details?.email ?? session.customer_email ?? '';
    const name = session.customer_details?.name;

    await env.DB
      .prepare(
        `INSERT OR IGNORE INTO fulfilled_orders
         (session_id, customer_email, amount_total, currency)
         VALUES (?, ?, ?, ?)`
      )
      .bind(session.id, email, session.amount_total, session.currency)
      .run();

    await env.DB
      .prepare(
        'INSERT INTO processed_stripe_events (event_id, session_id) VALUES (?, ?)'
      )
      .bind(event.id, session.id)
      .run();

    if (email) {
      await sendConfirmationEmail({
        customerEmail: email,
        customerName: name,
        amountTotal: session.amount_total,
        currency: session.currency,
        sessionId: session.id,
      });
    }

    return new Response('OK', { status: 200 });
  },
};
```

---

## Anti-patterns

- Never skip signature verification even in staging - use a test webhook secret from the Stripe Dashboard.
- Do not use `Date.now()` as the deduplication key; always use the stable Stripe `event.id`.
- Do not call MailChannels before writing the processed event to D1 - network failures would cause the Worker to retry and resend.
- Avoid calling `stripe.webhooks.constructEvent()` from the full Stripe SDK in Workers - it uses Node.js `Buffer` internally.

## Gotchas

- `checkout.session.completed` fires for both Payment Links and custom Sessions; filter by `session.payment_link` if needed.
- MailChannels requires Cloudflare to validate your sending domain via SPF/DKIM.
- Stripe retries failed webhooks with exponential backoff for up to 3 days.
- `amount_total` is in minor units (cents); never store as a float.

## Verification

```bash
# Apply migration
wrangler d1 migrations apply DB --env production

# Install Stripe CLI for local testing
stripe listen --forward-to http://localhost:8787/stripe/webhook

# Trigger a test checkout.session.completed event
stripe trigger checkout.session.completed

# Confirm order was recorded in D1
wrangler d1 execute DB --env production \
  --command "SELECT * FROM fulfilled_orders ORDER BY fulfilled_at DESC LIMIT 5"

# Confirm idempotency
wrangler d1 execute DB --env production \
  --command "SELECT COUNT(*) FROM fulfilled_orders"
```

## Related

- `documentation/categories/payments/workers-klarna-order-management-webhook.md`
- `documentation/categories/payments/workers-subscription-dunning-retry-d1.md`
- `documentation/categories/payments/workers-tax-calculation-stripe-tax-api.md`

## Sources

- https://stripe.com/docs/webhooks/best-practices
- https://stripe.com/docs/payments/payment-links
- https://mailchannels.zendesk.com/hc/en-us/articles/4565898358413
- https://developers.cloudflare.com/d1/
