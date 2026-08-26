# Mollie Recurring Subscriptions on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You are integrating Mollie as your payment gateway for a European SaaS or marketplace and need to handle first-payment mandate creation, recurring charge scheduling, and webhook-driven lifecycle events inside Cloudflare Workers — without a traditional server.

## Context

Mollie's recurring model uses a two-step flow: (1) a first payment that creates a mandate on the customer's payment method, and (2) subsequent server-side charges billed against that mandate. Unlike Stripe subscriptions, Mollie charges are initiated by the platform explicitly — there is no built-in scheduler, so the Worker cron trigger fills that role. Mollie supports SEPA direct debit, iDEAL, credit card, and Bancontact mandates.

---

## 1. First Payment — Mandate Creation

```typescript
// src/mollie-first-payment.ts
interface Env {
  MOLLIE_API_KEY: string; // test_... or live_...
  RETURN_URL_BASE: string;
}

interface FirstPaymentParams {
  customerId: string;
  amount: { value: string; currency: string }; // e.g. { value: '0.01', currency: 'EUR' }
  description: string;
  redirectUrl: string;
  webhookUrl: string;
}

async function createFirstPayment(
  env: Env,
  params: FirstPaymentParams
): Promise<{ checkoutUrl: string; paymentId: string }> {
  const res = await fetch('https://api.mollie.com/v2/payments', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.MOLLIE_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      amount: params.amount,
      description: params.description,
      redirectUrl: params.redirectUrl,
      webhookUrl: params.webhookUrl,
      customerId: params.customerId,
      sequenceType: 'first', // signals mandate creation
    }),
  });

  if (!res.ok) throw new Error(`Mollie first payment error: ${await res.text()}`);
  const data = await res.json<{
    id: string;
    _links: { checkout: { href: string } };
  }>();

  return { checkoutUrl: data._links.checkout.href, paymentId: data.id };
}

export { createFirstPayment };
```

---

## 2. Creating a Mollie Customer

```typescript
// src/mollie-customer.ts
async function getOrCreateCustomer(
  apiKey: string,
  email: string,
  name: string
): Promise<string> {
  // Mollie has no search-by-email; store customer ID in D1 on creation
  const res = await fetch('https://api.mollie.com/v2/customers', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name, email }),
  });

  if (!res.ok)
    throw new Error(`Mollie customer creation error: ${await res.text()}`);
  const { id } = await res.json<{ id: string }>();
  return id;
}

export { getOrCreateCustomer };
```

---

## 3. Charging a Recurring Payment Against an Existing Mandate

```typescript
// src/mollie-recurring-charge.ts
interface RecurringChargeParams {
  customerId: string;
  mandateId: string;
  amount: { value: string; currency: string };
  description: string;
  webhookUrl: string;
}

async function chargeRecurring(
  apiKey: string,
  params: RecurringChargeParams
): Promise<{ paymentId: string; status: string }> {
  const res = await fetch('https://api.mollie.com/v2/payments', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      amount: params.amount,
      description: params.description,
      webhookUrl: params.webhookUrl,
      customerId: params.customerId,
      mandateId: params.mandateId,
      sequenceType: 'recurring',
    }),
  });

  if (!res.ok) throw new Error(`Mollie recurring charge error: ${await res.text()}`);
  const { id, status } = await res.json<{ id: string; status: string }>();
  return { paymentId: id, status };
}

export { chargeRecurring };
```

---

## 4. Webhook Handler with HMAC Verification

Mollie webhooks send a `POST` with `id=<payment_id>` in the body (form-encoded). There is no built-in signature header in the standard API; use the `testmode` flag and verify by fetching the payment from Mollie.

