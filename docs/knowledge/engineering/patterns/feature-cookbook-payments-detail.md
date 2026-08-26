# feature-cookbook-payments-detail

**Issue:** Payments — Stripe, checkout, refunds
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a checkout. The user pays. You update the
DB. The Stripe webhook fails. The DB is wrong. The
user paid but the order is "pending."

## Root cause
**Payments are async.** Use webhooks as source of
truth.

**Source:** Stripe docs.

## The "Stripe setup" pattern

For Stripe setup:
```ts
import Stripe from 'stripe';

const stripe = new Stripe(env.STRIPE_API_KEY, {
  apiVersion: '2024-06-20',
  typescript: true,
});
```

The Stripe client is set up.

## The "checkout session" pattern

For a checkout session:
```ts
const session = await stripe.checkout.sessions.create({
  mode: 'payment',  // or 'subscription'
  line_items: [
    {
      price_data: {
        currency: 'usd',
        product_data: { name: product.name },
        unit_amount: product.priceCents,
      },
      quantity: 1,
    },
  ],
  success_url: 'https://example.com/success?session_id={CHECKOUT_SESSION_ID}',
  cancel_url: 'https://example.com/cancel',
  customer_email: user.email,
  metadata: { userId: user.id, productId: product.id },
});
```

The checkout is created.

## The "payment intent" pattern

For a payment intent (more control):
```ts
const intent = await stripe.paymentIntents.create({
  amount: product.priceCents,
  currency: 'usd',
  metadata: { userId: user.id, productId: product.id },
  automatic_payment_methods: { enabled: true },
});
```

The intent is created.

## The "idempotency" pattern

For Stripe idempotency:
```ts
const session = await stripe.checkout.sessions.create(
  { /* ... */ },
  { idempotencyKey: `checkout:${userId}:${productId}` },
);
```

The operation is idempotent.

**Source:** Stripe idempotency:
https://stripe.com/docs/api/idempotent_requests

## The "webhook" pattern

For webhooks:
```ts
app.post('/webhooks/stripe', async (req) => {
  const sig = req.headers.get('stripe-signature');
  const body = await req.text();

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig!, env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return new Response('Invalid signature', { status: 400 });
  }

  switch (event.type) {
    case 'checkout.session.completed':
      await handleCheckoutCompleted(event.data.object);
      break;
    case 'payment_intent.succeeded':
      await handlePaymentSucceeded(event.data.object);
      break;
    case 'payment_intent.payment_failed':
      await handlePaymentFailed(event.data.object);
      break;
    case 'charge.refunded':
      await handleRefund(event.data.object);
      break;
  }

  return new Response('OK');
});
```

The webhook is handled.

## The "refund" pattern

For refunds:
```ts
const refund = await stripe.refunds.create({
  payment_intent: paymentIntentId,
  reason: 'requested_by_customer',
});

// Or partial
const partialRefund = await stripe.refunds.create({
  payment_intent: paymentIntentId,
  amount: 500,  // $5
});
```

The refund is created.

## The "subscription" pattern

For subscriptions:
```ts
const subscription = await stripe.subscriptions.create({
  customer: customerId,
  items: [{ price: priceId }],
  payment_behavior: 'default_incomplete',
  payment_settings: { save_default_payment_method: 'on_subscription' },
  expand: ['latest_invoice.payment_intent'],
});
```

The subscription is created.

## The "customer" pattern

For a customer:
```ts
const customer = await stripe.customers.create({
  email: user.email,
  name: user.displayName,
  metadata: { userId: user.id },
});
```

The customer is created.

## The "payment method" pattern

For a payment method:
```ts
const paymentMethod = await stripe.paymentMethods.create({
  type: 'card',
  card: { token: 'tok_visa' },
});

await stripe.paymentMethods.attach(paymentMethod.id, {
  customer: customerId,
});
```

The payment method is attached.

## The "tax" pattern

For tax:
```ts
const session = await stripe.checkout.sessions.create({
  // ...
  automatic_tax: { enabled: true },
});
```

The tax is automatic.

**Source:** Stripe Tax:
https://stripe.com/docs/tax

## The "invoice" pattern

For invoices:
```ts
const invoice = await stripe.invoices.create({
  customer: customerId,
  collection_method: 'send_invoice',
  days_until_due: 30,
});

await stripe.invoices.finalizeInvoice(invoice.id);
```

The invoice is created.

## The "payment observability" pattern

For observability:
- **Conversion rate:** Checkout / start
- **Payment success:** % succeeded
- **Refund rate:** % refunded
- **Dispute rate:** % disputed
- **Revenue:** Per period

```ts
metrics.increment('payment.checkout_started_total');
metrics.increment('payment.completed_total', { amount });
```

The payments are monitored.

## The "payment security" pattern

For security:
- **API key:** In a secret manager
- **Webhook secret:** In a secret manager
- **Verify signature:** Always
- **3D Secure:** For high-risk
- **PCI DSS:** Stripe handles

The payment is secure.

## The "payment anti-pattern" anti-patterns

### 1. No webhook
- **Issue:** DB out of sync
- **Fix:** Webhook handler

### 2. No idempotency
- **Issue:** Double charge
- **Fix:** Stripe idempotency keys

### 3. No signature verification
- **Issue:** Forged webhooks
- **Fix:** Verify signature

### 4. Saving card data
- **Issue:** PCI violation
- **Fix:** Use Stripe Elements

### 5. No retry
- **Issue:** Transient failure = lost
- **Fix:** Retry + DLQ

## Verification
- **Test:** Checkout works
- **Test:** Webhook is processed
- **Test:** Refund works
- **Test:** Subscription works
- **Live:** Payment metrics monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no webhook" anti-pattern.** Use webhooks.
- **The "no idempotency" anti-pattern.** Stripe
  idempotency.
- **The "no signature" anti-pattern.** Verify.

## Related
- `feature-cookbook-billing.md`
- `feature-cookbook-webhook-detail.md`
- `feature-cookbook-webhook.md`
- `feature-cookbook-saas-detail.md`
- Stripe: https://stripe.com/docs/payments
- Stripe webhook: https://stripe.com/docs/webhooks
