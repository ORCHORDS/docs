# Paytm Workers — UPI Payment Flow

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to initiate and verify UPI payments through Paytm's payment gateway from a Cloudflare Workers backend. UPI (Unified Payments Interface) is the dominant real-time payment method in India, processing over 13 billion transactions per month. Paytm's gateway exposes a REST API compatible with Workers' `fetch`, but the checksum generation algorithm (SHA256 with pipe-delimited params) trips up developers coming from other payment providers. You need to handle the async UPI collect flow, polling or webhook-based status checks, and payment link generation for offline or WhatsApp-driven payment collection.

## Context

Paytm's payment gateway (distinct from the Paytm consumer app) is operated under **Paytm Payments Bank** via the `securegw.paytm.in` endpoint. It supports UPI, cards, Netbanking, wallets, and EMI. Authentication uses a **checksum** — a SHA256 HMAC over a pipe-delimited parameter string — rather than a Bearer token or Basic Auth. This checksum must be recalculated for every API call and must match the merchant key stored server-side.

The UPI flow has two paths:
1. **Intent/QR** — user opens their UPI app and scans a QR code or taps an intent link (synchronous callback after the app completes).
2. **Collect** — Paytm sends a push notification to the user's registered UPI VPA (Virtual Payment Address) requesting payment (asynchronous; settlement confirmed via webhook).

Workers cannot use Paytm's Node SDK (native module dependency). All requests use raw `fetch` + the Web Crypto API for checksum generation.

## 1. Environment Setup

```typescript
export interface Env {
  PAYTM_MID: string;          // Merchant ID
  PAYTM_MERCHANT_KEY: string; // 16-char secret — Workers Secret
  PAYTM_WEBSITE: string;      // "WEBPROD" for production, "WEBSTAGING" for test
  PAYTM_CHANNEL_ID: string;   // "WEB" for web, "WAP" for mobile
  PAYMENTS_KV: KVNamespace;
}

const PAYTM_BASE = "https://securegw.paytm.in"; // prod
// test: https://securegw-stage.paytm.in
```

## 2. Checksum Generation

Paytm's checksum algorithm: SHA256 HMAC over a pipe-delimited string of parameter values (sorted by key alphabetically), appended with the merchant key before hashing. The exact algorithm is:

```
checksum = sha256( pipe_join_sorted_values + "|" + merchant_key )
```

```typescript
async function generateChecksum(
  params: Record<string, string>,
  merchantKey: string
): Promise<string> {
  // Sort keys alphabetically, join values with pipe
  const sortedValues = Object.keys(params)
    .sort()
    .map((k) => params[k])
    .join("|");

  const message = `${sortedValues}|${merchantKey}`;

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(merchantKey),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function verifyChecksum(
  params: Record<string, string>,
  checksum: string,
  merchantKey: string
): Promise<boolean> {
  const expected = await generateChecksum(params, merchantKey);
  return crypto.timingSafeEqual(
    new TextEncoder().encode(expected),
    new TextEncoder().encode(checksum)
  );
}
```

## 3. Initiate Transaction (Payment Link)

