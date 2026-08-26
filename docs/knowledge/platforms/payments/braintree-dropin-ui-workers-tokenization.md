# Braintree Drop-in UI Tokenization with Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project wants to accept credit cards and PayPal through Braintree's Drop-in UI — a PCI-compliant
hosted component that tokenizes payment details in the browser without card data touching example project
servers. The client needs a server-generated `clientToken` to initialize the Drop-in, and the
nonce returned after tokenization must be transacted server-side in a Cloudflare Worker to prevent
client-side price manipulation or double-spend.

## Context
Braintree's server SDK is Node.js-only and requires network calls to Braintree's API, making it
unsuitable for Cloudflare Workers' V8 isolate environment. The integration instead uses Braintree's
REST-style HTTP API directly, authenticating with a Base64-encoded `Public Key:Private Key` pair.
D1 stores transaction records for reconciliation; Workers KV caches customer IDs to avoid
re-creating Braintree customers on every payment.

## Section 1 — Client Token Generation
The Drop-in UI requires a server-issued `clientToken` that is tied to the merchant account. The
token expires after 24 hours and may optionally include a customer ID to vault payment methods.

```typescript
interface Env {
  DB: D1Database;
  CUSTOMER_KV: KVNamespace;
  BRAINTREE_MERCHANT_ID: string;
  BRAINTREE_PUBLIC_KEY: string;
  BRAINTREE_PRIVATE_KEY: string;
  BRAINTREE_BASE_URL: string; // https://api.braintreegateway.com or sandbox equivalent
}

function braintreeAuthHeader(env: Env): string {
  return `Basic ${btoa(`${env.BRAINTREE_PUBLIC_KEY}:${env.BRAINTREE_PRIVATE_KEY}`)}`;
}

async function generateClientToken(
  env: Env,
  userId: string
): Promise<string> {
  // Look up or create a Braintree customer ID for vault support
  let customerId = await env.CUSTOMER_KV.get(`bt_customer:${userId}`);

  if (!customerId) {
    customerId = await createBraintreeCustomer(env, userId);
    await env.CUSTOMER_KV.put(`bt_customer:${userId}`, customerId, {
      expirationTtl: 60 * 60 * 24 * 90, // 90-day cache
    });
  }

  const res = await fetch(
    `${env.BRAINTREE_BASE_URL}/merchants/${env.BRAINTREE_MERCHANT_ID}/client_token`,
    {
      method: 'POST',
      headers: {
        Authorization: braintreeAuthHeader(env),
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'Braintree-Version': '2019-01-01',
      },
      body: JSON.stringify({ client_token: { customer_id: customerId, version: 3 } }),
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Braintree client token error: ${res.status} ${err}`);
  }

  const data = await res.json<{ client_token: string }>();
  return data.client_token;
}

async function createBraintreeCustomer(env: Env, userId: string): Promise<string> {
  const res = await fetch(
    `${env.BRAINTREE_BASE_URL}/merchants/${env.BRAINTREE_MERCHANT_ID}/customers`,
    {
      method: 'POST',
      headers: {
        Authorization: braintreeAuthHeader(env),
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'Braintree-Version': '2019-01-01',
      },
      body: JSON.stringify({ customer: { id: `example project_${userId}` } }),
    }
  );

  if (!res.ok) {
    const text = await res.text();
    // 422 with "customer already exists" is safe to treat as success on retry
    if (res.status === 422 && text.includes('already')) return `example project_${userId}`;
    throw new Error(`Braintree customer creation error: ${res.status} ${text}`);
  }

  const data = await res.json<{ customer: { id: string } }>();
  return data.customer.id;
}
```

## Section 2 — Nonce Transact: Server-Side Sale
After the Drop-in returns a `paymentMethodNonce`, POST it to a Worker endpoint. The Worker reads the
authoritative amount from D1 (keyed to an `orderId`), never from the client, then transacts with
Braintree's `/transactions` endpoint.

```typescript
interface SaleRequest {
  orderId: string;
  nonce: string;
  userId: string;
  deviceData?: string; // Braintree's device fingerprint for fraud scoring
}

