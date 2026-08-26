# GoCardless Direct Debit Mandate Management on Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to collect recurring bank payments via Direct Debit (UK Bacs, SEPA, ACH) without
redirecting users to a hosted GoCardless page, or you need to build mandate creation,
cancellation, and payment scheduling workflows entirely within a Cloudflare Workers edge
environment backed by D1 for state persistence.

## Context

GoCardless exposes a REST API for mandate-based pull payments. A mandate authorises future
debits from a customer's bank account without requiring the customer to re-authenticate each
time. Workers serve as the serverless backend that:

- creates billing requests and redirect flows
- handles GoCardless webhooks to track mandate and payment state changes
- schedules payments against confirmed mandates
- stores mandate metadata in D1 for reconciliation

GoCardless webhooks are signed with a `Webhook-Signature` header (HMAC-SHA256). All mandate
state transitions (created → active → cancelled) arrive as webhook events before the API
response propagates fully, so event-driven state management is required.

---

## 1. Creating a Mandate via Billing Request

GoCardless uses a two-step flow: create a BillingRequest, then create a BillingRequestFlow
to redirect the payer.

```typescript
// src/gocardless/mandate-create.ts
interface BillingRequestResponse {
  billing_requests: {
    id: string;
    status: string;
    links: { mandate_request: string };
  };
}

export async function createBillingRequest(
  customerId: string,
  env: Env
): Promise<{ billingRequestId: string; authorisationUrl: string }> {
  const gcToken = env.GOCARDLESS_ACCESS_TOKEN;
  const baseUrl = env.GOCARDLESS_ENVIRONMENT === 'live'
    ? 'https://api.gocardless.com'
    : 'https://api-sandbox.gocardless.com';

  // Step 1: create billing request
  const brRes = await fetch(`${baseUrl}/billing_requests`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${gcToken}`,
      'GoCardless-Version': '2015-07-06',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      billing_requests: {
        mandate_request: { scheme: 'bacs' },
        links: { customer: customerId },
      },
    }),
  });

  if (!brRes.ok) throw new Error(`GoCardless BR create failed: ${brRes.status}`);
  const brData = await brRes.json<BillingRequestResponse>();
  const billingRequestId = brData.billing_requests.id;

  // Step 2: create flow to get redirect URL
  const flowRes = await fetch(`${baseUrl}/billing_request_flows`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${gcToken}`,
      'GoCardless-Version': '2015-07-06',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      billing_request_flows: {
        redirect_uri: env.APP_BASE_URL + '/gocardless/return',
        exit_uri: env.APP_BASE_URL + '/gocardless/cancelled',
        links: { billing_request: billingRequestId },
      },
    }),
  });

  if (!flowRes.ok) throw new Error(`GoCardless flow create failed: ${flowRes.status}`);
  const flowData = await flowRes.json<{ billing_request_flows: { authorisation_url: string } }>();

  return {
    billingRequestId,
    authorisationUrl: flowData.billing_request_flows.authorisation_url,
  };
}
```

---

## 2. Storing Mandate State in D1

```typescript
// src/gocardless/mandate-store.ts
export async function upsertMandate(
  db: D1Database,
  mandate: {
    id: string;
    customerId: string;
    status: string;
    scheme: string;
    createdAt: string;
  }
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO gc_mandates (id, customer_id, status, scheme, created_at, updated_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6)
       ON CONFLICT(id) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at`
    )
    .bind(
      mandate.id,
      mandate.customerId,
      mandate.status,
      mandate.scheme,
      mandate.createdAt,
      new Date().toISOString()
    )
    .run();
}

export async function getActiveMandate(
  db: D1Database,
  customerId: string
): Promise<{ id: string; scheme: string } | null> {
  const row = await db
    .prepare(
      `SELECT id, scheme FROM gc_mandates
       WHERE customer_id = ?1 AND status = 'active'
       ORDER BY created_at DESC LIMIT 1`
    )
    .bind(customerId)
    .first<{ id: string; scheme: string }>();
  return row ?? null;
}
```

---

## 3. Verifying and Processing GoCardless Webhooks

```typescript
// src/gocardless/webhook-handler.ts
async function verifySignature(
  secret: string,
  rawBody: string,
  signature: string
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(rawBody));
  const expected = Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
  return expected === signature;
}

