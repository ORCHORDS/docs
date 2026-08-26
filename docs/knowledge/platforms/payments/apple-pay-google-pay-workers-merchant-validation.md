# Apple Pay and Google Pay Merchant Validation via Cloudflare Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Serving Wallet Merchant Validation Endpoints at the Edge

Both Apple Pay and Google Pay require server-side steps before the browser
Payment Request API resolves: Apple demands a merchant validation call from
your server to its validation endpoint, and Google Pay's server API optionally
verifies payment tokens. Running both from a Cloudflare Worker eliminates cold
starts, serves the domain association file from R2, and records every
transaction attempt in D1.

## Context

Apple Pay flow: browser fires `merchantvalidation` event → your Worker calls
Apple's validation URL with your merchant certificate → returns the merchant
session object to the browser. Google Pay flow: browser collects the encrypted
payment token → your Worker forwards it to the Google Pay Server API for
verification. Both write a pending transaction row to D1 before responding to
the browser.

## Apple Pay Domain Association File from R2

Apple requires `/.well-known/apple-developer-merchantid-domain-association` to
be served as `text/plain` with no redirect.

```typescript
// src/handlers/applePayAssociation.ts
interface Env {
  ASSETS_BUCKET: R2Bucket;
}

export async function handleApplePayAssociation(
  _request: Request,
  env: Env,
): Promise<Response> {
  const object = await env.ASSETS_BUCKET.get('apple-developer-merchantid-domain-association');
  if (!object) {
    return new Response('Not Found', { status: 404 });
  }
  const text = await object.text();
  return new Response(text, {
    headers: {
      'Content-Type': 'text/plain',
      'Cache-Control': 'public, max-age=86400',
    },
  });
}
```

Upload the file to R2 once:

```bash
wrangler r2 object put payments-assets/apple-developer-merchantid-domain-association \
  --file ./apple-developer-merchantid-domain-association
```

## Apple Pay Merchant Validation Endpoint

```typescript
// src/handlers/applePayValidation.ts
interface Env {
  APPLE_MERCHANT_ID: string;
  APPLE_MERCHANT_CERT: string;          // PEM cert, stored as secret
  APPLE_MERCHANT_KEY: string;           // PEM private key, stored as secret
  SITE_DOMAIN: string;
  DB: D1Database;
}

export async function handleApplePayValidation(
  request: Request,
  env: Env,
): Promise<Response> {
  const { validationURL, transactionId, amount, currency, userId } =
    await request.json<{
      validationURL: string;
      transactionId: string;
      amount: number;
      currency: string;
      userId: string;
    }>();

  // Record pending transaction before calling Apple
  await env.DB.prepare(
    `INSERT OR IGNORE INTO wallet_transactions
       (id, user_id, amount, currency, wallet_type, status, created_at)
     VALUES (?, ?, ?, ?, 'apple_pay', 'pending', ?)`,
  )
    .bind(transactionId, userId, amount, currency, Date.now())
    .run();

  // Fetch mTLS identity — Workers mTLS via service bindings or custom fetch
  const merchantSessionRes = await fetch(validationURL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      merchantIdentifier: env.APPLE_MERCHANT_ID,
      domainName: env.SITE_DOMAIN,
      displayName: 'Orchords',
    }),
    // In production: attach client certificate via Workers mTLS binding
    // cf: { mtlsBinding: env.APPLE_MTLS }
  });

  if (!merchantSessionRes.ok) {
    await env.DB.prepare(
      `UPDATE wallet_transactions SET status = 'validation_failed' WHERE id = ?`,
    )
      .bind(transactionId)
      .run();
    return new Response('Apple validation failed', { status: 502 });
  }

  const merchantSession = await merchantSessionRes.json();
  return Response.json(merchantSession);
}
```

## Google Pay Server API Verification

Google Pay tokens are end-to-end encrypted. For gateway tokenisation (Stripe,
Adyen) the PSP decrypts server-side; for direct integration you verify the
token yourself.

