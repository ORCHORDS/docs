# Nuvei Payment Gateway Integration via Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to process card payments, alternative payment methods (APMs), and recurring billing
through Nuvei (formerly SafeCharge) from a Cloudflare Workers backend — particularly for markets
where Nuvei has stronger acquiring relationships than Stripe (Eastern Europe, Latam, Middle East)
or where you need advanced fraud scoring through Nuvei's native Fraud Management tools.

---

## Context

Nuvei's REST payment API uses a checksum-signed request model rather than OAuth or API keys alone.
Every request includes an `checksum` (SHA-256 of concatenated fields) that Nuvei validates
server-side. The integration flow:

```
Worker  →  POST /getSessionToken  →  Nuvei (returns sessionToken)
Client  →  Nuvei Web SDK (tokenizes card, produces paymentToken)
Worker  →  POST /payment with sessionToken + paymentToken + checksum  →  Nuvei
Nuvei   →  webhook (DMN) →  Worker callback
```

On example project we handle all server-side calls from Workers, tokenize via Nuvei's Simply Connect
(hosted fields), and use D1 to track session tokens, orders, and DMN (Direct Merchant
Notification) events.

---

## D1 Schema

```sql
-- migrations/0022_nuvei_orders.sql
CREATE TABLE IF NOT EXISTS nuvei_orders (
  order_id        TEXT PRIMARY KEY,         -- your internal order id
  session_token   TEXT NOT NULL,
  client_unique_id TEXT NOT NULL UNIQUE,    -- idempotency key you generate
  amount          TEXT NOT NULL,            -- stored as decimal string per Nuvei spec
  currency        TEXT NOT NULL,
  user_id         TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'PENDING',
  nuvei_txn_id    TEXT,                     -- Nuvei transactionId on completion
  payment_method  TEXT,
  created_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS nuvei_dmn_events (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  client_unique_id TEXT NOT NULL,
  txn_type        TEXT NOT NULL,
  status          TEXT NOT NULL,
  nuvei_txn_id    TEXT,
  checksum        TEXT NOT NULL,
  received_at     INTEGER NOT NULL DEFAULT (unixepoch()),
  processed       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_nuvei_orders_user ON nuvei_orders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_nuvei_dmn_uid ON nuvei_dmn_events(client_unique_id);
```

---

## Checksum Generation

```typescript
// src/lib/nuvei-checksum.ts

/**
 * Nuvei requires SHA-256 of concatenated string:
 *   merchantSiteId + merchantId + clientRequestId + amount + currency + timeStamp + merchantSecretKey
 * The exact field order varies by endpoint — always match the Nuvei docs for that call.
 */
export async function buildNuveiChecksum(parts: string[]): Promise<string> {
  const raw = parts.join('');
  const encoder = new TextEncoder();
  const data = encoder.encode(raw);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

export function nowTimestamp(): string {
  // Nuvei format: YYYYMMDDHHmmss
  return new Date()
    .toISOString()
    .replace(/[-T:.Z]/g, '')
    .slice(0, 14);
}
```

---

## Session Token

```typescript
// src/lib/nuvei-session.ts
import { buildNuveiChecksum, nowTimestamp } from './nuvei-checksum';
import { Env } from '../types';

const NUVEI_BASE = 'https://ppp-test.nuvei.com/ppp/api/v1'; // swap to ppp.nuvei.com in prod

export async function getSessionToken(
  clientRequestId: string,
  env: Env,
): Promise<string> {
  const timeStamp = nowTimestamp();
  const checksum = await buildNuveiChecksum([
    env.NUVEI_MERCHANT_ID,
    env.NUVEI_MERCHANT_SITE_ID,
    clientRequestId,
    timeStamp,
    env.NUVEI_SECRET_KEY,
  ]);

  const resp = await fetch(`${NUVEI_BASE}/getSessionToken`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      merchantId: env.NUVEI_MERCHANT_ID,
      merchantSiteId: env.NUVEI_MERCHANT_SITE_ID,
      clientRequestId,
      timeStamp,
      checksum,
    }),
  });

  if (!resp.ok) throw new Error(`Nuvei session token error: ${resp.status}`);
  const data = await resp.json<{ sessionToken: string; status: string }>();
  if (data.status !== 'SUCCESS') throw new Error(`Nuvei session error: ${data.status}`);
  return data.sessionToken;
}
```

