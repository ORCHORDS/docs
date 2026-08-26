# Rapyd eFX Currency Conversion on Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to collect payments in local currencies and settle in a different currency (e.g.
collect BRL from Brazil, settle in USD) using Rapyd's eFX (embedded foreign exchange) API,
from a Cloudflare Workers backend — without exposing Rapyd credentials to the browser and
without running a persistent server for rate fetching, signature generation, or webhook
processing.

## Context

Rapyd is a fintech-as-a-service platform with global payment method coverage. Its eFX
feature allows platform businesses to:

1. Lock a conversion rate at the time of payment intent creation.
2. Collect the payment in the payer's local currency.
3. Receive settled funds in the merchant's wallet currency.

All Rapyd REST API calls require an HMAC-SHA256 signature built from:
`salt + timestamp + accessKey + secretKey + httpBody` (concatenated, not separated).

Workers handle this signature construction server-side, keep credentials in `env` secrets,
and cache exchange rates in KV to avoid hammering the Rapyd rate endpoint.

---

## 1. Building the Rapyd HMAC Signature

```typescript
// src/rapyd/signature.ts
export async function buildRapydSignature(params: {
  method: string;
  path: string;
  body: string;
  accessKey: string;
  secretKey: string;
}): Promise<{ signature: string; salt: string; timestamp: string }> {
  const { method: _method, path: _path, body, accessKey, secretKey } = params;

  const salt = crypto.randomUUID().replace(/-/g, '').slice(0, 8);
  const timestamp = Math.floor(Date.now() / 1000).toString();

  const toSign = salt + timestamp + accessKey + secretKey + body;

  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secretKey),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(toSign));
  const signature = btoa(
    Array.from(new Uint8Array(mac))
      .map(b => String.fromCharCode(b))
      .join('')
  );

  return { signature, salt, timestamp };
}

export function rapydHeaders(
  accessKey: string,
  salt: string,
  timestamp: string,
  signature: string
): HeadersInit {
  return {
    'Content-Type': 'application/json',
    access_key: accessKey,
    salt,
    timestamp,
    signature,
  };
}
```

---

## 2. Fetching and Caching Exchange Rates in KV