```typescript
// src/handlers/googlePayVerify.ts
interface Env {
  GOOGLE_PAY_MERCHANT_ID: string;
  GOOGLE_PAY_ENV: 'TEST' | 'PRODUCTION';
  DB: D1Database;
}

export async function handleGooglePayVerify(
  request: Request,
  env: Env,
): Promise<Response> {
  const { paymentToken, transactionId, amount, currency, userId } =
    await request.json<{
      paymentToken: string;
      transactionId: string;
      amount: number;
      currency: string;
      userId: string;
    }>();

  await env.DB.prepare(
    `INSERT OR IGNORE INTO wallet_transactions
       (id, user_id, amount, currency, wallet_type, status, created_at)
     VALUES (?, ?, ?, ?, 'google_pay', 'pending', ?)`,
  )
    .bind(transactionId, userId, amount, currency, Date.now())
    .run();

  // For gateway integrations: forward the paymentMethodData.tokenizationData.token
  // directly to the PSP (Stripe / Adyen) — no server-side decryption needed.
  // For direct integration: call Google Pay Server API below.
  const verifyRes = await fetch(
    `https://pay.google.com/gp/p/apis/pay/v1/merchants/${env.GOOGLE_PAY_MERCHANT_ID}/tokens/verify`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paymentToken,
        environment: env.GOOGLE_PAY_ENV,
      }),
    },
  );

  if (!verifyRes.ok) {
    await env.DB.prepare(
      `UPDATE wallet_transactions SET status = 'verification_failed' WHERE id = ?`,
    )
      .bind(transactionId)
      .run();
    return new Response('Google Pay verification failed', { status: 502 });
  }

  const verified = await verifyRes.json();
  await env.DB.prepare(
    `UPDATE wallet_transactions SET status = 'verified', psp_ref = ? WHERE id = ?`,
  )
    .bind(verified.decryptedToken?.gatewayToken ?? null, transactionId)
    .run();

  return Response.json({ ok: true });
}
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS wallet_transactions (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  amount      INTEGER NOT NULL,
  currency    TEXT NOT NULL,
  wallet_type TEXT NOT NULL CHECK (wallet_type IN ('apple_pay','google_pay')),
  status      TEXT NOT NULL DEFAULT 'pending',
  psp_ref     TEXT,
  created_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wallet_tx_user ON wallet_transactions (user_id, created_at);
```

## Anti-patterns

- Do NOT serve the domain association file from a Worker KV key with a
  `Content-Type: application/json` default. Apple rejects non-plain-text.
- Do NOT validate the Apple `validationURL` against an allowlist. Stripe's
  guidance is to restrict calls to `*.apple.com` domains only.
- Do NOT store Apple merchant certificates in Worker environment variables as
  plain text; use Workers Secrets and rotate annually.
- Do NOT skip the D1 pre-write. Without it, failed validation events leave no
  audit trail for support.

## Gotchas

- Apple merchant validation must originate from the **same registered domain**;
  a Workers custom domain must match the domain registered in Apple Pay
  merchant portal.
- Google Pay's `PRODUCTION` environment requires your merchant account to be
  approved before live tokens are issued; `TEST` tokens cannot be charged.
- Workers mTLS bindings for Apple's validation endpoint require an mTLS
  certificate uploaded to Cloudflare and bound in `wrangler.toml`.
- Both wallets only work over HTTPS; local dev requires `ngrok` or `cloudflared
  tunnel` for end-to-end testing.

## Verification

```bash
# Check domain association file is reachable
curl -I https://yourdomain.com/.well-known/apple-developer-merchantid-domain-association

# Test Apple Pay validation endpoint
curl -X POST https://yourdomain.com/api/apple-pay/validate \
  -H 'Content-Type: application/json' \
  -d '{"validationURL":"https://apple-pay-gateway.apple.com/paymentservices/startSession","transactionId":"tx_test","amount":1000,"currency":"usd","userId":"u1"}'
```

## Related

- `stripe-apple-pay-setup.md`
- `stripe-google-pay-setup.md`
- `stripe-payment-method-domain-registration-governance.md`
- `pci-dss-scope-reduction-tokenization.md`

## Sources

- https://developer.apple.com/documentation/apple_pay_on_the_web/apple_pay_js_api/providing_merchant_validation
- https://developers.google.com/pay/api/web/guides/resources/payment-data-cryptography
- https://developers.cloudflare.com/r2/
- https://developers.cloudflare.com/workers/runtime-apis/mtls/
