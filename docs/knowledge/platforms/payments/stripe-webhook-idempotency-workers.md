# stripe-webhook-idempotency-workers

**Date:** 2026-08-22
**Author:** example.com
**Repo:** example-org/example-repo
**Status:** published

## Symptom

example project receives Stripe webhook events in a Cloudflare Worker. Stripe
retries delivery for up to 72 hours on non-2xx responses. Without
idempotency guards, network hiccups and manual retries from the Stripe
Dashboard duplicate order fulfilment, subscription state changes,
and Connect payout triggers. Workers are stateless and share no
in-process memory, so the guard must live in D1.

## Context

Stripe sends each event with a globally unique `id` (e.g.
`evt_1Qx...`). The same physical event can arrive multiple times:
- Stripe's own 72-hour retry schedule (3 retries over 1 h, then
  exponential back-off)
- Manual retries from the Stripe Dashboard
- Stripe's `stripe-cli trigger` during development
- Duplicate test events when rotating webhook endpoints

The example project Worker must return 200 within Stripe's 30-second timeout
and handle the event exactly once regardless of how many copies arrive.

## Stripe-Signature verification

Verify the signature **before** any D1 read or business logic:

```typescript
import Stripe from 'stripe';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const body = await req.text(); // must be raw bytes
    const sig  = req.headers.get('stripe-signature') ?? '';

    let event: Stripe.Event;
    try {
      // Uses HMAC-SHA256 over `timestamp.body` payload
      event = await stripe.webhooks.constructEventAsync(
        body, sig, env.STRIPE_WEBHOOK_SECRET
      );
    } catch (err) {
      // Invalid signature or stale timestamp (> 300 s default)
      return new Response('Bad signature', { status: 400 });
    }

    return handleEvent(event, env);
  },
};
```

`constructEventAsync` is the Workers-compatible variant; the
synchronous `constructEvent` uses Node's `crypto` module which is
unavailable in the Workers runtime. Store the signing secret from
the Stripe Dashboard endpoint configuration as:
`wrangler secret put STRIPE_WEBHOOK_SECRET`

Stripe embeds a `t=<unix-timestamp>` in the `Stripe-Signature` header
and rejects replays older than 300 seconds by default (configurable
via `tolerance` option). Do not disable tolerance — it prevents
replay attacks even if the secret is leaked briefly.

## D1 processed_events table

```sql
-- One-time migration
CREATE TABLE IF NOT EXISTS processed_events (
  event_id     TEXT PRIMARY KEY,        -- evt_xxx
  event_type   TEXT NOT NULL,
  processed_at INTEGER NOT NULL,        -- Unix ms
  outcome      TEXT                     -- JSON summary
);

CREATE INDEX IF NOT EXISTS idx_pe_processed_at
  ON processed_events (processed_at);
```

```typescript
async function handleEvent(
  event: Stripe.Event, env: Env): Promise<Response> {

  // 1. Fast idempotency check — D1 SELECT before any work
  const existing = await env.DB.prepare(
    `SELECT outcome FROM processed_events WHERE event_id = ?`
  ).bind(event.id).first<{ outcome: string }>();

  if (existing) {
    // 200 is required; returning 4xx causes Stripe to retry
    return new Response('already processed', { status: 200 });
  }

  // 2. Process the event
  let outcome: unknown;
  try {
    outcome = await dispatchEvent(event, env);
  } catch (err) {
    // Don't write to processed_events — allow Stripe to retry
    console.error('dispatch failed', event.id, err);
    return new Response('handler error', { status: 500 });
  }

  // 3. Durably record completion
  await env.DB.prepare(
    `INSERT OR IGNORE INTO processed_events
     (event_id, event_type, processed_at, outcome)
     VALUES (?, ?, ?, ?)`
  ).bind(
    event.id,
    event.type,
    Date.now(),
    JSON.stringify(outcome)
  ).run();

  return new Response('ok', { status: 200 });
}
```

`INSERT OR IGNORE` is safe for concurrent Workers invocations of the
same event: D1's PRIMARY KEY constraint serialises the insert and the
slower invocation becomes a no-op.

## dispatchEvent routing

```typescript
async function dispatchEvent(
  event: Stripe.Event, env: Env): Promise<unknown> {
  switch (event.type) {
    case 'payment_intent.succeeded':
      return onPaymentSucceeded(
        event.data.object as Stripe.PaymentIntent, env);

    case 'customer.subscription.deleted':
      return onSubscriptionCancelled(
        event.data.object as Stripe.Subscription, env);

    case 'account.updated':                       // Connect
      return onConnectAccountUpdated(
        event.data.object as Stripe.Account, env);

    case 'charge.dispute.created':
      return onDisputeCreated(
        event.data.object as Stripe.Dispute, env);

    default:
      return { ignored: true };
  }
}
```

Register only event types you handle in the Stripe Dashboard endpoint
configuration. Receiving all events (`*`) bloats the `processed_events`
table and wastes D1 write units.

## Thin events and API hydration

Stripe's 2025-11 API introduced thin events where `event.data.object`
may be a minimal stub. For high-value types, always hydrate from the
API rather than trusting the payload object:

