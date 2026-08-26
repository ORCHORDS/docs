# Flutterwave Workers — Pan-Africa Payments

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to accept payments across Nigeria, Ghana, Kenya, Uganda, Tanzania, Rwanda, Zambia, South Africa, Egypt, and diaspora corridors (US, UK, EU sending to Africa) from a Cloudflare Workers backend. Flutterwave covers more African markets than any single competitor and is the default choice when a product must work across anglophone and francophone Africa simultaneously. Common pain points: differences between the `v2` and `v3` API contracts, handling the `charge` versus `standard` (hosted) flow split, verifying the webhook hash (not HMAC — Flutterwave uses a plain SHA256 hash of the payload + secret), and managing multiple currencies without hitting the wrong settlement account.

## Context

Flutterwave v3 (`api.flutterwave.com/v3`) has two payment flows:
- **Standard** — redirect to Flutterwave's hosted checkout page (simplest, supports all methods)
- **Inline** — embed Flutterwave's JS popup in your frontend (same as Standard but hosted in an iframe)
- **Direct Charge** — server-initiated card charge without redirect (requires PCI compliance)

For most Workers use cases, **Standard** is the right starting point. It returns a `link` URL; you redirect the user there. After payment, Flutterwave redirects to your `redirect_url` with `?status=successful&tx_ref=...&transaction_id=...`. Always verify the transaction ID server-side.

Webhook signature is **not** an HMAC — Flutterwave concatenates the raw JSON body with your `verif-hash` secret (a custom string you set in the dashboard) and SHA256-hashes the result. The hash arrives in the `verif-hash` header (confusingly named the same as your secret).

## 1. Environment Setup

```typescript
export interface Env {
  FW_SECRET_KEY: string;    // FLWSECK_TEST_... or FLWSECK_... — Workers Secret
  FW_VERIF_HASH: string;    // your custom hash secret set in FW dashboard
  PAYMENTS_KV: KVNamespace;
}

const FW_API = "https://api.flutterwave.com/v3";

function fwHeaders(env: Env): HeadersInit {
  return {
    Authorization: `Bearer ${env.FW_SECRET_KEY}`,
    "Content-Type": "application/json",
  };
}

// Currency map by country
const COUNTRY_CURRENCY: Record<string, string> = {
  NG: "NGN", GH: "GHS", KE: "KES", UG: "UGX", TZ: "TZS",
  RW: "RWF", ZM: "ZMW", ZA: "ZAR", EG: "EGP", US: "USD", GB: "GBP",
};
```

## 2. Standard Checkout — Initialize Payment

```typescript
interface FWStandardPayload {
  tx_ref: string;             // your unique transaction reference
  amount: number;             // in the target currency's major unit (naira, not kobo)
  currency: string;
  redirect_url: string;
  customer: {
    email: string;
    name: string;
    phonenumber?: string;
  };
  customizations?: {
    title?: string;
    logo?: string;
    description?: string;
  };
  payment_options?: string;   // "card,banktransfer,ussd,mobilemoneyghana" etc.
  meta?: Record<string, unknown>;
}

interface FWStandardResponse {
  status: "success";
  message: string;
  data: { link: string };
}

async function initStandardPayment(
  env: Env,
  payload: FWStandardPayload
): Promise<{ link: string; txRef: string }> {
  const res = await fetch(`${FW_API}/payments`, {
    method: "POST",
    headers: fwHeaders(env),
    body: JSON.stringify(payload),
  });

  const data = await res.json<FWStandardResponse | { status: string; message: string }>();

  if (data.status !== "success") {
    throw new Error(`Flutterwave init error: ${data.message}`);
  }

  return {
    link: (data as FWStandardResponse).data.link,
    txRef: payload.tx_ref,
  };
}

// Worker route: POST /checkout/init
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/checkout/init") {
      return new Response("Not found", { status: 404 });
    }

    const body = await request.json<{
      email: string;
      name: string;
      amount: number;
      currency: string;
      orderId: string;
    }>();

    const txRef = `order_${body.orderId}_${Date.now()}`;

    const result = await initStandardPayment(env, {
      tx_ref: txRef,
      amount: body.amount,
      currency: body.currency,
      redirect_url: "https://yourapp.com/checkout/callback",
      customer: { email: body.email, name: body.name },
      customizations: { title: "Your Store", description: `Order ${body.orderId}` },
      payment_options: "card,banktransfer,ussd,mobilemoneyrwanda,mobilemoneyzambia",
      meta: { orderId: body.orderId },
    });

    // Store txRef → orderId mapping for callback lookup
    await env.PAYMENTS_KV.put(
      `fw:txref:${txRef}`,
      body.orderId,
      { expirationTtl: 60 * 60 * 2 } // 2hr — checkout session window
    );

    return Response.json({ checkoutUrl: result.link, txRef });
  },
};
```

