# Apple Pay Domain Verification and Merchant Session with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Apple Pay does not appear in Safari on your checkout page, or the payment sheet fails to open with a merchant validation error. You need to serve the domain association file, complete the merchant session handshake with Apple, and forward the validated token to Stripe — all via a Cloudflare Workers backend.

## Context

Apple Pay requires two server-side steps before a payment sheet can open:
1. **Domain verification** — Apple fetches `/.well-known/apple-developer-merchantid-domain-association` from every domain that will show an Apple Pay button. The file must be served verbatim, with no redirect, within 5 seconds.
2. **Merchant session** — Your JavaScript calls `ApplePaySession.begin()`, which fires `onvalidatemerchant`. You must POST to Apple's gateway with your merchant certificate and return an opaque merchant session object to the browser within 30 seconds.

Cloudflare Workers handles both: KV stores the association file and caches merchant sessions; Workers Secrets hold the merchant certificate and private key.

## Worker Implementation

```typescript
// src/apple-pay.ts
import { Hono } from 'hono';

export interface Env {
  KV: KVNamespace;
  // PEM-encoded merchant certificate (leaf + intermediate chain, newline-separated)
  APPLE_PAY_MERCHANT_CERT: string;
  // PEM-encoded private key for the merchant certificate
  APPLE_PAY_MERCHANT_KEY: string;
  // Apple Merchant Identifier, e.g. merchant.com.example.shop
  APPLE_MERCHANT_ID: string;
  // Your display name shown in the payment sheet
  APPLE_DISPLAY_NAME: string;
}

const app = new Hono<{ Bindings: Env }>();

// ── 1. Domain Verification ───────────────────────────────────────────────────
// Upload the file content to KV before deploying:
//   wrangler kv key put apple-domain-association "<file contents>" --binding KV
app.get('/.well-known/apple-developer-merchantid-domain-association', async (c) => {
  const content = await c.env.KV.get('apple-domain-association');
  if (!content) {
    return c.text('Domain association file not found', 404);
  }
  return c.text(content, 200, {
    'Content-Type': 'text/plain',
    'Cache-Control': 'public, max-age=86400',
  });
});

// ── 2. Merchant Session Endpoint ─────────────────────────────────────────────
app.post('/apple-pay/validate-merchant', async (c) => {
  const { validationURL } = await c.req.json<{ validationURL: string }>();

  if (!validationURL || !validationURL.startsWith('https://apple-pay-gateway')) {
    return c.json({ error: 'invalid_validation_url' }, 400);
  }

  // Cache key includes the URL so different environments get different sessions
  const cacheKey = `apple-pay-session:${Buffer.from(validationURL).toString('base64').slice(0, 64)}`;
  const cached = await c.env.KV.get(cacheKey);
  if (cached) {
    return c.json(JSON.parse(cached));
  }

  // Build the mTLS request body Apple expects
  const requestBody = JSON.stringify({
    merchantIdentifier: c.env.APPLE_MERCHANT_ID,
    displayName: c.env.APPLE_DISPLAY_NAME,
    initiative: 'web',
    initiativeContext: new URL(validationURL).hostname,
  });

  // Workers supports fetch with client certificates via the `tls` option
  // when using the Cloudflare mTLS certificate store. Here we use the
  // certificate stored as a Secret and construct the request manually.
  // In production, bind a mTLS certificate via wrangler.toml `mtls_certificates`
  // and pass `cf: { mtlsCertificate: env.MTLS_CERT }` to fetch.
  const response = await fetch(validationURL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: requestBody,
    // @ts-expect-error - Cloudflare Workers mTLS extension
    cf: {
      mtlsCertificate: {
        cert: c.env.APPLE_PAY_MERCHANT_CERT,
        key: c.env.APPLE_PAY_MERCHANT_KEY,
      },
    },
  });

  if (!response.ok) {
    const errText = await response.text();
    return c.json({ error: 'apple_gateway_error', detail: errText }, 502);
  }

  const session = await response.json();

  // Cache for 5 minutes (Apple merchant sessions expire after ~5 min)
  await c.env.KV.put(cacheKey, JSON.stringify(session), { expirationTtl: 300 });

  return c.json(session);
});

// ── 3. Token Validation and Stripe Handoff ───────────────────────────────────
app.post('/apple-pay/process-payment', async (c) => {
  const { token, amount, currency } = await c.req.json<{
    token: ApplePayJS.ApplePayPaymentToken;
    amount: number;
    currency: string;
  }>();

  // Basic structural validation before forwarding to Stripe
  if (
    !token?.paymentData ||
    !token.paymentMethod?.network ||
    !token.transactionIdentifier
  ) {
    return c.json({ error: 'invalid_apple_pay_token' }, 400);
  }

  // Forward to Stripe — Stripe accepts the raw Apple Pay token
  const stripeResponse = await fetch('https://api.stripe.com/v1/payment_intents', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${c.env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      amount: String(amount),
      currency,
      'payment_method_data[type]': 'card',
      'payment_method_data[card][token]': JSON.stringify(token.paymentData),
      confirm: 'true',
    }),
  });

  const pi = await stripeResponse.json();
  return c.json({ clientSecret: (pi as any).client_secret });
});

export default app;
```

