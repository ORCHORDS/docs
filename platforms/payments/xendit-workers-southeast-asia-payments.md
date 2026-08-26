# Xendit: Southeast Asia Payment Aggregator on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to accept payments across Indonesia, Philippines, Malaysia, Vietnam, and Thailand —
covering bank virtual accounts, local e-wallets (GoPay, OVO, DANA, GrabPay, ShopeePay, Maya),
QRIS, and cards — without wiring each local method separately. Xendit aggregates them under one
REST API, and Workers handle the async webhook callbacks that confirm payment completion.

## Context

Xendit is the dominant payment infrastructure provider in Southeast Asia. Unlike synchronous
Western APIs (charge → immediate result), most Xendit flows are asynchronous: you create a
payment object (invoice, virtual account, e-wallet charge), redirect or present the user, and
receive a webhook when the user pays. Amounts are in local-currency integer (IDR has no decimals).
Workers hold D1 for payment intent state and KV for idempotency receipts.

## Create an Invoice (Hosted Payment Page)

```typescript
// src/handlers/xendit-create-invoice.ts
interface Env {
  XENDIT_SECRET_KEY: string; // money-in secret key (sk_live_...)
  DB: D1Database;
  IDEMPOTENCY_KV: KVNamespace;
}

interface XenditInvoice {
  id: string;
  status: string;
  invoice_url: string;
  external_id: string;
  expiry_date: string;
}

async function createXenditInvoice(
  env: Env,
  orderId: string,
  amountIDR: number,
  customerEmail: string,
  description: string
): Promise<XenditInvoice> {
  // Idempotency: skip duplicate creation for same orderId
  const existing = await env.IDEMPOTENCY_KV.get(`xendit:invoice:${orderId}`);
  if (existing) return JSON.parse(existing);

  const body = {
    external_id: orderId,
    amount: amountIDR,         // IDR: integer, no decimals
    currency: 'IDR',
    customer: { email: customerEmail },
    description,
    success_redirect_url: `https://yourdomain.com/checkout/success?order=${orderId}`,
    failure_redirect_url: `https://yourdomain.com/checkout/failed?order=${orderId}`,
    invoice_duration: 3600,    // seconds; expires in 1 hour
    payment_methods: ['CREDIT_CARD', 'OVO', 'DANA', 'LINKAJA', 'QRIS', 'BCA', 'BNI', 'MANDIRI'],
  };

  const res = await fetch('https://api.xendit.co/v2/invoices', {
    method: 'POST',
    headers: {
      'Authorization': `Basic ${btoa(env.XENDIT_SECRET_KEY + ':')}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json<{ error_code: string; message: string }>();
    throw new Error(`Xendit invoice creation failed: ${err.error_code} — ${err.message}`);
  }

  const invoice = await res.json<XenditInvoice>();

  // Cache idempotency record for 2 hours (longer than invoice_duration)
  await env.IDEMPOTENCY_KV.put(
    `xendit:invoice:${orderId}`,
    JSON.stringify(invoice),
    { expirationTtl: 7200 }
  );

  await env.DB.prepare(
    `INSERT INTO xendit_payments (order_id, xendit_id, status, invoice_url, created_at)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(orderId, invoice.id, invoice.status, invoice.invoice_url, Date.now()).run();

  return invoice;
}
```

## Webhook Callback Handler

```typescript
// src/handlers/xendit-webhook.ts
// Xendit sends x-callback-token header — compare against your configured callback token

interface XenditInvoiceCallback {
  id: string;
  external_id: string;
  status: 'PAID' | 'EXPIRED' | 'SETTLED';
  payment_method: string;
  payment_channel: string;
  paid_amount: number;
  paid_at: string;
}

export async function handleXenditWebhook(request: Request, env: Env): Promise<Response> {
  const callbackToken = request.headers.get('x-callback-token');
  if (callbackToken !== env.XENDIT_CALLBACK_TOKEN) {
    return new Response('Unauthorized', { status: 401 });
  }

  const event = await request.json<XenditInvoiceCallback>();

  if (event.status === 'PAID' || event.status === 'SETTLED') {
    await env.DB.prepare(
      `UPDATE xendit_payments
       SET status = ?, paid_amount = ?, paid_at = ?, payment_method = ?, payment_channel = ?
       WHERE xendit_id = ?`
    ).bind(
      event.status,
      event.paid_amount,
      new Date(event.paid_at).getTime(),
      event.payment_method,
      event.payment_channel,
      event.id
    ).run();

    // Fulfill order
    await fulfillOrder(env, event.external_id, event.paid_amount);
  } else if (event.status === 'EXPIRED') {
    await env.DB.prepare(
      `UPDATE xendit_payments SET status = 'EXPIRED' WHERE xendit_id = ?`
    ).bind(event.id).run();
  }

  return new Response('OK', { status: 200 });
}
```

## Virtual Account (VA) for Bank Transfer

```typescript
// Fixed VA for repeat payers — tied to bank code + customer
async function createVirtualAccount(
  env: Env,
  externalId: string,
  bankCode: 'BCA' | 'BNI' | 'BRI' | 'MANDIRI' | 'PERMATA',
  expectedAmount: number,
  name: string
): Promise<{ account_number: string; bank_code: string; expiration_date: string }> {
  const res = await fetch('https://api.xendit.co/callback_virtual_accounts', {
    method: 'POST',
    headers: {
      'Authorization': `Basic ${btoa(env.XENDIT_SECRET_KEY + ':')}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      external_id: externalId,
      bank_code: bankCode,
      name,
      expected_amount: expectedAmount,
      is_single_use: true,       // invalidate after first payment
      expiration_date: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
    }),
  });

  if (!res.ok) throw new Error(`VA creation failed: ${await res.text()}`);
  const va = await res.json<{ account_number: string; bank_code: string; expiration_date: string }>();
  return va;
}
```

## Payout (Disbursement)

```typescript
// Send money to a bank account — requires money-out secret key
async function disburseFunds(
  env: Env,
  disbursementId: string,
  bankCode: string,
  accountHolderName: string,
  accountNumber: string,
  amountIDR: number,
  description: string
): Promise<string> {
  const res = await fetch('https://api.xendit.co/disbursements', {
    method: 'POST',
    headers: {
      'Authorization': `Basic ${btoa(env.XENDIT_DISBURSEMENT_KEY + ':')}`,
      'Content-Type': 'application/json',
      'Idempotency-key': disbursementId,
    },
    body: JSON.stringify({
      external_id: disbursementId,
      bank_code: bankCode,
      account_holder_name: accountHolderName,
      account_number: accountNumber,
      description,
      amount: amountIDR,
    }),
  });

  if (!res.ok) throw new Error(`Disbursement failed: ${await res.text()}`);
  const result = await res.json<{ id: string; status: string }>();
  return result.id;
}
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS xendit_payments (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id         TEXT NOT NULL UNIQUE,
  xendit_id        TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'PENDING',
  invoice_url      TEXT,
  paid_amount      INTEGER,
  paid_at          INTEGER,
  payment_method   TEXT,
  payment_channel  TEXT,
  created_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_xendit_order ON xendit_payments(order_id);
CREATE INDEX IF NOT EXISTS idx_xendit_xendit_id ON xendit_payments(xendit_id);
```

## Anti-patterns

- **Trusting payment status from redirect URL alone** — the redirect fires on browser return, not
  on confirmed payment. Always wait for the webhook to update order status server-side.
- **Using the wrong secret key for disbursements** — Xendit issues separate "money-in" and
  "money-out" secret keys. Using the money-in key for disbursements returns 403.
- **Amounts with decimals for IDR** — IDR is a zero-decimal currency. Passing `10000.50` causes
  API validation errors; always send integers.
- **Skipping `is_single_use: true` on VAs** — multi-use VAs accept repeat payments, which will
  over-credit an order if not handled explicitly.

## Gotchas

- Xendit's `x-callback-token` is a static pre-shared string configured in your dashboard, not a
  per-request HMAC. Rotate it quarterly and store it as a Worker secret.
- Invoice `status` can be `PENDING` → `PAID` → `SETTLED`; `SETTLED` means funds have cleared
  into your Xendit balance (T+1 or T+2). Fulfill on `PAID`; reconcile on `SETTLED`.
- QRIS payments always arrive with `payment_channel: 'QRIS'` regardless of the underlying app
  (GoPay, OVO, Dana) — you cannot identify the e-wallet from the callback.
- Philippine peso (PHP) disbursements require a separate Philippines sub-account provisioned by
  Xendit. Verify your account region before calling the disbursement endpoint.
- Test mode uses `api.xendit.co` with test credentials (prefix `xnd_development_`), not a
  separate subdomain.

## Verification

```bash
# List your Xendit invoices (last 10)
curl -s https://api.xendit.co/v2/invoices?limit=10 \
  -H "Authorization: Basic $(echo -n 'xnd_development_YOUR_KEY:' | base64)"

# Simulate a paid callback locally via Miniflare
curl -s -X POST http://localhost:8787/webhooks/xendit \
  -H 'Content-Type: application/json' \
  -H 'x-callback-token: YOUR_CALLBACK_TOKEN' \
  -d '{"id":"inv_xxx","external_id":"order_001","status":"PAID","paid_amount":150000,"paid_at":"2026-08-23T10:00:00Z","payment_method":"VIRTUAL_ACCOUNT","payment_channel":"BCA"}'
```

## Related

- `flutterwave-workers-pan-africa-payments.md`
- `paystack-workers-africa-payment-integration.md`
- `mercadopago-workers-latin-america-payments.md`
- `payment-dunning-management-cloudflare-queues.md`
- `idempotency-keys-payment-apis.md`

## Sources

- https://developers.xendit.co/api-reference/
- https://developers.xendit.co/api-reference/#invoices
- https://developers.xendit.co/api-reference/#virtual-accounts
- https://developers.xendit.co/api-reference/#disbursements
- https://developers.xendit.co/api-reference/#callbacks
