# Managing Stripe Subscription Lifecycle Events in Workers with KV

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

SaaS products built on Cloudflare Workers need fast, low-latency reads of subscription status (active, past_due, canceled) to gate access to features on every request. Stripe fires webhook events across the entire subscription lifecycle — creation, renewal, payment failure, cancellation — but storing that state in a SQL database and querying it per-request adds latency. This article shows how to handle the full Stripe subscription lifecycle in Workers, store state in KV for sub-millisecond reads, implement grace period logic for `past_due`, and trigger dunning emails via a Queue.

---

## Context

Stripe's subscription model uses a set of well-defined events: `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded`, and `invoice.payment_failed`. Each event carries the canonical subscription object, including `status`, `current_period_end`, `cancel_at_period_end`, and `customer` (the Stripe customer ID). Cloudflare KV is an eventually consistent key-value store with ~1ms read latency globally after replication; it is ideal for storing a compact subscription-status blob keyed by customer ID or your internal user ID. Grace periods for `past_due` are handled by checking `current_period_end` plus a configured grace window before denying access. Dunning (failed-payment notification) is dispatched to a Cloudflare Queue so that email sending does not block the webhook response.

---

## Section 1 — KV Namespace and Subscription Schema

```toml
# wrangler.toml
name = "payments-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "SUBSCRIPTIONS_KV"
id = "<your-kv-namespace-id>"

[[queues.producers]]
binding = "DUNNING_QUEUE"
queue = "dunning-emails"

[[queues.consumers]]
queue = "dunning-emails"
max_batch_size = 10
max_batch_timeout = 30
```

```typescript
// Subscription state stored in KV at key: `sub:<customerId>`
interface SubscriptionState {
  subscriptionId: string;
  status: 'active' | 'trialing' | 'past_due' | 'canceled' | 'unpaid' | 'incomplete';
  currentPeriodEnd: number;   // Unix timestamp
  cancelAtPeriodEnd: boolean;
  priceId: string;
  updatedAt: number;          // Unix timestamp of last KV write
}

// Grace period: allow access for 3 days after a payment failure
const GRACE_PERIOD_SECONDS = 3 * 24 * 60 * 60;

function isAccessAllowed(state: SubscriptionState): boolean {
  const now = Math.floor(Date.now() / 1000);
  if (state.status === 'active' || state.status === 'trialing') return true;
  if (state.status === 'past_due') {
    return now < state.currentPeriodEnd + GRACE_PERIOD_SECONDS;
  }
  return false;
}
```

---

## Section 2 — Worker Webhook Handler

```typescript
// src/subscription-lifecycle.ts
import { KVNamespace, Queue } from '@cloudflare/workers-types';

export interface Env {
  SUBSCRIPTIONS_KV: KVNamespace;
  DUNNING_QUEUE: Queue<DunningMessage>;
  STRIPE_WEBHOOK_SECRET: string;
}

interface DunningMessage {
  customerId: string;
  subscriptionId: string;
  invoiceId: string;
  attemptCount: number;
  amountDue: number;
  currency: string;
}

interface StripeSubscription {
  id: string;
  customer: string;
  status: string;
  current_period_end: number;
  cancel_at_period_end: boolean;
  items: { data: Array<{ price: { id: string } }> };
}

interface StripeInvoice {
  id: string;
  customer: string;
  subscription: string;
  attempt_count: number;
  amount_due: number;
  currency: string;
}

async function upsertSubscriptionState(
  kv: KVNamespace,
  customerId: string,
  sub: StripeSubscription,
): Promise<void> {
  const state: SubscriptionState = {
    subscriptionId: sub.id,
    status: sub.status as SubscriptionState['status'],
    currentPeriodEnd: sub.current_period_end,
    cancelAtPeriodEnd: sub.cancel_at_period_end,
    priceId: sub.items.data[0]?.price?.id ?? '',
    updatedAt: Math.floor(Date.now() / 1000),
  };

  // TTL: expire KV entry 7 days after period end to avoid stale data
  const ttl = sub.current_period_end - Math.floor(Date.now() / 1000) + 7 * 24 * 3600;
  await kv.put(
    `sub:${customerId}`,
    JSON.stringify(state),
    ttl > 0 ? { expirationTtl: ttl } : undefined,
  );
}

export async function handleSubscriptionEvent(
  event: { type: string; data: { object: StripeSubscription | StripeInvoice } },
  env: Env,
): Promise<void> {
  switch (event.type) {
    case 'customer.subscription.created':
    case 'customer.subscription.updated': {
      const sub = event.data.object as StripeSubscription;
      await upsertSubscriptionState(env.SUBSCRIPTIONS_KV, sub.customer, sub);
      break;
    }

    case 'customer.subscription.deleted': {
      const sub = event.data.object as StripeSubscription;
      // Keep the canceled record; do not delete — useful for win-back flows
      await upsertSubscriptionState(env.SUBSCRIPTIONS_KV, sub.customer, sub);
      break;
    }

    case 'invoice.payment_succeeded': {
      const inv = event.data.object as StripeInvoice;
      // Re-fetch subscription status is handled by the subscription.updated event
      // that Stripe fires alongside payment_succeeded; no additional KV write needed.
      console.log(`Payment succeeded for customer ${inv.customer}, invoice ${inv.id}`);
      break;
    }

    case 'invoice.payment_failed': {
      const inv = event.data.object as StripeInvoice;
      // Subscription status will be set to past_due by Stripe, which fires
      // customer.subscription.updated — but we also dispatch a dunning email.
      await env.DUNNING_QUEUE.send({
        customerId: inv.customer,
        subscriptionId: inv.subscription,
        invoiceId: inv.id,
        attemptCount: inv.attempt_count,
        amountDue: inv.amount_due,
        currency: inv.currency,
      });
      break;
    }

    default:
      console.log(`Unhandled event type: ${event.type}`);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Signature verification omitted for brevity — see stripe-webhooks-workers-d1-event-deduplication.md
    const body = await request.json<{ type: string; data: { object: unknown } }>();
    await handleSubscriptionEvent(body as Parameters<typeof handleSubscriptionEvent>[0], env);
    return new Response('OK', { status: 200 });
  },
};
```

