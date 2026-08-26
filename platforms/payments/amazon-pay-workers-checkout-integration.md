# Amazon Pay Checkout on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You want to offer Amazon Pay as a checkout option — customers authenticate with their Amazon
account and use a saved payment method. Workers create and manage the Amazon Pay Checkout Session
server-side; KV caches the buyer token; D1 records charge results. Conversion lifts are typically
highest for Prime members who already have cards on file with Amazon.

## Context

Amazon Pay uses OAuth 2.0 for buyer sign-in and a REST Checkout Sessions API (v2) for payment.
The flow: render the Amazon Pay button → buyer logs in via Amazon-hosted overlay → your Worker
creates a `CheckoutSession` → redirect to Amazon's payment page → Amazon redirects back with
`amazonCheckoutSessionId` → Worker completes the session to charge. All calls require a
signature computed with AWS Signature Version 4 (SigV4) using your Amazon Pay private key.

## SigV4 Request Signing for Amazon Pay

```typescript
// src/lib/amazon-pay-signer.ts
// Amazon Pay REST API uses AWS4 SigV4 — no SDK needed in Workers

export async function signAmazonPayRequest(
  method: string,
  url: string,
  payload: string,
  region: string,
  accessKeyId: string,
  privateKey: CryptoKey
): Promise<Record<string, string>> {
  const now = new Date();
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, '').slice(0, 15) + 'Z';
  const dateStamp = amzDate.slice(0, 8);

  const parsedUrl = new URL(url);
  const host = parsedUrl.host;
  const canonicalUri = parsedUrl.pathname;
  const canonicalQueryString = [...parsedUrl.searchParams.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');

  const payloadHash = Array.from(
    new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(payload)))
  ).map(b => b.toString(16).padStart(2, '0')).join('');

  const signedHeaders = 'content-type;host;x-amz-date;x-amz-pay-region';
  const canonicalHeaders =
    `content-type:application/json\nhost:${host}\nx-amz-date:${amzDate}\nx-amz-pay-region:${region}\n`;

  const canonicalRequest = [
    method, canonicalUri, canonicalQueryString,
    canonicalHeaders, signedHeaders, payloadHash,
  ].join('\n');

  const credentialScope = `${dateStamp}/${region}/amazon-pay/aws4_request`;
  const requestHash = Array.from(
    new Uint8Array(await crypto.subtle.digest(
      'SHA-256', new TextEncoder().encode(canonicalRequest)
    ))
  ).map(b => b.toString(16).padStart(2, '0')).join('');

  const stringToSign = `AWS4-RSA-SHA256\n${amzDate}\n${credentialScope}\n${requestHash}`;

  const sig = await crypto.subtle.sign(
    { name: 'RSASSA-PKCS1-v1_5' },
    privateKey,
    new TextEncoder().encode(stringToSign)
  );
  const signature = Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, '0')).join('');

  return {
    'Authorization': `AWS4-RSA-SHA256 Credential=${accessKeyId}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`,
    'Content-Type': 'application/json',
    'x-amz-date': amzDate,
    'x-amz-pay-region': region,
  };
}
```

## Create a Checkout Session

