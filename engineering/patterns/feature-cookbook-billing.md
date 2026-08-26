# feature-cookbook-billing

**Issue:** Billing — subscriptions, invoices, webhooks
**Date:** 2026-08-09
**Status:** documented

## Symptom
You charge users. The user upgrades. Your DB still
says "free plan." The user complains. You find the
Stripe webhook is broken.

## Root cause
**Billing is async.** Handle webhooks.

**Source:** Stripe docs.

## The "subscription model" pattern

For a subscription:
```ts
interface Subscription {
  id: string;
  tenantId: string;
  stripeSubscriptionId: string;
  stripeCustomerId: string;
  plan: 'pro' | 'enterprise';
  status: 'active' | 'past_due' | 'cancelled' | 'trialing';
  currentPeriodStart: string;
  currentPeriodEnd: string;
  cancelAtPeriodEnd: boolean;
}
```

The subscription is in your DB.

## The "checkout session" pattern

For Stripe Checkout:
```ts
const session = await stripe.checkout.sessions.create({
  mode: 'subscription',
  line_items: [{
    price: STRIPE_PRICE_IDS[plan],
    quantity: 1,
  }],
  success_url: 'https://example.com/billing/success?session_id={CHECKOUT_SESSION_ID}',
  cancel_url: 'https://example.com/billing/cancel',
  customer_email: user.email,
  metadata: { tenantId: tenant.id, plan },
  subscription_data: {
    metadata: { tenantId: tenant.id, plan },
  },
});

return Response.json({ url: session.url });
```

The checkout is created.

## The "customer portal" pattern

For the customer portal:
```ts
const session = await stripe.billingPortal.sessions.create({
  customer: tenant.stripeCustomerId,
  return_url: 'https://example.com/billing',
});

return Response.json({ url: session.url });
```

The portal is created.

## The "webhook" pattern

For Stripe webhooks:
```ts
app.post('/webhooks/stripe', async (req) => {
  const sig = req.headers.get('stripe-signature');
  const body = await req.text();

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig!, STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return new Response('Invalid signature', { status: 400 });
  }

  switch (event.type) {
    case 'customer.subscription.created':
    case 'customer.subscription.updated': {
      const sub = event.data.object as Stripe.Subscription;
      await handleSubscriptionChange(sub);
      break;
    }
    case 'customer.subscription.deleted': {
      const sub = event.data.object as Stripe.Subscription;
      await handleSubscriptionCancelled(sub);
      break;
    }
    case 'invoice.payment_succeeded': {
      const invoice = event.data.object as Stripe.Invoice;
      await handlePaymentSucceeded(invoice);
      break;
    }
    case 'invoice.payment_failed': {
      const invoice = event.data.object as Stripe.Invoice;
      await handlePaymentFailed(invoice);
      break;
    }
  }

  return new Response('OK');
});
```

The webhook handles the events.

## The "idempotent webhook" pattern

For idempotency:
```ts
async function handleSubscriptionChange(sub: Stripe.Subscription): Promise<void> {
  const eventId = sub.id;
  const processed = await env.KV!.get(`webhook:${eventId}`);
  if (processed) return;

  await env.DB!.prepare(
    `UPDATE tenants SET plan = ?, status = ?, ... WHERE id = ?`
  ).bind(sub.metadata.plan, sub.status, sub.metadata.tenantId).run();

  await env.KV!.put(`webhook:${eventId}`, '1', { expirationTtl: 86400 * 7 });
}
```

The webhook is idempotent.

## The "subscription state" pattern

For the state machine:
```ts
async function updateTenantPlan(tenantId: string, status: SubscriptionStatus, env: Env): Promise<void> {
  const newState = mapStripeStatusToTenant(status);

  await env.DB!.prepare(
    `UPDATE tenants SET plan_status = ? WHERE id = ?`
  ).bind(newState, tenantId).run();
}

function mapStripeStatusToTenant(status: string): TenantStatus {
  switch (status) {
    case 'active': return 'active';
    case 'trialing': return 'trial';
    case 'past_due': return 'past_due';
    case 'canceled': return 'cancelled';
    case 'unpaid': return 'past_due';
    default: return 'active';
  }
}
```

The state is mapped.

## The "trial" pattern

For a trial:
```ts
const session = await stripe.checkout.sessions.create({
  mode: 'subscription',
  line_items: [{
    price: STRIPE_PRICE_IDS[plan],
    quantity: 1,
  }],
  subscription_data: {
    trial_period_days: 14,
    metadata: { tenantId, plan },
  },
  // ...
});
```

The trial is 14 days.

## The "upgrade/downgrade" pattern

For upgrade/downgrade:
```ts
const subscription = await stripe.subscriptions.update(
  tenant.stripeSubscriptionId,
  {
    items: [{
      id: subscriptionItem.id,
      price: STRIPE_PRICE_IDS[newPlan],
    }],
    proration_behavior: 'create_prorations',
  },
);
```

The plan is changed.

## The "cancel" pattern

For cancel:
- **At period end:** `cancel_at_period_end: true`
- **Immediately:** `cancel: true`

```ts
await stripe.subscriptions.update(tenant.stripeSubscriptionId, {
  cancel_at_period_end: true,
});
```

The cancellation is at period end.

## The "invoice" pattern

For invoices:
```ts
const invoices = await stripe.invoices.list({
  customer: tenant.stripeCustomerId,
  limit: 12,
});
```

The invoices are listed.

## The "tax" pattern

For tax (Stripe Tax):
```ts
const session = await stripe.checkout.sessions.create({
  // ...
  automatic_tax: { enabled: true },
});
```

The tax is automatic.

## The "billing observability" pattern

For observability:
- **MRR:** Monthly recurring revenue
- **Churn:** % lost per month
- **LTV:** Lifetime value
- **ARPU:** Average revenue per user

```ts
metrics.gauge('billing.mrr', mrr);
metrics.gauge('billing.churn_rate', churnRate);
```

The billing is monitored.

## The "billing anti-pattern" anti-patterns

### 1. No webhook
- **Issue:** Plan not updated
- **Fix:** Handle webhooks

### 2. No idempotency
- **Issue:** Double-process
- **Fix:** Idempotency keys

### 3. No retry
- **Issue:** Transient failure = data loss
- **Fix:** Stripe retries (configurable)

### 4. No tax
- **Issue:** Sales tax issues
- **Fix:** Stripe Tax

### 5. No invoice
- **Issue:** Customer asks for receipt
- **Fix:** Generate invoice

## Verification
- **Test:** Webhook is processed
- **Test:** State is updated
- **Test:** Trial works
- **Test:** Cancel works
- **Live:** Webhook health monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no webhook" anti-pattern.** Handle webhooks.
- **The "no idempotency" anti-pattern.** Idempotency
  keys.
- **The "no retry" anti-pattern.** Configure retries.

## Related
- `feature-cookbook-saas-detail.md`
- `feature-cookbook-webhook.md`
- `feature-cookbook-multi-tenancy-detail.md`
- `idempotency-keys.md`
- `feature-cookbook-state-machines.md`
- Stripe: https://stripe.com/docs/billing