---

## Section 3 — Dunning Email Queue Consumer

```typescript
// src/dunning-consumer.ts
import type { DunningMessage } from './subscription-lifecycle';

export interface DunningEnv {
  SENDGRID_API_KEY: string;
  DUNNING_FROM_EMAIL: string;
}

async function sendDunningEmail(
  msg: DunningMessage,
  env: DunningEnv,
): Promise<void> {
  const subject = msg.attemptCount === 1
    ? 'Your payment failed — please update your card'
    : `Payment retry ${msg.attemptCount} failed — action required`;

  const response = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.SENDGRID_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: msg.customerId }] }],
      from: { email: env.DUNNING_FROM_EMAIL },
      subject,
      content: [
        {
          type: 'text/plain',
          value: `Hi,\n\nWe couldn't process your payment of ${(msg.amountDue / 100).toFixed(2)} ${msg.currency.toUpperCase()}.\n\nPlease update your payment method to keep your subscription active.\n\nInvoice: ${msg.invoiceId}`,
        },
      ],
    }),
  });

  if (!response.ok) {
    throw new Error(`SendGrid error: ${response.status}`);
  }
}

export default {
  async queue(
    batch: MessageBatch<DunningMessage>,
    env: DunningEnv,
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await sendDunningEmail(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error('Dunning email failed:', err);
        msg.retry();
      }
    }
  },
};
```

---

## Anti-patterns

- **Reading subscription status from KV on every event and merging manually** — Stripe's `customer.subscription.updated` always contains the full canonical subscription object; use it as the source of truth rather than patching individual fields.
- **Deleting KV entry on `customer.subscription.deleted`** — Canceled subscriptions are useful for win-back campaigns and audit trails. Keep the record with `status: 'canceled'`.
- **Blocking the webhook response waiting for email delivery** — Always enqueue dunning messages; never call an email API synchronously inside the webhook handler.
- **Not setting a KV TTL** — Stale entries from churned customers accumulate indefinitely. Always set `expirationTtl` relative to `current_period_end`.

---

## Gotchas

- Stripe fires `customer.subscription.updated` before `invoice.payment_failed` — by the time your dunning handler runs, the KV entry already reflects `past_due`.
- KV is eventually consistent: a write in one region may take up to 60 seconds to propagate globally. For access-gating decisions, this is acceptable because grace periods absorb the window.
- `invoice.payment_failed` fires for every Stripe retry attempt; `attempt_count` increments each time. Use it to escalate dunning tone.
- If `cancel_at_period_end` is `true` and `status` is `active`, the subscription will cancel at `current_period_end` — factor this into UI messaging.

---

## Verification

```bash
# Create KV namespace
npx wrangler kv:namespace create SUBSCRIPTIONS_KV

# Forward Stripe events to local dev
stripe listen --forward-to http://localhost:8787/webhooks/stripe

# Trigger lifecycle events
stripe trigger customer.subscription.created
stripe trigger invoice.payment_failed
stripe trigger customer.subscription.updated

# Read KV entry
npx wrangler kv:key get --binding SUBSCRIPTIONS_KV "sub:cus_TEST123"
```

---

## Related

- `stripe-webhooks-workers-d1-event-deduplication.md`
- `workers-payment-retry-exponential-backoff-queues.md`
- `stripe-connect-oauth-workers-d1.md`

---

## Sources

- Stripe Subscription Lifecycle — https://stripe.com/docs/billing/subscriptions/overview
- Stripe Invoice Events — https://stripe.com/docs/billing/invoices/overview
- Cloudflare KV — https://developers.cloudflare.com/kv/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
