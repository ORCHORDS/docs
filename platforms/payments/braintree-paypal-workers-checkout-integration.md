# Braintree PayPal Workers Checkout Integration

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You want to accept credit cards and PayPal through Braintree's SDK on a Cloudflare Workers-backed checkout, storing transaction records in D1 and using the server-side GraphQL API for captures and refunds.

## Context
Braintree (a PayPal service) exposes a REST and GraphQL API for server-side operations and a JavaScript Drop-in UI for the browser. The Workers edge handles client-token generation, webhook ingestion, and idempotent transaction recording. D1 stores order and transaction rows; KV caches nonces briefly to prevent replay.

## Client Token Generation

The Braintree client token must be generated server-side per session and returned to the browser so the Drop-in UI can initialize. Tokens expire after 24 hours; generate them on demand rather than caching globally.

```typescript
// src/braintree-client-token.ts
export interface Env {
  BRAINTREE_MERCHANT_ID: string;
  BRAINTREE_PUBLIC_KEY: string;
  BRAINTREE_PRIVATE_KEY: string;
  DB: D1Database;
  NONCE_CACHE: KVNamespace;
}

const BT_BASE = 'https://payments.braintree-api.com';

function btAuth(env: Env): string {
  const creds = `${env.BRAINTREE_PUBLIC_KEY}:${env.BRAINTREE_PRIVATE_KEY}`;
  return `Basic ${btoa(creds)}`;
}

export async function generateClientToken(env: Env, customerId?: string): Promise<string> {
  const body: Record<string, unknown> = {};
  if (customerId) body.customerId = customerId;

  const res = await fetch(
    `${BT_BASE}/merchants/${env.BRAINTREE_MERCHANT_ID}/client_token`,
    {
      method: 'POST',
      headers: {
        Authorization: btAuth(env),
        'Braintree-Version': '2019-01-01',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    }
  );

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Braintree client token error ${res.status}: ${err}`);
  }

  const data = await res.json<{ clientToken: string }>();
  return data.clientToken;
}
```

## Transaction Sale via GraphQL API

Braintree's GraphQL endpoint is preferred for new integrations. Use it to charge a payment method nonce returned by the browser Drop-in UI.

```typescript
// src/braintree-transaction.ts
const GRAPHQL_URL = 'https://payments.braintree-api.com/graphql';

const CHARGE_MUTATION = `
  mutation ChargePaymentMethod($input: ChargePaymentMethodInput!) {
    chargePaymentMethod(input: $input) {
      transaction {
        id
        status
        amount { value currencyIsoCode }
        paymentMethodSnapshot {
          ... on CreditCardDetails { last4 cardholderName }
          ... on PayPalTransactionDetails { payerEmail }
        }
      }
    }
  }
`;