interface BraintreeTransaction {
  id: string;
  status: string;
  amount: string;
  currency_iso_code: string;
}

async function transactNonce(env: Env, req: SaleRequest): Promise<Response> {
  // Read authoritative price from D1 — never trust client-supplied amount
  const order = await env.DB
    .prepare(
      `SELECT amount, currency, product_id, status
       FROM pending_orders WHERE order_id = ? AND user_id = ?`
    )
    .bind(req.orderId, req.userId)
    .first<{ amount: string; currency: string; product_id: string; status: string }>();

  if (!order) return new Response('Order not found', { status: 404 });
  if (order.status === 'completed') {
    return Response.json({ already: true });
  }
  if (order.status !== 'pending') {
    return new Response(`Unexpected order status: ${order.status}`, { status: 409 });
  }

  const customerId = await env.CUSTOMER_KV.get(`bt_customer:${req.userId}`);

  const saleBody: Record<string, unknown> = {
    transaction: {
      type: 'sale',
      amount: order.amount,
      payment_method_nonce: req.nonce,
      order_id: req.orderId,
      options: {
        submit_for_settlement: true,
        store_in_vault_on_success: true,
      },
    },
  };

  if (customerId) (saleBody.transaction as Record<string, unknown>).customer_id = customerId;
  if (req.deviceData) (saleBody.transaction as Record<string, unknown>).device_data = req.deviceData;

  const txRes = await fetch(
    `${env.BRAINTREE_BASE_URL}/merchants/${env.BRAINTREE_MERCHANT_ID}/transactions`,
    {
      method: 'POST',
      headers: {
        Authorization: braintreeAuthHeader(env),
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'Braintree-Version': '2019-01-01',
      },
      body: JSON.stringify(saleBody),
    }
  );

  const txData = await txRes.json<{
    transaction?: BraintreeTransaction;
    api_error_response?: { errors: unknown; message: string };
  }>();

  if (!txRes.ok || !txData.transaction) {
    console.error(`Braintree sale failed: ${JSON.stringify(txData.api_error_response)}`);
    return new Response(
      txData.api_error_response?.message ?? 'Transaction failed',
      { status: 402 }
    );
  }

  const tx = txData.transaction;

  // Record transaction and mark order complete atomically
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO braintree_transactions
         (transaction_id, order_id, user_id, amount, currency, status, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT DO NOTHING`
    ).bind(tx.id, req.orderId, req.userId, tx.amount, tx.currency_iso_code, tx.status, Date.now()),
    env.DB.prepare(
      `UPDATE pending_orders SET status = 'completed', transaction_id = ?, updated_at = ?
       WHERE order_id = ? AND status = 'pending'`
    ).bind(tx.id, Date.now(), req.orderId),
  ]);

  return Response.json({ transactionId: tx.id, status: tx.status });
}
```

## Section 3 — Webhook Verification and Settlement Confirmation
Braintree sends webhook notifications for settlement, disputes, and subscription events. Verify
the signature using a two-part HMAC check on the `bt_signature` + `bt_payload` POST fields.

```typescript
async function verifyBraintreeWebhook(
  btSignature: string,
  btPayload: string,
  privateKey: string
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(privateKey),
    { name: 'HMAC', hash: 'SHA-1' },
    false,
    ['sign']
  );
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(btPayload));
  const computed = Array.from(new Uint8Array(mac))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
  return computed === btSignature.split('|')[1];
}

async function handleBraintreeWebhook(request: Request, env: Env): Promise<Response> {
  const formData = await request.formData();
  const btSignature = formData.get('bt_signature') as string;
  const btPayload = formData.get('bt_payload') as string;

  const valid = await verifyBraintreeWebhook(
    btSignature,
    btPayload,
    env.BRAINTREE_PRIVATE_KEY
  );
  if (!valid) return new Response('Invalid signature', { status: 400 });

  // Braintree payload is Base64-encoded XML; parse the notification kind
  const decoded = atob(btPayload);
  const kindMatch = decoded.match(/<kind>([^<]+)<\/kind>/);
  const kind = kindMatch?.[1];
  const txIdMatch = decoded.match(/<id>([^<]+)<\/id>/);
  const txId = txIdMatch?.[1];

  if (kind === 'transaction_settled' && txId) {
    await env.DB
      .prepare(
        `UPDATE braintree_transactions SET status = 'settled', settled_at = ?
         WHERE transaction_id = ?`
      )
      .bind(Date.now(), txId)
      .run();
  }

  if (kind === 'transaction_settlement_declined' && txId) {
    await env.DB
      .prepare(
        `UPDATE braintree_transactions SET status = 'settlement_declined', updated_at = ?
         WHERE transaction_id = ?`
      )
      .bind(Date.now(), txId)
      .run();
    console.error(JSON.stringify({ level: 'error', service: 'braintree', event: kind, txId }));
  }

  return new Response('OK', { status: 200 });
}
```

## Section 4 — Monitoring Transaction Settlement Lag
Alert when transactions remain in `authorized` or `submitted_for_settlement` status beyond the
expected 24-hour settlement window.

```typescript
export async function monitorBraintreeSettlement(env: Env): Promise<void> {
  const ONE_DAY_AGO = Date.now() - 86_400_000;

  const unsettled = await env.DB
    .prepare(
      `SELECT COUNT(*) AS count FROM braintree_transactions
       WHERE status IN ('authorized', 'submitted_for_settlement')
         AND created_at < ?`
    )
    .bind(ONE_DAY_AGO)
    .first<{ count: number }>();

  if ((unsettled?.count ?? 0) > 0) {
    console.error(JSON.stringify({
      level: 'error',
      service: 'braintree',
      alert: 'unsettled_transactions',
      count: unsettled?.count,
      ts: new Date().toISOString(),
    }));
  }
}
```

## Anti-patterns
- Using Braintree's Node.js SDK in Workers — it relies on `https` and `stream` Node.js core modules unavailable in V8 isolates
- Trusting the `amount` field from the Drop-in or the client POST body — always read from D1
- Skipping `submit_for_settlement: true` — this leaves charges in `authorized` state indefinitely, causing voiding
- Not collecting `deviceData` from the Drop-in — Braintree Fraud Tools require it for effective scoring
- Returning the raw Braintree XML error response to the client — it can reveal internal merchant account details

## Gotchas
- Braintree's webhook signature uses HMAC-SHA1, not SHA-256 — the `subtle.sign` hash algorithm must be `SHA-1`
- The `bt_payload` is Base64-encoded XML, not JSON; parse it with regex or an XML parser, not `JSON.parse`
- Customer IDs in Braintree sandbox and production are separate namespaces — KV keys must include environment discriminators in multi-env setups
- Braintree's `clientToken` version 3 enables fingerprinting; versions 1 and 2 are deprecated

## Verification
1. Initialize the Drop-in UI with a server-generated `clientToken` and verify the iframe renders
2. Submit a Braintree sandbox card nonce (`fake-valid-nonce`) and confirm a `submitted_for_settlement` transaction in D1
3. Trigger a `transaction_settled` webhook from Braintree's test tools and confirm D1 `status` updates to `settled`
4. Attempt a second transact call with the same `orderId` and confirm the idempotent `already` response

## Related
- /documentation/docs/policies/payments/braintree-paypal-workers-checkout-integration.md
- /documentation/docs/policies/payments/payment-fraud-detection-velocity-checks.md
- /documentation/docs/policies/payments/idempotency-keys-payment-apis.md
- /documentation/docs/policies/payments/pci-dss-saq-a-compliance.md

## Sources
- https://developer.paypal.com/braintree/docs/start/drop-in
- https://developer.paypal.com/braintree/docs/guides/client-sdk/setup/javascript/v3
- https://developer.paypal.com/braintree/docs/reference/general/webhooks/overview
- https://developer.paypal.com/braintree/docs/guides/transactions/overview