```typescript
// src/rapyd/exchange-rates.ts
interface RapydFxRate {
  buy_rate: number;
  sell_rate: number;
  from_currency: string;
  to_currency: string;
}

const RATE_TTL_SECONDS = 300; // 5-minute cache

export async function getExchangeRate(
  fromCurrency: string,
  toCurrency: string,
  env: Env
): Promise<RapydFxRate> {
  const cacheKey = `rapyd_rate:${fromCurrency}:${toCurrency}`;
  const cached = await env.KV.get<RapydFxRate>(cacheKey, 'json');
  if (cached) return cached;

  const path = `/v1/account/rates?buy_currency=${fromCurrency}&sell_currency=${toCurrency}`;
  const { signature, salt, timestamp } = await buildRapydSignature({
    method: 'GET',
    path,
    body: '',
    accessKey: env.RAPYD_ACCESS_KEY,
    secretKey: env.RAPYD_SECRET_KEY,
  });

  const res = await fetch(`https://sandboxapi.rapyd.net${path}`, {
    headers: rapydHeaders(env.RAPYD_ACCESS_KEY, salt, timestamp, signature),
  });

  if (!res.ok) throw new Error(`Rapyd rate fetch failed: ${res.status}`);
  const data = await res.json<{ data: RapydFxRate }>();

  await env.KV.put(cacheKey, JSON.stringify(data.data), {
    expirationTtl: RATE_TTL_SECONDS,
  });
  return data.data;
}
```

---

## 3. Creating a Rapyd Checkout Page with eFX

```typescript
// src/rapyd/checkout.ts
export async function createRapydCheckout(params: {
  amount: number;
  fromCurrency: string;       // payer currency, e.g. 'BRL'
  toCurrency: string;         // settlement currency, e.g. 'USD'
  customerId: string;
  orderId: string;
  returnUrl: string;
  cancelUrl: string;
  env: Env;
}): Promise<string> {
  const {
    amount, fromCurrency, toCurrency,
    customerId, orderId, returnUrl, cancelUrl, env,
  } = params;

  const body = JSON.stringify({
    amount,
    currency: fromCurrency,
    ewallet: env.RAPYD_EWALLET_ID,
    complete_payment_url: returnUrl,
    cancel_checkout_url: cancelUrl,
    metadata: { order_id: orderId, customer_id: customerId },
    requested_currency: toCurrency, // eFX: receive in this currency
    merchant_reference_id: orderId,
  });

  const path = '/v1/checkout';
  const { signature, salt, timestamp } = await buildRapydSignature({
    method: 'POST',
    path,
    body,
    accessKey: env.RAPYD_ACCESS_KEY,
    secretKey: env.RAPYD_SECRET_KEY,
  });

  const res = await fetch(`https://sandboxapi.rapyd.net${path}`, {
    method: 'POST',
    headers: rapydHeaders(env.RAPYD_ACCESS_KEY, salt, timestamp, signature),
    body,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Rapyd checkout create failed: ${res.status} ${err}`);
  }

  const data = await res.json<{ data: { redirect_url: string } }>();
  return data.data.redirect_url;
}
```

---

## 4. Handling Rapyd Webhooks

```typescript
// src/rapyd/webhook-handler.ts
// Rapyd signs webhooks with HMAC-SHA256 using the same signature scheme as API calls.
// The webhook secret is available from the Rapyd Dashboard under Client Portal > Webhooks.

export async function handleRapydWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  const rawBody = await request.text();
  const rapydSignature = request.headers.get('signature') ?? '';
  const salt = request.headers.get('salt') ?? '';
  const timestamp = request.headers.get('timestamp') ?? '';

  // Reconstruct the signed string
  const toSign = salt + timestamp + env.RAPYD_ACCESS_KEY + env.RAPYD_SECRET_KEY + rawBody;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(env.RAPYD_SECRET_KEY),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(toSign));
  const expected = btoa(
    Array.from(new Uint8Array(mac))
      .map(b => String.fromCharCode(b))
      .join('')
  );

  if (expected !== rapydSignature) {
    return new Response('Unauthorized', { status: 401 });
  }

  const event = JSON.parse(rawBody) as {
    type: string;
    data: {
      id?: string;
      merchant_reference_id?: string;
      status?: string;
      fx_rate?: number;
      requested_currency?: string;
    };
  };

  if (event.type === 'PAYMENT_COMPLETED' && event.data.merchant_reference_id) {
    await env.DB.prepare(
      `UPDATE orders SET status = 'paid', rapyd_payment_id = ?1,
       fx_rate = ?2, settled_currency = ?3, paid_at = ?4
       WHERE id = ?5`
    )
      .bind(
        event.data.id ?? null,
        event.data.fx_rate ?? null,
        event.data.requested_currency ?? null,
        new Date().toISOString(),
        event.data.merchant_reference_id
      )
      .run();
  }

  return new Response('OK', { status: 200 });
}
```

---

## 5. Displaying a Locked Rate to Users Before Checkout

```typescript
// src/rapyd/quote-display.ts
export async function getLockedQuote(
  fromAmount: number,
  fromCurrency: string,
  toCurrency: string,
  env: Env
): Promise<{ displayAmount: string; rate: number; expiresInSeconds: number }> {
  const rate = await getExchangeRate(fromCurrency, toCurrency, env);
  const convertedAmount = (fromAmount / rate.sell_rate).toFixed(2);

  return {
    displayAmount: `${convertedAmount} ${toCurrency}`,
    rate: rate.sell_rate,
    expiresInSeconds: RATE_TTL_SECONDS,
  };
}

const RATE_TTL_SECONDS = 300;
```

---

## Anti-patterns

- **Building the signature client-side** — this exposes `RAPYD_SECRET_KEY` to the browser;
  always construct signatures in Workers.
- **Not caching exchange rates** — the Rapyd rate endpoint has per-minute rate limits; cache
  in KV with a TTL matching your acceptable price drift (3-5 minutes is typical).
- **Using `sandboxapi.rapyd.net` in production** — the production endpoint is
  `api.rapyd.net`; guard with an environment variable.
- **Assuming eFX settlement is instant** — settlement timing depends on the payout cycle
  configured in the Rapyd eWallet; do not mark orders "settled" until the
  `PAYOUT_COMPLETED` webhook arrives.

## Gotchas

- The Rapyd signature string concatenates fields **without any separator** —
  `salt + timestamp + accessKey + secretKey + body`; adding spaces or newlines breaks auth.
- `timestamp` must be within 5 minutes of Rapyd's server time; Worker clock skew is
  negligible, but validate if you see 401 errors.
- `requested_currency` (the eFX target currency) must match an active currency supported by
  the eWallet; validate against `GET /v1/user/{ewallet}/accounts` before creating a checkout.
- Rapyd returns HTTP 200 even for error responses; check `data.status.status` or
  `status.error_code` in the response body to detect failures.
- The eFX `fx_rate` in the webhook is the **sell** rate (what Rapyd charged), not your
  cached buy rate; store it on the order for accurate P&L accounting.

## Verification

```bash
# Confirm KV rate cache is populated
wrangler kv key get "rapyd_rate:BRL:USD" --namespace-id $KV_NAMESPACE_ID

# Check D1 for settled order with fx_rate
wrangler d1 execute DB --command \
  "SELECT id, status, fx_rate, settled_currency, paid_at FROM orders ORDER BY paid_at DESC LIMIT 5"
```

## Related

- `forex-rate-caching.md`
- `multi-currency-kv-exchange-rate-cache-edge-pricing.md`
- `cross-border-payment-routing.md`
- `currency-conversion-display.md`

## Sources

- https://docs.rapyd.net/build-with-rapyd/reference/payment/checkout-page
- https://docs.rapyd.net/build-with-rapyd/reference/payment-operations/get-daily-rate
- https://docs.rapyd.net/build-with-rapyd/docs/webhooks
- https://developers.cloudflare.com/kv/