export async function chargePaymentMethod(
  env: Env,
  paymentMethodNonce: string,
  amountCents: number,
  orderId: string
): Promise<{ transactionId: string; status: string }> {
  const amount = (amountCents / 100).toFixed(2);

  const res = await fetch(GRAPHQL_URL, {
    method: 'POST',
    headers: {
      Authorization: btAuth(env),
      'Braintree-Version': '2019-01-01',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query: CHARGE_MUTATION,
      variables: {
        input: {
          paymentMethodId: paymentMethodNonce,
          transaction: {
            amount,
            orderId,
            options: { submitForSettlement: true },
          },
        },
      },
    }),
  });

  if (!res.ok) throw new Error(`GraphQL HTTP ${res.status}`);

  const json = await res.json<{
    data?: { chargePaymentMethod: { transaction: { id: string; status: string } } };
    errors?: { message: string }[];
  }>();

  if (json.errors?.length) throw new Error(json.errors[0].message);

  const tx = json.data!.chargePaymentMethod.transaction;
  return { transactionId: tx.id, status: tx.status };
}
```

## D1 Order and Transaction Storage

Store orders and Braintree transaction IDs in D1 with an idempotency column keyed on `orderId` to survive retries from the browser.

```typescript
// src/braintree-d1.ts
export async function upsertTransaction(
  db: D1Database,
  orderId: string,
  btTransactionId: string,
  status: string,
  amountCents: number,
  currency: string
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO bt_transactions
         (order_id, bt_transaction_id, status, amount_cents, currency, created_at)
       VALUES (?, ?, ?, ?, ?, unixepoch())
       ON CONFLICT(order_id) DO UPDATE SET
         bt_transaction_id = excluded.bt_transaction_id,
         status            = excluded.status,
         updated_at        = unixepoch()`
    )
    .bind(orderId, btTransactionId, status, amountCents, currency)
    .run();
}

export async function getTransactionByOrder(
  db: D1Database,
  orderId: string
): Promise<{ bt_transaction_id: string; status: string } | null> {
  const row = await db
    .prepare('SELECT bt_transaction_id, status FROM bt_transactions WHERE order_id = ?')
    .bind(orderId)
    .first<{ bt_transaction_id: string; status: string }>();
  return row ?? null;
}
```

## Webhook Ingestion and Verification

Braintree webhooks use HMAC-SHA1. Parse the `bt_signature` and `bt_payload` form fields, verify, then process the notification kind.

```typescript
// src/braintree-webhook.ts
async function verifyBraintreeWebhook(
  env: Env,
  signature: string,
  payload: string
): Promise<boolean> {
  const [publicKey, hmacHex] = signature.split('|');
  if (publicKey !== env.BRAINTREE_PUBLIC_KEY) return false;

  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(env.BRAINTREE_PRIVATE_KEY),
    { name: 'HMAC', hash: 'SHA-1' },
    false,
    ['verify']
  );

  const hexBytes = new Uint8Array(
    hmacHex.match(/.{2}/g)!.map((b) => parseInt(b, 16))
  );
  const payloadBytes = new TextEncoder().encode(atob(payload));

  return crypto.subtle.verify('HMAC', key, hexBytes, payloadBytes);
}

export async function handleBraintreeWebhook(request: Request, env: Env): Promise<Response> {
  const form = await request.formData();
  const btSignature = form.get('bt_signature') as string;
  const btPayload = form.get('bt_payload') as string;

  if (!btSignature || !btPayload) return new Response('Bad Request', { status: 400 });

  const valid = await verifyBraintreeWebhook(env, btSignature, btPayload);
  if (!valid) return new Response('Unauthorized', { status: 401 });

  // Braintree payloads are base64-encoded XML; parse the kind field minimally
  const decoded = atob(btPayload);
  const kindMatch = decoded.match(/<kind>([^<]+)<\/kind>/);
  const kind = kindMatch?.[1] ?? 'unknown';

  if (kind === 'transaction_settled') {
    const idMatch = decoded.match(/<id>([^<]+)<\/id>/);
    const txId = idMatch?.[1];
    if (txId) {
      await env.DB.prepare(
        "UPDATE bt_transactions SET status = 'settled', updated_at = unixepoch() WHERE bt_transaction_id = ?"
      )
        .bind(txId)
        .run();
    }
  }

  return new Response('OK');
}
```

## Worker Entry Point

```typescript
// src/index.ts
import { Env } from './braintree-client-token';
import { generateClientToken } from './braintree-client-token';
import { chargePaymentMethod } from './braintree-transaction';
import { upsertTransaction, getTransactionByOrder } from './braintree-d1';
import { handleBraintreeWebhook } from './braintree-webhook';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/client-token' && request.method === 'GET') {
      const token = await generateClientToken(env);
      return Response.json({ clientToken: token });
    }

    if (url.pathname === '/checkout' && request.method === 'POST') {
      const { nonce, orderId, amountCents, currency } = await request.json<{
        nonce: string;
        orderId: string;
        amountCents: number;
        currency: string;
      }>();

      // Idempotency: return existing result if already processed
      const existing = await getTransactionByOrder(env.DB, orderId);
      if (existing) return Response.json(existing);

      const { transactionId, status } = await chargePaymentMethod(env, nonce, amountCents, orderId);
      await upsertTransaction(env.DB, orderId, transactionId, status, amountCents, currency);
      return Response.json({ transactionId, status });
    }

    if (url.pathname === '/webhook/braintree' && request.method === 'POST') {
      return handleBraintreeWebhook(request, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Anti-patterns
- Never pass raw card data through Workers — always use the Braintree Drop-in UI or Hosted Fields to tokenize in the browser.
- Do not cache client tokens globally; they are session-specific and encode optional customer context.
- Avoid the legacy REST `/transactions` endpoint — the GraphQL API supports vault operations and has a cleaner error model.
- Do not skip webhook signature verification even in staging; replay attacks on test webhooks can corrupt D1 state.
- Never store the raw `paymentMethodNonce` in D1 — it is single-use and must not be persisted.

## Gotchas
- Braintree GraphQL uses `paymentMethodId` for vault tokens but `paymentMethodNonce` for one-time nonces; the mutation field name is the same but semantics differ.
- `submitForSettlement: true` is required unless you want a separate capture step; forgetting it leaves transactions authorized but unsettled and they void after 30 days.
- Webhook payloads are base64-encoded XML, not JSON — plan your parser accordingly.
- The Braintree sandbox and production endpoints share the same domain pattern but different credentials; misconfigured environments will silently succeed in sandbox mode.
- PayPal transactions through Braintree do not support partial refunds via the GraphQL API as of 2026; use the REST API for those.

## Verification
1. Call `GET /client-token` and confirm a JWT-like string is returned.
2. Use the Braintree sandbox Drop-in UI with test card `4111 1111 1111 1111` to obtain a nonce.
3. `POST /checkout` with that nonce and `orderId=test-001`; confirm `status: submitted_for_settlement`.
4. Repeat the same POST and confirm the idempotent path returns the stored result without hitting Braintree.
5. Send a test webhook from the Braintree control panel and confirm the D1 row updates to `settled`.

## Related
- `stripe-checkout-session-cloudflare-workers.md`
- `paypal-orders-confirm-payment-source.md`
- `stripe-webhook-idempotency-d1-event-log.md`
- `payment-state-machine-design.md`

## Sources
- https://developer.paypal.com/braintree/docs/guides/payment-methods/overview
- https://developer.paypal.com/braintree/docs/reference/general/graphql/overview
- https://developer.paypal.com/braintree/docs/guides/webhooks/overview
