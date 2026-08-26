# Apple Pay Payment Session Validation in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your frontend Apple Pay sheet fires `validatemerchant` and needs a server endpoint to POST to Apple's gateway and return a session object. Doing this from a browser is blocked by CORS and certificate requirements, so a Worker must act as the mTLS-capable proxy. You need the merchant session returned to the client within the 30-second Apple Pay timeout.

---

## Context

Apple Pay requires the merchant server to call `https://apple-pay-gateway.apple.com/paymentservices/startSession` using a merchant identity certificate issued by Apple (mTLS). Cloudflare Workers support mTLS client certificates through `wrangler.toml` `[mtls_certificates]` bindings, which make the certificate available in the `fetch()` call via `Request` options. The session object returned by Apple is short-lived (5 minutes) and should be cached in KV to avoid redundant Apple gateway calls when multiple tabs trigger validation simultaneously. The Worker validates the incoming `validationURL` hostname against an allowlist of known Apple Pay gateway domains before proxying the request.

---

## Section 1 — wrangler.toml mTLS & KV Config

```toml
name = "apple-pay-session"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "SESSION_CACHE"
id = "<your-kv-namespace-id>"

[[mtls_certificates]]
binding = "APPLE_PAY_CERT"
certificate_id = "<your-certificate-id>"
```

Upload your merchant identity certificate with:

```bash
wrangler mtls-certificate upload \
  --cert merchant_identity.crt \
  --key merchant_identity.key \
  --name apple-pay-merchant
```

---

## Section 2 — Worker Implementation

