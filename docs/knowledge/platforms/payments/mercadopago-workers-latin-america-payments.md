# MercadoPago Workers — Latin America Payment Integration

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to accept payments in Brazil, Argentina, Mexico, Colombia, Chile, or Peru from a Cloudflare Workers edge function. MercadoPago is the dominant payment network in Latin America, handling local payment methods — Pix, Boleto Bancário, OXXO cash, PSE bank transfer, and local credit installments — that Stripe and PayPal do not natively offer in every market. Users report 402/403 errors, IPN signature mismatches, and confusion over currency codes when wiring up the API from Workers.

## Context

MercadoPago exposes two primary surfaces: the **Checkout API** (server-side, card tokenization via MP's SDK or your own form) and **Checkout Pro** (hosted redirect). Both use country-scoped access tokens; a token for Brazil (`MLB`) will be rejected when called against Mexico (`MLM`) endpoints. The API base is `https://api.mercadopago.com` for all markets, but `site_id` and currency differ per country. IPN (Instant Payment Notification) callbacks carry an `x-signature` header verified with HMAC-SHA256 against your webhook secret. Workers must verify this header before trusting any payload.

MercadoPago's SDK is Node-centric and bundles native modules — it cannot run in the Workers runtime. All requests must be made with raw `fetch`.

## 1. Environment Setup

```typescript
// wrangler.toml bindings
// [vars]
// MP_SITE_ID = "MLB"   # Brazil | MLM=Mexico | MLA=Argentina | MLC=Chile | MCO=Colombia | MPE=Peru

export interface Env {
  MP_ACCESS_TOKEN: string; // secret — store in Workers Secret
  MP_WEBHOOK_SECRET: string;
  MP_SITE_ID: string;      // var — not sensitive
  PAYMENTS_KV: KVNamespace;
}

const MP_API = "https://api.mercadopago.com";

function mpHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    "X-Idempotency-Key": crypto.randomUUID(),
  };
}
```

## 2. Creating a Payment Preference (Checkout Pro)

Checkout Pro redirects customers to MercadoPago's hosted page. Useful for markets where local payment method coverage matters most (Argentina, Mexico).

```typescript
interface MPItem {
  id: string;
  title: string;
  quantity: number;
  unit_price: number;
  currency_id: string; // "BRL" | "ARS" | "MXN" | "CLP" | "COP" | "PEN"
}

interface MPPreferencePayload {
  items: MPItem[];
  payer: { email: string };
  back_urls: { success: string; failure: string; pending: string };
  auto_return: "approved";
  notification_url: string;
  external_reference: string; // your internal order ID
  expires?: boolean;
  expiration_date_to?: string; // ISO8601
  installments?: number;
}

async function createPreference(
  env: Env,
  payload: MPPreferencePayload
): Promise<{ id: string; init_point: string; sandbox_init_point: string }> {
  const res = await fetch(`${MP_API}/checkout/preferences`, {
    method: "POST",
    headers: mpHeaders(env.MP_ACCESS_TOKEN),
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json<{ message: string; status: number }>();
    throw new Error(`MP preference error ${err.status}: ${err.message}`);
  }

  return res.json();
}

// Usage in a Worker handler
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/checkout/start") {
      return new Response("Not found", { status: 404 });
    }

    const body = await request.json<{ orderId: string; email: string; amountBRL: number }>();

    const pref = await createPreference(env, {
      items: [{
        id: body.orderId,
        title: "Order #" + body.orderId,
        quantity: 1,
        unit_price: body.amountBRL,
        currency_id: "BRL",
      }],
      payer: { email: body.email },
      back_urls: {
        success: "https://yourapp.com/order/success",
        failure: "https://yourapp.com/order/failure",
        pending: "https://yourapp.com/order/pending",
      },
      auto_return: "approved",
      notification_url: "https://your-worker.workers.dev/webhooks/mp",
      external_reference: body.orderId,
      expires: true,
      expiration_date_to: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
    });

    return Response.json({ checkoutUrl: pref.init_point, preferenceId: pref.id });
  },
};
```

## 3. Direct Checkout API — Card Payments

For branded checkout, tokenize the card client-side with `mercadopago.js`, then submit the token to your Worker.

```typescript
interface MPPaymentPayload {
  transaction_amount: number;
  token: string;            // card token from MP.js
  description: string;
  installments: number;     // 1–12, market-dependent
  payment_method_id: string; // "visa" | "master" | "amex" | "elo" | "hipercard"
  payer: { email: string; identification?: { type: string; number: string } };
  external_reference: string;
  notification_url: string;
}

interface MPPaymentResponse {
  id: number;
  status: "approved" | "pending" | "in_process" | "rejected";
  status_detail: string;
  transaction_amount: number;
  currency_id: string;
}

async function createPayment(
  env: Env,
  payload: MPPaymentPayload
): Promise<MPPaymentResponse> {
  const res = await fetch(`${MP_API}/v1/payments`, {
    method: "POST",
    headers: mpHeaders(env.MP_ACCESS_TOKEN),
    body: JSON.stringify(payload),
  });

  const data = await res.json<MPPaymentResponse & { message?: string }>();

  if (!res.ok) {
    throw new Error(`MP payment error: ${data.message ?? res.status}`);
  }

  return data;
}
```

## 4. Pix Payment (Brazil)

Pix is an instant bank transfer system. MercadoPago generates a QR code or copy-paste code valid for a short window.

```typescript
async function createPixPayment(env: Env, opts: {
  amountBRL: number;
  payerEmail: string;
  payerCpf: string;
  orderId: string;
}): Promise<{ pixCode: string; qrCodeBase64: string; expiresAt: string }> {
  const payload = {
    transaction_amount: opts.amountBRL,
    description: `Order ${opts.orderId}`,
    payment_method_id: "pix",
    payer: {
      email: opts.payerEmail,
      identification: { type: "CPF", number: opts.payerCpf },
    },
    external_reference: opts.orderId,
    notification_url: "https://your-worker.workers.dev/webhooks/mp",
    date_of_expiration: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
  };

  const res = await fetch(`${MP_API}/v1/payments`, {
    method: "POST",
    headers: mpHeaders(env.MP_ACCESS_TOKEN),
    body: JSON.stringify(payload),
  });

  const data = await res.json<{
    id: number;
    point_of_interaction: {
      transaction_data: {
        qr_code: string;
        qr_code_base64: string;
      };
    };
    date_of_expiration: string;
  }>();

  return {
    pixCode: data.point_of_interaction.transaction_data.qr_code,
    qrCodeBase64: data.point_of_interaction.transaction_data.qr_code_base64,
    expiresAt: data.date_of_expiration,
  };
}
```

## 5. Webhook Signature Verification

MercadoPago sends IPN notifications with two headers: `x-signature` (HMAC-SHA256) and `x-request-id`. Verify both before processing.

```typescript
async function verifyMPSignature(
  request: Request,
  secret: string
): Promise<boolean> {
  const xSignature = request.headers.get("x-signature");
  const xRequestId = request.headers.get("x-request-id");
  const url = new URL(request.url);
  const dataId = url.searchParams.get("data.id");

  if (!xSignature || !xRequestId || !dataId) return false;

  // MP signature format: "ts=<timestamp>,v1=<hmac>"
  const parts = Object.fromEntries(
    xSignature.split(",").map((p) => p.split("=") as [string, string])
  );
  const ts = parts["ts"];
  const v1 = parts["v1"];
  if (!ts || !v1) return false;

  const manifest = `id:${dataId};request-id:${xRequestId};ts:${ts};`;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(manifest));
  const computed = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return crypto.timingSafeEqual(
    new TextEncoder().encode(computed),
    new TextEncoder().encode(v1)
  );
}

async function handleMPWebhook(request: Request, env: Env): Promise<Response> {
  const valid = await verifyMPSignature(request, env.MP_WEBHOOK_SECRET);
  if (!valid) return new Response("Unauthorized", { status: 401 });

  const body = await request.json<{ type: string; data: { id: string } }>();

  if (body.type === "payment") {
    // Fetch full payment details — IPN body is minimal
    const res = await fetch(`${MP_API}/v1/payments/${body.data.id}`, {
      headers: { Authorization: `Bearer ${env.MP_ACCESS_TOKEN}` },
    });
    const payment = await res.json<MPPaymentResponse>();

    await env.PAYMENTS_KV.put(
      `mp:payment:${payment.id}`,
      JSON.stringify(payment),
      { expirationTtl: 60 * 60 * 24 * 30 }
    );
  }

  return new Response("OK");
}
```

## Anti-patterns

- **Using the Node SDK in Workers** — it imports `https`, `crypto`, and `fs` native modules. Use raw `fetch` exclusively.
- **Hardcoding `currency_id` as "USD"** — each market has its own currency (`BRL`, `ARS`, `MXN`). MercadoPago will reject a BRL token with `MXN` currency.
- **Trusting IPN body without fetching** — the IPN webhook payload only contains type and ID. Always re-fetch the payment from the API.
- **Reusing `X-Idempotency-Key` across requests** — generate a fresh UUID per request. Reuse causes the API to return a cached result from an earlier call.
- **Not handling `status: "pending"` or `"in_process"`** — many Latin American methods (Boleto, PSE, OXXO) are asynchronous. Treat these as non-final and wait for the webhook update.

## Gotchas

- Argentina (`MLA`) amounts must be integers — pesos have no decimal subdivision at the API level.
- Pix codes expire in 30 minutes by default; `date_of_expiration` must be set explicitly for longer windows.
- Sandbox tokens start with `TEST-`; production tokens start with `APP_USR-`. Mixing them causes 401 errors with no useful message.
- The `installments` field is required even for single-charge card payments; pass `1`.
- Colombia (`MCO`) requires `payer.identification.type: "CC"` (cédula) for local methods.

## Verification

```bash
# Create a test preference and confirm init_point returns a URL
curl -X POST https://api.mercadopago.com/checkout/preferences \
  -H "Authorization: Bearer TEST-your-token" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"title":"Test","quantity":1,"unit_price":100,"currency_id":"BRL"}],
       "payer":{"email":"test@test.com"},
       "back_urls":{"success":"https://example.com","failure":"https://example.com","pending":"https://example.com"},
       "notification_url":"https://your-worker.workers.dev/webhooks/mp",
       "external_reference":"order-001"}'

# Simulate a Pix payment in sandbox and wait for IPN
# Use MP's test credentials and test CPF: 12345678909
```

## Related

- `nowpayments-webhook-hmac-sha512.md` — similar IPN signature pattern
- `payment-orchestration-multi-psp-routing.md` — routing LatAm traffic to MP
- `multi-currency-kv-exchange-rate-cache-edge-pricing.md` — BRL/ARS/MXN rate caching
- `idempotency-keys-payment-apis.md` — idempotency key discipline

## Sources

- MercadoPago Developers: https://www.mercadopago.com.br/developers/en/docs
- Checkout API reference: https://www.mercadopago.com.br/developers/en/reference/payments/_payments/post
- IPN notifications: https://www.mercadopago.com.br/developers/en/docs/your-integrations/notifications/ipn
- Pix payment guide: https://www.mercadopago.com.br/developers/en/docs/checkout-api/payment-methods/other-payment-methods/brazil/pix