```typescript
interface PaytmTxnInitPayload {
  MID: string;
  WEBSITE: string;
  CHANNEL_ID: string;
  ORDER_ID: string;
  CUST_ID: string;
  MOBILE_NO?: string;
  EMAIL?: string;
  TXN_AMOUNT: string;         // always string, 2 decimal places e.g. "499.00"
  CURRENCY: "INR";
  CALLBACK_URL: string;
  CHECKSUMHASH?: string;      // added after generation
}

async function initPaytmTransaction(
  env: Env,
  opts: { orderId: string; customerId: string; amountINR: number; callbackUrl: string }
): Promise<{ txnToken: string; orderId: string }> {
  const params: Record<string, string> = {
    MID: env.PAYTM_MID,
    WEBSITE: env.PAYTM_WEBSITE,
    CHANNEL_ID: env.PAYTM_CHANNEL_ID,
    ORDER_ID: opts.orderId,
    CUST_ID: opts.customerId,
    TXN_AMOUNT: opts.amountINR.toFixed(2),
    CURRENCY: "INR",
    CALLBACK_URL: opts.callbackUrl,
  };

  const checksum = await generateChecksum(params, env.PAYTM_MERCHANT_KEY);

  const body = { body: params, head: { signature: checksum } };

  const res = await fetch(
    `${PAYTM_BASE}/theia/api/v1/initiateTransaction?mid=${env.PAYTM_MID}&orderId=${opts.orderId}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );

  const data = await res.json<{
    body: { txnToken: string; resultInfo: { resultStatus: string; resultMsg: string } };
  }>();

  if (data.body.resultInfo.resultStatus !== "S") {
    throw new Error(`Paytm init error: ${data.body.resultInfo.resultMsg}`);
  }

  return { txnToken: data.body.txnToken, orderId: opts.orderId };
}
```

## 4. UPI Collect — Initiate VPA Payment

For server-initiated UPI collect (push to user's VPA without a QR scan):

```typescript
async function initiateUPICollect(
  env: Env,
  opts: { orderId: string; vpa: string; amountINR: number; customerId: string }
): Promise<{ refId: string }> {
  const params: Record<string, string> = {
    MID: env.PAYTM_MID,
    ORDER_ID: opts.orderId,
    CUST_ID: opts.customerId,
    TXN_AMOUNT: opts.amountINR.toFixed(2),
    CURRENCY: "INR",
    PAYMENT_MODE_ONLY: "UPI",
    AUTH_MODE: "USRPWD",
    PAYMENT_TYPE_ID: "UPI",
    MOBILE_NO: "9999999999", // required placeholder if real mobile unavailable
    VPA: opts.vpa,
  };

  const checksum = await generateChecksum(params, env.PAYTM_MERCHANT_KEY);

  const res = await fetch(`${PAYTM_BASE}/order/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...params, CHECKSUMHASH: checksum }),
  });

  const data = await res.json<{
    STATUS: string;
    RESPMSG: string;
    TXNID?: string;
  }>();

  if (data.STATUS !== "PENDING") {
    throw new Error(`UPI collect failed: ${data.RESPMSG}`);
  }

  return { refId: data.TXNID ?? opts.orderId };
}
```

## 5. Transaction Status Check

UPI collect payments are asynchronous. Poll or handle webhooks to confirm final status.

```typescript
interface PaytmTxnStatus {
  STATUS: "TXN_SUCCESS" | "TXN_FAILURE" | "PENDING";
  TXNID: string;
  ORDERID: string;
  TXNAMOUNT: string;
  RESPMSG: string;
  RESPCODE: string;
  CHECKSUMHASH: string;
}

async function checkTxnStatus(
  env: Env,
  orderId: string
): Promise<PaytmTxnStatus> {
  const params: Record<string, string> = {
    MID: env.PAYTM_MID,
    ORDERID: orderId,
  };

  const checksum = await generateChecksum(params, env.PAYTM_MERCHANT_KEY);

  const res = await fetch(
    `${PAYTM_BASE}/order/status`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...params, CHECKSUMHASH: checksum }),
    }
  );

  return res.json<PaytmTxnStatus>();
}

// Polling helper — use Cloudflare Queues for production retries
async function pollUntilFinal(
  env: Env,
  orderId: string,
  maxAttempts = 10,
  intervalMs = 3000
): Promise<PaytmTxnStatus> {
  for (let i = 0; i < maxAttempts; i++) {
    const status = await checkTxnStatus(env, orderId);
    if (status.STATUS !== "PENDING") return status;
    if (i < maxAttempts - 1) {
      await new Promise((r) => setTimeout(r, intervalMs));
    }
  }
  throw new Error(`Payment still PENDING after ${maxAttempts} attempts`);
}
```

## 6. Webhook Verification

Paytm POSTs payment status to your callback URL. Verify the checksum in the posted body before updating order state.

```typescript
async function handlePaytmCallback(request: Request, env: Env): Promise<Response> {
  const formData = await request.formData();
  const params: Record<string, string> = {};
  let receivedChecksum = "";

  for (const [key, value] of formData.entries()) {
    if (key === "CHECKSUMHASH") {
      receivedChecksum = value.toString();
    } else {
      params[key] = value.toString();
    }
  }

  const valid = await verifyChecksum(params, receivedChecksum, env.PAYTM_MERCHANT_KEY);
  if (!valid) return new Response("Checksum mismatch", { status: 401 });

  const orderId = params["ORDERID"];
  const status = params["STATUS"] as PaytmTxnStatus["STATUS"];

  await env.PAYMENTS_KV.put(
    `paytm:${orderId}`,
    JSON.stringify({ status, txnId: params["TXNID"], amount: params["TXNAMOUNT"], raw: params }),
    { expirationTtl: 60 * 60 * 24 * 90 }
  );

  // Always return a 200 — Paytm will retry on non-2xx
  return new Response("OK");
}
```

## Anti-patterns

- **Generating the checksum in the browser** — the `PAYTM_MERCHANT_KEY` must never leave the server. Always generate checksums in Workers.
- **Trusting the callback body without checksum verification** — Paytm's callback is a form POST, not HMAC-signed like Stripe. Verifying the checksum is the only authenticity check.
- **Treating `PENDING` as final** — UPI collect payments can take 2–5 minutes. Use a Cloudflare Queue with delayed retries rather than a synchronous polling loop in the Worker.
- **Using string comparison on checksums** — use `crypto.timingSafeEqual` to prevent timing attacks.
- **Hardcoding `TXN_AMOUNT` as a number** — Paytm requires it as a string with exactly two decimal places (`"499.00"`, not `499`).

## Gotchas

- Test environment base is `https://securegw-stage.paytm.in`; production is `https://securegw.paytm.in`. Using the wrong base returns HTTP 404, not a JSON error.
- `ORDER_ID` must be unique per merchant account and cannot be reused, even after payment failure.
- VPA validation for UPI collect: invalid VPAs return `STATUS: TXN_FAILURE` with `RESPCODE: 334`. Always validate VPA format (`name@bank`) before initiating collect.
- Paytm's callback may arrive as a GET redirect (for Checkout-hosted) or a POST (for silent callback). Handle both: read params from `formData` on POST and `URL.searchParams` on GET.
- The API's checksum algorithm pads the SHA256 hex to 64 characters; no base64 encoding.

## Verification

```bash
# Test checksum generation against Paytm's provided test vector
# MID=Merchant ID, MERCHANT_KEY=16-char key from staging dashboard

# Test status check with a known staging order
curl -X POST https://securegw-stage.paytm.in/order/status \
  -H "Content-Type: application/json" \
  -d '{"MID":"YOUR_MID","ORDERID":"TEST001","CHECKSUMHASH":"<generated>"}'

# Expected: {"STATUS":"TXN_FAILURE","RESPMSG":"Order does not exist"}
# (for a non-existent order — confirms endpoint is reachable and checksum format accepted)
```

## Related

- `razorpay-workers-india-payment-integration.md` — Razorpay as alternative India gateway
- `payment-retry-exponential-backoff-cloudflare-queues.md` — polling UPI settle with queues
- `payment-state-machine-design.md` — PENDING → SUCCESS/FAILURE transition
- `idempotency-keys-payment-apis.md` — ORDER_ID uniqueness strategy

## Sources

- Paytm Payment Gateway Docs: https://developer.paytm.com/docs/
- Initiate Transaction API: https://developer.paytm.com/docs/transaction-token-api/
- Transaction Status API: https://developer.paytm.com/docs/transaction-status-api/
- UPI Collect Integration: https://developer.paytm.com/docs/upi-collect/
- Checksum generation: https://developer.paytm.com/docs/checksum/
