# Authorize.Net Accept.js + Cloudflare Workers Integration

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to accept card payments through Authorize.Net on a Cloudflare Workers + D1 backend.
Cardholders enter card details in a hosted Accept.js iframe; Workers call the Authorize.Net
Transaction API server-side. PCI SAQ-A scope is maintained because raw PANs never touch your servers.

## Context

Authorize.Net (owned by Visa) dominates US small-to-mid-market merchants. Its API uses
XML/JSON over HTTPS with an API Login ID + Transaction Key credential pair — no OAuth. Accept.js
generates a one-time `opaqueData` descriptor that replaces the PAN for server-side processing.
The API is synchronous: a 200 response contains the transaction result, so no webhook is needed
for the initial charge, though settlement and void events arrive via Silent Post or Webhooks v1.

## Accept.js Client-Side Token Flow

```html
<!-- Load Accept.js from Authorize.Net CDN — allowed by Workers CSP -->
<script src="https://jstest.authorize.net/v1/Accept.js"
        data-client-key="YOUR_PUBLIC_CLIENT_KEY"></script>
<script>
function dispatchData(response) {
  if (response.messages.resultCode === 'Error') {
    console.error(response.messages.message[0].text);
    return;
  }
  // Send opaqueData to your Worker endpoint — NO raw card data leaves the browser
  fetch('/api/charge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      opaqueDataDescriptor: response.opaqueData.dataDescriptor,
      opaqueDataValue: response.opaqueData.dataValue,
      amount: document.getElementById('amount').value,
    }),
  });
}

function sendPaymentDataToAnet() {
  Accept.dispatchData({
    authData: {
      clientKey: 'YOUR_PUBLIC_CLIENT_KEY',
      apiLoginID: 'YOUR_API_LOGIN_ID',
    },
    cardData: {
      cardNumber: document.getElementById('cardNum').value,
      month: document.getElementById('expMonth').value,
      year: document.getElementById('expYear').value,
      cardCode: document.getElementById('cvv').value,
    },
  }, dispatchData);
}
</script>
```

## Worker: Charge via Authorize.Net Transaction API

```typescript
// src/handlers/authorize-net-charge.ts
interface Env {
  ANET_API_LOGIN_ID: string;
  ANET_TRANSACTION_KEY: string;
  ANET_ENDPOINT: string; // https://api.authorize.net/xml/v1/request.api
  DB: D1Database;
}

interface ANetTransactionResponse {
  transactionResponse: {
    responseCode: string;
    transId: string;
    messages?: { message: Array<{ code: string; description: string }> };
    errors?: { error: Array<{ errorCode: string; errorText: string }> };
  };
}

async function chargeOpaqueData(
  env: Env,
  descriptor: string,
  value: string,
  amountCents: number,
  orderId: string
): Promise<{ transactionId: string; approved: boolean; error?: string }> {
  const payload = {
    createTransactionRequest: {
      merchantAuthentication: {
        name: env.ANET_API_LOGIN_ID,
        transactionKey: env.ANET_TRANSACTION_KEY,
      },
      refId: orderId.slice(0, 20), // Authorize.Net refId max 20 chars
      transactionRequest: {
        transactionType: 'authCaptureTransaction',
        amount: (amountCents / 100).toFixed(2),
        payment: {
          opaqueData: {
            dataDescriptor: descriptor,
            dataValue: value,
          },
        },
      },
    },
  };

  const res = await fetch(env.ANET_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  // Authorize.Net sometimes returns 200 with BOM; strip it
  const text = (await res.text()).replace(/^﻿/, '');
  const data: ANetTransactionResponse = JSON.parse(text);
  const txn = data.transactionResponse;

  if (txn.responseCode === '1') {
    return { transactionId: txn.transId, approved: true };
  }
  const errorText = txn.errors?.error[0]?.errorText ?? 'Transaction declined';
  return { transactionId: txn.transId, approved: false, error: errorText };
}

export async function handleCharge(request: Request, env: Env): Promise<Response> {
  const { opaqueDataDescriptor, opaqueDataValue, amount, orderId } = await request.json<{
    opaqueDataDescriptor: string;
    opaqueDataValue: string;
    amount: string;
    orderId: string;
  }>();

  const amountCents = Math.round(parseFloat(amount) * 100);
  const result = await chargeOpaqueData(
    env, opaqueDataDescriptor, opaqueDataValue, amountCents, orderId
  );

  await env.DB.prepare(
    `INSERT INTO anet_transactions (order_id, transaction_id, approved, created_at)
     VALUES (?, ?, ?, ?)`
  ).bind(orderId, result.transactionId, result.approved ? 1 : 0, Date.now()).run();

  if (!result.approved) {
    return Response.json({ error: result.error }, { status: 402 });
  }
  return Response.json({ transactionId: result.transactionId });
}
```

## Void and Refund