## 3. Verify a Transaction After Redirect

After checkout, Flutterwave redirects to your `redirect_url` with `?status=successful&tx_ref=X&transaction_id=Y`. Always verify using `transaction_id` — `tx_ref` alone is user-controllable.

```typescript
interface FWTransactionVerify {
  status: "success";
  data: {
    id: number;
    tx_ref: string;
    flw_ref: string;
    status: "successful" | "failed" | "cancelled";
    amount: number;
    currency: string;
    charged_amount: number;
    app_fee: number;
    merchant_fee: number;
    customer: { name: string; email: string; phone_number: string };
    card?: { first_6digits: string; last_4digits: string; issuer: string; type: string };
    meta: Record<string, unknown> | null;
    created_at: string;
  };
}

async function verifyTransaction(
  env: Env,
  transactionId: string | number
): Promise<FWTransactionVerify["data"]> {
  const res = await fetch(`${FW_API}/transactions/${transactionId}/verify`, {
    headers: fwHeaders(env),
  });

  const data = await res.json<FWTransactionVerify | { status: string; message: string }>();

  if (data.status !== "success") {
    throw new Error(`FW verify error: ${data.message}`);
  }

  const txn = (data as FWTransactionVerify).data;

  if (txn.status !== "successful") {
    throw new Error(`Payment not successful: ${txn.status}`);
  }

  return txn;
}

// Callback route: GET /checkout/callback
async function handleCallback(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const status = url.searchParams.get("status");
  const txRef = url.searchParams.get("tx_ref") ?? "";
  const transactionId = url.searchParams.get("transaction_id") ?? "";

  if (status !== "successful" || !transactionId) {
    return Response.redirect("https://yourapp.com/checkout/failed", 302);
  }

  const txn = await verifyTransaction(env, transactionId);
  const orderId = await env.PAYMENTS_KV.get(`fw:txref:${txRef}`);

  await env.PAYMENTS_KV.put(
    `fw:paid:${orderId}`,
    JSON.stringify({ txnId: txn.id, flwRef: txn.flw_ref, amount: txn.amount, currency: txn.currency }),
    { expirationTtl: 60 * 60 * 24 * 90 }
  );

  return Response.redirect(`https://yourapp.com/order/${orderId}/success`, 302);
}
```

## 4. Webhook Verification

Flutterwave uses a non-HMAC hash: `SHA256(rawBody + verifHash)`. This differs from every other payment provider. The resulting hex digest appears in the `verif-hash` header.

```typescript
async function verifyFWWebhook(
  request: Request,
  verifHash: string
): Promise<{ valid: boolean; body: string }> {
  const body = await request.text(); // raw text FIRST
  const receivedHash = request.headers.get("verif-hash") ?? "";

  // FW hash: SHA256 of (body + verifHash secret)
  const message = body + verifHash;
  const hashBuffer = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(message)
  );
  const computed = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  const valid = crypto.timingSafeEqual(
    new TextEncoder().encode(computed),
    new TextEncoder().encode(receivedHash)
  );

  return { valid, body };
}

interface FWWebhookEvent {
  event: "charge.completed" | "transfer.completed" | "transfer.failed" | "subscription.cancelled";
  data: {
    id: number;
    tx_ref: string;
    status: "successful" | "failed";
    amount: number;
    currency: string;
    customer: { email: string };
  };
}