```typescript
async function onPaymentSucceeded(
  pi: Stripe.PaymentIntent, env: Env) {
  // Re-fetch to get latest status, avoiding stale snapshot
  const fresh = await stripe.paymentIntents.retrieve(pi.id);
  if (fresh.status !== 'succeeded') return { skipped: true };
  // ...fulfill order...
}
```

## Mobile vs desktop retry behaviour

Stripe's retry schedule is the same regardless of the client that
initiated the payment, but the *observable effect* differs:

| Scenario | What the user sees | Worker behaviour |
|---|---|---|
| Mobile network drop after payment | Card charged; app shows spinner | Retry delivers event; idempotency prevents double-fulfill |
| Desktop browser closed mid-redirect | Checkout session may expire | `checkout.session.expired` fires; no duplicate `succeeded` |
| Mobile PWA backgrounded | Payment completes in background | Stripe delivers `succeeded`; dedup by `event.id` |
| Manual Dashboard retry | Dev testing scenario | `INSERT OR IGNORE` is the last line of defence |

For mobile sessions, the `PaymentIntent` `metadata` should carry a
example project `orderId` set at creation time so the Worker can correlate
events to orders without a database round-trip:

```typescript
await stripe.paymentIntents.create({
  amount: 4999,
  currency: 'eur',
  metadata: { orderId: 'wam_ord_abc123', platform: 'mobile' },
  automatic_tax: { enabled: true },
});
```

## Pruning old records

```typescript
// Cron Trigger: '0 3 * * *'
async function pruneProcessedEvents(env: Env) {
  const cutoff = Date.now() - 30 * 86_400_000; // 30 days
  await env.DB.prepare(
    `DELETE FROM processed_events WHERE processed_at < ?`
  ).bind(cutoff).run();
}
```

Stripe retries for at most 72 hours; 30 days provides a safe buffer
for manually-replayed events and audit queries.

## Multiple webhook endpoints

example project uses separate endpoints per concern:
- `/webhooks/stripe/payments` — PaymentIntent + Checkout events
- `/webhooks/stripe/subscriptions` — Subscription + Invoice events
- `/webhooks/stripe/connect` — Connect account + transfer events

Each endpoint has its own signing secret. `STRIPE_WEBHOOK_SECRET` must
be scoped per endpoint:
```
STRIPE_WEBHOOK_SECRET_PAYMENTS
STRIPE_WEBHOOK_SECRET_SUBS
STRIPE_WEBHOOK_SECRET_CONNECT
```

Store all three as Worker secrets and pass the correct one to
`constructEventAsync` based on the request path.

## Anti-patterns

- Reading the raw body as JSON (`req.json()`) before calling
  `constructEventAsync` — the method requires the raw string to
  recompute the HMAC; parsing first discards bytes.
- Checking idempotency only in-memory (a Map or Set on the module
  scope) — Workers restart frequently; the map is empty on every
  cold start.
- Returning 200 before the D1 write succeeds — a Worker crash after
  business logic but before the record write means Stripe retries and
  the event processes twice.
- Using `event.data.previous_attributes` alone to detect
  subscription cancellation — it is absent on thin events.
- Setting a single `STRIPE_WEBHOOK_SECRET` for all endpoints — a
  stolen secret for one endpoint would validate events for another.

## Gotchas

- `constructEventAsync` was added in `stripe` npm ≥ 12.0.0; older
  versions expose only `constructEvent` which calls `crypto.createHmac`
  — unavailable in Workers. Pin `"stripe": ">=12"` in `package.json`.
- Stripe's 300-second replay window starts from the `t=` timestamp in
  the header, not delivery time. Clock skew > 5 minutes between the
  Worker host and Stripe's servers fails all events; Workers inherit
  the correct UTC time automatically.
- Dashboard manual retries reuse the original `event.id`; Stripe CLI
  triggers generate a new `evt_` ID each time — the `outcome` column
  is useful for distinguishing which invocation actually ran.
- D1's `INSERT OR IGNORE` is atomic only within a single write;
  across multiple statements use a D1 transaction or rely on the
  PRIMARY KEY constraint for last-resort dedup.

## Verification checklist

- Replay the same event ID twice in quick succession (e.g. via curl);
  assert the second call returns 200 and writes zero new D1 rows.
- Send a forged payload with an incorrect signature; assert 400.
- Send a valid event with `t=` timestamp 400 seconds in the past;
  assert 400 (tolerance exceeded).
- Kill the Worker mid-handler (via an artificial `throw`) after
  business logic runs but before D1 write; confirm Stripe retries
  and the event processes correctly on the retry.
- Verify `stripe trigger payment_intent.succeeded` produces exactly
  one order fulfilment even when fired three times.

## Related

- `payments/stripe-webhook-setup.md`
- `payments/stripe-webhook-signature-verification.md`
- `payments/stripe-webhook-retry-handling.md`
- `payments/stripe-thin-events-fetch-and-idempotent-processing.md`
- `payments/idempotency-keys-payment-apis.md`

## Source URLs (verified 2026-08-22)

- https://docs.stripe.com/webhooks/best-practices
- https://docs.stripe.com/webhooks#verify-official-libraries
- https://docs.stripe.com/api/events/types
- https://docs.stripe.com/connect/webhooks
- https://developers.cloudflare.com/d1/
- https://github.com/stripe/stripe-node/releases/tag/v12.0.0