## Front-end JavaScript Snippet

```javascript
const session = new ApplePaySession(3, {
  countryCode: 'GB',
  currencyCode: 'GBP',
  supportedNetworks: ['visa', 'masterCard', 'amex'],
  merchantCapabilities: ['supports3DS'],
  total: { label: 'Orchords', amount: '19.99' },
});

session.onvalidatemerchant = async (event) => {
  const res = await fetch('/apple-pay/validate-merchant', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ validationURL: event.validationURL }),
  });
  const merchantSession = await res.json();
  session.completeMerchantValidation(merchantSession);
};

session.onpaymentauthorized = async (event) => {
  const res = await fetch('/apple-pay/process-payment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: event.payment.token, amount: 1999, currency: 'gbp' }),
  });
  const result = await res.json();
  session.completePayment(
    result.clientSecret
      ? ApplePaySession.STATUS_SUCCESS
      : ApplePaySession.STATUS_FAILURE
  );
};

session.begin();
```

## Anti-patterns

- **Redirecting the domain association URL**: Apple's verification crawler does not follow redirects. The file must be served at the exact path with a 200 response.
- **Hardcoding the merchant certificate in source code**: Store it as a Workers Secret (`wrangler secret put APPLE_PAY_MERCHANT_CERT`) to prevent accidental exposure in version control.
- **Caching merchant sessions beyond 5 minutes**: Apple's opaque session object contains a short-lived token. Using a stale session causes `STATUS_FAILURE` and a confusing user error.

## Gotchas

- Cloudflare Workers' mTLS support requires the certificate to be uploaded to the Cloudflare mTLS Certificate Store via the API or dashboard before it can be referenced in `wrangler.toml`. The Secret approach shown above works for small merchants but check Cloudflare's current mTLS binding docs for the recommended production path.
- `ApplePaySession` is only constructable inside a user gesture handler (`click`). Calling it outside (e.g. on page load) throws a `InvalidAccessError`.
- Apple will re-verify your domain monthly. If the KV entry for the association file is missing or returns non-200, Apple Pay silently hides the button for all users on that domain.

## Verification

```bash
# 1. Confirm domain association file is reachable
curl -I https://yourdomain.com/.well-known/apple-developer-merchantid-domain-association
# Expect: HTTP/2 200, Content-Type: text/plain

# 2. Validate merchant session endpoint manually
curl -X POST https://yourdomain.com/apple-pay/validate-merchant \
  -H 'Content-Type: application/json' \
  -d '{"validationURL":"https://apple-pay-gateway.apple.com/paymentservices/startSession"}'
# Expect: JSON with epochTimestamp, expiresAt, merchantSessionIdentifier fields

# 3. Use Safari Web Inspector → Apple Pay panel to step through a real session
```

## Related

- `stripe-radar-custom-rules-workers-integration.md`
- `adyen-payments-workers-integration.md`
- Apple Pay on the Web documentation: https://developer.apple.com/documentation/apple_pay_on_the_web

## Sources

- Apple Pay merchant session reference: https://developer.apple.com/documentation/apple_pay_on_the_web/applepaysession/1778021-onvalidatemerchant
- Cloudflare Workers mTLS: https://developers.cloudflare.com/workers/runtime-apis/fetch/#mtls
- Cloudflare KV: https://developers.cloudflare.com/kv/