```typescript
async function voidTransaction(env: Env, transId: string): Promise<boolean> {
  const payload = {
    createTransactionRequest: {
      merchantAuthentication: { name: env.ANET_API_LOGIN_ID, transactionKey: env.ANET_TRANSACTION_KEY },
      transactionRequest: { transactionType: 'voidTransaction', refTransId: transId },
    },
  };
  const res = await fetch(env.ANET_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const text = (await res.text()).replace(/^﻿/, '');
  const data = JSON.parse(text);
  return data.transactionResponse?.responseCode === '1';
}

async function refundTransaction(
  env: Env,
  transId: string,
  lastFour: string,
  amountCents: number
): Promise<boolean> {
  const payload = {
    createTransactionRequest: {
      merchantAuthentication: { name: env.ANET_API_LOGIN_ID, transactionKey: env.ANET_TRANSACTION_KEY },
      transactionRequest: {
        transactionType: 'refundTransaction',
        amount: (amountCents / 100).toFixed(2),
        payment: { creditCard: { cardNumber: lastFour, expirationDate: 'XXXX' } },
        refTransId: transId,
      },
    },
  };
  const res = await fetch(env.ANET_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const text = (await res.text()).replace(/^﻿/, '');
  const data = JSON.parse(text);
  return data.transactionResponse?.responseCode === '1';
}
```

## Webhook Signature Verification (Authorize.Net Webhooks v1)

```typescript
// Authorize.Net signs webhooks with HMAC-SHA512 using your Signature Key
async function verifyANetWebhook(
  body: string,
  signatureHeader: string,
  signatureKey: string
): Promise<boolean> {
  const keyBytes = new TextEncoder().encode(signatureKey);
  const cryptoKey = await crypto.subtle.importKey(
    'raw', keyBytes, { name: 'HMAC', hash: 'SHA-512' }, false, ['sign']
  );
  const bodyBytes = new TextEncoder().encode(body);
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, bodyBytes);
  const computed = Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, '0')).join('').toUpperCase();
  // Header arrives as "sha512=<hex>"
  const provided = signatureHeader.replace(/^sha512=/i, '').toUpperCase();
  return computed === provided;
}
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS anet_transactions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id    TEXT NOT NULL,
  transaction_id TEXT NOT NULL,
  approved    INTEGER NOT NULL DEFAULT 0,
  voided      INTEGER NOT NULL DEFAULT 0,
  refunded    INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anet_order ON anet_transactions(order_id);
```

## Anti-patterns

- **Storing the Transaction Key in KV without encryption** — treat it as a secret; bind it as an
  encrypted Worker secret via `wrangler secret put ANET_TRANSACTION_KEY`.
- **Parsing the JSON response without stripping the BOM** — Authorize.Net responses include a
  UTF-8 BOM that breaks `JSON.parse`; always call `.replace(/^﻿/, '')` first.
- **Refunding before settlement** — transactions in "Pending Settlement" cannot be refunded; void
  them instead. Query transaction status with `getTransactionDetailsRequest` if unsure.
- **Using `refId` longer than 20 characters** — Authorize.Net silently truncates, breaking
  order-to-transaction lookups.

## Gotchas

- The test endpoint (`apitest.authorize.net`) and production endpoint (`api.authorize.net`) use
  the same URL path but different credentials. Use an `ANET_ENDPOINT` env var to toggle.
- `opaqueData` tokens expire after 15 minutes and are single-use.
- Authorize.Net response codes: `1` = Approved, `2` = Declined, `3` = Error, `4` = Held for review.
- Silent Post (legacy) and Webhooks v1 are separate systems; prefer Webhooks v1 for reliability.
- The `refTransId` field in refunds must be the settled transaction's `transId`, not `authCode`.

## Verification

```bash
# Sandbox test charge — card number 4111111111111111, any future expiry, any CVV
curl -s https://apitest.authorize.net/xml/v1/request.api \
  -H 'Content-Type: application/json' \
  -d '{"createTransactionRequest":{"merchantAuthentication":{"name":"API_LOGIN","transactionKey":"TRANS_KEY"},"transactionRequest":{"transactionType":"authCaptureTransaction","amount":"1.00","payment":{"creditCard":{"cardNumber":"4111111111111111","expirationDate":"2030-12","cardCode":"123"}}}}}'

# Check Worker charge endpoint with opaqueData from Accept.js sandbox
curl -s -X POST https://your-worker.workers.dev/api/charge \
  -H 'Content-Type: application/json' \
  -d '{"opaqueDataDescriptor":"COMMON.ACCEPT.INAPP.PAYMENT","opaqueDataValue":"...","amount":"9.99","orderId":"order_001"}'
```

## Related

- `idempotency-keys-payment-apis.md`
- `pci-dss-saq-a-compliance.md`
- `payment-error-handling.md`
- `partial-refund-handling.md`
- `payment-audit-logging.md`

## Sources

- https://developer.authorize.net/api/reference/index.html
- https://developer.authorize.net/api/reference/features/acceptjs.html
- https://developer.authorize.net/api/reference/features/webhooks.html
- https://developer.authorize.net/hello_world/testing_guide/
