# feature-cookbook-payments

**Issue:** Payment integration — Stripe, checkout, subscriptions
**Date:** 2026-08-09
**Status:** documented

## Symptom
You integrate Stripe. A user pays. Your DB doesn't know.
You check Stripe; the payment succeeded. The user is
charged. You ship the product. The user says "I never got
it." You check your DB; no record of the payment. The
chargeback comes.

## Root cause
**Payment integration is hard.** Webhooks are the source
of truth; polling is unreliable.

**Source:** Stripe docs:
https://stripe.com/docs/payments

## The "Stripe setup" pattern

```ts
import Stripe from 'stripe';

const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
  apiVersion: '2024-06-20',
  typescript: true,
});
```

Always pin the API version.

## The "one-time payment" pattern

```ts
async function createPaymentIntent(input: PaymentInput, env: Env): Promise<{ clientSecret: string }> {
  const paymentIntent = await stripe.paymentIntents.create({
    amount: input.amount,  // In cents
    currency: 'usd',
    automatic_payment_methods: { enabled: true },
    metadata: {
      userId: input.userId,
      tenantId: input.tenantId,
    },
  });

  return { clientSecret: <redacted-secret> };
}
```

The client uses the `clientSecret` with Stripe Elements.

## The "subscription" pattern

```ts
async function createSubscription(userId: string, priceId: string, env: Env): Promise<Stripe.Subscription> {
  // 1. Get or create the customer
  const customer = await getOrCreateCustomer(userId, env);

  // 2. Create the subscription
  const subscription = await stripe.subscriptions.create({
    customer: customer.id,
    items: [{ price: priceId }],
    payment_behavior: 'default_incomplete',
    payment_settings: { save_default_payment_method: 'on_subscription' },
    expand: ['latest_invoice.payment_intent'],
  });

  return subscription;
}
```

The subscription is created; the payment is pending until
the user completes it.

## The "webhook handler" pattern

The webhook is the source of truth:
```ts
async function handleStripeEvent(event: Stripe.Event, env: Env): Promise<void> {
  // Idempotency
  const processed = await env.KV.get(`stripe:event:${event.id}`);
  if (processed) return;

  switch (event.type) {
    case 'payment_intent.succeeded': {
      const pi = event.data.object as Stripe.PaymentIntent;
      await fulfillOrder(pi.metadata.orderId, pi, env);
      break;
    }
    case 'customer.subscription.created':
    case 'customer.subscription.updated': {
      const sub = event.data.object as Stripe.Subscription;
      await updateUserPlan(sub.metadata.userId, sub, env);
      break;
    }
    case 'customer.subscription.deleted': {
      const sub = event.data.object as Stripe.Subscription;
      await cancelUserPlan(sub.metadata.userId, env);
      break;
    }
    case 'invoice.payment_failed': {
      const invoice = event.data.object as Stripe.Invoice;
      await handlePaymentFailed(invoice, env);
      break;
    }
  }

  await env.KV.put(`stripe:event:${event.id}`, '1', { expirationTtl: 86400 * 7 });
}
```

## The "fulfill order" pattern

```ts
async function fulfillOrder(orderId: string, paymentIntent: Stripe.PaymentIntent, env: Env): Promise<void> {
  // 1. Update the order
  await env.DB!.prepare(
    `UPDATE orders SET status = 'paid', stripe_payment_intent_id = ? WHERE id = ? AND status = 'pending'`
  ).bind(paymentIntent.id, orderId).run();

  // 2. Grant access (digital goods, etc.)
  await env.DB!.prepare(
    `INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)`
  ).bind(orderId, paymentIntent.metadata.productId, 1).run();

  // 3. Send the confirmation email
  await sendEmail({
    to: paymentIntent.metadata.email,
    subject: 'Your order is confirmed',
    body: 'Thanks for your order!',
  }, env);
}
```

The order is fulfilled after the webhook confirms payment.

## The "subscription update" pattern

```ts
async function updateUserPlan(userId: string, subscription: Stripe.Subscription, env: Env): Promise<void> {
  // Get the price ID
  const priceId = subscription.items.data[0].price.id;

  // Map price ID to plan
  const plan = mapPriceToPlan(priceId);

  // Update the user
  await env.DB!.prepare(
    `UPDATE users SET plan = ?, stripe_subscription_id = ?, plan_expires_at = ? WHERE id = ?`
  ).bind(
    plan,
    subscription.id,
    new Date(subscription.current_period_end * 1000).toISOString(),
    userId,
  ).run();

  // Audit
  await writeAudit(env, {
    userId,
    action: 'subscription.updated',
    resourceType: 'subscription',
    resourceId: subscription.id,
    metadata: { plan },
  });
}
```

The user's plan is updated from the subscription.

## The "test mode" pattern