async function handleWebhook(request: Request, env: Env): Promise<Response> {
  const { valid, body } = await verifyFWWebhook(request, env.FW_VERIF_HASH);
  if (!valid) return new Response("Unauthorized", { status: 401 });

  const event = JSON.parse(body) as FWWebhookEvent;

  if (event.event === "charge.completed" && event.data.status === "successful") {
    await env.PAYMENTS_KV.put(
      `fw:charge:${event.data.tx_ref}`,
      JSON.stringify({
        id: event.data.id,
        amount: event.data.amount,
        currency: event.data.currency,
        email: event.data.customer.email,
      }),
      { expirationTtl: 60 * 60 * 24 * 90 }
    );
  }

  return new Response(null, { status: 200 });
}
```

## 5. Mobile Money — Ghana, Uganda, Rwanda, Zambia

Flutterwave supports mobile money (MTN MoMo, Airtel Money, M-Pesa) as direct charges. These are async — they send a USSD push to the customer's phone and settle via webhook.

```typescript
async function chargeMobileMoney(
  env: Env,
  opts: {
    txRef: string;
    amount: number;
    currency: "GHS" | "UGX" | "RWF" | "ZMW";
    email: string;
    phoneNumber: string; // include country code e.g. "+23300000000"
    network: "MTN" | "VODAFONE" | "TIGO" | "AIRTEL" | "ZAMTEL";
    country: "GH" | "UG" | "RW" | "ZM";
  }
): Promise<{ status: string; flwRef: string; redirectUrl?: string }> {
  const res = await fetch(`${FW_API}/charges?type=mobile_money_${opts.country.toLowerCase()}`, {
    method: "POST",
    headers: fwHeaders(env),
    body: JSON.stringify({
      tx_ref: opts.txRef,
      amount: opts.amount,
      currency: opts.currency,
      email: opts.email,
      phone_number: opts.phoneNumber,
      network: opts.network,
      order_id: opts.txRef,
      fullname: opts.email, // required field
    }),
  });

  const data = await res.json<{
    status: string;
    message: string;
    meta?: { authorization: { redirect?: string; mode: string } };
  }>();

  return {
    status: data.status,
    flwRef: opts.txRef,
    redirectUrl: data.meta?.authorization?.redirect,
  };
}
```

## Anti-patterns

- **Using HMAC for webhook verification** — Flutterwave's hash is `SHA256(body + secret)`, not `HMAC-SHA256(secret, body)`. The difference is subtle but produces completely different output.
- **Verifying by `tx_ref` alone** — `tx_ref` is user-supplied during init and could be replayed. Always verify via the numeric `transaction_id` returned in the redirect params.
- **Assuming amounts are in minor units** — unlike Stripe and Paystack, Flutterwave uses the major currency unit (naira, not kobo). Sending `50000` in Flutterwave creates a ₦50,000 charge, not a ₦500 one.
- **Hardcoding `payment_options: "card"`** — mobile money and bank transfer are often the only options in Uganda, Rwanda, and Zambia. Always match payment options to the user's country.
- **Not scoping `payment_options` to the settlement currency** — if your Flutterwave account has only NGN settlement, accepting GHS mobile money will fail settlement. Configure split accounts for multi-currency.

## Gotchas

- Test keys start with `FLWSECK_TEST`; live keys start with `FLWSECK`. Mixing them returns HTTP 401 with message "Invalid authorization key".
- The `verif-hash` header name uses a hyphen, not underscore. Some frameworks normalize headers; use `request.headers.get("verif-hash")` exactly.
- Mobile money in Ghana (`GH`) requires `type=mobile_money_gh` as the query parameter, not `mobile_money_ghana` as in the payment_options string.
- Flutterwave's `app_fee` is deducted from the `charged_amount`; `amount` is the customer-facing amount. Your settlement is `charged_amount - app_fee - merchant_fee`.
- Transaction IDs from the redirect callback are numeric strings — cast to number when calling the verify endpoint (`/v3/transactions/123456/verify`).

## Verification

```bash
# Initialize a test payment
curl -X POST https://api.flutterwave.com/v3/payments \
  -H "Authorization: Bearer FLWSECK_TEST_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tx_ref":"test_001",
    "amount":5000,
    "currency":"NGN",
    "redirect_url":"https://example.com/callback",
    "customer":{"email":"test@test.com","name":"Test User"}
  }'

# Verify a test transaction
curl https://api.flutterwave.com/v3/transactions/TEST_ID/verify \
  -H "Authorization: Bearer FLWSECK_TEST_YOUR_KEY"
```

## Related

- `paystack-workers-africa-payment-integration.md` — Paystack for Nigeria/Ghana primary market
- `payment-orchestration-multi-psp-routing.md` — routing strategy across African gateways
- `multi-currency-kv-exchange-rate-cache-edge-pricing.md` — multi-currency display pricing
- `nowpayments-webhook-hmac-sha512.md` — comparison: HMAC-based webhook signatures

## Sources

- Flutterwave API reference: https://developer.flutterwave.com/reference
- Standard Payment: https://developer.flutterwave.com/docs/collecting-payments/standard
- Verify Transaction: https://developer.flutterwave.com/reference/endpoints/transactions/#verify-a-transaction
- Mobile Money: https://developer.flutterwave.com/docs/collecting-payments/mobile-money
- Webhooks: https://developer.flutterwave.com/docs/integration-guides/webhooks