```typescript
export interface Env {
  SESSION_CACHE: KVNamespace;
  APPLE_PAY_CERT: Fetcher; // mTLS binding
  MERCHANT_IDENTIFIER: string; // Workers secret
  MERCHANT_DISPLAY_NAME: string;
  MERCHANT_DOMAIN: string;
}

const ALLOWED_APPLE_GATEWAYS = new Set([
  "apple-pay-gateway.apple.com",
  "cn-apple-pay-gateway.apple.com",
  "apple-pay-gateway-nc-pod1.apple.com",
  "apple-pay-gateway-nc-pod2.apple.com",
  "apple-pay-gateway-nc-pod3.apple.com",
  "apple-pay-gateway-nc-pod4.apple.com",
  "apple-pay-gateway-nc-pod5.apple.com",
]);

async function validateMerchant(
  validationURL: string,
  env: Env
): Promise<unknown> {
  const url = new URL(validationURL);
  if (!ALLOWED_APPLE_GATEWAYS.has(url.hostname)) {
    throw new Error(`Untrusted Apple Pay gateway hostname: ${url.hostname}`);
  }

  // Check KV cache first (TTL: 5 minutes = 300 seconds)
  const cacheKey = `applepay:session:${btoa(validationURL)}`;
  const cached = await env.SESSION_CACHE.get(cacheKey, { type: "json" });
  if (cached) return cached;

  const body = JSON.stringify({
    merchantIdentifier: env.MERCHANT_IDENTIFIER,
    displayName: env.MERCHANT_DISPLAY_NAME,
    initiative: "web",
    initiativeContext: env.MERCHANT_DOMAIN,
  });

  // APPLE_PAY_CERT binding injects mTLS cert automatically
  const appleResponse = await env.APPLE_PAY_CERT.fetch(validationURL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });

  if (!appleResponse.ok) {
    const text = await appleResponse.text();
    throw new Error(
      `Apple Pay gateway error ${appleResponse.status}: ${text}`
    );
  }

  const session = await appleResponse.json();

  // Cache with 5-minute TTL
  await env.SESSION_CACHE.put(cacheKey, JSON.stringify(session), {
    expirationTtl: 300,
  });

  return session;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/apple-pay/session") {
      return new Response("Not Found", { status: 404 });
    }

    const origin = request.headers.get("Origin") ?? "";
    const allowedOrigins = [`https://${env.MERCHANT_DOMAIN}`];
    if (!allowedOrigins.includes(origin)) {
      return new Response("Forbidden", { status: 403 });
    }

    let validationURL: string;
    try {
      const body = await request.json<{ validationURL: string }>();
      validationURL = body.validationURL;
      if (!validationURL) throw new Error("Missing validationURL");
    } catch {
      return new Response(JSON.stringify({ error: "Invalid request body" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    try {
      const session = await validateMerchant(validationURL, env);
      return new Response(JSON.stringify(session), {
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": origin,
        },
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      return new Response(JSON.stringify({ error: message }), {
        status: 502,
        headers: { "Content-Type": "application/json" },
      });
    }
  },
};
```

---

## Section 3 — Frontend Handler

```typescript
// In your Apple Pay JS session handler
const session = new ApplePaySession(3, paymentRequest);

session.onvalidatemerchant = async (event: ApplePayValidateMerchantEvent) => {
  try {
    const response = await fetch("/apple-pay/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ validationURL: event.validationURL }),
    });
    if (!response.ok) throw new Error("Session validation failed");
    const merchantSession = await response.json();
    session.completeMerchantValidation(merchantSession);
  } catch (err) {
    console.error("Apple Pay merchant validation failed:", err);
    session.abort();
  }
};

session.onpaymentauthorized = async (event: ApplePayPaymentAuthorizedEvent) => {
  // Send event.payment.token to your payment processor
  const result = { status: ApplePaySession.STATUS_SUCCESS };
  session.completePayment(result);
};

session.begin();
```

---

## Anti-patterns

- **Forwarding raw validationURL without allowlist** — Apple's domain validation is not a security guarantee by itself; an attacker could supply an internal URL. Always check against the official Apple Pay gateway hostname list.
- **Not caching the merchant session** — Calling Apple's gateway on every `validatemerchant` event (e.g., multiple open tabs) risks rate limiting; the 5-minute KV TTL prevents this.
- **Storing the merchant certificate in Workers Secrets as PEM text** — mTLS bindings via `wrangler.toml` are the correct mechanism; manually loading a PEM from a Secret and constructing TLS config is not supported in Workers.
- **Skipping Origin header validation** — Without checking `Origin`, any site could use your Worker as a proxy to obtain Apple Pay merchant sessions.

---

## Gotchas

- The mTLS certificate binding (`APPLE_PAY_CERT`) acts as a `Fetcher`, not a `CryptoKey`. You call `.fetch()` on it, and Cloudflare injects the certificate into the outbound TLS handshake automatically.
- Apple Pay gateway domains vary by region and PoP. Keep your allowlist up to date using Apple's published documentation; the `cn-apple-pay-gateway` prefix is for China.
- The merchant identity certificate must be renewed annually through Apple Developer. A lapsed certificate causes silent 401 errors from Apple's gateway.
- `expirationTtl` in Workers KV is a minimum, not a guaranteed maximum. Build tolerance for stale cache misses in staging.
- The Apple Pay JS `onvalidatemerchant` callback must call `completeMerchantValidation` or `abort` within 30 seconds; ensure your Worker's p99 latency stays well under this budget.

---

## Verification

```bash
# Deploy the Worker
wrangler deploy

# Verify mTLS certificate is uploaded
wrangler mtls-certificate list

# Smoke-test session endpoint (replace with a real Apple validationURL during a test payment)
curl -X POST https://<your-worker>.workers.dev/apple-pay/session \
  -H "Content-Type: application/json" \
  -H "Origin: https://yourdomain.com" \
  -d '{"validationURL": "https://apple-pay-gateway.apple.com/paymentservices/startSession"}'

# Check KV cache entry was written
wrangler kv key list --namespace-id <your-kv-namespace-id>
```

---

## Related

- `workers-google-pay-token-decryption.md`
- `stripe-checkout-session-workers-d1.md`
- `workers-paypal-webhook-verification.md`

---

## Sources

- Apple Pay on the Web — https://developer.apple.com/documentation/apple_pay_on_the_web
- Cloudflare Workers mTLS — https://developers.cloudflare.com/workers/runtime-apis/bindings/mtls/
- Cloudflare KV — https://developers.cloudflare.com/kv/