Always use Stripe's test mode for development:
```ts
// In dev: sk_test_...
// In prod: sk_live_...
const stripe = new Stripe(env.STRIPE_SECRET_KEY);
```

Use test card numbers: `4242 4242 4242 4242`.

## The "PCI compliance" pattern

Use Stripe Elements to avoid PCI scope:
```html
<form>
  <div id="card-element"><!-- Stripe injects --></div>
  <button type="submit">Pay</button>
</form>

<script src="https://js.stripe.com/v3/"></script>
<script>
const stripe = Stripe('pk_test_...');
const elements = stripe.elements();
const card = elements.create('card');
card.mount('#card-element');
</script>
```

The card data goes directly to Stripe; you never touch it.

## The "3D Secure" pattern

For European cards, 3D Secure is required:
```ts
const paymentIntent = await stripe.paymentIntents.create({
  amount,
  currency: 'eur',
  payment_method_options: {
    card: { request_three_d_secure: 'automatic' },
  },
});
```

Stripe handles 3DS automatically; the user sees the
challenge if required.

## The "refund" pattern

```ts
async function refundPayment(paymentIntentId: string, env: Env): Promise<Stripe.Refund> {
  return stripe.refunds.create({
    payment_intent: paymentIntentId,
  });
}
```

The refund is processed; the user gets the money back.

## The "subscription cancel" pattern

For cancel at end of period:
```ts
async function cancelSubscription(subscriptionId: string, env: Env): Promise<Stripe.Subscription> {
  return stripe.subscriptions.update(subscriptionId, {
    cancel_at_period_end: true,
  });
}
```

The subscription stays active until the end of the period.

For immediate cancel:
```ts
async function cancelSubscriptionImmediately(subscriptionId: string, env: Env): Promise<Stripe.Subscription> {
  return stripe.subscriptions.cancel(subscriptionId);
}
```

The subscription is canceled immediately.

## The "Stripe Tax" pattern

For tax calculation:
```ts
const paymentIntent = await stripe.paymentIntents.create({
  amount,
  currency: 'usd',
  automatic_tax: { enabled: true },
});
```

Stripe Tax calculates the tax based on the customer's
location.

## The "idempotency" pattern

For duplicate prevention:
```ts
const idempotencyKey = `create-payment-${orderId}`;
const paymentIntent = await stripe.paymentIntents.create(
  { amount, currency: 'usd' },
  { idempotencyKey }
);
```

The same idempotency key returns the same result.

## The "error handling" pattern

For Stripe errors:
```ts
try {
  await stripe.charges.create({ ... });
} catch (err) {
  if (err instanceof Stripe.errors.CardError) {
    // Card declined
    return new Response(err.message, { status: 402 });
  } else if (err instanceof Stripe.errors.RateLimitError) {
    // Rate limited
    return new Response('Try again', { status: 429 });
  } else if (err instanceof Stripe.errors.StripeError) {
    // Other Stripe error
    return new Response('Payment error', { status: 500 });
  } else {
    // Non-Stripe error
    throw err;
  }
}
```

The error type drives the response.

## The "customer portal" pattern

For self-service plan management:
```ts
async function createPortalSession(customerId: string, returnUrl: string, env: Env): Promise<{ url: string }> {
  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: returnUrl,
  });
  return { url: session.url };
}
```

The user manages their subscription in Stripe's portal.

## The "checkout session" pattern

For hosted checkout:
```ts
async function createCheckoutSession(userId: string, priceId: string, env: Env): Promise<{ url: string }> {
  const session = await stripe.checkout.sessions.create({
    mode: 'subscription',
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: 'https://example.com/success',
    cancel_url: 'https://example.com/cancel',
    client_reference_id: userId,
  });
  return { url: session.url! };
}
```

Stripe hosts the checkout; the user is redirected.

## Verification
- **Test:** Payment intent is created
- **Test:** Webhook updates the DB
- **Test:** Subscription is updated
- **Test:** Refund is processed
- **Live:** Payment is monitored; alerts on failures

## Gotchas
- **The "no webhook" anti-pattern.** Polling is unreliable.
  Use webhooks.
- **The "duplicate fulfillment" anti-pattern.** Without
  idempotency, the user may get the product twice.
- **The "no plan update on cancel" anti-pattern.** When a
  subscription is canceled, the user's plan must be
  downgraded.
- **The "secret in the client" anti-pattern.** The publishable
  key is in the client; the secret key is on the server.
- **The "no test mode" anti-pattern.** Always test in
  Stripe's test mode before going live.
- **The "wrong API version" anti-pattern.** Always pin the
  Stripe API version; updates can break things.

## Related
- `webhook-implementation.md`
- `idempotency-keys.md`
- `feature-gating-implementation.md`
- `audit-log-as-product.md`
- Stripe: https://stripe.com/docs
- Stripe testing: https://stripe.com/docs/testing