```typescript
// src/mollie-webhook.ts
interface Env {
  MOLLIE_API_KEY: string;
  DB: D1Database;
}

export async function handleMollieWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.text();
  const params = new URLSearchParams(body);
  const paymentId = params.get('id');
  if (!paymentId) return new Response('Missing id', { status: 400 });

  // Verify by fetching from Mollie (prevents spoofed notifications)
  const res = await fetch(`https://api.mollie.com/v2/payments/${paymentId}`, {
    headers: { Authorization: `Bearer ${env.MOLLIE_API_KEY}` },
  });

  if (!res.ok) return new Response('Payment not found', { status: 404 });
  const payment = await res.json<{
    id: string;
    status: string;
    customerId?: string;
    mandateId?: string;
    metadata: Record<string, string>;
  }>();

  await env.DB.prepare(
    `INSERT INTO mollie_payments (payment_id, status, customer_id, mandate_id, updated_at)
     VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(payment_id) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at`
  )
    .bind(
      payment.id,
      payment.status,
      payment.customerId ?? null,
      payment.mandateId ?? null
    )
    .run();

  if (payment.status === 'paid' && payment.metadata?.subscriptionId) {
    await env.DB.prepare(
      'UPDATE subscriptions SET status = ? WHERE id = ?'
    )
      .bind('active', payment.metadata.subscriptionId)
      .run();
  }

  return new Response('OK');
}
```

---

## 5. Cron Trigger for Monthly Billing Runs

```typescript
// src/billing-cron.ts
interface Env {
  DB: D1Database;
  MOLLIE_API_KEY: string;
  WEBHOOK_URL: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const due = await env.DB.prepare(
      `SELECT s.id, s.customer_id, s.mandate_id, s.plan_amount, s.plan_currency
       FROM subscriptions s
       WHERE s.status = 'active'
         AND s.next_billing_date <= date('now')
       LIMIT 100`
    ).all<{
      id: string;
      customer_id: string;
      mandate_id: string;
      plan_amount: string;
      plan_currency: string;
    }>();

    const { chargeRecurring } = await import('./mollie-recurring-charge');

    for (const sub of due.results) {
      try {
        const { paymentId } = await chargeRecurring(env.MOLLIE_API_KEY, {
          customerId: sub.customer_id,
          mandateId: sub.mandate_id,
          amount: { value: sub.plan_amount, currency: sub.plan_currency },
          description: `Subscription renewal ${sub.id}`,
          webhookUrl: `${env.WEBHOOK_URL}/mollie/webhook`,
        });

        await env.DB.prepare(
          `UPDATE subscriptions
           SET last_payment_id = ?, next_billing_date = date(next_billing_date, '+1 month')
           WHERE id = ?`
        ).bind(paymentId, sub.id).run();
      } catch (err) {
        console.error(`Billing failed for subscription ${sub.id}:`, err);
      }
    }
  },
};
```

---

## Anti-patterns

- **Using `sequenceType: 'recurring'` without a valid `mandateId`** — Mollie will reject the charge with a 422; always verify the mandate's `status === 'valid'` before billing.
- **Relying on Mollie's built-in subscription resource** — Mollie Subscriptions are a convenience wrapper with limited flexibility; for custom plans use explicit recurring payments as shown above.
- **Not verifying webhook payments by re-fetching from Mollie** — Without this verification step, any actor who knows your webhook URL can fake payment events.
- **Storing amounts as floats** — Mollie requires amounts as strings with exactly two decimal places (`"9.99"`); floating-point arithmetic will cause validation errors.

## Gotchas

- Mollie's `first` payment does not immediately create a mandate — the mandate appears only after the payment reaches `paid` status. Poll `GET /v2/customers/{id}/mandates` after the webhook fires.
- SEPA direct debit mandates take 2–5 business days to settle; charge status remains `pending` during this window.
- Test mode and live mode use different API keys but the same API host; switch keys via `wrangler secret`.
- `metadata` on payments is limited to 1 KB and is returned in webhook-triggered fetches.

## Verification

```bash
# Trigger test webhook from Mollie dashboard or via:
curl -X POST https://your-worker.workers.dev/mollie/webhook \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'id=tr_WDqYK6vllg'

# Confirm D1 updated
wrangler d1 execute <DB> --command "SELECT * FROM mollie_payments WHERE payment_id='tr_WDqYK6vllg'"

# Trigger cron manually
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"
```

## Related

- `payment-dunning-management-cloudflare-queues.md`
- `recurring-mandate-lifecycle.md`
- `sepa-direct-debit-return-handling.md`
- `idempotency-keys-payment-apis.md`

## Sources

- https://docs.mollie.com/reference/v2/payments-api/create-payment
- https://docs.mollie.com/reference/v2/mandates-api/get-mandate
- https://docs.mollie.com/payments/recurring
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