export async function handleGoCardlessWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  const rawBody = await request.text();
  const signature = request.headers.get('Webhook-Signature') ?? '';

  const valid = await verifySignature(env.GOCARDLESS_WEBHOOK_SECRET, rawBody, signature);
  if (!valid) return new Response('Unauthorized', { status: 401 });

  const payload = JSON.parse(rawBody) as {
    events: Array<{
      id: string;
      resource_type: string;
      action: string;
      links: Record<string, string>;
    }>;
  };

  for (const event of payload.events) {
    if (event.resource_type === 'mandates') {
      const mandateId = event.links.mandate;
      const status = mapMandateAction(event.action);
      if (status) {
        await env.DB.prepare(
          `UPDATE gc_mandates SET status = ?1, updated_at = ?2 WHERE id = ?3`
        )
          .bind(status, new Date().toISOString(), mandateId)
          .run();
      }
    }

    if (event.resource_type === 'payments' && event.action === 'paid_out') {
      await env.DB.prepare(
        `UPDATE gc_payments SET status = 'paid_out', settled_at = ?1 WHERE id = ?2`
      )
        .bind(new Date().toISOString(), event.links.payment)
        .run();
    }
  }

  return new Response('OK', { status: 200 });
}

function mapMandateAction(action: string): string | null {
  const map: Record<string, string> = {
    created: 'pending_submission',
    submitted: 'submitted',
    active: 'active',
    cancelled: 'cancelled',
    expired: 'expired',
    failed: 'failed',
    reinstated: 'active',
  };
  return map[action] ?? null;
}
```

---

## 4. Scheduling a One-off Payment Against an Active Mandate

```typescript
// src/gocardless/payment-create.ts
export async function createPayment(
  mandateId: string,
  amountPence: number,
  currency: string,
  description: string,
  env: Env
): Promise<string> {
  const baseUrl = env.GOCARDLESS_ENVIRONMENT === 'live'
    ? 'https://api.gocardless.com'
    : 'https://api-sandbox.gocardless.com';

  const idempotencyKey = crypto.randomUUID();

  const res = await fetch(`${baseUrl}/payments`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.GOCARDLESS_ACCESS_TOKEN}`,
      'GoCardless-Version': '2015-07-06',
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify({
      payments: {
        amount: amountPence,
        currency,
        description,
        links: { mandate: mandateId },
      },
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`GoCardless payment failed: ${res.status} ${err}`);
  }

  const data = await res.json<{ payments: { id: string } }>();
  return data.payments.id;
}
```

---

## Anti-patterns

- **Polling for mandate status** instead of relying on webhook events — mandates take 2-3
  business days to activate under Bacs; polling burns API quota and is unreliable.
- **Skipping idempotency keys** on payment creation — GoCardless deduplicates on
  `Idempotency-Key`; omitting it can cause double charges on retry.
- **Cancelling a mandate via the API and assuming instant effect** — the customer's bank
  still processes in-flight payments submitted before cancellation.
- **Mixing live and sandbox credentials** — sandbox tokens do not work against
  `api.gocardless.com`; guard with an environment flag.

## Gotchas

- Bacs Direct Debit has a mandatory 3-business-day advance notice requirement before the
  first charge; SEPA Core is 5 calendar days. Schedule payments accordingly.
- GoCardless sends `billing_requests.fulfilled` only after the mandate and optional payment
  request are both satisfied. Do not assume mandate activation from this event alone.
- The sandbox does not simulate bank clearing delays; use the "scenario simulator" endpoints
  (`/scenario_simulators/payment_paid_out/actions/run`) to test state transitions.
- GoCardless webhook retries occur with exponential backoff for up to 24 hours; always
  return 200 quickly and process asynchronously via a Queue if needed.

## Verification

```bash
# Confirm mandate status in D1
wrangler d1 execute DB --command \
  "SELECT id, status, updated_at FROM gc_mandates ORDER BY updated_at DESC LIMIT 10"

# Trigger a sandbox payment transition
curl -X POST https://api-sandbox.gocardless.com/scenario_simulators/payment_paid_out/actions/run \
  -H "Authorization: Bearer $GC_SANDBOX_TOKEN" \
  -H "GoCardless-Version: 2015-07-06" \
  -H "Content-Type: application/json" \
  -d '{"data":{"links":{"payment":"PM123"}}}'
```

## Related

- `recurring-mandate-lifecycle.md`
- `sepa-direct-debit-return-handling.md`
- `payment-dunning-management-cloudflare-queues.md`
- `idempotency-keys-payment-apis.md`

## Sources

- https://developer.gocardless.com/api-reference/
- https://developer.gocardless.com/getting-started/billing-requests/overview/
- https://developer.gocardless.com/api-reference/#webhooks-overview
- https://developers.cloudflare.com/d1/