---

## Payment Request

```typescript
// src/lib/nuvei-payment.ts
import { buildNuveiChecksum, nowTimestamp } from './nuvei-checksum';
import { Env } from '../types';

const NUVEI_BASE = 'https://ppp-test.nuvei.com/ppp/api/v1';

interface NuveiPaymentParams {
  sessionToken: string;
  clientUniqueId: string;
  amount: string;           // e.g. "99.99" — always string, 2 decimal places
  currency: string;         // e.g. "USD"
  paymentOption: {
    card?: {
      cardNumber?: string;  // not used when using Simply Connect tokenization
      expirationMonth?: string;
      expirationYear?: string;
      CVV?: string;
    };
    userPaymentOptionId?: string; // for saved payment methods
  };
  billingAddress: {
    firstName: string;
    lastName: string;
    email: string;
    country: string;
  };
  deviceDetails: {
    ipAddress: string;
  };
}

interface NuveiPaymentResult {
  transactionStatus: string; // APPROVED | DECLINED | ERROR
  transactionId: string;
  errCode: string;
  reason: string;
  authCode?: string;
}

export async function processNuveiPayment(
  params: NuveiPaymentParams,
  env: Env,
): Promise<NuveiPaymentResult> {
  const timeStamp = nowTimestamp();
  const checksum = await buildNuveiChecksum([
    env.NUVEI_MERCHANT_ID,
    env.NUVEI_MERCHANT_SITE_ID,
    params.clientUniqueId,
    params.amount,
    params.currency,
    params.sessionToken,
    timeStamp,
    env.NUVEI_SECRET_KEY,
  ]);

  const body = {
    sessionToken: params.sessionToken,
    merchantId: env.NUVEI_MERCHANT_ID,
    merchantSiteId: env.NUVEI_MERCHANT_SITE_ID,
    clientUniqueId: params.clientUniqueId,
    amount: params.amount,
    currency: params.currency,
    paymentOption: params.paymentOption,
    billingAddress: params.billingAddress,
    deviceDetails: params.deviceDetails,
    timeStamp,
    checksum,
  };

  const resp = await fetch(`${NUVEI_BASE}/payment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!resp.ok) throw new Error(`Nuvei payment error: ${resp.status}`);
  return resp.json<NuveiPaymentResult>();
}
```

---

## Worker Handler — Initiate Payment

```typescript
// src/handlers/nuvei-checkout.ts
import { Env } from '../types';
import { getSessionToken } from '../lib/nuvei-session';
import { processNuveiPayment } from '../lib/nuvei-payment';

interface CheckoutBody {
  amountCents: number;
  currency: string;
  paymentOptionId?: string;
  billingAddress: { firstName: string; lastName: string; email: string; country: string };
  ipAddress: string;
}