```typescript
// src/handlers/amazon-pay-create-session.ts
interface Env {
  AMAZON_PAY_PUBLIC_KEY_ID: string;
  AMAZON_PAY_PRIVATE_KEY: string;   // PEM, stored as Worker secret
  AMAZON_PAY_MERCHANT_ID: string;
  AMAZON_PAY_REGION: string;        // 'us', 'eu', 'jp', 'fe'
  DB: D1Database;
}

async function importPrivateKey(pem: string): Promise<CryptoKey> {
  const pemBody = pem.replace(/-----.*?-----/g, '').replace(/\s/g, '');
  const der = Uint8Array.from(atob(pemBody), c => c.charCodeAt(0));
  return crypto.subtle.importKey(
    'pkcs8', der.buffer,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false, ['sign']
  );
}

export async function createAmazonPaySession(
  env: Env,
  orderId: string,
  amountCents: number,
  currencyCode: string
): Promise<{ checkoutSessionId: string; redirectUrl: string }> {
  const endpoint = `https://pay-api.amazon.${env.AMAZON_PAY_REGION === 'us' ? 'com' : env.AMAZON_PAY_REGION}/v2/checkoutSessions`;

  const payload = JSON.stringify({
    webCheckoutDetails: {
      checkoutReviewReturnUrl: `https://yourdomain.com/checkout/review?order=${orderId}`,
      checkoutResultReturnUrl: `https://yourdomain.com/checkout/result?order=${orderId}`,
    },
    storeId: env.AMAZON_PAY_MERCHANT_ID,
    chargePermissionType: 'OneTime',
    paymentDetails: {
      paymentIntent: 'AuthorizeWithCapture',
      canHandlePendingAuthorization: false,
      chargeAmount: {
        amount: (amountCents / 100).toFixed(2),
        currencyCode,
      },
    },
  });

  const privateKey = await importPrivateKey(env.AMAZON_PAY_PRIVATE_KEY);
  const headers = await signAmazonPayRequest(
    'POST', endpoint, payload, env.AMAZON_PAY_REGION,
    env.AMAZON_PAY_PUBLIC_KEY_ID, privateKey
  );

  const res = await fetch(endpoint, { method: 'POST', headers, body: payload });
  if (!res.ok) throw new Error(`Amazon Pay session error: ${await res.text()}`);

  const session = await res.json<{
    checkoutSessionId: string;
    webCheckoutDetails: { amazonPayRedirectUrl: string };
  }>();

  await env.DB.prepare(
    `INSERT INTO amazon_pay_sessions (order_id, session_id, status, created_at)
     VALUES (?, ?, 'OPEN', ?)`
  ).bind(orderId, session.checkoutSessionId, Date.now()).run();

  return {
    checkoutSessionId: session.checkoutSessionId,
    redirectUrl: session.webCheckoutDetails.amazonPayRedirectUrl,
  };
}
```

## Complete the Checkout Session (Charge)

```typescript
// Called after Amazon redirects buyer back to checkoutResultReturnUrl
export async function completeAmazonPaySession(
  env: Env,
  checkoutSessionId: string,
  amountCents: number,
  currencyCode: string
): Promise<{ chargeId: string; status: string }> {
  const endpoint = `https://pay-api.amazon.${env.AMAZON_PAY_REGION === 'us' ? 'com' : env.AMAZON_PAY_REGION}/v2/checkoutSessions/${checkoutSessionId}/complete`;

  const payload = JSON.stringify({
    chargeAmount: {
      amount: (amountCents / 100).toFixed(2),
      currencyCode,
    },
  });

  const privateKey = await importPrivateKey(env.AMAZON_PAY_PRIVATE_KEY);
  const headers = await signAmazonPayRequest(
    'POST', endpoint, payload, env.AMAZON_PAY_REGION,
    env.AMAZON_PAY_PUBLIC_KEY_ID, privateKey
  );

  const res = await fetch(endpoint, { method: 'POST', headers, body: payload });
  if (!res.ok) throw new Error(`Amazon Pay complete failed: ${await res.text()}`);

  const result = await res.json<{
    chargePermissionId: string;
    chargeId: string;
    statusDetails: { state: string; reasonCode?: string };
  }>();

  await env.DB.prepare(
    `UPDATE amazon_pay_sessions
     SET status = ?, charge_id = ?, charge_permission_id = ?, completed_at = ?
     WHERE session_id = ?`
  ).bind(
    result.statusDetails.state,
    result.chargeId,
    result.chargePermissionId,
    Date.now(),
    checkoutSessionId
  ).run();

  return { chargeId: result.chargeId, status: result.statusDetails.state };
}
```

## IPN (Instant Payment Notification) Handler

```typescript
// Amazon Pay sends IPNs via SNS — verify the SNS signature before processing
export async function handleAmazonPayIPN(request: Request, env: Env): Promise<Response> {
  const body = await request.text();
  const msg = JSON.parse(body) as {
    Type: string;
    Message: string;
    SignatureVersion: string;
    Signature: string;
    SigningCertURL: string;
  };

  // SNS signature verification (fetch cert from AWS, verify RSA-SHA1)
  // In production: use a dedicated SNS verification library or validate the cert domain
  if (!msg.SigningCertURL.startsWith('https://sns.') || !msg.SigningCertURL.endsWith('.amazonaws.com/')) {
    return new Response('Invalid cert URL', { status: 400 });
  }

  const notification = JSON.parse(msg.Message) as {
    NotificationType: string;
    ChargePermissionId?: string;
    ChargeId?: string;
    StatusDetails?: { State: string };
  };

  if (notification.NotificationType === 'ChargeStatusUpdated' && notification.ChargeId) {
    await env.DB.prepare(
      `UPDATE amazon_pay_sessions SET status = ? WHERE charge_id = ?`
    ).bind(notification.StatusDetails?.State ?? 'UNKNOWN', notification.ChargeId).run();
  }

  return new Response('OK');
}
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS amazon_pay_sessions (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id             TEXT NOT NULL UNIQUE,
  session_id           TEXT NOT NULL,
  status               TEXT NOT NULL DEFAULT 'OPEN',
  charge_id            TEXT,
  charge_permission_id TEXT,
  created_at           INTEGER NOT NULL,
  completed_at         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_amzpay_session ON amazon_pay_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_amzpay_charge  ON amazon_pay_sessions(charge_id);
```

## Anti-patterns

- **Fulfilling on the redirect return alone** — the `checkoutResultReturnUrl` redirect fires
  optimistically. Always verify session state via `GET /v2/checkoutSessions/{id}` or wait for
  the IPN `ChargeStatusUpdated` event before shipping.
- **Hardcoding the API domain as `pay-api.amazon.com`** — the EU endpoint is
  `pay-api.amazon.eu`, Japan is `pay-api.amazon.jp`. Derive from `AMAZON_PAY_REGION`.
- **Caching the SigV4 signed headers** — signatures are time-bound to the `x-amz-date` value.
  Sign each request independently.

## Gotchas

- Amazon Pay private keys are RSA-2048 in PKCS#8 PEM. The Web Crypto API accepts PKCS#8 DER.
  Strip PEM headers and base64-decode before `importKey`.
- `chargePermissionType: 'OneTime'` cannot be used for subscriptions. Use `'Recurring'` with
  recurring metadata for subscription billing.
- Amazon Pay is unavailable in a browser's private/incognito mode if the buyer is not logged in —
  handle this gracefully in your button rendering logic.
- Sandbox credentials are separate from production. The sandbox endpoint uses the same base domain
  but requires sandbox-specific Public Key IDs (prefix `SANDBOX`).

## Verification

```bash
# Get sandbox checkout session details
curl -s "https://pay-api.amazon.com/v2/checkoutSessions/YOUR_SESSION_ID" \
  -H "Authorization: AWS4-RSA-SHA256 ..." \
  -H "x-amz-date: ..." \
  -H "x-amz-pay-region: us"

# Check D1 sessions
wrangler d1 execute YOUR_DB --command "SELECT * FROM amazon_pay_sessions ORDER BY created_at DESC LIMIT 5;"
```

## Related

- `apple-pay-google-pay-workers-merchant-validation.md`
- `payment-state-machine-design.md`
- `payment-audit-logging.md`
- `idempotency-keys-payment-apis.md`

## Sources

- https://developer.amazon.com/docs/amazon-pay-api-v2/intro.html
- https://developer.amazon.com/docs/amazon-pay-api-v2/signing-requests.html
- https://developer.amazon.com/docs/amazon-pay-api-v2/checkout-session.html
- https://developer.amazon.com/docs/amazon-pay-api-v2/ipn.html