export async function handleNuveiCheckout(
  request: Request,
  env: Env,
  userId: string,
): Promise<Response> {
  const body = await request.json<CheckoutBody>();
  const clientUniqueId = crypto.randomUUID();
  const amount = (body.amountCents / 100).toFixed(2);

  // Get session token (short-lived, per-transaction)
  const sessionToken = await getSessionToken(clientUniqueId, env);

  // Write pending order
  await env.DB.prepare(
    `INSERT INTO nuvei_orders
       (order_id, session_token, client_unique_id, amount, currency, user_id, status)
     VALUES (?, ?, ?, ?, ?, ?, 'PENDING')`,
  )
    .bind(clientUniqueId, sessionToken, clientUniqueId, amount, body.currency, userId)
    .run();

  // Process payment (card token from Simply Connect comes via paymentOptionId)
  const result = await processNuveiPayment(
    {
      sessionToken,
      clientUniqueId,
      amount,
      currency: body.currency,
      paymentOption: body.paymentOptionId
        ? { userPaymentOptionId: body.paymentOptionId }
        : {},
      billingAddress: body.billingAddress,
      deviceDetails: { ipAddress: body.ipAddress },
    },
    env,
  );

  const status = result.transactionStatus === 'APPROVED' ? 'COMPLETED' : 'FAILED';
  await env.DB.prepare(
    'UPDATE nuvei_orders SET status = ?, nuvei_txn_id = ?, updated_at = unixepoch() WHERE client_unique_id = ?',
  )
    .bind(status, result.transactionId, clientUniqueId)
    .run();

  if (result.transactionStatus !== 'APPROVED') {
    return new Response(
      JSON.stringify({ error: result.reason, errCode: result.errCode }),
      { status: 402, headers: { 'Content-Type': 'application/json' } },
    );
  }

  return new Response(
    JSON.stringify({ transactionId: result.transactionId, authCode: result.authCode }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}
```

---

## DMN (Direct Merchant Notification) Webhook

```typescript
// src/handlers/nuvei-dmn.ts
import { Env } from '../types';
import { buildNuveiChecksum } from '../lib/nuvei-checksum';

/**
 * DMN checksum is SHA-256 of:
 *   merchantSecretKey + totalAmount + currency + responseTimeStamp +
 *   PPP_TransactionID + Status + productId
 */
export async function handleNuveiDMN(request: Request, env: Env): Promise<Response> {
  // DMN is sent as application/x-www-form-urlencoded
  const formData = await request.formData();
  const params = Object.fromEntries(formData.entries()) as Record<string, string>;

  const {
    totalAmount,
    currency,
    responseTimeStamp,
    PPP_TransactionID,
    Status,
    productId,
    advanceResponseChecksum,
    clientUniqueId,
    transactionType,
  } = params;

  // Verify checksum
  const expected = await buildNuveiChecksum([
    env.NUVEI_SECRET_KEY,
    totalAmount,
    currency,
    responseTimeStamp,
    PPP_TransactionID,
    Status,
    productId ?? '',
  ]);

  if (expected !== advanceResponseChecksum) {
    return new Response('Bad checksum', { status: 400 });
  }

  // Store DMN event for idempotent processing
  await env.DB.prepare(
    `INSERT OR IGNORE INTO nuvei_dmn_events
       (client_unique_id, txn_type, status, nuvei_txn_id, checksum)
     VALUES (?, ?, ?, ?, ?)`,
  )
    .bind(clientUniqueId, transactionType, Status, PPP_TransactionID, advanceResponseChecksum)
    .run();

  // Update order status from DMN (more reliable than direct API response)
  if (Status === 'APPROVED') {
    await env.DB.prepare(
      'UPDATE nuvei_orders SET status = ?, nuvei_txn_id = ?, updated_at = unixepoch() WHERE client_unique_id = ? AND status = ?',
    )
      .bind('COMPLETED', PPP_TransactionID, clientUniqueId, 'PENDING')
      .run();
  } else if (Status === 'DECLINED' || Status === 'ERROR') {
    await env.DB.prepare(
      'UPDATE nuvei_orders SET status = ?, updated_at = unixepoch() WHERE client_unique_id = ? AND status = ?',
    )
      .bind('FAILED', clientUniqueId, 'PENDING')
      .run();
  }

  return new Response('OK', { status: 200 });
}
```

---

## Saved Payment Methods (Nuvei User Payment Options)

```typescript
// src/lib/nuvei-saved-cards.ts
import { buildNuveiChecksum, nowTimestamp } from './nuvei-checksum';
import { Env } from '../types';

const NUVEI_BASE = 'https://ppp-test.nuvei.com/ppp/api/v1';

export async function getUserPaymentOptions(
  userTokenId: string,
  env: Env,
): Promise<Array<{ userPaymentOptionId: string; brand: string; lastFour: string; expiryDate: string }>> {
  const clientRequestId = crypto.randomUUID();
  const timeStamp = nowTimestamp();
  const checksum = await buildNuveiChecksum([
    env.NUVEI_MERCHANT_ID,
    env.NUVEI_MERCHANT_SITE_ID,
    userTokenId,
    clientRequestId,
    timeStamp,
    env.NUVEI_SECRET_KEY,
  ]);

  const resp = await fetch(`${NUVEI_BASE}/getUserUPOs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      merchantId: env.NUVEI_MERCHANT_ID,
      merchantSiteId: env.NUVEI_MERCHANT_SITE_ID,
      userTokenId,
      clientRequestId,
      timeStamp,
      checksum,
    }),
  });

  if (!resp.ok) throw new Error(`Nuvei UPOs error: ${resp.status}`);
  const data = await resp.json<{ UPOs: Array<{ userPaymentOptionId: string; card?: { cardBrand: string; lastFourDigits: string; expirationDate: string } }> }>();
  return (data.UPOs ?? []).map((u) => ({
    userPaymentOptionId: u.userPaymentOptionId,
    brand: u.card?.cardBrand ?? 'unknown',
    lastFour: u.card?.lastFourDigits ?? '',
    expiryDate: u.card?.expirationDate ?? '',
  }));
}
```

---

## Anti-patterns

- **Building checksum client-side**: The checksum uses your `merchantSecretKey`. Never expose this
  to the browser. Always compute checksums in the Worker.
- **Using amount as an integer (cents)**: Nuvei expects amount as a decimal string (e.g. `"9.99"`),
  not an integer in cents. Passing `999` will attempt to charge $999.
- **Ignoring DMN in favour of only the direct payment API response**: Nuvei's direct response can
  be lost on network timeout. The DMN (webhook) is the authoritative signal. Design your order
  state machine to accept both but prefer DMN.
- **Reusing sessionToken across multiple payment attempts**: Session tokens are single-use per
  transaction. Always call `getSessionToken` fresh for each payment attempt.
- **Skipping DMN checksum verification**: Nuvei DMNs do not carry HMAC headers; they use the
  body-field checksum. Skipping this check allows forged notifications to mark orders as paid.

---

## Gotchas

- **Nuvei test and production environments share the same API structure but different base URLs**:
  Test: `ppp-test.nuvei.com`; Production: `ppp.nuvei.com`. An accidental test-env call in
  production (or vice versa) returns 200 with no error — it just processes against the wrong env.
- **Currency decimal rules**: JPY amounts have no decimal places; EUR/USD have 2. Nuvei validates
  this strictly. Use a currency-aware formatter.
- **`clientUniqueId` must be globally unique**: Nuvei rejects duplicate `clientUniqueId` values
  with a checksum error that looks like a configuration mistake. Always use `crypto.randomUUID()`.
- **DMN delivery timing**: DMNs can arrive before, during, or after your direct API response.
  Handle the case where the DMN marks an order APPROVED before your Worker has created the order
  row in D1 (e.g., use `INSERT OR IGNORE` then update).
- **3DS2 challenge flow**: For EEA/UK transactions, Nuvei requires SCA. After the payment API
  call you may receive `transactionStatus: "REDIRECT"` with a `redirectUrl` for the ACS challenge
  page. Handle this redirect in your client SDK.

---

## Verification

```bash
# 1. Get a session token
curl -X POST https://ppp-test.nuvei.com/ppp/api/v1/getSessionToken \
  -H "Content-Type: application/json" \
  -d "{
    \"merchantId\": \"$NUVEI_MERCHANT_ID\",
    \"merchantSiteId\": \"$NUVEI_MERCHANT_SITE_ID\",
    \"clientRequestId\": \"test-001\",
    \"timeStamp\": \"$(date +%Y%m%d%H%M%S)\",
    \"checksum\": \"$COMPUTED_CHECKSUM\"
  }"

# 2. Process a test payment with test card 4111111111111111
# Use Nuvei sandbox API as above with paymentOption.card fields

# 3. Verify D1 order row
wrangler d1 execute example project-db \
  --command "SELECT * FROM nuvei_orders ORDER BY created_at DESC LIMIT 5"

# 4. Verify DMN event received
wrangler d1 execute example project-db \
  --command "SELECT * FROM nuvei_dmn_events ORDER BY received_at DESC LIMIT 5"
```

---

## Related

- `/payments/payment-orchestration-multi-psp-routing.md`
- `/payments/gateway-failover-circuit-breakers.md`
- `/payments/idempotency-keys-payment-apis.md`
- `/payments/sca-3d-secure-2-psd2-authentication.md`
- `/payments/payment-reconciliation-settlement.md`

---

## Sources

- Nuvei REST API Reference: https://docs.nuvei.com/api/main/indexMain_v1_0.html
- Nuvei Simply Connect Integration Guide: https://docs.nuvei.com/documentation/integration-guide/simply-connect/
- Nuvei DMN Reference: https://docs.nuvei.com/documentation/guides/dmn-direct-merchant-notification/
- Nuvei Test Cards: https://docs.nuvei.com/documentation/integration-guide/testing/test-cards/
- Cloudflare Workers: https://developers.cloudflare.com/workers/
